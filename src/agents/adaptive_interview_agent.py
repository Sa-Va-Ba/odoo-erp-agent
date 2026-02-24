"""
Adaptive Interview Agent - Dynamically generates interview questions based on Odoo module
documentation and interviewee responses.

Instead of hardcoded questions, this agent:
1. Starts with high-level discovery questions
2. Analyzes responses to identify relevant Odoo modules
3. Loads module-specific configuration requirements
4. Generates targeted follow-up questions dynamically
5. Refines questions based on interviewee feedback
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

from ..llm.base import Message
from ..llm.manager import LLMManager, LLMManagerConfig
from ..swarm.registry import ModuleRegistry
from ..signals import SIGNAL_PATTERNS as _SIGNAL_PATTERNS, detect_signals as shared_detect_signals


def get_interview_llm_manager() -> LLMManager:
    """
    Get an LLM manager configured for interviews.

    Uses free/open-source providers only:
    - Groq: Free tier with Llama 3.3 70B (1000 requests/day)
    - Ollama: Local inference (unlimited, requires ollama running)

    Returns:
        Configured LLM manager
    """
    config = LLMManagerConfig(
        provider_priority=["groq", "ollama"],
        default_models={
            "groq": "llama-3.3-70b-versatile",
            "ollama": "mistral:latest"
        }
    )
    return LLMManager(config)


def load_module_config_knowledge(path: Optional[Path] = None) -> dict:
    """
    Load module configuration knowledge from JSON file.

    This allows updating questions without code changes.

    Args:
        path: Path to JSON file. If None, uses default location.

    Returns:
        Module configuration knowledge dictionary
    """
    if path is None:
        path = Path(__file__).parent.parent / "knowledge" / "module_config_requirements.json"

    if path.exists():
        try:
            data = json.loads(path.read_text())
            # Filter out metadata keys
            return {k: v for k, v in data.items() if not k.startswith("_")}
        except Exception as e:
            print(f"Warning: Could not load module config from {path}: {e}")

    # Return empty dict - will fall back to hardcoded
    return {}


@dataclass
class ModuleConfigRequirement:
    """Configuration requirement for an Odoo module."""
    module_name: str
    requirement_id: str
    question: str
    context: str
    config_field: str  # What Odoo configuration this maps to
    options: list[str] = field(default_factory=list)  # Possible values if applicable
    depends_on: list[str] = field(default_factory=list)  # Other requirements this depends on
    priority: int = 5  # 1-10, higher = more important


@dataclass
class DynamicQuestion:
    """A dynamically generated interview question."""
    id: str
    text: str
    context: str
    module_source: str  # Which module triggered this question
    config_target: str  # What configuration this will inform
    priority: int
    follow_ups: list[str] = field(default_factory=list)
    asked: bool = False
    response: str = ""


@dataclass
class InterviewContext:
    """Tracks the evolving context during an interview."""
    client_name: str
    industry: str
    detected_signals: dict[str, int] = field(default_factory=dict)
    mentioned_modules: list[str] = field(default_factory=list)
    gathered_info: dict[str, Any] = field(default_factory=dict)
    pain_points: list[str] = field(default_factory=list)
    responses: list[dict] = field(default_factory=list)
    current_focus_modules: list[str] = field(default_factory=list)


# Module configuration knowledge base - loaded from registry + enhanced with setup needs
MODULE_CONFIG_KNOWLEDGE = {
    "sale_management": {
        "name": "Sales",
        "setup_areas": [
            {
                "area": "product_types",
                "questions": [
                    "What types of products do you sell? (Physical goods, services, subscriptions, or a mix?)",
                    "For each product type, when should invoicing happen? (On order confirmation, on delivery, based on time spent?)"
                ],
                "config_fields": ["product.product.type", "product.product.invoice_policy"],
                "context": "Determines product type and invoicing policy configuration"
            },
            {
                "area": "pricing",
                "questions": [
                    "Do you need multiple price lists? (e.g., retail vs wholesale, regional pricing)",
                    "How should discounts work? (Fixed amount, percentage, tiered based on quantity?)"
                ],
                "config_fields": ["product.pricelist", "sale.order.line.discount"],
                "context": "Configures pricelists and discount policies"
            },
            {
                "area": "quotation_workflow",
                "questions": [
                    "Do quotations need approval before being sent to customers?",
                    "What validity period should quotations have by default?",
                    "Do you need electronic signatures on quotes?"
                ],
                "config_fields": ["sale.order.validity_date", "sale.order.signature"],
                "context": "Configures quotation templates and approval workflows"
            },
            {
                "area": "sales_teams",
                "questions": [
                    "How are sales organized? (By region, product line, customer type?)",
                    "Do salespeople have individual targets or quotas to track?"
                ],
                "config_fields": ["crm.team", "sale.order.team_id"],
                "context": "Configures sales team structure"
            }
        ]
    },
    "crm": {
        "name": "CRM",
        "setup_areas": [
            {
                "area": "pipeline_stages",
                "questions": [
                    "Walk me through your sales pipeline stages from first contact to closed deal",
                    "Are there stages where deals commonly get stuck? What happens then?",
                    "Do certain stages require specific actions before moving forward?"
                ],
                "config_fields": ["crm.stage", "crm.lead.stage_id"],
                "context": "Configures CRM pipeline stages and requirements"
            },
            {
                "area": "lead_sources",
                "questions": [
                    "Where do your leads come from? (Website, referrals, trade shows, cold outreach?)",
                    "Do you need to track which marketing campaigns generate leads?"
                ],
                "config_fields": ["utm.source", "crm.lead.source_id"],
                "context": "Configures lead source tracking and UTM parameters"
            },
            {
                "area": "lead_scoring",
                "questions": [
                    "How do you currently qualify leads? What makes a lead 'hot' vs 'cold'?",
                    "Should leads be automatically assigned to salespeople based on criteria?"
                ],
                "config_fields": ["crm.lead.priority", "crm.team.assignment_domain"],
                "context": "Configures lead scoring and assignment rules"
            }
        ]
    },
    "stock": {
        "name": "Inventory",
        "setup_areas": [
            {
                "area": "warehouse_structure",
                "questions": [
                    "Describe your warehouse layout - do you have zones, aisles, racks, bins?",
                    "Do you need to track inventory at bin/shelf level or just warehouse level?",
                    "How many physical warehouse locations do you have?"
                ],
                "config_fields": ["stock.warehouse", "stock.location"],
                "context": "Configures warehouse hierarchy and locations"
            },
            {
                "area": "tracking",
                "questions": [
                    "Do any products require serial number tracking? (Unique ID per unit)",
                    "Do any products require lot/batch tracking? (Group ID for production batches)",
                    "Do you have products with expiration dates that need tracking?"
                ],
                "config_fields": ["product.template.tracking", "stock.lot"],
                "context": "Configures product traceability"
            },
            {
                "area": "routes",
                "questions": [
                    "For each product type: do you keep it in stock, make it on demand, or dropship it?",
                    "At what inventory level should reordering be triggered?",
                    "Do you need to reserve stock when orders are confirmed?"
                ],
                "config_fields": ["product.template.route_ids", "stock.warehouse.orderpoint"],
                "context": "Configures inventory routes and replenishment"
            },
            {
                "area": "operations",
                "questions": [
                    "Describe your picking process - do pickers pick individual orders or batches?",
                    "Do you pack items at a packing station or is picking and packing combined?",
                    "Do you use barcode scanners in your warehouse?"
                ],
                "config_fields": ["stock.picking.batch", "stock.picking.type"],
                "context": "Configures warehouse operations"
            }
        ]
    },
    "account": {
        "name": "Accounting",
        "setup_areas": [
            {
                "area": "localization",
                "questions": [
                    "In which country/countries do you need to file tax returns?",
                    "What accounting standards do you follow? (Local GAAP, IFRS?)",
                    "Do you need specific legal document formats for invoices?"
                ],
                "config_fields": ["res.company.country_id", "account.fiscal.position"],
                "context": "Selects localization package and compliance settings"
            },
            {
                "area": "chart_of_accounts",
                "questions": [
                    "Do you have an existing chart of accounts you want to replicate?",
                    "How detailed should account tracking be? (One revenue account vs. by product category)",
                    "Do you need separate P&L tracking by business unit or location?"
                ],
                "config_fields": ["account.account", "account.analytic.account"],
                "context": "Configures chart of accounts structure"
            },
            {
                "area": "taxes",
                "questions": [
                    "What tax rates do you charge on sales? (VAT, GST, sales tax?)",
                    "Do tax rates vary by product type or customer location?",
                    "Do you have any tax-exempt products or customers?"
                ],
                "config_fields": ["account.tax", "account.fiscal.position.tax"],
                "context": "Configures tax rates and fiscal positions"
            },
            {
                "area": "payment_terms",
                "questions": [
                    "What are your standard payment terms? (Net 30, Due on receipt, etc.)",
                    "Do you offer early payment discounts?",
                    "Do different customer types have different payment terms?"
                ],
                "config_fields": ["account.payment.term"],
                "context": "Configures payment terms"
            },
            {
                "area": "bank_reconciliation",
                "questions": [
                    "Which banks do you use for business banking?",
                    "How do you currently import bank statements? (Manual, download, API?)",
                    "How should payments be matched to invoices?"
                ],
                "config_fields": ["res.partner.bank", "account.journal"],
                "context": "Configures bank accounts and reconciliation"
            }
        ]
    },
    "purchase": {
        "name": "Purchase",
        "setup_areas": [
            {
                "area": "vendors",
                "questions": [
                    "How many active vendors/suppliers do you work with?",
                    "Do you negotiate pricing agreements or contracts with vendors?",
                    "Do you have preferred vendors for specific product categories?"
                ],
                "config_fields": ["res.partner.supplier_rank", "product.supplierinfo"],
                "context": "Configures vendor relationships"
            },
            {
                "area": "approval_workflow",
                "questions": [
                    "Do purchase orders require approval? At what amount thresholds?",
                    "Who has authority to approve purchases?",
                    "Are there spending limits per person or department?"
                ],
                "config_fields": ["purchase.order.approval", "base.approval.type"],
                "context": "Configures purchase approval workflows"
            },
            {
                "area": "receiving",
                "questions": [
                    "Do you do quality inspection on received goods?",
                    "How do you handle partial deliveries from vendors?",
                    "Do you need to track vendor performance (on-time delivery, quality)?"
                ],
                "config_fields": ["stock.picking", "quality.check"],
                "context": "Configures receiving and vendor management"
            }
        ]
    },
    "mrp": {
        "name": "Manufacturing",
        "setup_areas": [
            {
                "area": "bom",
                "questions": [
                    "Describe a typical bill of materials - how many levels deep are your BOMs?",
                    "Do you have products with variants that share similar BOMs?",
                    "Do you track by-products or scrap from manufacturing?"
                ],
                "config_fields": ["mrp.bom", "mrp.bom.line"],
                "context": "Configures bill of materials structure"
            },
            {
                "area": "work_centers",
                "questions": [
                    "What workstations/machines are involved in production?",
                    "Do you track time and capacity per work center?",
                    "Do you need to schedule based on work center availability?"
                ],
                "config_fields": ["mrp.workcenter", "mrp.workcenter.capacity"],
                "context": "Configures work centers and capacity"
            },
            {
                "area": "operations",
                "questions": [
                    "Do manufacturing orders follow a specific routing (sequence of operations)?",
                    "Do workers need detailed work instructions at each step?",
                    "Do you need to track actual time vs. expected time per operation?"
                ],
                "config_fields": ["mrp.routing", "mrp.routing.workcenter"],
                "context": "Configures manufacturing operations and routing"
            }
        ]
    },
    "hr": {
        "name": "HR / Employees",
        "setup_areas": [
            {
                "area": "organization",
                "questions": [
                    "What is your organizational structure? (Departments, teams, reporting lines)",
                    "Do you have multiple office locations with different employee groups?",
                    "What job positions exist in your company?"
                ],
                "config_fields": ["hr.department", "hr.job", "hr.employee"],
                "context": "Configures organizational structure"
            },
            {
                "area": "attendance",
                "questions": [
                    "How do employees track their working hours?",
                    "Do you have flexible working hours or fixed schedules?",
                    "Do you need overtime tracking and rules?"
                ],
                "config_fields": ["hr.attendance", "resource.calendar"],
                "context": "Configures attendance tracking"
            },
            {
                "area": "leave",
                "questions": [
                    "What types of leave do you offer? (Vacation, sick, personal, etc.)",
                    "How are leave balances calculated and allocated?",
                    "What is the approval process for leave requests?"
                ],
                "config_fields": ["hr.leave.type", "hr.leave.allocation"],
                "context": "Configures leave management"
            }
        ]
    },
    "project": {
        "name": "Project",
        "setup_areas": [
            {
                "area": "project_types",
                "questions": [
                    "What types of projects do you manage? (Client projects, internal, R&D?)",
                    "How do you structure projects? (Phases, milestones, tasks?)",
                    "Do projects have budgets that need tracking?"
                ],
                "config_fields": ["project.project", "project.task.type"],
                "context": "Configures project structure"
            },
            {
                "area": "billing",
                "questions": [
                    "How do you bill clients for project work? (Fixed price, time & materials, milestone-based?)",
                    "Do you need to track project profitability?",
                    "Should timesheets automatically create invoice lines?"
                ],
                "config_fields": ["project.project.pricing_type", "account.analytic.line"],
                "context": "Configures project billing"
            },
            {
                "area": "timesheets",
                "questions": [
                    "How should employees log time? (Per task, per project, per day?)",
                    "Do timesheets need manager approval?",
                    "Should there be minimum/maximum hours per day validation?"
                ],
                "config_fields": ["hr.timesheet.config", "account.analytic.line"],
                "context": "Configures timesheet entry"
            }
        ]
    }
}


class AdaptiveInterviewAgent:
    """
    An interview agent that dynamically generates questions based on:
    1. Detected business signals from responses
    2. Odoo module configuration requirements
    3. LLM-driven analysis of what information is still needed
    """

    def __init__(
        self,
        client_name: str,
        industry: str,
        registry_path: str = None,
        llm_manager: Optional[LLMManager] = None,
        output_dir: str = "./outputs",
        config_knowledge_path: Optional[str] = None,  # External JSON for questions
    ):
        self.context = InterviewContext(client_name=client_name, industry=industry)

        # Initialize LLM - uses free/open-source providers (Groq, Ollama)
        if llm_manager:
            self.llm_manager = llm_manager
        else:
            self.llm_manager = get_interview_llm_manager()

        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Load module configuration knowledge (questions) from external JSON
        # This allows updating questions without code changes
        self.module_config_knowledge = load_module_config_knowledge(
            Path(config_knowledge_path) if config_knowledge_path else None
        )
        # Fall back to hardcoded if JSON not available
        if not self.module_config_knowledge:
            self.module_config_knowledge = MODULE_CONFIG_KNOWLEDGE

        # Load module registry
        if registry_path:
            self.registry = ModuleRegistry.from_json(registry_path)
        else:
            default_path = Path(__file__).parent.parent / "knowledge" / "odoo_modules.json"
            if default_path.exists():
                self.registry = ModuleRegistry.from_json(default_path)
            else:
                self.registry = None

        # Question queue - dynamically populated
        self.question_queue: list[DynamicQuestion] = []
        self.asked_questions: list[DynamicQuestion] = []

        # Initialize with discovery questions
        self._add_discovery_questions()

    def _add_discovery_questions(self):
        """Add initial high-level discovery questions."""
        discovery_questions = [
            DynamicQuestion(
                id="disc_01",
                text="Tell me about your business - what products or services do you offer and who are your customers?",
                context="Initial business understanding",
                module_source="discovery",
                config_target="industry_profile",
                priority=10
            ),
            DynamicQuestion(
                id="disc_02",
                text="What are the main challenges or pain points you're hoping to solve with this ERP implementation?",
                context="Understanding motivation and priorities",
                module_source="discovery",
                config_target="pain_points",
                priority=10
            ),
            DynamicQuestion(
                id="disc_03",
                text="Walk me through a typical order - from when a customer places it to when they receive the product/service and pay.",
                context="End-to-end process understanding",
                module_source="discovery",
                config_target="order_to_cash_flow",
                priority=9
            ),
            DynamicQuestion(
                id="disc_04",
                text="How many people will be using the system and what are their main roles?",
                context="User scope and permissions planning",
                module_source="discovery",
                config_target="user_roles",
                priority=8
            )
        ]
        self.question_queue.extend(discovery_questions)

    def _detect_signals(self, response: str) -> dict[str, int]:
        """Detect business signals from a response with negation awareness."""
        result = shared_detect_signals(response)
        return result.active_signals

    def _generate_module_questions(self, modules: list[str]) -> list[DynamicQuestion]:
        """Generate configuration questions for detected modules."""
        questions = []

        for module in modules:
            if module not in self.module_config_knowledge:
                continue

            module_info = self.module_config_knowledge[module]

            for area in module_info["setup_areas"]:
                # Check if we already have info for this area
                area_key = f"{module}_{area['area']}"
                if area_key in self.context.gathered_info:
                    continue

                for i, q_text in enumerate(area["questions"]):
                    q_id = f"{module}_{area['area']}_{i:02d}"

                    # Skip if already asked
                    if any(aq.id == q_id for aq in self.asked_questions):
                        continue

                    questions.append(DynamicQuestion(
                        id=q_id,
                        text=q_text,
                        context=area["context"],
                        module_source=module,
                        config_target=", ".join(area["config_fields"]),
                        priority=7 - i  # First questions in area are higher priority
                    ))

        return questions

    def _use_llm_to_generate_followup(self, response: str, current_question: DynamicQuestion) -> Optional[DynamicQuestion]:
        """Use LLM to generate a contextual follow-up question."""
        if not self.llm_manager:
            return None

        prompt = f"""You are an Odoo ERP consultant conducting a requirements interview.

