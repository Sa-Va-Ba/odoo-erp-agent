"""
Interview Domain Definitions for Odoo ERP Implementation

Defines the 10 core interview domains, each with:
- Domain context and Odoo capabilities
- Core questions to ask
- Follow-up questions based on responses
- Requirements to extract
"""

from dataclasses import dataclass, field
from typing import Callable
from enum import Enum


class InterviewDomain(str, Enum):
    COMPANY_BASICS = "company_basics"
    CURRENT_SYSTEMS = "current_systems"
    FINANCE_ACCOUNTING = "finance_accounting"
    SALES_CRM = "sales_crm"
    INVENTORY_OPERATIONS = "inventory_operations"
    HR_PAYROLL = "hr_payroll"
    PROJECT_MANAGEMENT = "project_management"
    INTEGRATIONS = "integrations"
    USERS_PERMISSIONS = "users_permissions"
    DATA_MIGRATION = "data_migration"


@dataclass
class Question:
    """A single interview question."""
    id: str
    text: str
    context: str = ""  # Why we're asking this
    follow_ups: list[str] = field(default_factory=list)  # Conditional follow-ups
    required: bool = True
    extracts: list[str] = field(default_factory=list)  # What requirements this extracts


@dataclass
class DomainDefinition:
    """Complete definition of an interview domain."""
    domain: InterviewDomain
    title: str
    description: str
    odoo_context: str  # What Odoo can do in this area
    questions: list[Question]
    completion_criteria: list[str]  # What we need to know before moving on


# =============================================================================
# DOMAIN 1: COMPANY BASICS
# =============================================================================
COMPANY_BASICS = DomainDefinition(
    domain=InterviewDomain.COMPANY_BASICS,
    title="Company Overview",
    description="Understanding the company structure, size, and basic operations",
    odoo_context="""Odoo supports multi-company setups, multiple locations/warehouses,
    multi-currency operations, and can be configured for various industries including
    manufacturing, retail, services, distribution, and more.""",
    questions=[
        Question(
            id="cb_01",
            text="Can you tell me about your company? What industry are you in and what are your main products or services?",
            context="Understanding the core business helps determine which Odoo apps are most relevant",
            extracts=["industry", "business_type", "products_services"]
        ),
        Question(
            id="cb_02",
            text="How many employees does your company have?",
            context="Employee count affects HR module needs and user licensing",
            follow_ups=[
                "Are employees spread across different departments?",
                "Do you have remote workers or field staff?"
            ],
            extracts=["employee_count", "department_structure"]
        ),
        Question(
            id="cb_03",
            text="How many office locations or warehouses do you operate?",
            context="Multi-location setups require specific inventory and accounting configurations",
            follow_ups=[
                "Are these in different countries?",
                "Do you need to track inventory separately per location?"
            ],
            extracts=["locations", "multi_warehouse"]
        ),
        Question(
            id="cb_04",
            text="What currencies do you work with?",
            context="Multi-currency requires specific accounting setup",
            follow_ups=["Do you need to invoice in multiple currencies?"],
            extracts=["currencies", "multi_currency"]
        ),
        Question(
            id="cb_05",
            text="When does your fiscal year end?",
            context="Important for accounting period configuration",
            extracts=["fiscal_year"]
        ),
        Question(
            id="cb_06",
            text="What is your approximate annual revenue range?",
            context="Helps gauge complexity and scalability needs",
            required=False,
            extracts=["revenue_range"]
        ),
    ],
    completion_criteria=[
        "Industry and business type identified",
        "Company size understood",
        "Location structure known",
        "Currency requirements clear"
    ]
)


