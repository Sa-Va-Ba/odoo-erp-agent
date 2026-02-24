"""
Shared Context Schema for Odoo ERP Implementation Agent System

This defines the data structure that is shared between all agents
and maintains the project state throughout the implementation lifecycle.
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
from enum import Enum


class ProjectPhase(str, Enum):
    INTERVIEW = "interview"
    SPECIFICATION = "specification"
    MODULE_SELECTION = "module_selection"
    CONFIGURATION = "configuration"
    DEVELOPMENT = "development"
    MIGRATION = "migration"
    QA = "qa"
    DEPLOYMENT = "deployment"


class AgentType(str, Enum):
    ORCHESTRATOR = "orchestrator"
    INTERVIEW = "interview_agent"
    SPECIFICATION = "specification_agent"
    TECHNICAL_ARCHITECT = "technical_architect"
    MODULE_SELECTOR = "module_selector"
    CONFIGURATION = "configuration_agent"
    CODING = "coding_agent"
    DATA_MIGRATION = "data_migration_agent"
    QA_VALIDATION = "qa_validation_agent"


@dataclass
class CompanyProfile:
    """Basic company information gathered during interview."""
    name: str = ""
    industry: str = ""
    employee_count: int = 0
    locations: list[str] = field(default_factory=list)
    annual_revenue: str = ""
    fiscal_year_end: str = ""
    currency: str = "EUR"
    country: str = ""
    languages: list[str] = field(default_factory=lambda: ["en_US"])


@dataclass
class Requirement:
    """A single requirement captured during interview."""
    id: str = ""
    domain: str = ""
    description: str = ""
    priority: str = "medium"  # high, medium, low
    current_process: str = ""
    pain_points: list[str] = field(default_factory=list)
    desired_outcome: str = ""
    constraints: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class Integration:
    """External system integration requirement."""
    system_name: str = ""
    system_type: str = ""  # e-commerce, banking, pos, api, etc.
    direction: str = "bidirectional"  # inbound, outbound, bidirectional
    data_types: list[str] = field(default_factory=list)
    frequency: str = ""  # realtime, hourly, daily, etc.
    priority: str = "medium"
    notes: str = ""


@dataclass
class UserRole:
    """User role and permission requirement."""
    role_name: str = ""
    department: str = ""
    user_count: int = 0
    access_areas: list[str] = field(default_factory=list)
    approval_workflows: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class DataMigrationScope:
    """Data migration requirements."""
    source_systems: list[str] = field(default_factory=list)
    data_types: list[str] = field(default_factory=list)
    volume_estimate: str = ""
    historical_data_years: int = 0
    cleanup_needed: bool = False
    notes: str = ""


@dataclass
class InterviewOutput:
    """Complete output from the Interview Agent."""
    company_profile: CompanyProfile = field(default_factory=CompanyProfile)
    requirements_by_domain: dict[str, list[Requirement]] = field(default_factory=lambda: {
        "accounting": [],
        "sales": [],
        "inventory": [],
        "hr": [],
        "project": [],
        "manufacturing": [],
        "purchase": [],
        "crm": [],
        "website": [],
        "general": []
    })
    integrations_needed: list[Integration] = field(default_factory=list)
    users_and_roles: list[UserRole] = field(default_factory=list)
    data_migration_scope: DataMigrationScope = field(default_factory=DataMigrationScope)
    current_systems: list[str] = field(default_factory=list)
    pain_points: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    budget_range: str = ""
    timeline_preference: str = ""


@dataclass
class ModuleRecommendation:
    """A recommended Odoo module."""
    name: str = ""
    technical_name: str = ""
    repository: str = ""  # OCA GitHub URL or apps.odoo.com
    version: str = "17.0"
    maintainer: str = ""
    purpose: str = ""
    configuration_needed: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    coverage_percentage: int = 0
    status: str = "recommended"  # recommended, approved, rejected


@dataclass
class ProjectState:
    """Current state of the implementation project."""
    current_phase: ProjectPhase = ProjectPhase.INTERVIEW
    current_agent: AgentType = AgentType.INTERVIEW
    completion_percentage: int = 0
    last_updated: str = ""
    blockers: list[str] = field(default_factory=list)
    pending_decisions: list[str] = field(default_factory=list)


@dataclass
class SharedContext:
    """
    Main shared context structure passed between all agents.
    This is the single source of truth for the entire implementation.
    """
    # Project metadata
    project_id: str = ""
    client_name: str = ""
    industry: str = ""
    project_start: str = ""
    odoo_version: str = "17.0"
    target_go_live: str = ""

    # Current state
    state: ProjectState = field(default_factory=ProjectState)

    # Interview outputs (populated by Interview Agent)
    interview_output: InterviewOutput = field(default_factory=InterviewOutput)

    # Specification (populated by Specification Agent)
    specification: dict = field(default_factory=lambda: {
        "approved": False,
        "document_url": "",
        "in_scope": [],
        "out_of_scope": [],
        "future_phases": []
    })

    # Module selection (populated by Module Selector Agent)
    modules: dict = field(default_factory=lambda: {
        "selected_modules": [],
        "custom_modules": []
    })

    # Configuration files (populated by Configuration Agent)
    configuration_files: dict = field(default_factory=lambda: {
        "generated": False,
        "location": "",
        "reviewed_by_architect": False
    })

    # Custom code (populated by Coding Agent)
    custom_code: dict = field(default_factory=lambda: {
        "files_generated": [],
        "unit_tests_passed": False,
        "code_review_status": "pending"
    })

    # Migration (populated by Data Migration Agent)
    migration: dict = field(default_factory=lambda: {
        "scripts_ready": False,
        "test_migration_completed": False,
        "validation_passed": False
    })

    # QA results (populated by QA Agent)
    qa_results: dict = field(default_factory=lambda: {
        "test_date": "",
        "total_tests": 0,
        "passed": 0,
        "failed": 0,
        "status": "pending",
        "report_url": ""
    })

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        import dataclasses
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SharedContext":
        """Create from dictionary (e.g., loaded from JSON)."""
        # This is a simplified version - a full implementation would
        # recursively convert nested dicts to their dataclass types
        context = cls()
        for key, value in data.items():
            if hasattr(context, key):
                setattr(context, key, value)
        return context


def create_new_project(client_name: str, industry: str) -> SharedContext:
    """Create a new project with initialized shared context."""
    now = datetime.now()
    return SharedContext(
        project_id=f"odoo-impl-{now.strftime('%Y%m%d%H%M%S')}",
        client_name=client_name,
        industry=industry,
        project_start=now.strftime("%Y-%m-%d"),
        state=ProjectState(
            current_phase=ProjectPhase.INTERVIEW,
            current_agent=AgentType.INTERVIEW,
            completion_percentage=0,
            last_updated=now.isoformat()
        )
    )
