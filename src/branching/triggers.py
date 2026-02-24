"""
Domain-specific trigger rules for interview branching.

Each domain has rules that define:
- Keywords that trigger specific follow-up questions
- Required information that must be gathered
- Questions that can be skipped based on context
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Callable
from enum import Enum


class TriggerAction(str, Enum):
    """Type of action to take when a trigger fires."""
    ASK_FOLLOW_UP = "ask_follow_up"       # Ask a specific follow-up question
    PROBE_DEEPER = "probe_deeper"          # Generic probing
    FLAG_FOR_REVIEW = "flag_for_review"    # Flag for Technical Architect
    SKIP_QUESTIONS = "skip_questions"      # Skip certain future questions
    ADD_REQUIREMENT = "add_requirement"    # Add to requirements list
    MARK_CRITICAL = "mark_critical"        # Mark as critical requirement


@dataclass
class TriggerRule:
    """A single trigger rule for branching logic."""
    id: str
    domain: str
    trigger_type: str  # "keyword", "missing", "pattern", "condition"
    trigger_value: str  # Keyword, pattern, or condition name
    action: TriggerAction
    follow_up_question: str = ""
    target_questions: List[str] = field(default_factory=list)  # Question IDs
    priority: int = 5  # 1-10, lower = higher priority
    description: str = ""


@dataclass
class DomainTriggers:
    """Collection of triggers for a specific domain."""
    domain: str
    triggers: List[TriggerRule] = field(default_factory=list)
    required_info: List[str] = field(default_factory=list)  # Must have before completing domain

    def get_keyword_triggers(self) -> List[TriggerRule]:
        """Get all keyword-based triggers."""
        return [t for t in self.triggers if t.trigger_type == "keyword"]

    def get_missing_triggers(self) -> List[TriggerRule]:
        """Get all missing-info triggers."""
        return [t for t in self.triggers if t.trigger_type == "missing"]


# =============================================================================
# COMPANY BASICS TRIGGERS
# =============================================================================
COMPANY_BASICS_TRIGGERS = DomainTriggers(
    domain="company_basics",
    required_info=["industry", "employee_count", "locations"],
    triggers=[
        TriggerRule(
            id="cb_multi_country",
            domain="company_basics",
            trigger_type="keyword",
            trigger_value=r"(?:multiple|several|different)\s+(?:countries|country|locations|offices)",
            action=TriggerAction.ASK_FOLLOW_UP,
            follow_up_question="Which countries do you operate in? This affects tax configuration and localizations.",
            priority=2
        ),
        TriggerRule(
            id="cb_multi_company",
            domain="company_basics",
            trigger_type="keyword",
            trigger_value=r"(?:subsidiaries|sister\s+companies|holding|group\s+of\s+companies)",
            action=TriggerAction.ASK_FOLLOW_UP,
            follow_up_question="Do these entities need separate accounting or can they share a chart of accounts?",
            priority=2
        ),
        TriggerRule(
            id="cb_rapid_growth",
            domain="company_basics",
            trigger_type="keyword",
            trigger_value=r"(?:growing|growth|expand|scaling|doubl)",
            action=TriggerAction.ASK_FOLLOW_UP,
            follow_up_question="What's your expected headcount in 12-24 months? This helps us plan for scalability.",
            priority=4
        ),
    ]
)


# =============================================================================
# CURRENT SYSTEMS TRIGGERS
# =============================================================================
CURRENT_SYSTEMS_TRIGGERS = DomainTriggers(
    domain="current_systems",
    required_info=["current_systems", "pain_points"],
    triggers=[
        TriggerRule(
            id="cs_excel_heavy",
            domain="current_systems",
            trigger_type="keyword",
            trigger_value=r"(?:excel|spreadsheet|google\s+sheets)",
            action=TriggerAction.ASK_FOLLOW_UP,
            follow_up_question="Which business processes are managed in spreadsheets? These are often good candidates for automation.",
            priority=2
        ),
        TriggerRule(
            id="cs_legacy_erp",
            domain="current_systems",
            trigger_type="keyword",
            trigger_value=r"(?:sap|oracle|netsuite|dynamics|navision|sage\s+erp)",
            action=TriggerAction.PROBE_DEEPER,
            follow_up_question="What's driving the decision to move away from your current ERP?",
            priority=1
        ),
        TriggerRule(
            id="cs_integration_mess",
            domain="current_systems",
            trigger_type="keyword",
            trigger_value=r"(?:don'?t\s+talk|not\s+connected|manual\s+sync|copy\s+paste|re-?enter)",
            action=TriggerAction.FLAG_FOR_REVIEW,
            follow_up_question="Which systems most urgently need to be connected? What data flows between them?",
            priority=2,
            description="Integration pain point detected"
        ),
    ]
)


# =============================================================================
# FINANCE & ACCOUNTING TRIGGERS
# =============================================================================
FINANCE_ACCOUNTING_TRIGGERS = DomainTriggers(
    domain="finance_accounting",
    required_info=[
        "invoicing_workflow",
        "payment_workflow",
        "tax_requirements",
        "chart_of_accounts",
        "payment_methods"
    ],
    triggers=[
        TriggerRule(
            id="fa_multi_currency",
            domain="finance_accounting",
            trigger_type="keyword",
            trigger_value=r"(?:multi.?currency|multiple\s+currencies|foreign\s+currency|usd|eur|gbp)",
            action=TriggerAction.ASK_FOLLOW_UP,
            follow_up_question="Do you invoice in different currencies than you pay vendors in? Do you need to track gains/losses on currency exchange?",
            priority=2
        ),
        TriggerRule(
            id="fa_vat_complexity",
            domain="finance_accounting",
            trigger_type="keyword",
            trigger_value=r"(?:vat|gst|sales\s+tax|multiple\s+tax|tax\s+rate)",
            action=TriggerAction.ASK_FOLLOW_UP,
            follow_up_question="Do you have different tax rates for different products or customer types? Do you need automated tax reporting?",
            priority=1
        ),
        TriggerRule(
            id="fa_cost_centers",
            domain="finance_accounting",
            trigger_type="keyword",
            trigger_value=r"(?:cost\s+cent|analytic|department.?wise|project.?wise|track\s+by)",
            action=TriggerAction.ASK_FOLLOW_UP,
            follow_up_question="What dimensions do you track costs by - departments, projects, products, or something else?",
            priority=3
        ),
        TriggerRule(
            id="fa_bank_feeds",
            domain="finance_accounting",
            trigger_type="keyword",
            trigger_value=r"(?:bank\s+feed|bank\s+sync|bank\s+connect|automatic\s+reconcil)",
            action=TriggerAction.ASK_FOLLOW_UP,
            follow_up_question="Which banks do you use? We'll need to check if Odoo has direct integration or if we need a third-party service.",
            priority=4
        ),
        TriggerRule(
            id="fa_subscription_billing",
            domain="finance_accounting",
            trigger_type="keyword",
            trigger_value=r"(?:subscription|recurring|monthly\s+billing|annual\s+contract)",
            action=TriggerAction.ASK_FOLLOW_UP,
            follow_up_question="How many subscription customers do you have? Do you need automated invoicing and renewal management?",
            priority=3
        ),
        # Missing info triggers
        TriggerRule(
            id="fa_missing_coa",
            domain="finance_accounting",
            trigger_type="missing",
            trigger_value="chart_of_accounts",
            action=TriggerAction.ASK_FOLLOW_UP,
            follow_up_question="Can you tell me about your Chart of Accounts structure? Do you follow a specific standard?",
            priority=1
        ),
    ]
)


# =============================================================================
# SALES & CRM TRIGGERS
# =============================================================================
SALES_CRM_TRIGGERS = DomainTriggers(
    domain="sales_crm",
    required_info=["sales_process", "pricing_strategy", "quotation_process"],
    triggers=[
        TriggerRule(
            id="sc_discount_approval",
            domain="sales_crm",
            trigger_type="keyword",
            trigger_value=r"(?:discount|special\s+pricing|negotiate|price\s+adjustment)",
            action=TriggerAction.ASK_FOLLOW_UP,
            follow_up_question="Who can approve discounts? What are the approval thresholds (e.g., manager for >10%, director for >20%)?",
            priority=2
        ),
        TriggerRule(
            id="sc_commission",
            domain="sales_crm",
            trigger_type="keyword",
            trigger_value=r"(?:commission|sales\s+incentive|bonus|target|quota)",
            action=TriggerAction.ASK_FOLLOW_UP,
            follow_up_question="How is commission calculated - flat percentage, tiered, or based on margin?",
            priority=3
        ),
        TriggerRule(
            id="sc_complex_pricing",
            domain="sales_crm",
            trigger_type="keyword",
            trigger_value=r"(?:pricelist|price\s+list|customer\s+specific|volume\s+discount|tier)",
            action=TriggerAction.ASK_FOLLOW_UP,
            follow_up_question="How many pricelists do you need? Are they by customer segment, region, or volume?",
            priority=2
        ),
        TriggerRule(
            id="sc_long_sales_cycle",
            domain="sales_crm",
            trigger_type="keyword",
            trigger_value=r"(?:months?\s+to\s+close|long\s+sales|complex\s+deals|enterprise|rfp|tender)",
            action=TriggerAction.ASK_FOLLOW_UP,
            follow_up_question="What stages does a deal go through? Do multiple people need to be involved in the decision?",
            priority=3
        ),
        TriggerRule(
            id="sc_ecommerce",
            domain="sales_crm",
            trigger_type="keyword",
            trigger_value=r"(?:online\s+store|e-?commerce|website\s+sales|shopify|woocommerce)",
            action=TriggerAction.ASK_FOLLOW_UP,
            follow_up_question="Does your online store need to sync inventory, prices, and orders with your ERP?",
            priority=2
        ),
    ]
)


# =============================================================================
# INVENTORY & OPERATIONS TRIGGERS
# =============================================================================
INVENTORY_OPERATIONS_TRIGGERS = DomainTriggers(
    domain="inventory_operations",
    required_info=["inventory_management", "warehouse_layout", "tracking_method"],
    triggers=[
        TriggerRule(
            id="io_serial_tracking",
            domain="inventory_operations",
            trigger_type="keyword",
            trigger_value=r"(?:serial\s+number|serialized|unique\s+id|imei|asset\s+tag)",
            action=TriggerAction.ASK_FOLLOW_UP,
            follow_up_question="Which product categories need serial number tracking? Is it for warranty, traceability, or asset management?",
            priority=2
        ),
        TriggerRule(
            id="io_lot_tracking",
            domain="inventory_operations",
            trigger_type="keyword",
            trigger_value=r"(?:lot|batch|expir|shelf\s+life|best\s+before|fifo)",
            action=TriggerAction.ASK_FOLLOW_UP,
            follow_up_question="Do you need to track expiration dates? What's the typical shelf life of your products?",
            priority=2
        ),
        TriggerRule(
            id="io_manufacturing",
            domain="inventory_operations",
            trigger_type="keyword",
            trigger_value=r"(?:manufactur|produc(?:e|tion)|assembl|build|make\s+to\s+order|mto)",
            action=TriggerAction.PROBE_DEEPER,
            follow_up_question="Do you need Bill of Materials (BOM) management? Do you have multiple work centers or routing steps?",
            priority=1
        ),
        TriggerRule(
            id="io_no_manufacturing",
            domain="inventory_operations",
            trigger_type="keyword",
            trigger_value=r"(?:don'?t\s+manufactur|not\s+manufactur|only\s+resell|distributor|trading)",
            action=TriggerAction.SKIP_QUESTIONS,
            target_questions=["io_04"],  # Skip BOM question
            priority=1
        ),
        TriggerRule(
            id="io_dropship",
            domain="inventory_operations",
            trigger_type="keyword",
            trigger_value=r"(?:drop\s*ship|direct\s+ship|vendor\s+fulfil)",
            action=TriggerAction.ASK_FOLLOW_UP,
            follow_up_question="What percentage of orders are dropshipped? How do you currently manage vendor communication for these?",
            priority=3
        ),
        TriggerRule(
            id="io_multi_warehouse",
            domain="inventory_operations",
            trigger_type="keyword",
            trigger_value=r"(?:warehouse|location|store|depot|fulfillment\s+center)",
            action=TriggerAction.ASK_FOLLOW_UP,
            follow_up_question="Do you need to transfer stock between locations? Should inventory be visible across all locations?",
            priority=3
        ),
        TriggerRule(
            id="io_barcode",
            domain="inventory_operations",
            trigger_type="keyword",
            trigger_value=r"(?:barcode|scan|rf\s+gun|handheld|mobile\s+device)",
            action=TriggerAction.ASK_FOLLOW_UP,
            follow_up_question="Which operations need barcode scanning - receiving, picking, shipping, or all of them?",
            priority=3
        ),
    ]
)


# =============================================================================
# HR & PAYROLL TRIGGERS
# =============================================================================
HR_PAYROLL_TRIGGERS = DomainTriggers(
    domain="hr_payroll",
    required_info=["hr_processes", "attendance", "payroll"],
    triggers=[
        TriggerRule(
            id="hr_timesheets",
            domain="hr_payroll",
            trigger_type="keyword",
            trigger_value=r"(?:timesheet|time\s+track|hour|billable|project\s+time)",
            action=TriggerAction.ASK_FOLLOW_UP,
            follow_up_question="Do employees bill time to specific projects or customers? Do timesheets need approval?",
            priority=2
        ),
        TriggerRule(
            id="hr_remote_workers",
            domain="hr_payroll",
            trigger_type="keyword",
            trigger_value=r"(?:remote|work\s+from\s+home|field|on.?site|travel)",
            action=TriggerAction.ASK_FOLLOW_UP,
            follow_up_question="How do remote/field workers currently log their time and attendance?",
            priority=3
        ),
        TriggerRule(
            id="hr_no_employees",
            domain="hr_payroll",
            trigger_type="keyword",
            trigger_value=r"(?:just\s+me|solo|one\s+person|no\s+employees|freelancer)",
            action=TriggerAction.SKIP_QUESTIONS,
            target_questions=["hr_02", "hr_03", "hr_04", "hr_05"],
            priority=1
        ),
        TriggerRule(
            id="hr_external_payroll",
            domain="hr_payroll",
            trigger_type="keyword",
            trigger_value=r"(?:payroll\s+provider|adp|gusto|paychex|outsource\s+payroll)",
            action=TriggerAction.ASK_FOLLOW_UP,
            follow_up_question="Do you need Odoo to integrate with your payroll provider, or just manage HR data separately?",
            priority=3
        ),
    ]
)


# =============================================================================
# PROJECT MANAGEMENT TRIGGERS
# =============================================================================
PROJECT_MANAGEMENT_TRIGGERS = DomainTriggers(
    domain="project_management",
    required_info=["project_types", "billing_method"],
    triggers=[
        TriggerRule(
            id="pm_billable_projects",
            domain="project_management",
            trigger_type="keyword",
            trigger_value=r"(?:bill\s+client|charge|invoice\s+project|time\s+and\s+material|t&m)",
            action=TriggerAction.ASK_FOLLOW_UP,
            follow_up_question="Do you bill hourly rates or fixed project prices? Do rates vary by employee level or task type?",
            priority=2
        ),
        TriggerRule(
            id="pm_no_projects",
            domain="project_management",
            trigger_type="keyword",
            trigger_value=r"(?:don'?t\s+have\s+project|not\s+project|no\s+project)",
            action=TriggerAction.SKIP_QUESTIONS,
            target_questions=["pm_02", "pm_03", "pm_04", "pm_05"],
            priority=1
        ),
        TriggerRule(
            id="pm_resource_planning",
            domain="project_management",
            trigger_type="keyword",
            trigger_value=r"(?:resource|capacity|allocat|schedule|availability|planning)",
            action=TriggerAction.ASK_FOLLOW_UP,
            follow_up_question="Do you need to plan resource capacity across projects? How far ahead do you plan?",
            priority=3
        ),
    ]
)


# =============================================================================
# INTEGRATIONS TRIGGERS
# =============================================================================
INTEGRATIONS_TRIGGERS = DomainTriggers(
    domain="integrations",
    required_info=["integration_systems", "data_flows"],
    triggers=[
        TriggerRule(
            id="in_api_custom",
            domain="integrations",
            trigger_type="keyword",
            trigger_value=r"(?:api|webhook|custom\s+integrat|proprietary)",
            action=TriggerAction.FLAG_FOR_REVIEW,
            follow_up_question="What data needs to flow through the API? Do you have API documentation for your system?",
            priority=2,
            description="Custom integration likely needed"
        ),
        TriggerRule(
            id="in_realtime_sync",
            domain="integrations",
            trigger_type="keyword",
            trigger_value=r"(?:real.?time|instant|immediate|live)",
            action=TriggerAction.FLAG_FOR_REVIEW,
            follow_up_question="What specifically needs real-time sync? Could near-real-time (every few minutes) work?",
            priority=2,
            description="Real-time sync requirement - may need technical review"
        ),
        TriggerRule(
            id="in_ecommerce_sync",
            domain="integrations",
            trigger_type="keyword",
            trigger_value=r"(?:shopify|woocommerce|magento|prestashop|amazon|ebay)",
            action=TriggerAction.ASK_FOLLOW_UP,
            follow_up_question="What needs to sync - products, inventory, orders, customers, or all of them?",
            priority=2
        ),
    ]
)


# =============================================================================
# USERS & PERMISSIONS TRIGGERS
# =============================================================================
USERS_PERMISSIONS_TRIGGERS = DomainTriggers(
    domain="users_permissions",
    required_info=["user_count", "user_roles", "approval_workflows"],
    triggers=[
        TriggerRule(
            id="up_strict_security",
            domain="users_permissions",
            trigger_type="keyword",
            trigger_value=r"(?:sensitive|confidential|restrict|only\s+certain|segregat|audit)",
            action=TriggerAction.ASK_FOLLOW_UP,
            follow_up_question="What specific data or actions need to be restricted? Do you need audit trails for compliance?",
            priority=2
        ),
        TriggerRule(
            id="up_approval_complex",
            domain="users_permissions",
            trigger_type="keyword",
            trigger_value=r"(?:multiple\s+approv|chain\s+of\s+approv|hierarchy|escalat)",
            action=TriggerAction.ASK_FOLLOW_UP,
            follow_up_question="Can you describe the approval chain? What triggers escalation to the next level?",
            priority=2
        ),
        TriggerRule(
            id="up_multi_company_access",
            domain="users_permissions",
            trigger_type="keyword",
            trigger_value=r"(?:multi.?company|across\s+companies|all\s+entities|group\s+level)",
            action=TriggerAction.FLAG_FOR_REVIEW,
            follow_up_question="Should some users see data across all companies while others only see their own?",
            priority=1,
            description="Multi-company access control needed"
        ),
    ]
)


# =============================================================================
# DATA MIGRATION TRIGGERS
# =============================================================================
DATA_MIGRATION_TRIGGERS = DomainTriggers(
    domain="data_migration",
    required_info=["migration_scope", "data_format", "historical_requirements"],
    triggers=[
        TriggerRule(
            id="dm_large_volume",
            domain="data_migration",
            trigger_type="keyword",
            trigger_value=r"(?:million|hundreds\s+of\s+thousands|massive|huge\s+amount|years?\s+of\s+data)",
            action=TriggerAction.FLAG_FOR_REVIEW,
            follow_up_question="What's the approximate record count for each data type? This helps us plan the migration approach.",
            priority=1,
            description="Large data volume - may need phased migration"
        ),
        TriggerRule(
            id="dm_dirty_data",
            domain="data_migration",
            trigger_type="keyword",
            trigger_value=r"(?:clean.?up|duplicat|mess|inconsisten|bad\s+data|garbage)",
            action=TriggerAction.ASK_FOLLOW_UP,
            follow_up_question="Should we clean the data during migration or do you want to clean it first in the source system?",
            priority=2
        ),
        TriggerRule(
            id="dm_compliance",
            domain="data_migration",
            trigger_type="keyword",
            trigger_value=r"(?:gdpr|legal|regulat|compliance|audit|retain)",
            action=TriggerAction.FLAG_FOR_REVIEW,
            follow_up_question="What's the legally required data retention period? Do you need data anonymization for old records?",
            priority=1,
            description="Compliance considerations for data migration"
        ),
    ]
)


# =============================================================================
# ALL DOMAIN TRIGGERS
# =============================================================================
ALL_DOMAIN_TRIGGERS: Dict[str, DomainTriggers] = {
    "company_basics": COMPANY_BASICS_TRIGGERS,
    "current_systems": CURRENT_SYSTEMS_TRIGGERS,
    "finance_accounting": FINANCE_ACCOUNTING_TRIGGERS,
    "sales_crm": SALES_CRM_TRIGGERS,
    "inventory_operations": INVENTORY_OPERATIONS_TRIGGERS,
    "hr_payroll": HR_PAYROLL_TRIGGERS,
    "project_management": PROJECT_MANAGEMENT_TRIGGERS,
    "integrations": INTEGRATIONS_TRIGGERS,
    "users_permissions": USERS_PERMISSIONS_TRIGGERS,
    "data_migration": DATA_MIGRATION_TRIGGERS,
}


def load_domain_triggers(domain: str) -> Optional[DomainTriggers]:
    """Load triggers for a specific domain."""
    return ALL_DOMAIN_TRIGGERS.get(domain)


def get_all_triggers() -> Dict[str, DomainTriggers]:
    """Get all domain triggers."""
    return ALL_DOMAIN_TRIGGERS