# =============================================================================
# DOMAIN 2: CURRENT SYSTEMS
# =============================================================================
CURRENT_SYSTEMS = DomainDefinition(
    domain=InterviewDomain.CURRENT_SYSTEMS,
    title="Current Systems & Pain Points",
    description="Understanding existing tools, processes, and what's not working",
    odoo_context="""Odoo can replace or integrate with most business software including
    accounting systems (QuickBooks, Sage, Xero), CRMs (Salesforce, HubSpot),
    spreadsheet-based processes, and legacy ERP systems.""",
    questions=[
        Question(
            id="cs_01",
            text="What software systems are you currently using to run your business?",
            context="Understanding current tech stack for migration and integration planning",
            follow_ups=[
                "How long have you been using these systems?",
                "Are there any you're particularly happy or unhappy with?"
            ],
            extracts=["current_systems", "system_satisfaction"]
        ),
        Question(
            id="cs_02",
            text="What are your biggest pain points with your current setup?",
            context="Pain points drive requirements and help prioritize features",
            follow_ups=[
                "Can you give me a specific example of when this caused problems?",
                "How often does this issue occur?"
            ],
            extracts=["pain_points", "problem_frequency"]
        ),
        Question(
            id="cs_03",
            text="Are you currently using spreadsheets for any core business processes?",
            context="Spreadsheet processes are often candidates for automation in Odoo",
            follow_ups=[
                "What processes are managed in spreadsheets?",
                "How many people access these spreadsheets?"
            ],
            extracts=["spreadsheet_processes", "automation_candidates"]
        ),
        Question(
            id="cs_04",
            text="Do you have any manual processes that you'd like to automate?",
            context="Identifying automation opportunities",
            extracts=["manual_processes", "automation_needs"]
        ),
        Question(
            id="cs_05",
            text="What does your ideal future state look like? What would success mean for this implementation?",
            context="Understanding the vision helps align solution design",
            extracts=["success_criteria", "vision"]
        ),
    ],
    completion_criteria=[
        "Current systems documented",
        "Pain points identified",
        "Success criteria defined"
    ]
)


# =============================================================================
# DOMAIN 3: FINANCE & ACCOUNTING
# =============================================================================
FINANCE_ACCOUNTING = DomainDefinition(
    domain=InterviewDomain.FINANCE_ACCOUNTING,
    title="Finance & Accounting",
    description="Chart of accounts, invoicing, payments, reporting requirements",
    odoo_context="""Odoo Accounting provides: Full double-entry bookkeeping,
    configurable Chart of Accounts, bank synchronization, automated reconciliation,
    multi-currency support, tax management (VAT, GST, etc.), financial reporting,
    budgeting, asset management, and localization packages for country-specific compliance.""",
    questions=[
        Question(
            id="fa_01",
            text="Can you walk me through your current accounting workflow from invoice to payment?",
            context="Understanding the complete financial flow",
            extracts=["invoicing_workflow", "payment_workflow"]
        ),
        Question(
            id="fa_02",
            text="What accounting standards or regulations do you need to comply with?",
            context="Determines localization modules needed",
            follow_ups=[
                "Do you need specific tax reporting formats?",
                "Are there industry-specific compliance requirements?"
            ],
            extracts=["accounting_standards", "tax_requirements", "compliance"]
        ),
        Question(
            id="fa_03",
            text="How do you currently manage your Chart of Accounts? Can you describe the structure?",
            context="COA migration is critical for accounting setup",
            follow_ups=[
                "Do you have cost centers or analytic accounts?",
                "Do you track by department or project?"
            ],
            extracts=["chart_of_accounts", "cost_centers", "analytic_accounting"]
        ),
        Question(
            id="fa_04",
            text="What payment methods do you accept from customers and use for vendors?",
            context="Payment configuration requirements",
            follow_ups=[
                "Do you use any payment gateways?",
                "Do you need automated payment reminders?"
            ],
            extracts=["payment_methods", "payment_gateways"]
        ),
        Question(
            id="fa_05",
            text="What financial reports do you need to generate regularly?",
            context="Reporting requirements for configuration",
            follow_ups=[
                "Who needs access to these reports?",
                "How often are they generated?"
            ],
            extracts=["financial_reports", "reporting_frequency"]
        ),
        Question(
            id="fa_06",
            text="Do you have any recurring billing or subscription-based revenue?",
            context="Subscription management module may be needed",
            extracts=["recurring_billing", "subscriptions"]
        ),
        Question(
            id="fa_07",
            text="Do you manage fixed assets that need depreciation tracking?",
            context="Asset management module consideration",
            extracts=["fixed_assets", "depreciation"]
        ),
        # NEW: Odoo-specific configuration questions
        Question(
            id="fa_08",
            text="What is your country of primary operation? This determines the localization package and default chart of accounts.",
            context="Odoo localization module selection - affects tax, COA, and legal reporting",
            follow_ups=[
                "Do you operate in multiple countries that need separate accounting?"
            ],
            extracts=["primary_country", "localization_package", "multi_country_accounting"]
        ),
        Question(
            id="fa_09",
            text="What are your standard payment terms? For example: Due on Receipt, Net 15, Net 30, 2% 10 Net 30?",
            context="Payment terms configuration in Odoo",
            follow_ups=[
                "Do different customer types have different payment terms?",
                "Do you offer early payment discounts?"
            ],
            extracts=["payment_terms", "early_payment_discount", "customer_payment_terms"]
        ),
        Question(
            id="fa_10",
            text="Do you need to track expenses by project, department, or cost center using analytic accounting?",
            context="Analytic accounting configuration in Odoo",
            follow_ups=[
                "Should analytic accounts be mandatory on certain transactions?",
                "Do you need multiple analytic dimensions (e.g., both project AND department)?"
            ],
            extracts=["analytic_accounting", "analytic_mandatory", "analytic_dimensions"]
        ),
        Question(
            id="fa_11",
            text="How do you handle bank reconciliation today? Do you import bank statements automatically or manually?",
            context="Bank synchronization and reconciliation setup",
            follow_ups=[
                "Which banks do you use?",
                "Do you need automatic matching of payments to invoices?"
            ],
            extracts=["bank_reconciliation", "bank_sync", "auto_matching"]
        ),
        Question(
            id="fa_12",
            text="Do you need budgeting capabilities? If so, at what level - by account, department, project, or all of these?",
            context="Budget management configuration",
            extracts=["budgeting", "budget_levels", "budget_tracking"]
        ),
    ],
    completion_criteria=[
        "Accounting workflow understood",
        "Compliance requirements identified",
        "COA structure documented",
        "Payment methods known",
        "Reporting needs defined",
        "Localization determined",
        "Payment terms specified"
    ]
)


