"""
Core types for the module-selection swarm.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class NormalizedInterview:
    project_id: str
    client_name: str
    industry: str
    raw_text: str
    signals: dict[str, int]
    evidence_map: dict[str, list[str]]
    company_profile: dict[str, Any] = field(default_factory=dict)
    requirements: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    pain_points: list[str] = field(default_factory=list)
    systems_mentioned: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModuleCandidate:
    technical_name: str
    name: str
    domain: str
    reason: str
    confidence: float
    evidence: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    priority: str = "medium"
    requires_enterprise: bool = False
    conflicts_with: list[str] = field(default_factory=list)


@dataclass
class AgentResult:
    agent_name: str
    module_candidates: list[ModuleCandidate]
    notes: list[str] = field(default_factory=list)
    confidence: float = 0.5


@dataclass
class SwarmDecision:
    selected_modules: list[ModuleCandidate]
    rejected_modules: list[ModuleCandidate]
    open_questions: list[str]
    risks: list[str]
    notes: list[str]
    coverage_map: dict[str, list[str]]
    agent_results: list[AgentResult]
    auto_added_dependencies: list[str] = field(default_factory=list)


@dataclass
class ConfigTask:
    task_id: str
    module_technical_name: str
    module_name: str
    description: str
    steps: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    owner_role: str = "functional_consultant"


@dataclass
class SwarmOutput:
    decision: SwarmDecision
    module_plan_path: str
    config_tasks_path: str
    implementation_spec_path: str
    audit_path: str
