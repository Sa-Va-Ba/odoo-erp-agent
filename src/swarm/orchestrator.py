"""Swarm orchestration for module selection and setup planning."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .agents.domain_agents import build_default_agents
from .moderator import SwarmModerator
from .normalizer import load_interview, normalize_interview
from .registry import ModuleRegistry
from .types import ConfigTask, SwarmDecision, SwarmOutput
from .validator import SwarmValidator


class SwarmOrchestrator:
    def __init__(
        self,
        registry: ModuleRegistry,
        edition: str = "community",
        odoo_version: str = "17.0",
    ):
        self.registry = registry
        self.edition = edition
        self.odoo_version = odoo_version

    def run(self, interview_path: str | Path, output_dir: str | Path) -> SwarmOutput:
        data = load_interview(interview_path)
        normalized = normalize_interview(data)

        agents = build_default_agents(self.registry, odoo_version=self.odoo_version)
        agent_results = [agent.run(normalized) for agent in agents]

        moderator = SwarmModerator(
            self.registry,
            edition=self.edition,
            odoo_version=self.odoo_version,
        )
        decision = moderator.consolidate(agent_results)

        validator = SwarmValidator(self.registry)
        decision = validator.ensure_dependencies(decision)

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

        module_plan_path = output_dir / f"module-plan-{timestamp}.json"
        config_tasks_path = output_dir / f"config-tasks-{timestamp}.json"
        implementation_spec_path = output_dir / f"implementation-spec-{timestamp}.md"
        audit_path = output_dir / f"swarm-audit-{timestamp}.json"

        module_plan = self._serialize_decision(decision, normalized)
        module_plan_path.write_text(json.dumps(module_plan, indent=2))

        tasks = self._build_config_tasks(decision)
        config_tasks_path.write_text(json.dumps([asdict(t) for t in tasks], indent=2))

        implementation_spec_path.write_text(
            self._render_implementation_spec(decision, normalized, tasks)
        )

        audit_payload = {
            "target": {
                "odoo_version": self.odoo_version,
                "odoo_edition": self.edition,
                "module_registry": self.registry.source_path,
            },
            "normalized": {
                "project_id": normalized.project_id,
                "client_name": normalized.client_name,
                "industry": normalized.industry,
                "signals": normalized.signals,
                "evidence_map": normalized.evidence_map,
            },
            "agent_results": [
                {
                    "agent": result.agent_name,
                    "notes": result.notes,
                    "modules": [asdict(m) for m in result.module_candidates],
                }
                for result in decision.agent_results
            ],
        }
        audit_path.write_text(json.dumps(audit_payload, indent=2))

        return SwarmOutput(
            decision=decision,
            module_plan_path=str(module_plan_path),
            config_tasks_path=str(config_tasks_path),
            implementation_spec_path=str(implementation_spec_path),
            audit_path=str(audit_path),
        )

    def _serialize_decision(self, decision: SwarmDecision, normalized) -> dict:
        return {
            "project_id": normalized.project_id,
            "client_name": normalized.client_name,
            "industry": normalized.industry,
            "odoo_version": self.odoo_version,
            "odoo_edition": self.edition,
            "module_registry": self.registry.source_path,
            "signals": normalized.signals,
            "selected_modules": [asdict(m) for m in decision.selected_modules],
            "rejected_modules": [asdict(m) for m in decision.rejected_modules],
            "auto_added_dependencies": decision.auto_added_dependencies,
            "open_questions": decision.open_questions,
            "risks": decision.risks,
            "notes": decision.notes,
            "coverage_map": decision.coverage_map,
        }

    def _build_config_tasks(self, decision: SwarmDecision) -> list[ConfigTask]:
        tasks: list[ConfigTask] = []
        for idx, module in enumerate(decision.selected_modules, start=1):
            module_def = self.registry.get(module.technical_name)
            steps = module_def.configuration_steps if module_def else []
            task_id = f"CFG-{idx:03d}"
            tasks.append(
                ConfigTask(
                    task_id=task_id,
                    module_technical_name=module.technical_name,
                    module_name=module.name,
                    description=f"Configure {module.name} ({module.technical_name}).",
                    steps=steps,
                    dependencies=module.dependencies,
                    owner_role="functional_consultant",
                )
            )
        return tasks

    def _render_implementation_spec(self, decision: SwarmDecision, normalized, tasks: list[ConfigTask]) -> str:
        lines: list[str] = []
        lines.append(f"# Implementation Specification - {normalized.client_name}\n")
        lines.append("## Summary")
        lines.append(f"- Industry: {normalized.industry}")
        lines.append(f"- Project ID: {normalized.project_id}")
        lines.append(f"- Odoo Version Target: {self.odoo_version}")
        lines.append(f"- Odoo Edition Target: {self.edition}")
        lines.append(f"- Module Registry: {self.registry.source_path}")
        lines.append("")

        if normalized.company_profile:
            lines.append("## Company Profile")
            for key, value in normalized.company_profile.items():
                if value in ("", [], None, 0):
                    continue
                lines.append(f"- {key.replace('_', ' ').title()}: {value}")
            lines.append("")

        lines.append("## Detected Signals")
        for signal, count in normalized.signals.items():
            if count > 0:
                lines.append(f"- {signal.replace('_', ' ').title()}: {count}")
        lines.append("")

        lines.append("## Module Plan")
        for module in decision.selected_modules:
            lines.append(
                f"- {module.name} ({module.technical_name}) [{module.domain}] - {module.reason}"
            )
        lines.append("")

        if decision.rejected_modules:
            lines.append("## Excluded Modules")
            for module in decision.rejected_modules:
                lines.append(
                    f"- {module.name} ({module.technical_name}) excluded for edition '{self.edition}'."
                )
            lines.append("")

        if decision.open_questions:
            lines.append("## Open Questions")
            for question in decision.open_questions:
                lines.append(f"- {question}")
            lines.append("")

        if decision.risks:
            lines.append("## Risks / Flags")
            for risk in decision.risks:
                lines.append(f"- {risk}")
            lines.append("")

        lines.append("## Configuration Tasks")
        for task in tasks:
            lines.append(f"- {task.task_id}: {task.description}")
        lines.append("")

        lines.append("## Next Steps")
        lines.append("- Confirm Odoo edition and hosting approach.")
        lines.append("- Validate module plan with stakeholders.")
        lines.append("- Prepare configuration workshop agenda.")
        lines.append("")

        return "\n".join(lines)