# =============================================================================
# DOMAIN 4: SALES & CRM
# =============================================================================
SALES_CRM = DomainDefinition(
    domain=InterviewDomain.SALES_CRM,
    title="Sales & CRM",
    description="Sales pipeline, customer management, quotations, and orders",
    odoo_context="""Odoo Sales & CRM offers: Lead/opportunity management, sales pipeline,
    quotation templates, sales orders, pricing rules (pricelists), discounts,
    commission tracking, customer portal, e-signature, and integration with
    Accounting and Inventory for seamless order-to-cash flow.""",
    questions=[
        Question(
            id="sc_01",
            text="Can you describe your sales process from lead to closed deal?",
            context="Understanding the complete sales workflow",
            extracts=["sales_process", "pipeline_stages"]
        ),
        Question(
            id="sc_02",
            text="How do you currently track leads and opportunities?",
            context="CRM configuration requirements",
            follow_ups=[
                "What information do you capture for each lead?",
                "How do you qualify leads?"
            ],
            extracts=["lead_tracking", "lead_qualification"]
        ),
        Question(
            id="sc_03",
            text="Do you use different pricing for different customers or regions?",
            context="Pricelist configuration needs",
            follow_ups=[
                "Do you offer volume discounts?",
                "Do you have special pricing agreements with certain customers?"
            ],
            extracts=["pricing_strategy", "pricelists", "discounts"]
        ),
        Question(
            id="sc_04",
            text="What does your quotation process look like?",
            context="Quote template and approval workflow setup",
            follow_ups=[
                "Do you need approval workflows for discounts or large orders?",
                "Do you use e-signatures?"
            ],
            extracts=["quotation_process", "approval_workflows"]
        ),
        Question(
            id="sc_05",
            text="Do you have a sales team structure? How are territories or accounts assigned?",
            context="Sales team configuration",
            follow_ups=[
                "Do you track sales commissions?",
                "Do salespeople have targets or quotas?"
            ],
            extracts=["sales_teams", "territories", "commissions"]
        ),
        Question(
            id="sc_06",
            text="Do you sell online or need a customer portal?",
            context="E-commerce and portal module consideration",
            extracts=["ecommerce", "customer_portal"]
        ),
        # NEW: Odoo-specific configuration questions
        Question(
            id="sc_07",
            text="What are the specific stages a sale goes through? For example: New, Qualified, Proposal, Negotiation, Won/Lost?",
            context="Configures CRM pipeline stages exactly as client needs them",
            follow_ups=[
                "Should certain stages require manager approval to move forward?",
                "Are there mandatory fields that must be filled at each stage?"
            ],
            extracts=["crm_stages", "stage_requirements", "mandatory_fields"]
        ),
        Question(
            id="sc_08",
            text="Do you need to track different types of products with different sales flows? For example: services vs physical products vs subscriptions?",
            context="Determines product type configuration and invoicing policies",
            follow_ups=[
                "For services, do you invoice upfront, on delivery, or based on timesheets?",
                "Do you need recurring invoicing for any products?"
            ],
            extracts=["product_types", "invoicing_policy", "subscription_products"]
        ),
        Question(
            id="sc_09",
            text="What taxes need to be applied to your sales? Do rates vary by product type, customer location, or both?",
            context="Tax configuration in Odoo - critical for compliance",
            follow_ups=[
                "Do you sell to customers in multiple tax jurisdictions?",
                "Do you have any tax-exempt products or customers?"
            ],
            extracts=["sales_taxes", "tax_jurisdictions", "tax_exemptions"]
        ),
        Question(
            id="sc_10",
            text="Do you need to track the source of your leads? For example: website, referral, trade show, cold call?",
            context="UTM source tracking and marketing attribution in Odoo",
            extracts=["lead_sources", "marketing_attribution"]
        ),
    ],
    completion_criteria=[
        "Sales process documented",
        "CRM needs identified",
        "Pricing strategy understood",
        "Team structure known",
        "Pipeline stages defined",
        "Tax requirements clear"
    ]
)


