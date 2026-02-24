"""
Phased Interview Agent - Structured interview with scoping + domain expert handoff.

Interview Flow:
1. SCOPING PHASE: Fixed questions to determine company scope
   - Identify which domain experts are needed
   - Set expectations for interview length

2. DOMAIN EXPERT PHASE: Hand off to specialized domain agents
   - Sales Expert → in-depth sales/CRM questions
   - Inventory Expert → warehouse/stock questions
   - Finance Expert → accounting/invoicing questions
   - etc.

3. SUMMARY PHASE: Compile findings and recommend modules
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Any

from ..llm.manager import LLMManager, LLMManagerConfig
from ..signals import detect_signals as shared_detect_signals, SIGNAL_TO_INTERVIEW_DOMAIN, DOMAIN_TO_MODULES


def get_phased_llm_manager() -> LLMManager:
    """Get LLM manager for phased interview (free/open-source only)."""
    config = LLMManagerConfig(
        provider_priority=["groq", "ollama"],
        default_models={
            "groq": "llama-3.3-70b-versatile",
            "ollama": "mistral:latest"
        }
    )
    return LLMManager(config)


class InterviewPhase(Enum):
    """Interview phases."""
    SCOPING = "scoping"
    DOMAIN_EXPERT = "domain_expert"
    SUMMARY = "summary"
    COMPLETE = "complete"


class DomainExpert(Enum):
    """Domain expert types - each is an Odoo specialist."""
    SALES = "sales"
    INVENTORY = "inventory"
    FINANCE = "finance"
    PURCHASE = "purchase"
    MANUFACTURING = "manufacturing"
    HR = "hr"
    PROJECT = "project"
    ECOMMERCE = "ecommerce"


@dataclass
class ScopingQuestion:
    """Fixed scoping question."""
    id: str
    text: str
    determines_domains: list[str]  # Which domains this question helps identify
    required: bool = True


@dataclass
class DomainQuestion:
    """Expert domain question."""
    id: str
    text: str
    context: str
    config_target: str  # What Odoo config this maps to
    priority: int = 5
    follow_ups: list[str] = field(default_factory=list)


@dataclass
class Response:
    """Recorded response."""
    question_id: str
    question_text: str
    response: str
    phase: str
    domain: Optional[str]
    timestamp: str


@dataclass
class InterviewState:
    """Tracks interview progress."""
    client_name: str
    industry: str
    phase: InterviewPhase = InterviewPhase.SCOPING

    # Scoping phase
    scoping_index: int = 0
    scoping_responses: list[Response] = field(default_factory=list)

    # Domain phase
    active_domains: list[str] = field(default_factory=list)  # Domains to cover
    completed_domains: list[str] = field(default_factory=list)
    current_domain: Optional[str] = None
    current_domain_index: int = 0
    domain_responses: dict[str, list[Response]] = field(default_factory=dict)

    # Detected info
    detected_signals: dict[str, int] = field(default_factory=dict)
    recommended_modules: list[str] = field(default_factory=list)

    # Progress tracking
    total_questions_asked: int = 0

    def get_progress(self) -> dict:
        """Get progress info for UI."""
        if self.phase == InterviewPhase.SCOPING:
            total_scoping = len(SCOPING_QUESTIONS)
            return {
                "phase": "Scoping",
                "phase_progress": self.scoping_index,
                "phase_total": total_scoping,
                "overall_percent": int((self.scoping_index / total_scoping) * 30),  # Scoping = 30%
                "domains_pending": [],
                "domains_completed": [],
                "current_domain": None
            }
        elif self.phase == InterviewPhase.DOMAIN_EXPERT:
            domain_progress = len(self.completed_domains)
            domain_total = len(self.active_domains)
            base_percent = 30  # After scoping
            domain_percent = int((domain_progress / max(domain_total, 1)) * 60)  # Domains = 60%
            return {
                "phase": f"Expert: {self.current_domain.title() if self.current_domain else 'Unknown'}",
                "phase_progress": self.current_domain_index,
                "phase_total": len(DOMAIN_EXPERT_QUESTIONS.get(self.current_domain, [])),
                "overall_percent": base_percent + domain_percent,
                "domains_pending": [d for d in self.active_domains if d not in self.completed_domains],
                "domains_completed": self.completed_domains,
                "current_domain": self.current_domain
            }
        else:
            return {
                "phase": "Summary",
                "phase_progress": 1,
                "phase_total": 1,
                "overall_percent": 100,
                "domains_pending": [],
                "domains_completed": self.active_domains,
                "current_domain": None
            }


# =============================================================================
# SCOPING QUESTIONS - Fixed questions to determine scope
# =============================================================================

SCOPING_QUESTIONS = [
    ScopingQuestion(
        id="scope_01",
        text="What products or services do you sell, and how do customers typically buy from you? (e.g., 'B2B quotes via sales reps', 'online store', 'contracts and renewals')",
        determines_domains=["sales", "ecommerce"]
    ),
    ScopingQuestion(
        id="scope_02",
        text="Do you handle physical goods — warehousing, shipping, or inventory tracking?",
        determines_domains=["inventory", "purchase"]
    ),
    ScopingQuestion(
        id="scope_03",
        text="Do you manufacture, assemble, or transform raw materials into finished products?",
        determines_domains=["manufacturing"]
    ),
    ScopingQuestion(
        id="scope_04",
        text="How do you handle purchasing from suppliers? Do you use purchase orders, blanket contracts, or something informal?",
        determines_domains=["purchase"]
    ),
    ScopingQuestion(
        id="scope_05",
        text="Do you track projects, timesheets, or bill clients on time & materials?",
        determines_domains=["project"]
    ),
    ScopingQuestion(
        id="scope_06",
        text="How do you handle invoicing and accounting today? Do you deal with multi-currency, multiple tax rates, or specific fiscal requirements?",
        determines_domains=["finance"]
    ),
    ScopingQuestion(
        id="scope_07",
        text="How many employees do you have? Do you need to manage leave requests, attendance, payroll, or expense claims in Odoo?",
        determines_domains=["hr"]
    ),
    ScopingQuestion(
        id="scope_08",
        text="Do you sell online or need a website? What platform are you using today, if any?",
        determines_domains=["ecommerce"]
    ),
    ScopingQuestion(
        id="scope_09",
        text="What existing software or systems need to connect to Odoo? (e.g., Shopify, QuickBooks, Stripe, spreadsheets, custom APIs)",
        determines_domains=[]
    ),
]

# Vague response indicators - triggers follow-up
_VAGUE_INDICATORS = {"maybe", "i think", "not sure", "depends", "sometimes", "i guess", "possibly", "probably", "sort of"}
_MIN_USEFUL_LENGTH = 15  # Responses shorter than this trigger follow-up


# =============================================================================
# DOMAIN EXPERT QUESTIONS - Deep-dive questions per domain
# =============================================================================

DOMAIN_EXPERT_QUESTIONS = {
    "sales": [
        DomainQuestion(
            id="sales_01",
            text="Walk me through your sales process: How does someone go from 'interested' to 'paying customer'?",
            context="Understanding the sales pipeline",
            config_target="crm.stage, sale.order workflow",
            priority=10,
            follow_ups=[
                "How long does this process typically take?",
                "Who's involved in approving a deal?"
            ]
        ),
        DomainQuestion(
            id="sales_02",
            text="How do you price your products? Do you have standard prices, or does it vary by customer, quantity, or region?",
            context="Pricing strategy for pricelist configuration",
            config_target="product.pricelist",
            priority=9
        ),
        DomainQuestion(
            id="sales_03",
            text="Do your salespeople give discounts? If so, are there limits or do they need approval?",
            context="Discount policies",
            config_target="sale.order.line.discount, approval workflows",
            priority=8
        ),
        DomainQuestion(
            id="sales_04",
            text="Do you send quotes/proposals to customers? What needs to be on them?",
            context="Quotation template requirements",
            config_target="sale.order template, PDF report",
            priority=7
        ),
        DomainQuestion(
            id="sales_05",
            text="How do you track where leads come from? (Website, referrals, ads, trade shows, etc.)",
            context="Lead source tracking for CRM",
            config_target="utm.source, crm.lead.source_id",
            priority=6
        ),
    ],

    "inventory": [
        DomainQuestion(
            id="inv_01",
            text="Describe your warehouse setup: How many locations? Do you have zones, aisles, shelves, bins?",
            context="Warehouse structure configuration",
            config_target="stock.warehouse, stock.location",
            priority=10
        ),
        DomainQuestion(
            id="inv_02",
            text="Do any of your products need serial numbers or batch/lot tracking? (e.g., for recalls, expiration, warranties)",
            context="Product traceability requirements",
            config_target="product.template.tracking",
            priority=9
        ),
        DomainQuestion(
            id="inv_03",
            text="How do you know when to reorder? Do you have minimum stock levels set up?",
            context="Reordering rules",
            config_target="stock.warehouse.orderpoint",
            priority=8
        ),
        DomainQuestion(
            id="inv_04",
            text="When an order comes in, how do your warehouse staff know what to pick and ship?",
            context="Picking and shipping workflow",
            config_target="stock.picking.type, stock.picking.batch",
            priority=7
        ),
        DomainQuestion(
            id="inv_05",
            text="Do you use barcode scanners? Or plan to?",
            context="Barcode implementation",
            config_target="stock.picking barcode integration",
            priority=6
        ),
    ],

    "finance": [
        DomainQuestion(
            id="fin_01",
            text="Which countries do you operate in financially? (This affects tax rules and legal invoice formats)",
            context="Localization package selection",
            config_target="account.fiscal.position, localization module",
            priority=10
        ),
        DomainQuestion(
            id="fin_02",
            text="What tax rates do you charge? Does it vary by product type or customer location?",
            context="Tax configuration",
            config_target="account.tax, account.fiscal.position.tax",
            priority=9
        ),
        DomainQuestion(
            id="fin_03",
            text="What are your payment terms? (Net 30, Due on receipt, installments, etc.)",
            context="Payment terms setup",
            config_target="account.payment.term",
            priority=8
        ),
        DomainQuestion(
            id="fin_04",
            text="How do you currently track what's been paid vs. what's outstanding?",
            context="Receivables management",
            config_target="account.move, payment matching",
            priority=7
        ),
        DomainQuestion(
            id="fin_05",
            text="Do you need separate reporting by department, project, or business unit?",
            context="Analytic accounting needs",
            config_target="account.analytic.account",
            priority=6
        ),
    ],

    "purchase": [
        DomainQuestion(
            id="pur_01",
            text="How many suppliers do you regularly buy from? Do you have preferred vendors for specific products?",
            context="Vendor management",
            config_target="res.partner, product.supplierinfo",
            priority=10
        ),
        DomainQuestion(
            id="pur_02",
            text="Do purchase orders need approval? At what amount threshold?",
            context="PO approval workflow",
            config_target="purchase.order.approval",
            priority=9
        ),
        DomainQuestion(
            id="pur_03",
            text="Do you negotiate pricing or contracts with suppliers in advance?",
            context="Vendor agreements",
            config_target="purchase.requisition",
            priority=8
        ),
        DomainQuestion(
            id="pur_04",
            text="When goods arrive, what's your receiving process? Do you inspect quality?",
            context="Receiving and QC",
            config_target="stock.picking, quality.check",
            priority=7
        ),
    ],

    "manufacturing": [
        DomainQuestion(
            id="mfg_01",
            text="Walk me through making one of your products: What raw materials go in, what comes out?",
            context="Bill of materials structure",
            config_target="mrp.bom",
            priority=10
        ),
        DomainQuestion(
            id="mfg_02",
            text="What machines or workstations are involved? Do they have capacity limits?",
            context="Work center configuration",
            config_target="mrp.workcenter",
            priority=9
        ),
        DomainQuestion(
            id="mfg_03",
            text="Is there a specific sequence of steps (routing) to make your products?",
            context="Manufacturing routing",
            config_target="mrp.routing",
            priority=8
        ),
        DomainQuestion(
            id="mfg_04",
            text="Do you make to stock (in advance) or make to order (when customer orders)?",
            context="Manufacturing strategy",
            config_target="product.template.route_ids",
            priority=7
        ),
        DomainQuestion(
            id="mfg_05",
            text="How do you track production time? Do workers clock in/out of jobs?",
            context="Work order time tracking",
            config_target="mrp.workorder",
            priority=6
        ),
    ],

    "hr": [
        DomainQuestion(
            id="hr_01",
            text="What's your company structure? Departments, teams, reporting lines?",
            context="Organizational hierarchy",
            config_target="hr.department, hr.employee",
            priority=10
        ),
        DomainQuestion(
            id="hr_02",
            text="How do employees request time off? What types of leave do you offer?",
            context="Leave management",
            config_target="hr.leave.type, hr.leave",
            priority=9
        ),
        DomainQuestion(
            id="hr_03",
            text="Do you track attendance? How do people clock in/out?",
            context="Attendance tracking",
            config_target="hr.attendance",
            priority=8
        ),
        DomainQuestion(
            id="hr_04",
            text="Do employees submit expenses for reimbursement?",
            context="Expense management",
            config_target="hr.expense",
            priority=7
        ),
    ],

    "project": [
        DomainQuestion(
            id="proj_01",
            text="What types of projects do you do? (Client work, internal, R&D, etc.)",
            context="Project types",
            config_target="project.project.type",
            priority=10
        ),
        DomainQuestion(
            id="proj_02",
            text="How do you bill clients? Fixed price, time & materials, milestones?",
            context="Project billing method",
            config_target="project.project.pricing_type",
            priority=9
        ),
        DomainQuestion(
            id="proj_03",
            text="Do team members track time against projects? How?",
            context="Timesheet configuration",
            config_target="account.analytic.line, hr.timesheet",
            priority=8
        ),
        DomainQuestion(
            id="proj_04",
            text="How do you track project progress? Stages, tasks, subtasks?",
            context="Task workflow",
            config_target="project.task.type",
            priority=7
        ),
    ],

    "ecommerce": [
        DomainQuestion(
            id="ecom_01",
            text="Do you have an existing website, or will Odoo be your main website too?",
            context="Website integration scope",
            config_target="website module selection",
            priority=10
        ),
        DomainQuestion(
            id="ecom_02",
            text="How many products will be on the website? How are they organized?",
            context="Product catalog structure",
            config_target="product.public.category",
            priority=9
        ),
        DomainQuestion(
            id="ecom_03",
            text="What payment methods do customers use? (Cards, PayPal, bank transfer, etc.)",
            context="Payment provider setup",
            config_target="payment.provider",
            priority=8
        ),
        DomainQuestion(
            id="ecom_04",
            text="How do you handle shipping? Flat rate, real-time carrier rates, free over X?",
            context="Delivery methods",
            config_target="delivery.carrier",
            priority=7
        ),
        DomainQuestion(
            id="ecom_05",
            text="Do you need customer accounts with order history, or guest checkout only?",
            context="Customer portal needs",
            config_target="website.sale customer settings",
            priority=6
        ),
    ],
}


# Signal detection now uses shared module (src/signals.py)
# Kept here as a reference for domain expert mapping
_INTERVIEW_DOMAINS = ["sales", "inventory", "finance", "purchase", "manufacturing", "hr", "project", "ecommerce"]


class PhasedInterviewAgent:
    """
    Interview agent with clear phases and domain expert handoff.

    Flow:
    1. Scoping questions (fixed) → Determine which domains apply
    2. Domain expert questions → Deep dive per relevant domain
    3. Summary → Compile recommendations
    """

    def __init__(
        self,
        client_name: str,
        industry: str,
        llm_manager: Optional[LLMManager] = None,
        output_dir: str = "./outputs"
    ):
        self.state = InterviewState(client_name=client_name, industry=industry)
        self.llm_manager = llm_manager or get_phased_llm_manager()
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Cross-domain intelligence: track topics mentioned so we skip redundant questions
        self._mentioned_topics: dict[str, str] = {}  # topic -> response snippet
        # Follow-up tracking: max 2 follow-ups per question to avoid annoyance
        self._follow_up_count: dict[str, int] = {}
        self._pending_follow_up: Optional[dict] = None

    def get_next_question(self) -> Optional[dict]:
        """
        Get the next question based on current phase.

        Returns dict with:
        - id: question ID
        - text: question text
        - phase: current phase
        - domain: current domain (if in domain phase)
        - progress: progress info
        """
        # Check for pending follow-up first
        if self._pending_follow_up:
            follow_up = self._pending_follow_up
            self._pending_follow_up = None
            return follow_up

        if self.state.phase == InterviewPhase.SCOPING:
            return self._get_scoping_question()
        elif self.state.phase == InterviewPhase.DOMAIN_EXPERT:
            return self._get_domain_question()
        else:
            return None

    def _get_scoping_question(self) -> Optional[dict]:
        """Get next scoping question."""
        if self.state.scoping_index >= len(SCOPING_QUESTIONS):
            # Scoping complete - transition to domain phase
            self._transition_to_domain_phase()
            return self._get_domain_question()

        q = SCOPING_QUESTIONS[self.state.scoping_index]
        return {
            "id": q.id,
            "text": q.text,
            "phase": "scoping",
            "domain": None,
            "context": "Determining your business scope",
            "progress": self.state.get_progress()
        }

    def _get_domain_question(self) -> Optional[dict]:
        """Get next domain expert question."""
        # Check if we need to move to next domain
        if self.state.current_domain is None:
            if not self.state.active_domains:
                self._transition_to_summary()
                return None
            self.state.current_domain = self.state.active_domains[0]
            self.state.current_domain_index = 0

        domain_questions = DOMAIN_EXPERT_QUESTIONS.get(self.state.current_domain, [])

        if self.state.current_domain_index >= len(domain_questions):
            # Domain complete - move to next
            self.state.completed_domains.append(self.state.current_domain)
            remaining = [d for d in self.state.active_domains if d not in self.state.completed_domains]

            if not remaining:
                self._transition_to_summary()
                return None

            self.state.current_domain = remaining[0]
            self.state.current_domain_index = 0
            domain_questions = DOMAIN_EXPERT_QUESTIONS.get(self.state.current_domain, [])

        if self.state.current_domain_index >= len(domain_questions):
            self._transition_to_summary()
            return None

        q = domain_questions[self.state.current_domain_index]

        # Get expert intro message if first question in domain
        expert_intro = None
        if self.state.current_domain_index == 0:
            expert_intro = self._get_expert_intro(self.state.current_domain)

        return {
            "id": q.id,
            "text": q.text,
            "phase": "domain_expert",
            "domain": self.state.current_domain,
            "context": q.context,
            "config_target": q.config_target,
            "expert_intro": expert_intro,
            "progress": self.state.get_progress()
        }

    def _get_expert_intro(self, domain: str) -> str:
        """Get a natural, context-aware introduction for each domain expert."""
        client = self.state.client_name or "your company"

        # Build context from what we already know
        context_hints = []
        for resp in self.state.scoping_responses:
            if resp.response.strip():
                context_hints.append(resp.response.strip())
        context_summary = " ".join(context_hints)[:200]

        intros = {
            "sales": (
                f"Great, now I'd like to focus on how {client} sells. "
                "I'll ask about your sales pipeline, pricing, and how you close deals. "
                "This helps me set up the CRM and sales workflows correctly."
            ),
            "inventory": (
                f"Let's talk about how {client} handles physical goods. "
                "I need to understand your warehouse layout, how you track stock, "
                "and how orders get picked and shipped."
            ),
            "finance": (
                f"Now for the financial side of {client}. "
                "I'll ask about invoicing, taxes, and how you track payments. "
                "This is critical for getting the accounting setup right from day one."
            ),
            "purchase": (
                f"Let's look at how {client} buys from suppliers. "
                "I need to understand your procurement process, "
                "vendor relationships, and how purchase orders work."
            ),
            "manufacturing": (
                f"Now let's dive into how {client} makes products. "
                "I'll ask about your bill of materials, production steps, "
                "and how you plan manufacturing runs."
            ),
            "hr": (
                f"Let's talk about managing the team at {client}. "
                "I'll cover employee management, time off policies, "
                "and any attendance or expense tracking you need."
            ),
            "project": (
                f"Let's discuss how {client} manages projects and client work. "
                "I'll ask about how you scope, track, and bill for projects."
            ),
            "ecommerce": (
                f"Let's cover {client}'s online sales channel. "
                "I need to understand your website needs, product catalog, "
                "and how online orders flow into your operations."
            ),
        }
        return intros.get(domain, f"Let's discuss {domain} in more detail for {client}.")

    def _transition_to_domain_phase(self):
        """Analyze scoping responses and determine which domains to cover."""
        # Detect domains from scoping responses
        detected_domains = set()

        for response in self.state.scoping_responses:
            signals = self._detect_signals(response.response)
            for signal, count in signals.items():
                self.state.detected_signals[signal] = self.state.detected_signals.get(signal, 0) + count
                detected_domains.add(signal)

        # Set active domains (at minimum: sales, finance)
        self.state.active_domains = list(detected_domains) if detected_domains else ["sales"]

        # Always include finance/accounting
        if "finance" not in self.state.active_domains:
            self.state.active_domains.append("finance")

        # Sort by priority
        priority_order = ["sales", "inventory", "finance", "purchase", "manufacturing", "hr", "project", "ecommerce"]
        self.state.active_domains.sort(key=lambda x: priority_order.index(x) if x in priority_order else 99)

        self.state.phase = InterviewPhase.DOMAIN_EXPERT

    def _transition_to_summary(self):
        """Transition to summary phase."""
        self.state.phase = InterviewPhase.SUMMARY
        self._compile_recommendations()

    def _compile_recommendations(self):
        """Compile module recommendations based on responses."""
        modules = set()
        for domain in self.state.completed_domains:
            for module in DOMAIN_TO_MODULES.get(domain, []):
                modules.add(module)

        self.state.recommended_modules = list(modules)

    def _detect_signals(self, text: str) -> dict[str, int]:
        """Detect business domain signals from text with negation awareness."""
        result = shared_detect_signals(text)
        # Map raw signals to interview domains and return only positive/active ones
        domain_signals: dict[str, int] = {}
        for signal_domain, count in result.active_signals.items():
            interview_domain = SIGNAL_TO_INTERVIEW_DOMAIN.get(signal_domain)
            if interview_domain and interview_domain in _INTERVIEW_DOMAINS:
                domain_signals[interview_domain] = domain_signals.get(interview_domain, 0) + count
        return domain_signals

    def process_response(self, response_text: str, question_info: dict) -> dict:
        """
        Process a response to a question.

        Includes:
        - Signal detection with negation awareness
        - Follow-up generation for vague/short responses
        - Cross-domain topic tracking to avoid redundant questions
        """
        question_text = question_info.get("text") or question_info.get("question", "")
        question_id = question_info.get("id", "unknown")
        phase = question_info.get("phase", "scoping")

        response = Response(
            question_id=question_id,
            question_text=question_text,
            response=response_text,
            phase=phase,
            domain=question_info.get("domain"),
            timestamp=datetime.now().isoformat()
        )

        # Record response
        if phase == "scoping":
            self.state.scoping_responses.append(response)
            self.state.scoping_index += 1
        else:
            domain = question_info.get("domain")
            if domain:
                if domain not in self.state.domain_responses:
                    self.state.domain_responses[domain] = []
                self.state.domain_responses[domain].append(response)
            self.state.current_domain_index += 1

        self.state.total_questions_asked += 1

        # Detect signals
        signals = self._detect_signals(response_text)
        for signal, count in signals.items():
            self.state.detected_signals[signal] = self.state.detected_signals.get(signal, 0) + count

        # Track cross-domain mentions
        self._track_mentions(response_text)

        # Check if we should add newly detected domains
        for signal in signals:
            if signal not in self.state.active_domains and signal in DOMAIN_EXPERT_QUESTIONS:
                if self.state.phase == InterviewPhase.DOMAIN_EXPERT:
                    if signal not in self.state.completed_domains:
                        self.state.active_domains.append(signal)

        # Check if response is vague/short and generate follow-up
        follow_up = self._maybe_follow_up(response_text, question_info)

        result = {
            "signals_detected": signals,
            "phase": self.state.phase.value,
            "progress": self.state.get_progress(),
            "domains_active": self.state.active_domains,
            "recommended_modules": self.state.recommended_modules,
        }

        if follow_up:
            result["follow_up"] = follow_up

        return result

    def _track_mentions(self, response_text: str):
        """Track topics mentioned across domains to avoid redundant questions."""
        topics = {
            "serial_tracking": ["serial number", "serial", "lot tracking", "batch tracking", "traceability"],
            "multi_warehouse": ["multiple warehouse", "two warehouse", "several location", "multi-location"],
            "pricelist": ["pricelist", "volume discount", "tiered pricing", "different price"],
            "approval": ["approval", "approve", "sign off", "authorization"],
            "barcode": ["barcode", "scanner", "scanning"],
            "timesheet": ["timesheet", "time tracking", "hours", "billable"],
            "payroll": ["payroll", "salary", "wages"],
            "ecommerce": ["online store", "webshop", "e-commerce", "website sales"],
        }
        text_lower = response_text.lower()
        for topic, keywords in topics.items():
            if any(kw in text_lower for kw in keywords):
                self._mentioned_topics[topic] = response_text[:100]

    def _maybe_follow_up(self, response_text: str, question_info: dict) -> Optional[dict]:
        """Generate a follow-up question if the response is vague or too short."""
        question_id = question_info.get("id", "unknown")
        # Use the base question ID (before any _followup_ suffix) for counting
        base_id = question_id.split("_followup_")[0]

        # Max 2 follow-ups per question
        follow_up_count = self._follow_up_count.get(base_id, 0)
        if follow_up_count >= 2:
            return None

        response_stripped = response_text.strip()

        # Skip empty responses (handled by voice agent)
        if not response_stripped:
            return None

        needs_follow_up = False
        follow_up_text = ""

        # Check for short responses
        if len(response_stripped) < _MIN_USEFUL_LENGTH:
            needs_follow_up = True
            follow_up_text = "Could you elaborate a bit more? Even a specific example would help me understand your needs better."

        # Check for vague language
        elif any(vague in response_stripped.lower() for vague in _VAGUE_INDICATORS):
            needs_follow_up = True
            follow_up_text = "Can you be more specific? For instance, can you walk me through a real example from the last week or two?"

        if needs_follow_up:
            self._follow_up_count[base_id] = follow_up_count + 1
            self._pending_follow_up = {
                "id": f"{question_id}_followup_{follow_up_count + 1}",
                "text": follow_up_text,
                "phase": question_info.get("phase", "scoping"),
                "domain": question_info.get("domain"),
                "context": f"Follow-up to: {question_info.get('text', '')[:60]}",
                "is_follow_up": True,
                "progress": self.state.get_progress()
            }
            return self._pending_follow_up

        return None

    def skip_question(self, question_info: dict):
        """Skip the current question."""
        phase = question_info.get("phase", "scoping")
        if phase == "scoping":
            self.state.scoping_index += 1
        else:
            self.state.current_domain_index += 1

    def get_summary(self) -> dict:
        """Get interview summary with completeness metadata."""
        total_questions = self.state.total_questions_asked
        answered = sum(
            1 for r in self.state.scoping_responses if r.response.strip()
        ) + sum(
            1 for responses in self.state.domain_responses.values()
            for r in responses if r.response.strip()
        )

        return {
            "client_name": self.state.client_name,
            "industry": self.state.industry,
            "phase": self.state.phase.value,
            "questions_asked": total_questions,
            "questions_answered": answered,
            "detected_signals": self.state.detected_signals,
            "domains_covered": self.state.completed_domains,
            "recommended_modules": self.state.recommended_modules,
            "mentioned_topics": dict(self._mentioned_topics),
            "scoping_responses": [
                {"q": r.question_text, "a": r.response}
                for r in self.state.scoping_responses
            ],
            "domain_responses": {
                domain: [{"q": r.question_text, "a": r.response} for r in responses]
                for domain, responses in self.state.domain_responses.items()
            },
            "progress": self.state.get_progress(),
            "llm_available": self.llm_manager.is_available if self.llm_manager else False,
        }

    def is_complete(self) -> bool:
        """Check if interview is complete."""
        return self.state.phase in [InterviewPhase.SUMMARY, InterviewPhase.COMPLETE]

    def save_interview(self) -> str:
        """Save interview to file."""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"interview-{self.state.client_name.replace(' ', '-')}-{timestamp}.json"
        filepath = self.output_dir / filename

        with open(filepath, 'w') as f:
            json.dump(self.get_summary(), f, indent=2)

        return str(filepath)


def get_total_interview_estimate(agent: PhasedInterviewAgent) -> dict:
    """Estimate total interview length based on active domains."""
    scoping_qs = len(SCOPING_QUESTIONS)
    domain_qs = sum(
        len(DOMAIN_EXPERT_QUESTIONS.get(d, []))
        for d in agent.state.active_domains
    )

    return {
        "scoping_questions": scoping_qs,
        "domain_questions": domain_qs,
        "total_estimated": scoping_qs + domain_qs,
        "estimated_minutes": (scoping_qs + domain_qs) * 1.5  # ~1.5 min per question
    }