The client just answered this question:
Q: {current_question.text}
A: {response}

Based on their answer, determine if a follow-up question is needed to clarify:
1. Specific Odoo configuration options
2. Business rules that affect system setup
3. Edge cases or exceptions

If a follow-up is needed, generate ONE specific question.
If the answer was complete, respond with "NO_FOLLOWUP".

Your response should be ONLY the follow-up question text, nothing else.
If no follow-up is needed, respond ONLY with "NO_FOLLOWUP"."""

        try:
            result = self.llm_manager.complete(prompt, max_tokens=150)
            followup_text = result.content.strip()

            if followup_text == "NO_FOLLOWUP" or len(followup_text) < 10:
                return None

            return DynamicQuestion(
                id=f"followup_{current_question.id}_{len(self.asked_questions)}",
                text=followup_text,
                context=f"Follow-up to: {current_question.text[:50]}...",
                module_source=current_question.module_source,
                config_target=current_question.config_target,
                priority=current_question.priority + 1  # Slightly higher priority
            )
        except Exception as e:
            print(f"LLM follow-up generation failed: {e}")
            return None

    def _use_llm_to_refine_questions(self, gathered_context: str) -> list[DynamicQuestion]:
        """Use LLM to identify gaps and generate additional questions."""
        if not self.llm_manager:
            return []

        # Get list of modules we've identified
        detected_modules = list(set(self.context.current_focus_modules))

        prompt = f"""You are an Odoo ERP implementation consultant. Based on the interview so far:

