"""
Comprehensive edge case tests for the full Odoo ERP agent pipeline.

Tests signal detection, interview flow, PRD generation, and swarm pipeline
against adversarial and boundary-condition inputs.
"""

import json
import tempfile
from pathlib import Path

import pytest

from src.signals import detect_signals, detect_signals_multi, SignalStrength
from src.agents.phased_interview_agent import PhasedInterviewAgent, SCOPING_QUESTIONS
from src.schemas.implementation_spec import create_spec_from_interview
from src.swarm.normalizer import normalize_interview
from src.swarm.registry import ModuleRegistry
from src.swarm.registry_resolver import resolve_registry_path


# ═══════════════════════════════════════════════════════════════
# SIGNAL DETECTION EDGE CASES
# ═══════════════════════════════════════════════════════════════

class TestSignalNegation:
    """Test that negation-aware signal detection works correctly."""

    def test_simple_negation(self):
        result = detect_signals("We don't manufacture anything")
        assert result.is_denied("manufacturing")
        assert "manufacturing" not in result.active_signals

    def test_double_negation_stays_negative(self):
        result = detect_signals("We do not do any manufacturing at all")
        assert result.is_denied("manufacturing")

    def test_positive_not_negated(self):
        result = detect_signals("We manufacture electronics in our factory")
        assert result.is_confirmed("manufacturing")
        assert "manufacturing" in result.active_signals

    def test_mixed_positive_and_negative(self):
        result = detect_signals(
            "We don't do manufacturing but we have a large inventory warehouse"
        )
        assert result.is_denied("manufacturing")
        assert result.is_confirmed("inventory")

    def test_future_planned(self):
        result = detect_signals("We plan to start manufacturing next year")
        assert result.is_planned("manufacturing")

    def test_wont_negation(self):
        result = detect_signals("We won't need inventory management")
        assert result.is_denied("inventory")

    def test_never_negation(self):
        result = detect_signals("We never deal with purchase orders from suppliers")
        assert "purchase" not in result.active_signals

    def test_positive_outweighs_negative(self):
        result = detect_signals_multi([
            "We manufacture products in our factory",
            "Our manufacturing runs 24/7",
            "We don't outsource manufacturing",
        ])
        # Two positives vs one negative context (but "outsource manufacturing"
        # also contains "manufacturing" — the negation applies to "outsource")
        assert result.active_signals.get("manufacturing", 0) > 0

    def test_complex_sentence(self):
        result = detect_signals(
            "While we used to handle inventory ourselves, we no longer keep stock "
            "and instead dropship directly from suppliers"
        )
        # "no longer keep stock" should negate inventory
        assert result.negative_signals.get("inventory", 0) > 0 or \
               result.active_signals.get("inventory", 0) == 0

    def test_empty_text(self):
        result = detect_signals("")
        assert result.active_signals == {}
        assert result.negative_signals == {}

    def test_special_characters(self):
        result = detect_signals("We sell products! Our sales team is great!! 🎉")
        assert result.is_confirmed("sales")

    def test_unicode_text(self):
        result = detect_signals("Wir machen manufacturing und sales für unsere Kunden")
        assert result.is_confirmed("manufacturing")

    def test_very_long_text(self):
        long_text = "We do sales. " * 500
        result = detect_signals(long_text)
        assert result.is_confirmed("sales")


# ═══════════════════════════════════════════════════════════════
# INTERVIEW FLOW EDGE CASES
# ═══════════════════════════════════════════════════════════════