# =============================================================================
# DOMAIN 5: INVENTORY & OPERATIONS
# =============================================================================
INVENTORY_OPERATIONS = DomainDefinition(
    domain=InterviewDomain.INVENTORY_OPERATIONS,
    title="Inventory & Operations",
    description="Warehousing, manufacturing, purchasing, and logistics",
    odoo_context="""Odoo Inventory & Manufacturing provides: Multi-warehouse management,
    barcode scanning, serial/lot tracking, reordering rules, routes (dropship, MTO, MTS),
    quality control, Bill of Materials (BOM), work centers, manufacturing orders,
    maintenance scheduling, and PLM (Product Lifecycle Management).""",
    questions=[
        Question(
            id="io_01",
            text="How do you manage your inventory currently?",
            context="Understanding current inventory processes",
            follow_ups=[
                "Do you track by serial numbers or lot numbers?",
                "Do you have expiration date tracking needs?"
            ],
            extracts=["inventory_management", "tracking_method"]
        ),
        Question(
            id="io_02",
            text="Can you describe your warehouse layout and operations?",
            context="Warehouse configuration needs",
            follow_ups=[
                "Do you use bin locations?",
                "Do you need barcode scanning?"
            ],
            extracts=["warehouse_layout", "locations", "barcode_needs"]
        ),
        Question(
            id="io_03",
            text="What is your purchasing process like?",
            context="Purchase module configuration",
            follow_ups=[
                "Do you need approval workflows for purchases?",
                "Do you use vendor pricelists or agreements?"
            ],
            extracts=["purchase_process", "vendor_management"]
        ),
        Question(
            id="io_04",
            text="Do you manufacture or assemble products?",
            context="Manufacturing module needs",
            follow_ups=[
                "Do you need Bill of Materials management?",
                "Do you track work center capacity?",
                "Do you need work order routing?"
            ],
            extracts=["manufacturing", "bom", "work_centers"]
        ),
        Question(
            id="io_05",
            text="How do you handle shipping and logistics?",
            context="Delivery and shipping configuration",
            follow_ups=[
                "Which carriers do you use?",
                "Do you need automated shipping label generation?"
            ],
            extracts=["shipping", "carriers", "logistics"]
        ),
        Question(
            id="io_06",
            text="Do you need quality control checkpoints?",
            context="Quality module consideration",
            extracts=["quality_control", "inspections"]
        ),
        Question(
            id="io_07",
            text="How do you handle returns and repairs?",
            context="RMA and repair module needs",
            extracts=["returns", "repairs", "rma"]
        ),
        # NEW: Odoo-specific configuration questions
        Question(
            id="io_08",
            text="What product routes do you need? For example: Make to Stock (keep inventory), Make to Order (produce on demand), Dropship (ship directly from vendor)?",
            context="Configures Odoo inventory routes - critical for operations",
            follow_ups=[
                "Do different product categories need different routes?",
                "Do you need to automatically replenish stock when it falls below a threshold?"
            ],
            extracts=["product_routes", "mts_mto", "dropship", "reorder_rules"]
        ),
        Question(
            id="io_09",
            text="How do you want to value your inventory? FIFO (First In First Out), Average Cost, or Standard Cost?",
            context="Inventory valuation method in Odoo - affects accounting",
            follow_ups=[
                "Do you need to track landed costs (shipping, customs, etc.) in product cost?"
            ],
            extracts=["inventory_valuation", "costing_method", "landed_costs"]
        ),
        Question(
            id="io_10",
            text="Do you need to track products across multiple units of measure? For example: buy in cases, sell in units, stock in pallets?",
            context="Unit of Measure configuration in Odoo",
            extracts=["units_of_measure", "uom_conversion"]
        ),
        Question(
            id="io_11",
            text="What warehouse operations do you perform? Receiving, picking, packing, shipping - do these need to be separate steps or combined?",
            context="Warehouse operation types configuration",
            follow_ups=[
                "Do you use wave picking or batch picking?",
                "Do you have specific packing requirements?"
            ],
            extracts=["warehouse_operations", "picking_strategy", "packing_requirements"]
        ),
        Question(
            id="io_12",
            text="For manufacturing: do you have multi-level bills of materials where sub-assemblies are used in final products?",
            context="BOM structure configuration",
            follow_ups=[
                "Do you need to track by-products or scrap?",
                "Do production steps require specific work instructions?"
            ],
            extracts=["bom_levels", "subassemblies", "byproducts", "work_instructions"]
        ),
    ],
    completion_criteria=[
        "Inventory management approach understood",
        "Warehouse structure documented",
        "Manufacturing needs identified",
        "Logistics requirements clear",
        "Product routes defined",
        "Costing method determined"
    ]
)