Client: {self.context.client_name}
Industry: {self.context.industry}
Detected modules needed: {', '.join(detected_modules) or 'Still determining'}

Information gathered:
{gathered_context}

What critical configuration information is still missing for setting up these Odoo modules?
Focus on practical setup needs, not general business questions.

Generate 1-3 specific questions that would help configure Odoo correctly.
Format each question on a new line, prefixed with "Q: "

Only output questions, no explanations."""

        try:
            result = self.llm_manager.complete(prompt, max_tokens=300)
            lines = result.content.strip().split("\n")

            questions = []
            for i, line in enumerate(lines):
                if line.startswith("Q: "):
                    q_text = line[3:].strip()
                    if len(q_text) > 10:
                        questions.append(DynamicQuestion(
                            id=f"llm_refined_{len(self.asked_questions)}_{i}",
                            text=q_text,
                            context="LLM-identified gap in configuration requirements",
                            module_source="llm_analysis",
                            config_target="configuration_gap",
                            priority=6
                        ))

            return questions
        except Exception as e:
            print(f"LLM refinement failed: {e}")
            return []

    def process_response(self, response: str, question: DynamicQuestion) -> dict:
        """Process a response and update the interview context."""
        # Record the response
        question.response = response
        question.asked = True
        self.asked_questions.append(question)

        # Detect signals
        new_signals = self._detect_signals(response)
        for signal, count in new_signals.items():
            self.context.detected_signals[signal] = self.context.detected_signals.get(signal, 0) + count

        # Map signals to modules
        signal_to_module = {
            "sales": ["sale_management", "crm"],
            "crm": ["crm"],
            "ecommerce": ["sale_management", "website_sale"],
            "inventory": ["stock"],
            "purchase": ["purchase"],
            "accounting": ["account"],
            "manufacturing": ["mrp"],
            "hr": ["hr"],
            "project": ["project"],
            "support": ["helpdesk"],
        }

        for signal in new_signals:
            if signal in signal_to_module:
                for module in signal_to_module[signal]:
                    if module not in self.context.current_focus_modules:
                        self.context.current_focus_modules.append(module)

        # Store response
        self.context.responses.append({
            "question_id": question.id,
            "question": question.text,
            "response": response,
            "module": question.module_source,
            "config_target": question.config_target,
            "timestamp": datetime.now().isoformat(),
            "signals_detected": new_signals
        })

        # Generate module-specific questions for newly detected modules
        new_module_questions = self._generate_module_questions(self.context.current_focus_modules)
        for q in new_module_questions:
            if not any(eq.id == q.id for eq in self.question_queue):
                self.question_queue.append(q)

        # Try to generate LLM follow-up
        followup = self._use_llm_to_generate_followup(response, question)
        if followup:
            # Insert at front of queue for immediate asking
            self.question_queue.insert(0, followup)

        # Sort queue by priority
        self.question_queue.sort(key=lambda q: -q.priority)

        return {
            "signals_detected": new_signals,
            "modules_identified": self.context.current_focus_modules,
            "questions_in_queue": len(self.question_queue),
            "followup_generated": followup is not None
        }

    def get_next_question(self) -> Optional[DynamicQuestion]:
        """Get the next question to ask."""
        # If queue is running low, try to generate more with LLM
        if len(self.question_queue) < 3 and len(self.asked_questions) > 2:
            gathered = "\n".join([
                f"Q: {r['question']}\nA: {r['response']}"
                for r in self.context.responses[-5:]
            ])
            refined_questions = self._use_llm_to_refine_questions(gathered)
            self.question_queue.extend(refined_questions)
            self.question_queue.sort(key=lambda q: -q.priority)

        if not self.question_queue:
            return None

        return self.question_queue.pop(0)

    def get_interview_summary(self) -> dict:
        """Get a summary of the interview for the next agent."""
        return {
            "client_name": self.context.client_name,
            "industry": self.context.industry,
            "detected_signals": self.context.detected_signals,
            "recommended_modules": self.context.current_focus_modules,
            "questions_asked": len(self.asked_questions),
            "gathered_config_info": {
                r["config_target"]: r["response"]
                for r in self.context.responses
                if r.get("config_target")
            },
            "responses": self.context.responses
        }

    def save_interview(self) -> str:
        """Save the interview results."""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filepath = self.output_dir / f"adaptive-interview-{timestamp}.json"

        output = {
            "project_id": f"odoo-impl-{timestamp}",
            **self.get_interview_summary(),
            "raw_responses": {
                q.module_source: [
                    {
                        "question_id": r["question_id"],
                        "question": r["question"],
                        "response": r["response"],
                        "timestamp": r["timestamp"]
                    }
                    for r in self.context.responses
                    if any(aq.id == r["question_id"] and aq.module_source == q.module_source
                           for aq in self.asked_questions)
                ]
                for q in self.asked_questions
            },
            "module_config_requirements": {
                module: MODULE_CONFIG_KNOWLEDGE.get(module, {})
                for module in self.context.current_focus_modules
            }
        }

        with open(filepath, 'w') as f:
            json.dump(output, f, indent=2, default=str)

        return str(filepath)


def run_adaptive_interview(client_name: str, industry: str):
    """Run an interactive adaptive interview session."""
    agent = AdaptiveInterviewAgent(client_name, industry)

    print(f"\n{'='*60}")
    print(f"Adaptive Odoo Implementation Interview")
    print(f"Client: {client_name} | Industry: {industry}")
    print(f"{'='*60}\n")
    print("This interview adapts based on your responses.")
    print("Type 'done' to finish, 'skip' to skip a question.\n")

    while True:
        question = agent.get_next_question()

        if not question:
            print("\n✅ Interview complete - all relevant questions asked.")
            break

        print(f"\n📋 [{question.module_source}] {question.text}")
        if question.context:
            print(f"   (Context: {question.context})")

        response = input("\n> ").strip()

        if response.lower() == 'done':
            break
        if response.lower() == 'skip':
            print("Skipped.")
            continue

        result = agent.process_response(response, question)

        if result["signals_detected"]:
            print(f"   🔍 Detected: {', '.join(result['signals_detected'].keys())}")
        if result["followup_generated"]:
            print("   💡 Follow-up question queued")

    # Save and summarize
    filepath = agent.save_interview()
    summary = agent.get_interview_summary()

    print(f"\n{'='*60}")
    print("Interview Summary")
    print(f"{'='*60}")
    print(f"Questions asked: {summary['questions_asked']}")
    print(f"Recommended modules: {', '.join(summary['recommended_modules']) or 'None detected'}")
    print(f"Saved to: {filepath}")

    return agent


if __name__ == "__main__":
    import sys
    client = sys.argv[1] if len(sys.argv) > 1 else "Test Company"
    industry = sys.argv[2] if len(sys.argv) > 2 else "General"
    run_adaptive_interview(client, industry)