class TestInterviewEdgeCases:
    """Test interview agent handles edge cases gracefully."""

    def test_minimal_interview_two_answers(self):
        """Only 2 questions answered, rest skipped."""
        agent = PhasedInterviewAgent("Mini Corp", "Services")
        q1 = agent.get_next_question()
        agent.process_response("We provide consulting services to small businesses.", q1)

        q2 = agent.get_next_question()
        agent.process_response("Through referrals mostly.", q2)

        # Skip the rest
        while True:
            q = agent.get_next_question()
            if q is None or agent.is_complete():
                break
            if q.get("is_follow_up"):
                agent.process_response("ok", q)
                continue
            agent.skip_question(q)

        summary = agent.get_summary()
        assert summary["questions_answered"] >= 2

    def test_all_vague_responses(self):
        """Every answer is vague - should generate follow-ups."""
        agent = PhasedInterviewAgent("Vague Inc", "Unknown")
        follow_up_count = 0

        for _ in range(20):  # Run enough iterations
            q = agent.get_next_question()
            if q is None or agent.is_complete():
                break
            if q.get("is_follow_up"):
                follow_up_count += 1
                agent.process_response("still not sure about that", q)
            else:
                agent.process_response("maybe", q)

        assert follow_up_count > 0, "Should have generated follow-ups for vague answers"

    def test_very_long_response(self):
        """500+ word answer should process without error."""
        agent = PhasedInterviewAgent("Verbose Ltd", "Retail")
        q = agent.get_next_question()

        long_answer = (
            "We are a retail company that sells furniture and home decor. "
            "We have been in business for 25 years and have grown from a small "
            "local shop to a national chain with 15 locations. " * 20
        )

        result = agent.process_response(long_answer, q)
        assert "signals_detected" in result

    def test_special_chars_in_response(self):
        """Quotes, newlines, unicode in responses."""
        agent = PhasedInterviewAgent("Special's Corp", "Tech")
        q = agent.get_next_question()

        weird_answer = 'We sell "widgets" & <gadgets>.\nAlso things with émojis 🎯 and tabs\there.'
        result = agent.process_response(weird_answer, q)
        assert "signals_detected" in result

    def test_empty_responses_handled(self):
        """Empty string responses should not crash."""
        agent = PhasedInterviewAgent("Empty Corp", "Nothing")
        q = agent.get_next_question()
        result = agent.process_response("", q)
        assert result is not None

    def test_scoping_questions_expanded(self):
        """Verify we now have 9 scoping questions including tools and timeline."""
        assert len(SCOPING_QUESTIONS) == 9
        ids = [q.id for q in SCOPING_QUESTIONS]
        assert "scope_08" in ids  # Tools/integrations question
        assert "scope_09" in ids  # Timeline/budget question

    def test_follow_up_max_limit(self):
        """Follow-ups should be capped at 2 per question."""
        agent = PhasedInterviewAgent("Test Co", "Test")
        q = agent.get_next_question()

        # Three vague answers in a row for same question
        agent.process_response("maybe", q)
        fu1 = agent.get_next_question()
        assert fu1 is not None and fu1.get("is_follow_up")

        agent.process_response("i guess", fu1)
        fu2 = agent.get_next_question()
        # Should get either another follow-up or next question
        if fu2 and fu2.get("is_follow_up"):
            agent.process_response("probably", fu2)
            fu3 = agent.get_next_question()
            # Third should NOT be a follow-up (max 2)
            assert fu3 is None or not fu3.get("is_follow_up"), \
                "Should not get more than 2 follow-ups per question"


# ═══════════════════════════════════════════════════════════════
# PRD GENERATION EDGE CASES
# ═══════════════════════════════════════════════════════════════