# =============================================================================
# DOMAIN 6: HR & PAYROLL
# =============================================================================
HR_PAYROLL = DomainDefinition(
    domain=InterviewDomain.HR_PAYROLL,
    title="HR & Payroll",
    description="Employee management, attendance, leave, recruitment, payroll",
    odoo_context="""Odoo HR suite includes: Employee database, org charts,
    recruitment (applicant tracking), attendance tracking, leave management,
    expense management, appraisals, fleet management, and country-specific
    payroll modules (though payroll often needs localization).""",
    questions=[
        Question(
            id="hr_01",
            text="How do you currently manage employee information and HR processes?",
            context="Understanding current HR setup",
            extracts=["hr_processes", "employee_management"]
        ),
        Question(
            id="hr_02",
            text="Do you need to track employee attendance and time?",
            context="Attendance module consideration",
            follow_ups=[
                "Do employees clock in/out?",
                "Do you need timesheet tracking for projects?"
            ],
            extracts=["attendance", "timesheets"]
        ),
        Question(
            id="hr_03",
            text="How do you manage leave requests and approvals?",
            context="Leave management configuration",
            follow_ups=[
                "What types of leave do you offer?",
                "What is your approval workflow?"
            ],
            extracts=["leave_management", "leave_types"]
        ),
        Question(
            id="hr_04",
            text="Do you handle recruitment internally?",
            context="Recruitment module needs",
            follow_ups=[
                "Do you need to post to job boards?",
                "Do you need applicant tracking?"
            ],
            extracts=["recruitment", "applicant_tracking"]
        ),
        Question(
            id="hr_05",
            text="How do you currently process payroll?",
            context="Payroll requirements - often country-specific",
            follow_ups=[
                "What payroll provider do you use?",
                "Do you need integration with your payroll system?"
            ],
            extracts=["payroll", "payroll_provider"]
        ),
        Question(
            id="hr_06",
            text="Do you need to track employee expenses?",
            context="Expense management module",
            extracts=["expenses", "expense_approval"]
        ),
    ],
    completion_criteria=[
        "HR processes understood",
        "Attendance/timesheet needs identified",
        "Leave management requirements clear",
        "Payroll approach determined"
    ]
)


