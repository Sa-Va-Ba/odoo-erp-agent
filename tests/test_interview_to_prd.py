"""
Tests for the Interview Agent -> PRD pipeline.

Validates that the interview agents correctly:
1. Capture business requirements from simulated client responses
2. Detect domain signals (sales, inventory, manufacturing, etc.)
3. Generate structured PRD output consumable by the coding/builder agents
4. Handle edge cases (vague answers, missing domains, multi-domain signals)

These tests run without LLM providers by using the deterministic signal detection
and mocking the LLM manager where adaptive follow-ups are needed.
"""

import json
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.interview_agent import (
    InterviewAgent,
    InterviewState,
    QuestionResponse,
    create_interview_prompt,
)
from src.agents.adaptive_interview_agent import (
    AdaptiveInterviewAgent,
    DynamicQuestion,
    InterviewContext,
    MODULE_CONFIG_KNOWLEDGE,
)
from src.schemas.implementation_spec import (
    ImplementationSpec,
    CompanySetup,
    ConfigPriority,
    ModuleConfig,
    MODULE_CATALOG,
    create_spec_from_interview,
)
from src.schemas.shared_context import (
    SharedContext,
    create_new_project,
    InterviewOutput,
    Requirement,
)
from src.swarm.normalizer import (
    normalize_interview,
    extract_employee_count,
    _SIGNAL_PATTERNS,
)
from src.swarm.types import NormalizedInterview
from src.llm.base import LLMResponse


# ---------------------------------------------------------------------------
# Fixtures – reusable test data
# ---------------------------------------------------------------------------

MANUFACTURING_RESPONSES = {
    "disc_01": (
        "We are a mid-size manufacturing company producing custom metal parts. "
        "We have about 120 employees across 2 factory locations. Our customers "
        "are mostly B2B industrial buyers."
    ),
    "disc_02": (
        "Our biggest pain point is tracking inventory across warehouses. We also "
        "struggle with production scheduling and purchase order management. "
        "Our accounting is done in spreadsheets which is a nightmare."
    ),
    "disc_03": (
        "A customer sends an RFQ, our sales team creates a quotation. Once confirmed, "
        "manufacturing creates a production order with a bill of materials. We buy "
        "raw materials from suppliers, produce the parts, do quality inspection, "
        "then ship via freight carrier. Invoice is sent on delivery."
    ),
    "disc_04": (
        "About 30 people: 5 in sales, 3 in accounting, 2 managers, 15 on the "
        "factory floor, 3 in the warehouse, and 2 in HR."
    ),
}

ECOMMERCE_RESPONSES = {
    "disc_01": (
        "We sell organic skincare products online and through a few retail stores. "
        "Our team is about 25 people. Customers are mostly B2C through our webshop."
    ),
    "disc_02": (
        "We need better inventory management — we keep running out of stock on "
        "popular items. Also want to integrate our e-commerce website with our "
        "accounting system. Currently using QuickBooks and Shopify separately."
    ),
    "disc_03": (
        "Customer places order on our online store, warehouse picks and packs it, "
        "we ship with UPS or USPS. For wholesale orders, we send a quotation first, "
        "then invoice on delivery. Payment is usually via Stripe or bank transfer."
    ),
    "disc_04": "About 25 — 5 office staff, 3 in the warehouse, 2 in marketing, rest are part-time retail.",
}

SERVICES_RESPONSES = {
    "disc_01": (
        "We are a consulting firm specializing in IT project delivery. We have "
        "45 employees, mostly consultants. We bill clients for project work."
    ),
    "disc_02": (
        "We struggle with timesheet accuracy and project profitability tracking. "
        "Invoicing is manual and slow. We need better CRM to manage our pipeline."
    ),
    "disc_03": (
        "A lead comes in, our sales team qualifies it, we send a proposal. Once "
        "accepted, we staff the project, consultants log timesheets, and we invoice "
        "monthly based on time and materials."
    ),
    "disc_04": "45 people — 35 consultants, 5 in sales, 3 in finance, 2 in HR.",
}


def _make_mock_llm_manager():
    """Create a mock LLM manager that returns deterministic responses."""
    mock = MagicMock()
    mock.complete.return_value = LLMResponse(
        content="NO_FOLLOWUP",
        model="mock-model",
        provider="mock",
    )
    return mock