class TestPRDEdgeCases:
    """Test spec generation handles edge cases."""

    def test_no_domains_covered(self):
        """No domains at all should still produce valid spec with warnings."""
        spec = create_spec_from_interview({
            "client_name": "Empty Co",
            "industry": "Unknown",
            "domains_covered": [],
            "recommended_modules": [],
            "detected_signals": {},
            "scoping_responses": [],
            "domain_responses": {},
        })
        # Should always include accounting
        module_names = {m.module_name for m in spec.modules}
        assert "account" in module_names
        # Should have warnings
        assert len(spec.special_requirements) > 0
        assert spec.interview_summary["_completeness_score"] < 0.5

    def test_single_person_company(self):
        """Company with 1 employee should get minimal user roles."""
        spec = create_spec_from_interview({
            "client_name": "Solo Dev",
            "industry": "Freelance",
            "domains_covered": ["sales", "finance"],
            "recommended_modules": [],
            "detected_signals": {"sales": 1},
            "scoping_responses": [
                {"q": "How many employees?", "a": "Just me, 1 person freelancer."},
            ],
            "domain_responses": {},
        })
        total_users = sum(r.count for r in spec.user_roles)
        assert total_users <= 5, f"Solo company shouldn't need {total_users} users"

    def test_large_enterprise(self):
        """500+ employee company should get scaled roles."""
        spec = create_spec_from_interview({
            "client_name": "BigCorp International",
            "industry": "Manufacturing",
            "domains_covered": ["sales", "inventory", "finance", "manufacturing", "hr"],
            "recommended_modules": [],
            "detected_signals": {"sales": 5, "manufacturing": 3},
            "scoping_responses": [
                {"q": "How many employees?", "a": "We have 500 employees across 3 countries."},
                {"q": "Where?", "a": "Headquarters in Germany, offices in France and Spain."},
            ],
            "domain_responses": {
                "sales": [{"q": "Process?", "a": "Large B2B sales team with complex pricing."}],
            },
        })
        assert spec.company.currency == "EUR"
        total_users = sum(r.count for r in spec.user_roles)
        assert total_users > 20, f"Large company should have many users, got {total_users}"

    def test_integration_detection(self):
        """Should detect external systems mentioned in responses."""
        spec = create_spec_from_interview({
            "client_name": "Integrated Co",
            "industry": "Retail",
            "domains_covered": ["sales", "finance"],
            "recommended_modules": [],
            "detected_signals": {},
            "scoping_responses": [
                {"q": "Tools?", "a": "We use Shopify for online sales, Stripe for payments, and QuickBooks for accounting."},
            ],
            "domain_responses": {},
        })
        integration_names = {i.system_name for i in spec.integrations}
        assert "Shopify" in integration_names
        assert "Stripe" in integration_names
        assert "QuickBooks" in integration_names

    def test_pain_points_extracted_broadly(self):
        """Pain points should come from all responses, not just headache question."""
        spec = create_spec_from_interview({
            "client_name": "Pained Corp",
            "industry": "Services",
            "domains_covered": ["sales"],
            "recommended_modules": [],
            "detected_signals": {},
            "scoping_responses": [
                {"q": "What do you do?", "a": "We sell consulting but it's very frustrating managing proposals."},
            ],
            "domain_responses": {
                "sales": [
                    {"q": "Quotes?", "a": "Our manual spreadsheet process for quotes is error-prone and slow."},
                ],
            },
        })
        assert len(spec.pain_points) >= 1

    def test_module_settings_conditional(self):
        """Module settings should vary based on interview responses."""
        # With pricelist mentions
        spec1 = create_spec_from_interview({
            "client_name": "Price Co",
            "industry": "Retail",
            "domains_covered": ["sales"],
            "recommended_modules": [],
            "detected_signals": {},
            "scoping_responses": [],
            "domain_responses": {
                "sales": [{"q": "Pricing?", "a": "We have different pricelist per customer tier."}],
            },
        })
        sales_mod = next((m for m in spec1.modules if m.module_name == "sale_management"), None)
        assert sales_mod is not None
        assert sales_mod.settings.get("group_sale_pricelist") is True

        # Without pricelist mentions
        spec2 = create_spec_from_interview({
            "client_name": "Simple Co",
            "industry": "Retail",
            "domains_covered": ["sales"],
            "recommended_modules": [],
            "detected_signals": {},
            "scoping_responses": [],
            "domain_responses": {
                "sales": [{"q": "Pricing?", "a": "We just use fixed prices for everything."}],
            },
        })
        sales_mod2 = next((m for m in spec2.modules if m.module_name == "sale_management"), None)
        assert sales_mod2 is not None
        assert sales_mod2.settings.get("group_sale_pricelist") is False

    def test_spec_json_serialization(self):
        """Spec should round-trip through JSON without data loss."""
        spec = create_spec_from_interview({
            "client_name": "JSON Corp",
            "industry": "Tech",
            "domains_covered": ["sales", "finance"],
            "recommended_modules": [],
            "detected_signals": {"sales": 3},
            "scoping_responses": [{"q": "test", "a": "We sell software"}],
            "domain_responses": {},
        })

        json_str = spec.to_json()
        data = json.loads(json_str)

        from src.schemas.implementation_spec import ImplementationSpec
        restored = ImplementationSpec.from_dict(data)

        assert restored.company.name == spec.company.name
        assert len(restored.modules) == len(spec.modules)
        assert len(restored.user_roles) == len(spec.user_roles)


# ═══════════════════════════════════════════════════════════════
# NORMALIZER EDGE CASES
# ═══════════════════════════════════════════════════════════════

class TestNormalizerEdgeCases:
    """Test the normalizer handles edge inputs."""

    def test_empty_interview(self):
        norm = normalize_interview({})
        assert norm.client_name == ""
        assert all(v == 0 for v in norm.signals.values())

    def test_negated_signals_not_active(self):
        """Normalizer should not count negated signals."""
        norm = normalize_interview({
            "raw_responses": {
                "scoping": [
                    {"response": "We don't do any manufacturing"},
                    {"response": "We don't have inventory or warehouse"},
                ]
            }
        })
        assert norm.signals.get("manufacturing", 0) == 0
        assert norm.signals.get("inventory", 0) == 0

    def test_contradictory_responses(self):
        """Contradictory statements - positive should win if more frequent."""
        norm = normalize_interview({
            "raw_responses": {
                "scoping": [
                    {"response": "We manufacture products in our factory"},
                    {"response": "Manufacturing is our core business"},
                    {"response": "We don't outsource manufacturing"},
                ]
            }
        })
        # Should still detect manufacturing positively
        assert norm.signals.get("manufacturing", 0) >= 1

    def test_employee_count_extraction(self):
        """Should extract employee count from text."""
        norm = normalize_interview({
            "raw_responses": {
                "scoping": [
                    {"response": "We have about 150 employees across 3 offices"},
                ]
            },
            "company_profile": {}
        })
        assert norm.company_profile.get("employee_count") == 150


# ═══════════════════════════════════════════════════════════════
# SWARM PIPELINE EDGE CASES
# ═══════════════════════════════════════════════════════════════

