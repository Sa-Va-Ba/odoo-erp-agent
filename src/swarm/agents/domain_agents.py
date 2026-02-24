"""Domain agents for module selection."""

from __future__ import annotations

from dataclasses import dataclass

from .base import SwarmAgent
from ..registry import ModuleRegistry
from ..types import AgentResult, ModuleCandidate, NormalizedInterview


@dataclass
class SignalAgentConfig:
    name: str
    domain: str
    signal_to_modules: dict[str, list[str]]
    base_confidence: float = 0.6


class SignalAgent(SwarmAgent):
    def __init__(self, registry: ModuleRegistry, config: SignalAgentConfig):
        self.registry = registry
        self.config = config
        self.name = config.name

    def run(self, interview: NormalizedInterview) -> AgentResult:
        candidates: list[ModuleCandidate] = []
        notes: list[str] = []

        for signal, modules in self.config.signal_to_modules.items():
            if interview.signals.get(signal, 0) <= 0:
                continue

            evidence = interview.evidence_map.get(signal, [])
            for module_name in modules:
                module_def = self.registry.get(module_name)
                if not module_def:
                    notes.append(f"Missing registry entry for module '{module_name}'")
                    continue

                reason = f"Detected {signal.replace('_', ' ')} needs in interview responses."
                confidence = min(0.95, self.config.base_confidence + 0.05 * interview.signals[signal])
                candidates.append(
                    ModuleCandidate(
                        technical_name=module_def.technical_name,
                        name=module_def.name,
                        domain=module_def.domain,
                        reason=reason,
                        confidence=confidence,
                        evidence=evidence,
                        dependencies=module_def.dependencies,
                        priority="high" if signal in {"ecommerce", "accounting", "inventory"} else "medium",
                        requires_enterprise=module_def.requires_enterprise,
                        conflicts_with=module_def.conflicts_with,
                    )
                )

        return AgentResult(
            agent_name=self.name,
            module_candidates=candidates,
            notes=notes,
            confidence=self.config.base_confidence,
        )


class RiskSignalAgent(SwarmAgent):
    def __init__(self, name: str, signals: list[str]):
        self.name = name
        self.signals = signals

    def run(self, interview: NormalizedInterview) -> AgentResult:
        notes: list[str] = []
        for signal in self.signals:
            if interview.signals.get(signal, 0) > 0:
                notes.append(f"Detected {signal.replace('_', ' ')} considerations.")
        return AgentResult(agent_name=self.name, module_candidates=[], notes=notes, confidence=0.5)


def build_default_agents(registry: ModuleRegistry, odoo_version: str = "17.0") -> list[SwarmAgent]:
    agents: list[SwarmAgent] = []
    is_legacy_5 = (odoo_version or "").strip().startswith("5.")

    agents.append(
        SignalAgent(
            registry,
            SignalAgentConfig(
                name="sales_agent",
                domain="sales",
                signal_to_modules={
                    "crm": ["crm"],
                    "sales": ["sale_management", "crm"],
                    "ecommerce": ["sale_management"],
                },
                base_confidence=0.65,
            ),
        )
    )

    agents.append(
        SignalAgent(
            registry,
            SignalAgentConfig(
                name="website_agent",
                domain="ecommerce",
                signal_to_modules={
                    "ecommerce": (
                        ["sale_management", "delivery", "webshop_connector"]
                        if is_legacy_5
                        else ["website", "website_sale", "payment"]
                    ),
                    "shipping": ["delivery"],
                },
                base_confidence=0.7,
            ),
        )
    )

    agents.append(
        SignalAgent(
            registry,
            SignalAgentConfig(
                name="inventory_agent",
                domain="inventory",
                signal_to_modules={
                    "inventory": ["stock"],
                    "shipping": ["delivery"],
                },
                base_confidence=0.7,
            ),
        )
    )

    agents.append(
        SignalAgent(
            registry,
            SignalAgentConfig(
                name="purchase_agent",
                domain="purchase",
                signal_to_modules={
                    "purchase": ["purchase"],
                },
                base_confidence=0.6,
            ),
        )
    )

    agents.append(
        SignalAgent(
            registry,
            SignalAgentConfig(
                name="accounting_agent",
                domain="accounting",
                signal_to_modules={
                    "accounting": ["account"],
                },
                base_confidence=0.75,
            ),
        )
    )

    agents.append(
        SignalAgent(
            registry,
            SignalAgentConfig(
                name="manufacturing_agent",
                domain="manufacturing",
                signal_to_modules={
                    "manufacturing": ["mrp"],
                    "quality": ["quality"],
                    "maintenance": ["maintenance"],
                },
                base_confidence=0.6,
            ),
        )
    )

    agents.append(
        SignalAgent(
            registry,
            SignalAgentConfig(
                name="hr_agent",
                domain="hr",
                signal_to_modules={
                    "hr": ["hr"],
                },
                base_confidence=0.55,
            ),
        )
    )

    agents.append(
        SignalAgent(
            registry,
            SignalAgentConfig(
                name="project_agent",
                domain="project",
                signal_to_modules={
                    "project": ["project", "hr_timesheet"],
                },
                base_confidence=0.55,
            ),
        )
    )

    agents.append(
        SignalAgent(
            registry,
            SignalAgentConfig(
                name="marketing_agent",
                domain="marketing",
                signal_to_modules={
                    "marketing": ["marketing_automation"],
                },
                base_confidence=0.5,
            ),
        )
    )

    # Subscription agent for recurring revenue businesses
    agents.append(
        SignalAgent(
            registry,
            SignalAgentConfig(
                name="subscription_agent",
                domain="sales",
                signal_to_modules={
                    "subscriptions": ["sale_subscription"],
                },
                base_confidence=0.6,
            ),
        )
    )

    # Support/Helpdesk agent
    agents.append(
        SignalAgent(
            registry,
            SignalAgentConfig(
                name="support_agent",
                domain="service",
                signal_to_modules={
                    "support": ["helpdesk"],
                },
                base_confidence=0.55,
            ),
        )
    )

    # Point of Sale agent
    agents.append(
        SignalAgent(
            registry,
            SignalAgentConfig(
                name="pos_agent",
                domain="sales",
                signal_to_modules={
                    "pos": ["point_of_sale"],
                },
                base_confidence=0.6,
            ),
        )
    )

    agents.append(RiskSignalAgent("integration_agent", ["integration"]))
    agents.append(RiskSignalAgent("migration_agent", ["data_migration"]))
    agents.append(RiskSignalAgent("outsourced_manufacturing_agent", ["outsourced_manufacturing"]))

    return agents