# =============================================================================
# DOMAIN 7: PROJECT MANAGEMENT
# =============================================================================
PROJECT_MANAGEMENT = DomainDefinition(
    domain=InterviewDomain.PROJECT_MANAGEMENT,
    title="Project Management",
    description="Project tracking, timesheets, billing, resource allocation",
    odoo_context="""Odoo Project provides: Kanban/Gantt views, task management,
    subtasks, milestones, timesheet integration, project billing (fixed price,
    time & materials), profitability analysis, and customer portal access.""",
    questions=[
        Question(
            id="pm_01",
            text="Do you manage projects as part of your business?",
            context="Determining if project module is needed",
            follow_ups=[
                "What types of projects?",
                "Internal or client-facing?"
            ],
            extracts=["project_types", "project_scope"]
        ),
        Question(
            id="pm_02",
            text="How do you currently track project progress and tasks?",
            context="Project management workflow",
            extracts=["project_tracking", "task_management"]
        ),
        Question(
            id="pm_03",
            text="Do you bill clients for project work?",
            context="Project billing configuration",
            follow_ups=[
                "Is it time & materials or fixed price?",
                "Do you need to track profitability?"
            ],
            extracts=["project_billing", "billing_method"]
        ),
        Question(
            id="pm_04",
            text="Do team members log time against projects?",
            context="Timesheet integration needs",
            extracts=["timesheets", "time_tracking"]
        ),
        Question(
            id="pm_05",
            text="Do clients need visibility into project status?",
            context="Customer portal for projects",
            extracts=["client_portal", "project_visibility"]
        ),
    ],
    completion_criteria=[
        "Project management needs identified",
        "Billing approach understood",
        "Time tracking requirements clear"
    ]
)


# =============================================================================
# DOMAIN 8: INTEGRATIONS
# =============================================================================
INTEGRATIONS = DomainDefinition(
    domain=InterviewDomain.INTEGRATIONS,
    title="Integrations",
    description="External systems, e-commerce, banking, APIs",
    odoo_context="""Odoo supports integrations via: REST/JSON-RPC API,
    built-in connectors (shipping carriers, payment gateways, banks),
    e-commerce platforms (Shopify, WooCommerce, Amazon),
    and community modules for various third-party systems.""",
    questions=[
        Question(
            id="in_01",
            text="What external systems will need to integrate with Odoo?",
            context="Mapping integration landscape",
            follow_ups=[
                "What data needs to flow between systems?",
                "In which direction (in/out/both)?"
            ],
            extracts=["integration_systems", "data_flows"]
        ),
        Question(
            id="in_02",
            text="Do you have an e-commerce website that needs to sync with inventory and orders?",
            context="E-commerce integration needs",
            follow_ups=[
                "What platform (Shopify, WooCommerce, Magento, etc.)?",
                "What needs to sync (products, orders, inventory, customers)?"
            ],
            extracts=["ecommerce_platform", "ecommerce_sync"]
        ),
        Question(
            id="in_03",
            text="Do you need bank feeds or payment gateway integrations?",
            context="Financial integrations",
            follow_ups=[
                "Which banks do you use?",
                "Which payment providers (Stripe, PayPal, etc.)?"
            ],
            extracts=["bank_integration", "payment_gateways"]
        ),
        Question(
            id="in_04",
            text="Do you use any third-party logistics or shipping providers?",
            context="Shipping carrier integrations",
            extracts=["shipping_integrations", "carriers"]
        ),
        Question(
            id="in_05",
            text="Are there any other APIs or systems you need to connect?",
            context="Catch-all for additional integrations",
            extracts=["other_integrations", "api_needs"]
        ),
    ],
    completion_criteria=[
        "All integration points identified",
        "Data flow requirements documented",
        "Priority integrations ranked"
    ]
)