class TestSwarmPipelineEdgeCases:
    """Test swarm handles edge cases."""

    @pytest.fixture
    def registry(self):
        path = resolve_registry_path("17.0")
        return ModuleRegistry.from_json(path)

    def test_no_signals_produces_minimal_plan(self, registry):
        """Zero signals should still produce a valid (empty) plan."""
        from src.swarm.agents.domain_agents import build_default_agents
        from src.swarm.moderator import SwarmModerator
        from src.swarm.validator import SwarmValidator

        norm = normalize_interview({"raw_responses": {}})
        agents = build_default_agents(registry, odoo_version="17.0")
        results = [a.run(norm) for a in agents]

        moderator = SwarmModerator(registry, edition="community", odoo_version="17.0")
        decision = moderator.consolidate(results)

        validator = SwarmValidator(registry)
        decision = validator.ensure_dependencies(decision)

        # Should at least have base
        names = {m.technical_name for m in decision.selected_modules}
        assert "base" in names

    def test_all_signals_active(self, registry):
        """Every signal active should produce a comprehensive plan."""
        from src.swarm.agents.domain_agents import build_default_agents
        from src.swarm.moderator import SwarmModerator
        from src.swarm.validator import SwarmValidator

        responses = [
            "We manufacture and sell products through our website and retail stores.",
            "We have employees, projects, inventory, and purchasing needs.",
            "We need CRM, accounting, helpdesk, and marketing automation.",
            "We ship via carriers, track quality, and do equipment maintenance.",
            "We want to migrate data from our legacy system and integrate APIs.",
        ]
        norm = normalize_interview({
            "raw_responses": {"scoping": [{"response": r} for r in responses]}
        })

        agents = build_default_agents(registry, odoo_version="17.0")
        results = [a.run(norm) for a in agents]

        moderator = SwarmModerator(registry, edition="community", odoo_version="17.0")
        decision = moderator.consolidate(results)

        validator = SwarmValidator(registry)
        decision = validator.ensure_dependencies(decision)

        # Should have many modules
        assert len(decision.selected_modules) >= 5
        coverage = set(decision.coverage_map.keys())
        assert len(coverage) >= 3


# ═══════════════════════════════════════════════════════════════
# FULL PIPELINE INTEGRATION TEST
# ═══════════════════════════════════════════════════════════════

class TestFullPipelineIntegration:
    """End-to-end integration tests."""

    def test_interview_to_spec_to_swarm(self):
        """Full pipeline from interview to swarm output."""
        # Run interview
        agent = PhasedInterviewAgent("Pipeline Test Co", "Retail")
        answers = [
            "We run retail stores selling clothing and accessories. 30 employees.",
            "Customers come to our stores. We also have a Shopify website.",
            "Yes, we keep stock in 1 central warehouse.",
            "We buy and resell, no manufacturing.",
            "30 people - 10 store staff, 5 warehouse, 3 accounting, 2 marketing, 10 sales.",
            "No project work.",
            "Biggest issue: stock visibility across locations is terrible.",
            "We use Shopify, Excel, and QuickBooks currently.",
            "6 months timeline, 30k budget.",
        ]

        i = 0
        while True:
            q = agent.get_next_question()
            if q is None or agent.is_complete():
                break
            if q.get("is_follow_up"):
                agent.process_response("More detail about this topic for the system.", q)
                continue
            if i < len(answers):
                agent.process_response(answers[i], q)
                i += 1
            else:
                agent.process_response("Standard detailed answer here.", q)

        summary = agent.get_summary()
        assert summary["questions_asked"] > 0

        # Generate spec
        spec = create_spec_from_interview(summary)
        assert spec.company.name == "Pipeline Test Co"
        assert len(spec.modules) > 0

        # Normalize for swarm
        interview_data = {
            "project_id": "pipeline-test",
            "client_name": summary["client_name"],
            "industry": summary["industry"],
            "raw_responses": {
                "scoping": [{"response": r.get("a", "")} for r in summary["scoping_responses"]],
            },
        }
        norm = normalize_interview(interview_data)
        active = {k: v for k, v in norm.signals.items() if v > 0}
        assert len(active) > 0, "Should detect some signals from interview"

        # Run swarm
        registry = ModuleRegistry.from_json(resolve_registry_path("17.0"))
        from src.swarm.agents.domain_agents import build_default_agents
        from src.swarm.moderator import SwarmModerator
        from src.swarm.validator import SwarmValidator

        agents = build_default_agents(registry, odoo_version="17.0")
        results = [a.run(norm) for a in agents]
        moderator = SwarmModerator(registry, edition="community", odoo_version="17.0")
        decision = moderator.consolidate(results)
        validator = SwarmValidator(registry)
        decision = validator.ensure_dependencies(decision)

        assert len(decision.selected_modules) >= 2
        names = {m.technical_name for m in decision.selected_modules}
        assert "base" in names