def _run_adaptive_interview(responses: dict[str, str], client_name: str, industry: str):
    """
    Drive an AdaptiveInterviewAgent through a set of canned responses.

    Only answers the 4 discovery questions (disc_01..disc_04) since those
    are deterministic and don't require an LLM. Returns the agent after
    processing.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        agent = AdaptiveInterviewAgent(
            client_name=client_name,
            industry=industry,
            llm_manager=_make_mock_llm_manager(),
            output_dir=tmpdir,
        )

        answered = 0
        while answered < len(responses):
            question = agent.get_next_question()
            if question is None:
                break
            if question.id in responses:
                agent.process_response(responses[question.id], question)
                answered += 1
            else:
                # Skip module-specific questions generated after signal detection
                agent.process_response("Not applicable", question)

        return agent


# ---------------------------------------------------------------------------
# 1. Basic InterviewAgent tests
# ---------------------------------------------------------------------------

class TestInterviewAgentBasics:
    """Test the base InterviewAgent session management and recording."""

    def test_agent_initialises_with_all_domains(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = InterviewAgent("TestCorp", "Retail", output_dir=tmpdir)
            assert agent.session.state == InterviewState.NOT_STARTED
            assert len(agent.session.domain_progress) == 10

    def test_start_interview_sets_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = InterviewAgent("TestCorp", "Retail", output_dir=tmpdir)
            welcome = agent.start_interview()
            assert agent.session.state == InterviewState.IN_PROGRESS
            assert "TestCorp" in welcome
            assert agent.session.started_at != ""

    def test_record_response_advances_question(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = InterviewAgent("TestCorp", "Retail", output_dir=tmpdir)
            agent.start_interview()
            question = agent.get_next_question()
            assert question is not None

            agent.record_response(question, "We sell shoes online")
            progress = agent.current_domain_progress
            assert progress.current_question_index == 1
            assert len(progress.responses) == 1
            assert progress.responses[0].response == "We sell shoes online"

    def test_complete_domain_advances_to_next(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = InterviewAgent("TestCorp", "Retail", output_dir=tmpdir)
            agent.start_interview()
            assert agent.session.current_domain_index == 0
            agent.complete_current_domain()
            assert agent.session.current_domain_index == 1

    def test_follow_up_triggered_for_vague_answer(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = InterviewAgent("TestCorp", "Retail", output_dir=tmpdir)
            agent.start_interview()
            question = agent.get_next_question()
            # Vague short answer with follow-ups available
            follow_ups = agent.should_ask_follow_up(question, "maybe")
            if question.follow_ups:
                assert len(follow_ups) > 0

    def test_no_follow_up_for_detailed_answer(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = InterviewAgent("TestCorp", "Retail", output_dir=tmpdir)
            agent.start_interview()
            question = agent.get_next_question()
            detailed = (
                "We are a mid-size retailer selling electronics across three "
                "locations in Belgium. We have 50 employees and use EUR as our "
                "primary currency. Our fiscal year ends in December."
            )
            follow_ups = agent.should_ask_follow_up(question, detailed)
            assert len(follow_ups) == 0

    def test_save_and_load_session(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = InterviewAgent("TestCorp", "Retail", output_dir=tmpdir)
            agent.start_interview()
            q = agent.get_next_question()
            agent.record_response(q, "We sell electronics")
            path = agent.save_session()
            assert Path(path).exists()

            data = json.loads(Path(path).read_text())
            assert data["session"]["client_name"] == "TestCorp"
            assert len(data["session"]["domain_progress"]["company_basics"]["responses"]) == 1

    def test_generate_requirements_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = InterviewAgent("TestCorp", "Retail", output_dir=tmpdir)
            agent.start_interview()

            # Answer all questions in the first domain
            while True:
                q = agent.get_next_question()
                if q is None:
                    break
                agent.record_response(q, f"Test response for {q.id}")
            agent.complete_current_domain()

            path = agent.generate_requirements_json()
            assert Path(path).exists()

            data = json.loads(Path(path).read_text())
            assert data["client_name"] == "TestCorp"
            assert data["industry"] == "Retail"
            assert "requirements_by_domain" in data
            assert "raw_responses" in data
            # Should have responses in company_basics
            assert len(data["raw_responses"]["company_basics"]) > 0

    def test_progress_percentage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = InterviewAgent("TestCorp", "Retail", output_dir=tmpdir)
            assert agent.progress_percentage == 0
            agent.start_interview()
            agent.complete_current_domain()
            assert agent.progress_percentage == 10  # 1 of 10 domains


# ---------------------------------------------------------------------------
# 2. Adaptive Interview Agent tests
# ---------------------------------------------------------------------------

class TestAdaptiveInterviewAgent:
    """Test the adaptive interview agent's signal detection and question generation."""

    def test_discovery_questions_present_on_init(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = AdaptiveInterviewAgent(
                "TestCorp", "Retail",
                llm_manager=_make_mock_llm_manager(),
                output_dir=tmpdir,
            )
            assert len(agent.question_queue) == 4
            assert agent.question_queue[0].id == "disc_01"

    def test_manufacturing_signals_detected(self):
        agent = _run_adaptive_interview(
            MANUFACTURING_RESPONSES, "MetalWorks Inc", "Manufacturing"
        )
        signals = agent.context.detected_signals
        assert signals.get("manufacturing", 0) > 0
        assert signals.get("inventory", 0) > 0
        assert signals.get("purchase", 0) > 0
        assert signals.get("sales", 0) > 0

    def test_manufacturing_modules_recommended(self):
        agent = _run_adaptive_interview(
            MANUFACTURING_RESPONSES, "MetalWorks Inc", "Manufacturing"
        )
        modules = agent.context.current_focus_modules
        assert "mrp" in modules
        assert "stock" in modules
        assert "sale_management" in modules or "crm" in modules
        assert "purchase" in modules

    def test_ecommerce_signals_detected(self):
        agent = _run_adaptive_interview(
            ECOMMERCE_RESPONSES, "GlowSkin Co", "E-commerce"
        )
        signals = agent.context.detected_signals
        assert signals.get("ecommerce", 0) > 0
        assert signals.get("inventory", 0) > 0
        assert signals.get("shipping", 0) > 0

    def test_ecommerce_modules_recommended(self):
        agent = _run_adaptive_interview(
            ECOMMERCE_RESPONSES, "GlowSkin Co", "E-commerce"
        )
        modules = agent.context.current_focus_modules
        assert "stock" in modules
        assert "sale_management" in modules or "website_sale" in modules

    def test_services_signals_detected(self):
        agent = _run_adaptive_interview(
            SERVICES_RESPONSES, "Consult Co", "Professional Services"
        )
        signals = agent.context.detected_signals
        assert signals.get("project", 0) > 0
        assert signals.get("crm", 0) > 0
        assert signals.get("sales", 0) > 0

    def test_services_modules_recommended(self):
        agent = _run_adaptive_interview(
            SERVICES_RESPONSES, "Consult Co", "Professional Services"
        )
        modules = agent.context.current_focus_modules
        assert "project" in modules
        assert "crm" in modules or "sale_management" in modules

    def test_module_specific_questions_generated(self):
        """After detecting manufacturing signals, MRP-specific questions should be queued."""
        agent = _run_adaptive_interview(
            MANUFACTURING_RESPONSES, "MetalWorks Inc", "Manufacturing"
        )
        # The queue should contain module-specific questions beyond the initial 4 discovery
        all_question_ids = [q.id for q in agent.asked_questions + agent.question_queue]
        mrp_questions = [qid for qid in all_question_ids if qid.startswith("mrp_")]
        assert len(mrp_questions) > 0, "Expected MRP-specific questions after detecting manufacturing signals"

    def test_interview_summary_structure(self):
        agent = _run_adaptive_interview(
            MANUFACTURING_RESPONSES, "MetalWorks Inc", "Manufacturing"
        )
        summary = agent.get_interview_summary()

        assert summary["client_name"] == "MetalWorks Inc"
        assert summary["industry"] == "Manufacturing"
        assert "detected_signals" in summary
        assert "recommended_modules" in summary
        assert "gathered_config_info" in summary
        assert "responses" in summary
        assert summary["questions_asked"] > 0

    def test_save_interview_creates_valid_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = AdaptiveInterviewAgent(
                "TestCorp", "Retail",
                llm_manager=_make_mock_llm_manager(),
                output_dir=tmpdir,
            )
            q = agent.get_next_question()
            agent.process_response("We sell clothes online via our webshop", q)
            path = agent.save_interview()

            data = json.loads(Path(path).read_text())
            assert data["client_name"] == "TestCorp"
            assert "recommended_modules" in data
            assert "raw_responses" in data

    def test_llm_followup_injected_at_front_of_queue(self):
        """When the LLM generates a follow-up, it should be inserted at the front."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_llm = _make_mock_llm_manager()
            mock_llm.complete.return_value = LLMResponse(
                content="Can you tell me more about your production capacity?",
                model="mock",
                provider="mock",
            )
            agent = AdaptiveInterviewAgent(
                "TestCorp", "Manufacturing",
                llm_manager=mock_llm,
                output_dir=tmpdir,
            )
            q = agent.get_next_question()  # disc_01
            agent.process_response(MANUFACTURING_RESPONSES["disc_01"], q)

            # The next question should be the LLM-generated follow-up
            next_q = agent.get_next_question()
            assert next_q is not None
            assert "production capacity" in next_q.text.lower() or next_q.id.startswith("followup_")


# ---------------------------------------------------------------------------
# 3. Signal detection and normalizer tests
# ---------------------------------------------------------------------------

class TestSignalDetection:
    """Test the signal pattern matching used to detect business domains."""

    @pytest.mark.parametrize("text,expected_signal", [
        ("We manufacture custom parts in our factory", "manufacturing"),
        ("Our online store sells to B2C customers via webshop", "ecommerce"),
        ("We track inventory in our warehouse", "inventory"),
        ("We have a helpdesk for customer support tickets", "support"),
        ("We need to integrate with our existing API", "integration"),
        ("We want to migrate data from our legacy system", "data_migration"),
        ("Our employees track timesheets for billable projects", "project"),
        ("We manage purchase orders with suppliers", "purchase"),
        ("Our sales team handles B2B quotations", "sales"),
        ("We use a CRM to track our sales pipeline", "crm"),
        ("HR manages payroll and recruitment for our staff", "hr"),
        ("We need point of sale for our retail store checkout", "pos"),
        ("We ship via courier and freight carriers", "shipping"),
        ("We run quality control inspections", "quality"),
        ("We have recurring subscription revenue", "subscriptions"),
    ])
    def test_signal_pattern_matches(self, text, expected_signal):
        text_lower = text.lower()
        patterns = _SIGNAL_PATTERNS[expected_signal]
        assert any(p in text_lower for p in patterns), (
            f"Expected signal '{expected_signal}' not detected in: {text}"
        )

    def test_normalize_interview_basic(self):
        data = {
            "project_id": "test-001",
            "client_name": "TestCorp",
            "industry": "Retail",
            "raw_responses": {
                "discovery": [
                    {"response": "We sell products in our online store and warehouse"},
                    {"response": "We need inventory tracking and accounting"},
                ]
            },
        }
        normalized = normalize_interview(data)
        assert normalized.client_name == "TestCorp"
        assert normalized.signals["ecommerce"] > 0
        assert normalized.signals["inventory"] > 0
        assert normalized.signals["accounting"] > 0

    def test_normalize_preserves_evidence(self):
        data = {
            "project_id": "test-002",
            "client_name": "MfgCo",
            "industry": "Manufacturing",
            "raw_responses": {
                "discovery": [
                    {"response": "We manufacture parts and need quality control"},
                ]
            },
        }
        normalized = normalize_interview(data)
        assert len(normalized.evidence_map["manufacturing"]) > 0
        assert len(normalized.evidence_map["quality"]) > 0

    def test_extract_employee_count_from_text(self):
        assert extract_employee_count({}, "We have 120 employees") == 120
        assert extract_employee_count({}, "About 50 FTE plus contractors") == 50
        assert extract_employee_count({}, "roughly 15 staff members") == 15
        assert extract_employee_count({"employee_count": 200}, "") == 200

    def test_extract_employee_count_none_when_missing(self):
        assert extract_employee_count({}, "No numbers mentioned here") is None


# ---------------------------------------------------------------------------
# 4. PRD / Implementation Spec generation tests
# ---------------------------------------------------------------------------

class TestPRDGeneration:
    """Test that interview output correctly converts to a PRD (ImplementationSpec)."""

    def test_create_spec_from_manufacturing_interview(self):
        agent = _run_adaptive_interview(
            MANUFACTURING_RESPONSES, "MetalWorks Inc", "Manufacturing"
        )
        summary = agent.get_interview_summary()
        spec = create_spec_from_interview(summary)

        assert spec.company.name == "MetalWorks Inc"
        assert spec.company.industry == "Manufacturing"
        module_names = {m.module_name for m in spec.modules}
        # Manufacturing interview should produce these modules
        assert "mrp" in module_names, f"Expected mrp in {module_names}"
        assert "stock" in module_names, f"Expected stock in {module_names}"
        assert "account" in module_names, f"Expected account (always included) in {module_names}"

    def test_create_spec_from_ecommerce_interview(self):
        agent = _run_adaptive_interview(
            ECOMMERCE_RESPONSES, "GlowSkin Co", "E-commerce"
        )
        summary = agent.get_interview_summary()
        spec = create_spec_from_interview(summary)

        assert spec.company.name == "GlowSkin Co"
        module_names = {m.module_name for m in spec.modules}
        assert "stock" in module_names
        assert "account" in module_names

    def test_create_spec_from_services_interview(self):
        agent = _run_adaptive_interview(
            SERVICES_RESPONSES, "Consult Co", "Professional Services"
        )
        summary = agent.get_interview_summary()
        spec = create_spec_from_interview(summary)

        assert spec.company.name == "Consult Co"
        module_names = {m.module_name for m in spec.modules}
        assert "project" in module_names
        assert "account" in module_names

    def test_spec_always_includes_accounting(self):
        """Accounting should always be included regardless of interview content."""
        summary = {
            "client_name": "MinimalCo",
            "industry": "Other",
            "domains_covered": [],
            "recommended_modules": [],
            "detected_signals": {},
        }
        spec = create_spec_from_interview(summary)
        module_names = {m.module_name for m in spec.modules}
        assert "account" in module_names

    def test_spec_includes_default_user_roles(self):
        summary = {
            "client_name": "TestCo",
            "industry": "General",
            "domains_covered": ["sales"],
            "recommended_modules": [],
            "detected_signals": {},
        }
        spec = create_spec_from_interview(summary)
        role_names = {r.name for r in spec.user_roles}
        assert "Administrator" in role_names
        assert "Manager" in role_names
        # With domain-specific roles, "Sales User" replaces generic "User" when sales is covered
        assert "Sales User" in role_names or "User" in role_names

    def test_spec_install_order_respects_dependencies(self):
        """Modules with dependencies should come after their dependencies."""
        summary = {
            "client_name": "TestCo",
            "industry": "Manufacturing",
            "domains_covered": ["sales", "inventory", "manufacturing", "finance"],
            "recommended_modules": [],
            "detected_signals": {},
        }
        spec = create_spec_from_interview(summary)
        ordered = spec.get_install_order()
        ordered_names = [m.module_name for m in ordered]

        # stock should come before mrp (mrp depends on stock)
        if "stock" in ordered_names and "mrp" in ordered_names:
            assert ordered_names.index("stock") < ordered_names.index("mrp"), (
                f"stock should be installed before mrp, got: {ordered_names}"
            )

    def test_spec_serialization_roundtrip(self):
        """Spec should survive JSON serialization and deserialization."""
        summary = {
            "client_name": "RoundTripCo",
            "industry": "Retail",
            "domains_covered": ["sales", "inventory", "finance"],
            "recommended_modules": ["crm"],
            "detected_signals": {"sales": 3, "inventory": 2},
        }
        spec = create_spec_from_interview(summary)
        json_str = spec.to_json()
        data = json.loads(json_str)
        restored = ImplementationSpec.from_dict(data)

        assert restored.company.name == "RoundTripCo"
        assert len(restored.modules) == len(spec.modules)
        for orig, rest in zip(spec.modules, restored.modules):
            assert orig.module_name == rest.module_name

    def test_spec_estimated_time_positive(self):
        summary = {
            "client_name": "TestCo",
            "industry": "General",
            "domains_covered": ["sales", "finance"],
            "recommended_modules": [],
            "detected_signals": {},
        }
        spec = create_spec_from_interview(summary)
        assert spec.get_total_estimated_time() > 0

    def test_spec_to_dict_has_required_keys(self):
        """The dict output should have all keys the builder agents need."""
        summary = {
            "client_name": "TestCo",
            "industry": "General",
            "domains_covered": ["sales"],
            "recommended_modules": [],
            "detected_signals": {},
        }
        spec = create_spec_from_interview(summary)
        d = spec.to_dict()

        required_keys = [
            "spec_id", "created_at", "interview_session_id",
            "company", "modules", "user_roles", "data_imports",
            "integrations", "pain_points", "special_requirements",
            "estimated_setup_minutes",
        ]
        for key in required_keys:
            assert key in d, f"Missing required key '{key}' in spec output"

    def test_spec_modules_have_required_fields(self):
        """Each module in the spec should have fields the builder needs."""
        summary = {
            "client_name": "TestCo",
            "industry": "General",
            "domains_covered": ["sales", "inventory"],
            "recommended_modules": [],
            "detected_signals": {},
        }
        spec = create_spec_from_interview(summary)
        d = spec.to_dict()

        for module in d["modules"]:
            assert "module_name" in module
            assert "display_name" in module
            assert "install" in module
            assert "priority" in module
            assert "settings" in module
            assert "depends_on" in module
            assert "estimated_minutes" in module


# ---------------------------------------------------------------------------
# 5. End-to-end pipeline tests (Interview -> Normalize -> Spec)
# ---------------------------------------------------------------------------

class TestEndToEndPipeline:
    """Test the full pipeline from interview responses to builder-ready PRD."""

    def _simulate_full_pipeline(self, responses, client_name, industry):
        """Run interview, save output, normalize, and create spec."""
        agent = _run_adaptive_interview(responses, client_name, industry)
        summary = agent.get_interview_summary()

        # Build a normalizer-compatible dict from the adaptive agent's output
        # Group responses by module source, accumulating into lists
        raw_by_module: dict[str, list[dict]] = {}
        for r in summary["responses"]:
            key = r["module"]
            raw_by_module.setdefault(key, []).append({"response": r["response"]})

        interview_data = {
            "project_id": f"test-{client_name.lower().replace(' ', '-')}",
            "client_name": client_name,
            "industry": industry,
            "raw_responses": raw_by_module,
            "company_profile": {},
            "pain_points": [],
        }

        normalized = normalize_interview(interview_data)
        spec = create_spec_from_interview(summary)
        return agent, normalized, spec

    def test_manufacturing_pipeline(self):
        agent, normalized, spec = self._simulate_full_pipeline(
            MANUFACTURING_RESPONSES, "MetalWorks Inc", "Manufacturing"
        )

        # Normalizer should detect manufacturing signals
        assert normalized.signals["manufacturing"] > 0

        # Spec should contain manufacturing-relevant modules
        module_names = {m.module_name for m in spec.modules}
        assert "mrp" in module_names
        assert "stock" in module_names
        assert "purchase" in module_names
        assert "account" in module_names

        # Spec should be JSON-serializable (required by builder agent)
        json_str = spec.to_json()
        assert json.loads(json_str)  # Should not raise

    def test_ecommerce_pipeline(self):
        agent, normalized, spec = self._simulate_full_pipeline(
            ECOMMERCE_RESPONSES, "GlowSkin Co", "E-commerce"
        )

        assert normalized.signals["ecommerce"] > 0
        assert normalized.signals["inventory"] > 0

        module_names = {m.module_name for m in spec.modules}
        assert "stock" in module_names
        assert "account" in module_names

    def test_services_pipeline(self):
        agent, normalized, spec = self._simulate_full_pipeline(
            SERVICES_RESPONSES, "Consult Co", "Professional Services"
        )

        assert normalized.signals["project"] > 0

        module_names = {m.module_name for m in spec.modules}
        assert "project" in module_names
        assert "account" in module_names

    def test_pipeline_output_is_builder_compatible(self):
        """The final spec dict must match the contract the builder expects."""
        _, _, spec = self._simulate_full_pipeline(
            MANUFACTURING_RESPONSES, "MetalWorks Inc", "Manufacturing"
        )
        d = spec.to_dict()

        # Builder expects these top-level keys
        assert isinstance(d["company"], dict)
        assert isinstance(d["modules"], list)
        assert isinstance(d["user_roles"], list)
        assert isinstance(d["estimated_setup_minutes"], int)

        # Company must have name and industry
        assert d["company"]["name"] == "MetalWorks Inc"
        assert d["company"]["industry"] == "Manufacturing"

        # Each module must be installable
        for mod in d["modules"]:
            assert mod["install"] is True
            assert mod["priority"] in ("critical", "high", "medium", "low")

    def test_empty_interview_produces_minimal_spec(self):
        """Even with no real answers, the pipeline should produce a valid minimal spec."""
        empty_responses = {
            "disc_01": "Not sure yet.",
            "disc_02": "Nothing specific.",
            "disc_03": "Standard process.",
            "disc_04": "A few people.",
        }
        agent = _run_adaptive_interview(empty_responses, "Vague Corp", "Unknown")
        summary = agent.get_interview_summary()
        spec = create_spec_from_interview(summary)

        # Should still produce a valid spec with at least accounting
        assert spec.company.name == "Vague Corp"
        module_names = {m.module_name for m in spec.modules}
        assert "account" in module_names
        assert spec.to_json()  # Must be serializable

    def test_multi_domain_company_gets_comprehensive_modules(self):
        """A company mentioning many domains should get a broad module set."""
        comprehensive_responses = {
            "disc_01": (
                "We are a manufacturing company that also sells online through "
                "our e-commerce webshop. We have 200 employees across 3 warehouses. "
                "We also run internal projects and track timesheets."
            ),
            "disc_02": (
                "We need CRM for our sales pipeline, better inventory management, "
                "manufacturing planning with bills of materials, HR management for "
                "recruitment and payroll, and we want to integrate with our bank "
                "for accounting reconciliation."
            ),
            "disc_03": (
                "Customer places order via website or sales team. Manufacturing "
                "produces the goods, warehouse ships it, accounting invoices the "
                "customer, and our support helpdesk handles any issues."
            ),
            "disc_04": (
                "200 employees: sales team, factory floor workers, warehouse staff, "
                "HR department, finance team, project managers, and support agents."
            ),
        }
        agent = _run_adaptive_interview(
            comprehensive_responses, "MegaCorp", "Diversified"
        )
        modules = agent.context.current_focus_modules
        signals = agent.context.detected_signals

        # Should detect many signals
        assert len([s for s, c in signals.items() if c > 0]) >= 5

        # Should recommend a broad set of modules
        assert len(modules) >= 5


# ---------------------------------------------------------------------------
# 6. Module configuration knowledge tests
# ---------------------------------------------------------------------------

class TestModuleConfigKnowledge:
    """Test that module config knowledge is well-structured for question generation."""

    def test_all_config_modules_have_setup_areas(self):
        for module_name, config in MODULE_CONFIG_KNOWLEDGE.items():
            assert "setup_areas" in config, f"{module_name} missing setup_areas"
            assert len(config["setup_areas"]) > 0, f"{module_name} has empty setup_areas"

    def test_setup_areas_have_questions(self):
        for module_name, config in MODULE_CONFIG_KNOWLEDGE.items():
            for area in config["setup_areas"]:
                assert "questions" in area, f"{module_name}/{area.get('area')} missing questions"
                assert len(area["questions"]) > 0
                assert "config_fields" in area, f"{module_name}/{area.get('area')} missing config_fields"

    def test_module_catalog_covers_key_modules(self):
        expected = ["sales", "crm", "inventory", "purchase", "finance", "manufacturing", "hr", "project"]
        for key in expected:
            assert key in MODULE_CATALOG, f"MODULE_CATALOG missing '{key}'"


# ---------------------------------------------------------------------------
# 7. Shared context / project creation tests
# ---------------------------------------------------------------------------

class TestSharedContext:
    """Test the shared context that flows between agents."""

    def test_create_new_project(self):
        ctx = create_new_project("TestCo", "Retail")
        assert ctx.client_name == "TestCo"
        assert ctx.industry == "Retail"
        assert ctx.state.current_phase.value == "interview"
        assert ctx.project_id.startswith("odoo-impl-")

    def test_interview_output_has_all_domains(self):
        ctx = create_new_project("TestCo", "Retail")
        domains = ctx.interview_output.requirements_by_domain
        expected = [
            "accounting", "sales", "inventory", "hr", "project",
            "manufacturing", "purchase", "crm", "website", "general"
        ]
        for d in expected:
            assert d in domains, f"Missing domain '{d}' in interview output"

    def test_context_to_dict_serializable(self):
        ctx = create_new_project("TestCo", "Retail")
        d = ctx.to_dict()
        json_str = json.dumps(d, default=str)
        assert json.loads(json_str)
