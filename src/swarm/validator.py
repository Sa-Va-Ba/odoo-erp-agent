"""Validation and dependency completion for module plans."""

from __future__ import annotations

from .registry import ModuleRegistry
from .types import ModuleCandidate, SwarmDecision


class SwarmValidator:
    def __init__(self, registry: ModuleRegistry):
        self.registry = registry

    def ensure_dependencies(self, decision: SwarmDecision) -> SwarmDecision:
        selected = {m.technical_name: m for m in decision.selected_modules}
        auto_added: list[str] = []

        def add_module(module_name: str, reason: str) -> None:
            if module_name in selected:
                return
            module_def = self.registry.get(module_name)
            if not module_def:
                decision.notes.append(f"Dependency '{module_name}' not found in registry.")
                return
            selected[module_name] = ModuleCandidate(
                technical_name=module_def.technical_name,
                name=module_def.name,
                domain=module_def.domain,
                reason=reason,
                confidence=0.4,
                evidence=[],
                dependencies=module_def.dependencies,
                priority="low",
                requires_enterprise=module_def.requires_enterprise,
                conflicts_with=module_def.conflicts_with,
            )
            auto_added.append(module_name)

        # Base is always required
        add_module("base", "Core dependency for all Odoo modules.")

        # Resolve declared dependencies
        pending = list(selected.values())
        while pending:
            module = pending.pop()
            for dep in module.dependencies:
                if dep not in selected:
                    add_module(dep, f"Dependency required by {module.technical_name}.")
                    # Only append if successfully added (module exists in registry)
                    if dep in selected:
                        pending.append(selected[dep])

        decision.selected_modules = sorted(selected.values(), key=lambda c: c.technical_name)
        decision.auto_added_dependencies = sorted(set(auto_added))
        return decision