# =============================================================================
# DOMAIN 9: USERS & PERMISSIONS
# =============================================================================
USERS_PERMISSIONS = DomainDefinition(
    domain=InterviewDomain.USERS_PERMISSIONS,
    title="Users & Permissions",
    description="User roles, access levels, approval workflows",
    odoo_context="""Odoo provides: Role-based access control (groups),
    record rules for data-level security, multi-company access control,
    approval workflows (studio or custom), and audit logging.""",
    questions=[
        Question(
            id="up_01",
            text="How many users will need access to the system?",
            context="User count for licensing and setup",
            extracts=["user_count"]
        ),
        Question(
            id="up_02",
            text="What different roles or job functions need system access?",
            context="Role definition for access groups",
            follow_ups=[
                "What should each role be able to see and do?",
                "Are there any sensitive areas that need restricted access?"
            ],
            extracts=["user_roles", "access_requirements"]
        ),
        Question(
            id="up_03",
            text="What approval workflows do you need?",
            context="Workflow configuration requirements",
            follow_ups=[
                "Purchase order approvals?",
                "Sales discount approvals?",
                "Expense approvals?",
                "What are the approval thresholds?"
            ],
            extracts=["approval_workflows", "approval_thresholds"]
        ),
        Question(
            id="up_04",
            text="Do you need to restrict data visibility by department, region, or company?",
            context="Record rule configuration",
            extracts=["data_restrictions", "multi_company_access"]
        ),
        Question(
            id="up_05",
            text="Do you need audit trails for compliance purposes?",
            context="Audit logging requirements",
            extracts=["audit_requirements", "compliance_logging"]
        ),
    ],
    completion_criteria=[
        "User count determined",
        "Roles defined",
        "Approval workflows documented",
        "Security requirements clear"
    ]
)


# =============================================================================
# DOMAIN 10: DATA MIGRATION
# =============================================================================
DATA_MIGRATION = DomainDefinition(
    domain=InterviewDomain.DATA_MIGRATION,
    title="Data Migration",
    description="Legacy data, migration scope, historical records",
    odoo_context="""Odoo supports data import via: CSV import (built-in),
    Python scripts using ORM, XML-RPC/JSON-RPC API imports.
    Common migrations include: customers, products, chart of accounts,
    open invoices/bills, inventory balances, and historical transactions.""",
    questions=[
        Question(
            id="dm_01",
            text="What data do you need to migrate from your existing systems?",
            context="Defining migration scope",
            follow_ups=[
                "Customers/contacts?",
                "Products?",
                "Open transactions?",
                "Historical data?"
            ],
            extracts=["migration_scope", "data_types"]
        ),
        Question(
            id="dm_02",
            text="How many years of historical data do you need to migrate?",
            context="Historical data requirements",
            follow_ups=[
                "Is it required for compliance/legal reasons?",
                "Or is recent data sufficient?"
            ],
            extracts=["historical_years", "historical_requirements"]
        ),
        Question(
            id="dm_03",
            text="In what format is your current data stored?",
            context="Understanding source data format",
            follow_ups=[
                "Can you export to CSV or Excel?",
                "Is there API access to your current system?"
            ],
            extracts=["data_format", "export_capability"]
        ),
        Question(
            id="dm_04",
            text="Is there any data cleanup needed before migration?",
            context="Data quality assessment",
            follow_ups=[
                "Duplicate records?",
                "Incomplete records?",
                "Outdated information?"
            ],
            extracts=["data_cleanup", "data_quality"]
        ),
        Question(
            id="dm_05",
            text="What is your timeline expectation for the migration and go-live?",
            context="Timeline planning",
            extracts=["timeline", "go_live_target"]
        ),
    ],
    completion_criteria=[
        "Migration scope defined",
        "Data sources identified",
        "Historical requirements documented",
        "Timeline expectations set"
    ]
)


# =============================================================================
# ALL DOMAINS IN ORDER
# =============================================================================
ALL_DOMAINS = [
    COMPANY_BASICS,
    CURRENT_SYSTEMS,
    FINANCE_ACCOUNTING,
    SALES_CRM,
    INVENTORY_OPERATIONS,
    HR_PAYROLL,
    PROJECT_MANAGEMENT,
    INTEGRATIONS,
    USERS_PERMISSIONS,
    DATA_MIGRATION,
]

DOMAIN_MAP = {d.domain: d for d in ALL_DOMAINS}


def get_domain(domain: InterviewDomain) -> DomainDefinition:
    """Get domain definition by enum."""
    return DOMAIN_MAP[domain]


def get_domain_by_index(index: int) -> DomainDefinition:
    """Get domain definition by index (0-9)."""
    return ALL_DOMAINS[index]


def get_total_domains() -> int:
    """Get total number of interview domains."""
    return len(ALL_DOMAINS)
