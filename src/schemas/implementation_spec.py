"""
Implementation Specification Schema

This defines the structured output from the interview that builder agents
need to set up an Odoo environment. It's the contract between:
- Interview Agent (produces this)
- Builder Agents (consume this)
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any
import json


class ModuleCategory(Enum):
    """Odoo module categories."""
    SALES = "sales"
    CRM = "crm"
    INVENTORY = "inventory"
    PURCHASE = "purchase"
    ACCOUNTING = "accounting"
    MANUFACTURING = "manufacturing"
    HR = "hr"
    PROJECT = "project"
    WEBSITE = "website"
    ECOMMERCE = "ecommerce"
    HELPDESK = "helpdesk"


class ConfigPriority(Enum):
    """Configuration priority levels."""
    CRITICAL = "critical"  # Must be done for system to work
    HIGH = "high"          # Important for business operations
    MEDIUM = "medium"      # Nice to have
    LOW = "low"            # Optional enhancements


@dataclass
class ModuleConfig:
    """Configuration for a specific Odoo module."""
    module_name: str  # Technical name (e.g., 'sale_management')
    display_name: str  # Human name (e.g., 'Sales')
    install: bool = True
    priority: ConfigPriority = ConfigPriority.MEDIUM

    # Configuration parameters for this module
    settings: dict[str, Any] = field(default_factory=dict)

    # Dependencies that must be installed first
    depends_on: list[str] = field(default_factory=list)

    # Estimated setup time in minutes
    estimated_minutes: int = 5

    # Notes from interview about why this is needed
    notes: str = ""


@dataclass
class CompanySetup:
    """Company-level configuration."""
    name: str
    industry: str

    # Address info
    country: str = "US"
    currency: str = "USD"

    # Fiscal settings
    fiscal_year_start_month: int = 1  # January

    # Company logo (base64 or URL)
    logo: Optional[str] = None

    # Tax configuration
    tax_regime: str = "standard"  # standard, simplified, none

    # Timezone
    timezone: str = "UTC"


@dataclass
class UserRole:
    """User role definition."""
    name: str
    description: str
    groups: list[str]  # Odoo group XML IDs
    count: int = 1  # How many users with this role


@dataclass
class DataImport:
    """Data to import after setup."""
    entity_type: str  # 'products', 'customers', 'vendors', etc.
    source: str  # 'csv', 'manual', 'api'
    estimated_records: int = 0
    priority: ConfigPriority = ConfigPriority.MEDIUM
    notes: str = ""


@dataclass
class IntegrationRequirement:
    """External system integration requirement."""
    system_name: str
    integration_type: str  # 'api', 'file', 'manual'
    direction: str  # 'import', 'export', 'bidirectional'
    priority: ConfigPriority = ConfigPriority.LOW
    notes: str = ""


@dataclass
class ImplementationSpec:
    """
    Complete implementation specification.

    This is the structured output from the interview that tells
    builder agents exactly what to set up.
    """
    # Metadata
    spec_id: str
    created_at: str
    interview_session_id: str

    # Company setup
    company: CompanySetup

    # Modules to install and configure
    modules: list[ModuleConfig] = field(default_factory=list)

    # User roles to create
    user_roles: list[UserRole] = field(default_factory=list)

    # Data to import
    data_imports: list[DataImport] = field(default_factory=list)

    # External integrations
    integrations: list[IntegrationRequirement] = field(default_factory=list)

    # Interview insights (pain points, special requirements)
    pain_points: list[str] = field(default_factory=list)
    special_requirements: list[str] = field(default_factory=list)

    # Raw interview data for reference
    interview_summary: dict = field(default_factory=dict)

    def get_install_order(self) -> list[ModuleConfig]:
        """Get modules in correct installation order (respecting dependencies)."""
        installed = set()
        ordered = []
        remaining = list(self.modules)

        # Keep iterating until all modules are ordered
        max_iterations = len(remaining) * 2
        iteration = 0

        while remaining and iteration < max_iterations:
            iteration += 1
            for module in remaining[:]:
                # Check if all dependencies are installed
                deps_met = all(dep in installed for dep in module.depends_on)
                if deps_met:
                    ordered.append(module)
                    installed.add(module.module_name)
                    remaining.remove(module)

        # Add any remaining (circular deps or missing deps)
        ordered.extend(remaining)
        return ordered

    def get_total_estimated_time(self) -> int:
        """Get total estimated setup time in minutes."""
        base_time = 10  # Docker setup
        module_time = sum(m.estimated_minutes for m in self.modules)
        return base_time + module_time

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "spec_id": self.spec_id,
            "created_at": self.created_at,
            "interview_session_id": self.interview_session_id,
            "company": {
                "name": self.company.name,
                "industry": self.company.industry,
                "country": self.company.country,
                "currency": self.company.currency,
                "timezone": self.company.timezone,
                "fiscal_year_start_month": self.company.fiscal_year_start_month,
                "tax_regime": self.company.tax_regime,
            },
            "modules": [
                {
                    "module_name": m.module_name,
                    "display_name": m.display_name,
                    "install": m.install,
                    "priority": m.priority.value,
                    "settings": m.settings,
                    "depends_on": m.depends_on,
                    "estimated_minutes": m.estimated_minutes,
                    "notes": m.notes,
                }
                for m in self.modules
            ],
            "user_roles": [
                {
                    "name": r.name,
                    "description": r.description,
                    "groups": r.groups,
                    "count": r.count,
                }
                for r in self.user_roles
            ],
            "data_imports": [
                {
                    "entity_type": d.entity_type,
                    "source": d.source,
                    "estimated_records": d.estimated_records,
                    "priority": d.priority.value,
                    "notes": d.notes,
                }
                for d in self.data_imports
            ],
            "integrations": [
                {
                    "system_name": i.system_name,
                    "integration_type": i.integration_type,
                    "direction": i.direction,
                    "priority": i.priority.value,
                    "notes": i.notes,
                }
                for i in self.integrations
            ],
            "pain_points": self.pain_points,
            "special_requirements": self.special_requirements,
            "estimated_setup_minutes": self.get_total_estimated_time(),
            "interview_summary": self.interview_summary,
        }

    def to_markdown(self) -> str:
        """Render a full developer-ready PRD document in Markdown."""
        lines = []
        completeness = self.interview_summary.get("_completeness_score", 0)
        warnings = self.interview_summary.get("_warnings", [])

        # --- Executive Summary ---
        lines.append(f"# Odoo Implementation PRD — {self.company.name}")
        lines.append("")
        lines.append("## Executive Summary")
        lines.append("")
        lines.append(f"- **Company:** {self.company.name}")
        lines.append(f"- **Industry:** {self.company.industry}")
        lines.append(f"- **Modules:** {len(self.modules)}")
        lines.append(f"- **Estimated Setup Time:** {self.get_total_estimated_time()} minutes")
        lines.append(f"- **Completeness Score:** {int(completeness * 100)}%")
        if warnings:
            lines.append(f"- **Warnings:** {len(warnings)}")
        lines.append("")

        # --- Company Configuration ---
        lines.append("## Company Configuration")
        lines.append("")
        lines.append(f"| Setting | Value |")
        lines.append(f"|---------|-------|")
        lines.append(f"| Country | {self.company.country} |")
        lines.append(f"| Currency | {self.company.currency} |")
        lines.append(f"| Fiscal Year Start | Month {self.company.fiscal_year_start_month} |")
        lines.append(f"| Timezone | {self.company.timezone} |")
        lines.append(f"| Tax Regime | {self.company.tax_regime} |")
        lines.append("")

        # --- Module Installation Plan ---
        lines.append("## Module Installation Plan")
        lines.append("")
        ordered = self.get_install_order()
        lines.append("| # | Module | Display Name | Priority | Dependencies | Est. Minutes |")
        lines.append("|---|--------|-------------|----------|-------------|-------------|")
        for i, m in enumerate(ordered, 1):
            deps = ", ".join(m.depends_on) if m.depends_on else "—"
            lines.append(f"| {i} | `{m.module_name}` | {m.display_name} | {m.priority.value} | {deps} | {m.estimated_minutes} |")
        lines.append("")

        # --- Detailed Module Configuration ---
        lines.append("## Detailed Module Configuration")
        lines.append("")
        for m in ordered:
            lines.append(f"### {m.display_name} (`{m.module_name}`)")
            lines.append("")
            if m.notes:
                lines.append(f"**Purpose:** {m.notes}")
                lines.append("")
            if m.settings:
                lines.append("**Settings:**")
                lines.append("")
                lines.append("```")
                for k, v in m.settings.items():
                    lines.append(f"  {k}: {v}")
                lines.append("```")
                lines.append("")
            else:
                lines.append("Default configuration — no custom settings required.")
                lines.append("")

        # --- User Roles & Security ---
        if self.user_roles:
            lines.append("## User Roles & Security")
            lines.append("")
            lines.append("| Role | Description | Security Groups | Users |")
            lines.append("|------|------------|----------------|-------|")
            for r in self.user_roles:
                groups = ", ".join(f"`{g}`" for g in r.groups)
                lines.append(f"| {r.name} | {r.description} | {groups} | {r.count} |")
            lines.append("")

        # --- Data Migration Plan ---
        if self.data_imports:
            lines.append("## Data Migration Plan")
            lines.append("")
            lines.append("| Data Type | Source | Est. Records | Priority |")
            lines.append("|-----------|--------|-------------|----------|")
            for d in self.data_imports:
                lines.append(f"| {d.entity_type} | {d.source} | {d.estimated_records or '—'} | {d.priority.value} |")
            lines.append("")

        # --- Integration Requirements ---
        if self.integrations:
            lines.append("## Integration Requirements")
            lines.append("")
            lines.append("| System | Direction | Type | Priority | Notes |")
            lines.append("|--------|-----------|------|----------|-------|")
            for i in self.integrations:
                lines.append(f"| {i.system_name} | {i.direction} | {i.integration_type} | {i.priority.value} | {i.notes[:80] if i.notes else '—'} |")
            lines.append("")

        # --- Pain Points & Special Requirements ---
        if self.pain_points:
            lines.append("## Pain Points")
            lines.append("")
            for pp in self.pain_points:
                lines.append(f"- {pp}")
            lines.append("")

        if self.special_requirements:
            lines.append("## Special Requirements & Warnings")
            lines.append("")
            for sr in self.special_requirements:
                lines.append(f"- {sr}")
            lines.append("")

        # --- Implementation Checklist ---
        lines.append("## Implementation Checklist")
        lines.append("")
        lines.append("- [ ] Create Odoo instance and configure company details")
        for m in ordered:
            lines.append(f"- [ ] Install and configure **{m.display_name}** (`{m.module_name}`)")
        if self.user_roles:
            lines.append("- [ ] Create user roles and assign security groups")
        if self.data_imports:
            lines.append("- [ ] Execute data migration plan")
        if self.integrations:
            lines.append("- [ ] Set up external integrations")
        lines.append("- [ ] User acceptance testing")
        lines.append("- [ ] Go-live")
        lines.append("")

        return "\n".join(lines)

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> "ImplementationSpec":
        """Create from dictionary."""
        company = CompanySetup(
            name=data["company"]["name"],
            industry=data["company"]["industry"],
            country=data["company"].get("country", "US"),
            currency=data["company"].get("currency", "USD"),
            timezone=data["company"].get("timezone", "UTC"),
            fiscal_year_start_month=data["company"].get("fiscal_year_start_month", 1),
            tax_regime=data["company"].get("tax_regime", "standard"),
        )

        modules = [
            ModuleConfig(
                module_name=m["module_name"],
                display_name=m["display_name"],
                install=m.get("install", True),
                priority=ConfigPriority(m.get("priority", "medium")),
                settings=m.get("settings", {}),
                depends_on=m.get("depends_on", []),
                estimated_minutes=m.get("estimated_minutes", 5),
                notes=m.get("notes", ""),
            )
            for m in data.get("modules", [])
        ]

        user_roles = [
            UserRole(
                name=r["name"],
                description=r["description"],
                groups=r.get("groups", []),
                count=r.get("count", 1),
            )
            for r in data.get("user_roles", [])
        ]

        data_imports = [
            DataImport(
                entity_type=d["entity_type"],
                source=d["source"],
                estimated_records=d.get("estimated_records", 0),
                priority=ConfigPriority(d.get("priority", "medium")),
                notes=d.get("notes", ""),
            )
            for d in data.get("data_imports", [])
        ]

        integrations = [
            IntegrationRequirement(
                system_name=i["system_name"],
                integration_type=i["integration_type"],
                direction=i["direction"],
                priority=ConfigPriority(i.get("priority", "low")),
                notes=i.get("notes", ""),
            )
            for i in data.get("integrations", [])
        ]

        return cls(
            spec_id=data["spec_id"],
            created_at=data["created_at"],
            interview_session_id=data["interview_session_id"],
            company=company,
            modules=modules,
            user_roles=user_roles,
            data_imports=data_imports,
            integrations=integrations,
            pain_points=data.get("pain_points", []),
            special_requirements=data.get("special_requirements", []),
            interview_summary=data.get("interview_summary", {}),
        )


# Module catalog - maps detected domains to Odoo modules
MODULE_CATALOG = {
    "sales": ModuleConfig(
        module_name="sale_management",
        display_name="Sales",
        priority=ConfigPriority.HIGH,
        estimated_minutes=5,
        settings={
            "group_sale_pricelist": True,
            "group_discount_per_so_line": True,
        }
    ),
    "crm": ModuleConfig(
        module_name="crm",
        display_name="CRM",
        priority=ConfigPriority.HIGH,
        depends_on=["sale_management"],
        estimated_minutes=5,
        settings={
            "group_use_lead": True,
        }
    ),
    "inventory": ModuleConfig(
        module_name="stock",
        display_name="Inventory",
        priority=ConfigPriority.HIGH,
        estimated_minutes=8,
        settings={
            "group_stock_multi_locations": True,
            "group_stock_tracking_lot": True,
        }
    ),
    "purchase": ModuleConfig(
        module_name="purchase",
        display_name="Purchase",
        priority=ConfigPriority.MEDIUM,
        depends_on=["stock"],
        estimated_minutes=5,
    ),
    "finance": ModuleConfig(
        module_name="account",
        display_name="Invoicing/Accounting",
        priority=ConfigPriority.CRITICAL,
        estimated_minutes=10,
        settings={
            "group_analytic_accounting": True,
        }
    ),
    "manufacturing": ModuleConfig(
        module_name="mrp",
        display_name="Manufacturing",
        priority=ConfigPriority.MEDIUM,
        depends_on=["stock"],
        estimated_minutes=10,
    ),
    "hr": ModuleConfig(
        module_name="hr",
        display_name="Employees",
        priority=ConfigPriority.MEDIUM,
        estimated_minutes=5,
    ),
    "hr_holidays": ModuleConfig(
        module_name="hr_holidays",
        display_name="Time Off",
        priority=ConfigPriority.LOW,
        depends_on=["hr"],
        estimated_minutes=3,
    ),
    "hr_attendance": ModuleConfig(
        module_name="hr_attendance",
        display_name="Attendance",
        priority=ConfigPriority.LOW,
        depends_on=["hr"],
        estimated_minutes=3,
    ),
    "project": ModuleConfig(
        module_name="project",
        display_name="Project",
        priority=ConfigPriority.MEDIUM,
        estimated_minutes=5,
    ),
    "timesheet": ModuleConfig(
        module_name="hr_timesheet",
        display_name="Timesheets",
        priority=ConfigPriority.MEDIUM,
        depends_on=["project", "hr"],
        estimated_minutes=5,
    ),
    "ecommerce": ModuleConfig(
        module_name="website_sale",
        display_name="eCommerce",
        priority=ConfigPriority.MEDIUM,
        depends_on=["sale_management", "website"],
        estimated_minutes=15,
    ),
    "website": ModuleConfig(
        module_name="website",
        display_name="Website Builder",
        priority=ConfigPriority.MEDIUM,
        estimated_minutes=10,
    ),
    "helpdesk": ModuleConfig(
        module_name="helpdesk",
        display_name="Helpdesk",
        priority=ConfigPriority.LOW,
        estimated_minutes=5,
    ),
}


def _extract_pain_points(interview_summary: dict) -> list[str]:
    """Extract pain points from ALL interview responses, not just headache questions."""
    pain_points = []
    pain_keywords = [
        "headache", "pain", "frustrating", "frustrated", "annoying", "problem",
        "struggle", "difficult", "challenge", "issue", "broken", "slow",
        "manual", "spreadsheet", "workaround", "hack", "nightmare", "tedious",
        "error-prone", "time-consuming", "bottleneck", "delayed",
    ]

    # Check scoping responses
    for resp in interview_summary.get("scoping_responses", []):
        answer = resp.get("a", "").strip()
        if not answer:
            continue
        answer_lower = answer.lower()
        if any(kw in answer_lower for kw in pain_keywords):
            pain_points.append(answer)
        # Always include the "biggest headache" answer
        if "headache" in resp.get("q", "").lower() or "pain" in resp.get("q", "").lower():
            if answer and answer not in pain_points:
                pain_points.append(answer)

    # Check domain responses
    for domain, responses in interview_summary.get("domain_responses", {}).items():
        for resp in responses:
            answer = resp.get("a", "").strip()
            if not answer:
                continue
            answer_lower = answer.lower()
            if any(kw in answer_lower for kw in pain_keywords):
                if answer not in pain_points:
                    pain_points.append(answer)

    return pain_points


def _extract_user_roles(interview_summary: dict) -> list[UserRole]:
    """Extract user roles from interview responses, falling back to smart defaults."""
    roles = []
    all_responses = []

    for resp in interview_summary.get("scoping_responses", []):
        all_responses.append((resp.get("q", ""), resp.get("a", "")))
    for domain, responses in interview_summary.get("domain_responses", {}).items():
        for resp in responses:
            all_responses.append((resp.get("q", ""), resp.get("a", "")))

    # Try to find employee count from responses
    employee_count = 0
    for q, a in all_responses:
        q_lower = q.lower()
        a_lower = a.lower()
        if "employee" in q_lower or "how many" in q_lower or "staff" in q_lower or "user" in q_lower:
            import re
            numbers = re.findall(r'\d+', a)
            if numbers:
                employee_count = max(int(n) for n in numbers)
                break

    # Try to find mentioned roles
    role_keywords = {
        "sales": (["salesperson", "sales rep", "account manager", "sales manager"], "sale.group_sale_salesman"),
        "warehouse": (["warehouse", "stock keeper", "picker", "logistics"], "stock.group_stock_user"),
        "accounting": (["accountant", "bookkeeper", "finance", "controller"], "account.group_account_user"),
        "hr": (["hr manager", "hr", "recruiter", "payroll"], "hr.group_hr_user"),
        "purchase": (["buyer", "purchasing", "procurement"], "purchase.group_purchase_user"),
        "project": (["project manager", "consultant", "analyst"], "project.group_project_user"),
    }

    detected_roles = set()
    for q, a in all_responses:
        a_lower = a.lower()
        for role_type, (keywords, group) in role_keywords.items():
            if any(kw in a_lower for kw in keywords):
                detected_roles.add(role_type)

    # Build roles based on what we detected
    roles.append(UserRole(
        name="Administrator",
        description="Full system access",
        groups=["base.group_system"],
        count=1
    ))

    # Scale managers and users based on company size
    if employee_count > 0:
        manager_count = max(1, min(employee_count // 15, 10))
        user_count = max(1, employee_count - manager_count - 1)
    else:
        manager_count = 2
        user_count = 5

    domains_covered = interview_summary.get("domains_covered", [])

    # Add domain-specific roles
    if "sales" in domains_covered or "sales" in detected_roles:
        roles.append(UserRole(
            name="Sales User",
            description="Sales team member with CRM and quotation access",
            groups=["sale.group_sale_salesman", "base.group_user"],
            count=max(1, user_count // 3)
        ))

    if "inventory" in domains_covered or "warehouse" in detected_roles:
        roles.append(UserRole(
            name="Warehouse User",
            description="Warehouse staff with stock and picking access",
            groups=["stock.group_stock_user", "base.group_user"],
            count=max(1, user_count // 4)
        ))

    if "finance" in domains_covered or "accounting" in detected_roles:
        roles.append(UserRole(
            name="Accountant",
            description="Accounting and invoicing access",
            groups=["account.group_account_user", "base.group_user"],
            count=max(1, min(3, user_count // 5))
        ))

    # Always add generic manager and user roles
    roles.append(UserRole(
        name="Manager",
        description="Department manager with approval rights",
        groups=["base.group_user"],
        count=manager_count
    ))

    if not any(r.name in ("Sales User", "Warehouse User", "Accountant") for r in roles):
        roles.append(UserRole(
            name="User",
            description="Standard user access",
            groups=["base.group_user"],
            count=user_count
        ))

    return roles


def _extract_integrations(interview_summary: dict) -> list[IntegrationRequirement]:
    """Extract integration requirements from interview responses."""
    integrations = []
    integration_keywords = {
        "shopify": ("Shopify", "api", "bidirectional"),
        "woocommerce": ("WooCommerce", "api", "bidirectional"),
        "magento": ("Magento", "api", "bidirectional"),
        "quickbooks": ("QuickBooks", "file", "import"),
        "xero": ("Xero", "api", "bidirectional"),
        "stripe": ("Stripe", "api", "bidirectional"),
        "paypal": ("PayPal", "api", "bidirectional"),
        "amazon": ("Amazon", "api", "bidirectional"),
        "ebay": ("eBay", "api", "bidirectional"),
        "salesforce": ("Salesforce", "api", "bidirectional"),
        "hubspot": ("HubSpot", "api", "import"),
        "slack": ("Slack", "api", "export"),
        "excel": ("Excel/CSV", "file", "bidirectional"),
        "spreadsheet": ("Spreadsheets", "file", "import"),
        "bank": ("Banking", "file", "import"),
        "ups": ("UPS", "api", "bidirectional"),
        "fedex": ("FedEx", "api", "bidirectional"),
        "dhl": ("DHL", "api", "bidirectional"),
    }

    seen = set()
    for resp in interview_summary.get("scoping_responses", []):
        a = resp.get("a", "").lower()
        for keyword, (name, int_type, direction) in integration_keywords.items():
            if keyword in a and name not in seen:
                seen.add(name)
                integrations.append(IntegrationRequirement(
                    system_name=name,
                    integration_type=int_type,
                    direction=direction,
                    priority=ConfigPriority.MEDIUM,
                    notes=f"Mentioned during scoping: {resp.get('a', '')[:100]}"
                ))

    for domain, responses in interview_summary.get("domain_responses", {}).items():
        for resp in responses:
            a = resp.get("a", "").lower()
            for keyword, (name, int_type, direction) in integration_keywords.items():
                if keyword in a and name not in seen:
                    seen.add(name)
                    integrations.append(IntegrationRequirement(
                        system_name=name,
                        integration_type=int_type,
                        direction=direction,
                        priority=ConfigPriority.MEDIUM,
                        notes=f"Mentioned in {domain}: {resp.get('a', '')[:100]}"
                    ))

    return integrations


def _extract_data_imports(interview_summary: dict) -> list[DataImport]:
    """Extract data import needs from interview responses."""
    imports = []
    import_signals = {
        "customer": ("customers", "csv"),
        "product": ("products", "csv"),
        "vendor": ("vendors", "csv"),
        "supplier": ("vendors", "csv"),
        "invoice": ("invoices", "csv"),
        "employee": ("employees", "csv"),
        "inventory": ("stock_levels", "csv"),
        "contact": ("contacts", "csv"),
    }

    migration_keywords = [
        "migrate", "migration", "import", "transfer", "existing data",
        "historical", "legacy", "current system", "move over",
    ]

    seen = set()
    all_text = ""
    for resp in interview_summary.get("scoping_responses", []):
        all_text += " " + resp.get("a", "")
    for domain, responses in interview_summary.get("domain_responses", {}).items():
        for resp in responses:
            all_text += " " + resp.get("a", "")

    all_lower = all_text.lower()

    # Check if migration is mentioned at all
    needs_migration = any(kw in all_lower for kw in migration_keywords)

    if needs_migration:
        for keyword, (entity_type, source) in import_signals.items():
            if keyword in all_lower and entity_type not in seen:
                seen.add(entity_type)
                imports.append(DataImport(
                    entity_type=entity_type,
                    source=source,
                    priority=ConfigPriority.MEDIUM,
                    notes=f"Data type '{keyword}' mentioned alongside migration intent"
                ))

    return imports


def _apply_interview_settings(module: ModuleConfig, domain: str, interview_summary: dict) -> ModuleConfig:
    """Customize module settings based on actual interview responses."""
    all_domain_responses = interview_summary.get("domain_responses", {}).get(domain, [])
    all_text = " ".join(r.get("a", "") for r in all_domain_responses).lower()

    if module.module_name == "sale_management":
        # Pricelist: only enable if mentioned
        if any(kw in all_text for kw in ["pricelist", "tiered", "volume discount", "different price", "varies by"]):
            module.settings["group_sale_pricelist"] = True
        else:
            module.settings["group_sale_pricelist"] = False
        # Discounts
        if any(kw in all_text for kw in ["discount", "reduction", "markdown"]):
            module.settings["group_discount_per_so_line"] = True
        else:
            module.settings["group_discount_per_so_line"] = False

    elif module.module_name == "stock":
        # Multi-location only if multiple warehouses mentioned
        if any(kw in all_text for kw in ["multiple warehouse", "multiple location", "locations", "warehouses", "two warehouse", "several"]):
            module.settings["group_stock_multi_locations"] = True
        else:
            module.settings["group_stock_multi_locations"] = False
        # Lot/serial tracking
        if any(kw in all_text for kw in ["serial", "lot", "batch", "tracking", "expir", "recall"]):
            module.settings["group_stock_tracking_lot"] = True
        else:
            module.settings["group_stock_tracking_lot"] = False

    elif module.module_name == "account":
        # Analytic accounting for project-based or department-based reporting
        scoping_text = " ".join(r.get("a", "") for r in interview_summary.get("scoping_responses", [])).lower()
        if any(kw in all_text + scoping_text for kw in ["department", "project", "analytic", "cost center", "business unit"]):
            module.settings["group_analytic_accounting"] = True
        else:
            module.settings["group_analytic_accounting"] = False

    elif module.module_name == "crm":
        if any(kw in all_text for kw in ["lead", "pipeline", "opportunity", "prospect"]):
            module.settings["group_use_lead"] = True
        else:
            module.settings["group_use_lead"] = False

    return module


def _compute_completeness(interview_summary: dict, modules: list[ModuleConfig]) -> tuple[float, list[str]]:
    """Compute how complete the interview data is and return warnings."""
    warnings = []
    scores = []

    scoping = interview_summary.get("scoping_responses", [])
    domain_responses = interview_summary.get("domain_responses", {})
    domains_covered = interview_summary.get("domains_covered", [])

    # Check scoping completeness
    answered_scoping = sum(1 for r in scoping if r.get("a", "").strip())
    total_scoping = max(len(scoping), 1)
    scoping_score = answered_scoping / total_scoping
    scores.append(scoping_score)

    if scoping_score < 0.5:
        warnings.append("Less than half of scoping questions were answered - recommendations may be incomplete")

    # Check domain completeness
    if not domains_covered:
        warnings.append("No business domains were identified - spec is based on minimal data")
        scores.append(0.0)
    else:
        domain_scores = []
        for domain in domains_covered:
            responses = domain_responses.get(domain, [])
            answered = sum(1 for r in responses if r.get("a", "").strip())
            total = max(len(responses), 1)
            domain_scores.append(answered / total)
            if answered / total < 0.3:
                warnings.append(f"Domain '{domain}' has very few responses - configuration may need manual review")
        if domain_scores:
            scores.append(sum(domain_scores) / len(domain_scores))

    # Check for critical gaps
    module_names = {m.module_name for m in modules}
    if "account" not in module_names:
        warnings.append("No accounting module selected - this is unusual, verify with client")
    if not interview_summary.get("detected_signals"):
        warnings.append("No business signals detected from responses - interview quality may be low")

    # Overall questions answered
    total_answered = answered_scoping + sum(
        sum(1 for r in responses if r.get("a", "").strip())
        for responses in domain_responses.values()
    )
    if total_answered < 5:
        warnings.append(f"Only {total_answered} questions answered total - spec has low confidence")

    completeness = sum(scores) / max(len(scores), 1)
    return round(completeness, 2), warnings


def create_spec_from_interview(interview_summary: dict) -> ImplementationSpec:
    """
    Convert interview summary to implementation specification.

    Analyzes actual interview responses to:
    - Determine module settings based on what the user said
    - Extract real user roles from employee/team descriptions
    - Identify integration needs from mentioned systems
    - Gather pain points from all responses
    - Compute data migration scope
    - Score completeness and flag gaps
    """
    from datetime import datetime
    import uuid

    # Extract company info
    company = CompanySetup(
        name=interview_summary.get("client_name", "My Company"),
        industry=interview_summary.get("industry", "General"),
    )

    # Extract location/currency from ALL responses
    all_response_text = " ".join(r.get("a", "") for r in interview_summary.get("scoping_responses", []))
    for responses in interview_summary.get("domain_responses", {}).values():
        all_response_text += " " + " ".join(r.get("a", "") for r in responses)
    all_lower = all_response_text.lower()

    if any(kw in all_lower for kw in ["europe", "eu ", "belgium", "netherlands", "germany", "france", "spain", "italy"]):
        company.currency = "EUR"
    elif any(kw in all_lower for kw in ["uk", "united kingdom", "british", "pound", "gbp"]):
        company.currency = "GBP"
    elif any(kw in all_lower for kw in ["canada", "canadian", "cad"]):
        company.currency = "CAD"

    # Determine modules from detected signals and domains
    modules = []
    domains_covered = interview_summary.get("domains_covered", [])
    recommended_modules = interview_summary.get("recommended_modules", [])

    # Always include accounting
    if "finance" not in domains_covered:
        domains_covered.append("finance")

    # Map domains to modules with interview-aware settings
    for domain in domains_covered:
        if domain in MODULE_CATALOG:
            catalog_mod = MODULE_CATALOG[domain]
            module = ModuleConfig(
                module_name=catalog_mod.module_name,
                display_name=catalog_mod.display_name,
                priority=catalog_mod.priority,
                settings=catalog_mod.settings.copy(),
                depends_on=catalog_mod.depends_on.copy(),
                estimated_minutes=catalog_mod.estimated_minutes,
                notes=f"Detected from {domain} domain interview"
            )
            # Apply interview-specific settings
            module = _apply_interview_settings(module, domain, interview_summary)
            modules.append(module)

    # Add explicitly recommended modules not already included
    module_names = {m.module_name for m in modules}
    for mod_name in recommended_modules:
        if mod_name not in module_names:
            for key, mod in MODULE_CATALOG.items():
                if mod.module_name == mod_name:
                    modules.append(ModuleConfig(
                        module_name=mod.module_name,
                        display_name=mod.display_name,
                        priority=mod.priority,
                        settings=mod.settings.copy(),
                        depends_on=mod.depends_on.copy(),
                        estimated_minutes=mod.estimated_minutes,
                        notes="Recommended based on interview analysis"
                    ))
                    module_names.add(mod_name)
                    break

    # Add dependencies that aren't already included
    all_deps = set()
    for mod in modules:
        all_deps.update(mod.depends_on)

    for dep in all_deps:
        if dep not in module_names:
            for key, mod in MODULE_CATALOG.items():
                if mod.module_name == dep:
                    modules.append(ModuleConfig(
                        module_name=mod.module_name,
                        display_name=mod.display_name,
                        priority=ConfigPriority.HIGH,
                        settings=mod.settings.copy(),
                        depends_on=mod.depends_on.copy(),
                        estimated_minutes=mod.estimated_minutes,
                        notes="Required dependency"
                    ))
                    module_names.add(dep)
                    break

    # Extract real data from interview responses
    user_roles = _extract_user_roles(interview_summary)
    pain_points = _extract_pain_points(interview_summary)
    integrations = _extract_integrations(interview_summary)
    data_imports = _extract_data_imports(interview_summary)

    # Compute completeness and warnings
    completeness, warnings = _compute_completeness(interview_summary, modules)

    # Build special requirements from warnings
    special_requirements = warnings.copy()

    spec = ImplementationSpec(
        spec_id=f"spec-{uuid.uuid4().hex[:8]}",
        created_at=datetime.now().isoformat(),
        interview_session_id=interview_summary.get("session_id", "unknown"),
        company=company,
        modules=modules,
        user_roles=user_roles,
        data_imports=data_imports,
        integrations=integrations,
        pain_points=pain_points,
        special_requirements=special_requirements,
        interview_summary=interview_summary,
    )

    # Store completeness in the summary for downstream consumers
    spec.interview_summary["_completeness_score"] = completeness
    spec.interview_summary["_warnings"] = warnings

    return spec
