"""QA agents for validating swarm architecture, codebase, and Odoo setup plans."""

from __future__ import annotations

import argparse
import json
import py_compile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .registry import ModuleRegistry
from .registry_resolver import resolve_registry_path


@dataclass
class QAFinding:
    area: str
    severity: str
    message: str
    evidence: str = ""
    recommendation: str = ""


@dataclass
class QAAgentResult:
    agent_name: str
    status: str
    findings: list[QAFinding] = field(default_factory=list)
    summary: str = ""


class ArchitectureQAAgent:
    def run(self, workspace_root: Path) -> QAAgentResult:
        findings: list[QAFinding] = []
        registry_candidates = [
            workspace_root / "src" / "knowledge" / "odoo_modules.json",
            workspace_root / "src" / "knowledge" / "odoo_modules_5_3.json",
        ]
        required_paths = [
            workspace_root / "src" / "swarm" / "orchestrator.py",
            workspace_root / "src" / "swarm" / "moderator.py",
            workspace_root / "src" / "swarm" / "validator.py",
            workspace_root / "src" / "swarm" / "normalizer.py",
            workspace_root / "src" / "swarm" / "registry_resolver.py",
            workspace_root / "src" / "swarm" / "agents" / "domain_agents.py",
            workspace_root / "docs" / "swarm_architecture.md",
        ]

        for path in required_paths:
            if not path.exists():
                findings.append(
                    QAFinding(
                        area="architecture",
                        severity="high",
                        message="Required architecture component is missing.",
                        evidence=str(path),
                        recommendation="Restore or add the missing component file.",
                    )
                )
        if not any(path.exists() for path in registry_candidates):
            findings.append(
                QAFinding(
                    area="architecture",
                    severity="high",
                    message="No module registry file is available.",
                    evidence=", ".join(str(path) for path in registry_candidates),
                    recommendation="Add at least one registry under src/knowledge/.",
                )
            )

        orchestrator_file = workspace_root / "src" / "swarm" / "orchestrator.py"
        if orchestrator_file.exists():
            text = orchestrator_file.read_text()
            if "SwarmModerator" not in text:
                findings.append(
                    QAFinding(
                        area="architecture",
                        severity="high",
                        message="Orchestrator does not reference SwarmModerator.",
                        evidence=str(orchestrator_file),
                        recommendation="Route agent outputs through moderator before validation.",
                    )
                )
            if "SwarmValidator" not in text:
                findings.append(
                    QAFinding(
                        area="architecture",
                        severity="high",
                        message="Orchestrator does not reference SwarmValidator.",
                        evidence=str(orchestrator_file),
                        recommendation="Run dependency validation before output generation.",
                    )
                )

        status = "pass" if not findings else "fail"
        return QAAgentResult(
            agent_name="architecture_qa_agent",
            status=status,
            findings=findings,
            summary=(
                "Architecture checks passed."
                if status == "pass"
                else "Architecture gaps detected."
            ),
        )


class CodebaseQAAgent:
    def run(self, source_dir: Path) -> QAAgentResult:
        findings: list[QAFinding] = []
        py_files = sorted(source_dir.rglob("*.py"))

        if not py_files:
            findings.append(
                QAFinding(
                    area="codebase",
                    severity="high",
                    message="No Python files found for compilation checks.",
                    evidence=str(source_dir),
                )
            )

        for py_file in py_files:
            try:
                py_compile.compile(str(py_file), doraise=True)
            except py_compile.PyCompileError as exc:
                findings.append(
                    QAFinding(
                        area="codebase",
                        severity="critical",
                        message="Python compilation failed.",
                        evidence=f"{py_file}: {exc.msg}",
                        recommendation="Fix syntax/import errors and re-run QA.",
                    )
                )

        status = "pass" if not findings else "fail"
        return QAAgentResult(
            agent_name="codebase_qa_agent",
            status=status,
            findings=findings,
            summary=(
                f"Compiled {len(py_files)} Python files successfully."
                if status == "pass"
                else "Compilation failures detected."
            ),
        )


class OdooSetupQAAgent:
    def __init__(self, registry: ModuleRegistry):
        self.registry = registry

    def run(self, module_plan_path: Path) -> QAAgentResult:
        findings: list[QAFinding] = []
        module_plan = json.loads(module_plan_path.read_text())

        edition = str(module_plan.get("odoo_edition", "unknown")).lower()
        version = str(module_plan.get("odoo_version", "unknown"))
        selected_modules = module_plan.get("selected_modules", [])
        rejected_modules = module_plan.get("rejected_modules", [])

        if edition != "community":
            findings.append(
                QAFinding(
                    area="odoo_setup",
                    severity="high",
                    message="Module plan is not configured for Community edition.",
                    evidence=f"odoo_edition={edition}",
                    recommendation="Run swarm with '--edition community'.",
                )
            )

        selected_names = {m.get("technical_name", "") for m in selected_modules}

        for module in selected_modules:
            technical_name = module.get("technical_name", "")
            module_definition = self.registry.get(technical_name)
            if not module_definition:
                findings.append(
                    QAFinding(
                        area="odoo_setup",
                        severity="high",
                        message="Selected module is missing from registry.",
                        evidence=technical_name,
                    )
                )
                continue

            if module_definition.requires_enterprise:
                findings.append(
                    QAFinding(
                        area="odoo_setup",
                        severity="critical",
                        message="Enterprise-only module selected in Community mode.",
                        evidence=technical_name,
                        recommendation="Replace with a free-compatible alternative.",
                    )
                )

            if not self.registry.is_compatible(technical_name, version):
                findings.append(
                    QAFinding(
                        area="odoo_setup",
                        severity="high",
                        message="Selected module is not compatible with target Odoo version.",
                        evidence=f"{technical_name} vs {version}",
                        recommendation="Use a version-compatible registry or replace the module.",
                    )
                )

            for dependency in module_definition.dependencies:
                if dependency not in selected_names:
                    findings.append(
                        QAFinding(
                            area="odoo_setup",
                            severity="high",
                            message="Selected module has unresolved dependency.",
                            evidence=f"{technical_name} -> {dependency}",
                            recommendation="Ensure dependency is present in selected modules.",
                        )
                    )

        for rejected in rejected_modules:
            technical_name = rejected.get("technical_name", "")
            module_definition = self.registry.get(technical_name)
            if not module_definition or not module_definition.requires_enterprise:
                continue
            alternatives = module_definition.community_alternatives
            if not alternatives:
                findings.append(
                    QAFinding(
                        area="odoo_setup",
                        severity="medium",
                        message="Enterprise module has no explicit free alternative mapping.",
                        evidence=technical_name,
                        recommendation="Add 'community_alternatives' in registry.",
                    )
                )
            elif not any(name in selected_names for name in alternatives):
                findings.append(
                    QAFinding(
                        area="odoo_setup",
                        severity="medium",
                        message="Mapped free alternatives were not selected.",
                        evidence=f"{technical_name} -> {', '.join(alternatives)}",
                        recommendation="Review candidate scoring and include at least one alternative.",
                    )
                )

        status = "pass" if not any(f.severity in {"critical", "high"} for f in findings) else "fail"
        return QAAgentResult(
            agent_name="odoo_setup_qa_agent",
            status=status,
            findings=findings,
            summary=(
                "Odoo setup checks passed for Community mode."
                if status == "pass"
                else "Odoo setup risks detected."
            ),
        )


class QAOrchestrator:
    def __init__(self, workspace_root: Path, registry: ModuleRegistry):
        self.workspace_root = workspace_root
        self.registry = registry

    def run(self, module_plan_path: Path) -> dict:
        results: list[QAAgentResult] = []
        architecture_result = ArchitectureQAAgent().run(self.workspace_root)
        results.append(architecture_result)

        codebase_result = CodebaseQAAgent().run(self.workspace_root / "src" / "swarm")
        results.append(codebase_result)

        odoo_setup_result = OdooSetupQAAgent(self.registry).run(module_plan_path)
        results.append(odoo_setup_result)

        findings = [finding for result in results for finding in result.findings]
        severity_counts = {
            "critical": sum(1 for f in findings if f.severity == "critical"),
            "high": sum(1 for f in findings if f.severity == "high"),
            "medium": sum(1 for f in findings if f.severity == "medium"),
            "low": sum(1 for f in findings if f.severity == "low"),
            "info": sum(1 for f in findings if f.severity == "info"),
        }

        overall_status = (
            "fail"
            if severity_counts["critical"] > 0 or severity_counts["high"] > 0
            else "pass"
        )

        return {
            "overall_status": overall_status,
            "generated_at": datetime.now().isoformat(),
            "module_plan": str(module_plan_path),
            "severity_counts": severity_counts,
            "agents": [asdict(result) for result in results],
        }


def _render_markdown(report: dict) -> str:
    lines: list[str] = []
    lines.append("# Swarm QA Report")
    lines.append("")
    lines.append(f"- Overall status: {report['overall_status']}")
    lines.append(f"- Generated at: {report['generated_at']}")
    lines.append(f"- Module plan: {report['module_plan']}")
    if report.get("registry"):
        lines.append(f"- Registry: {report['registry']}")
    lines.append("")
    lines.append("## Severity Counts")
    for severity, count in report["severity_counts"].items():
        lines.append(f"- {severity}: {count}")
    lines.append("")
    lines.append("## Agent Results")

    for agent in report["agents"]:
        lines.append(f"### {agent['agent_name']}")
        lines.append(f"- Status: {agent['status']}")
        lines.append(f"- Summary: {agent['summary']}")
        if agent["findings"]:
            lines.append("- Findings:")
            for finding in agent["findings"]:
                lines.append(
                    f"  - [{finding['severity']}] {finding['message']}"
                    + (f" | evidence: {finding['evidence']}" if finding["evidence"] else "")
                    + (
                        f" | recommendation: {finding['recommendation']}"
                        if finding["recommendation"]
                        else ""
                    )
                )
        else:
            lines.append("- Findings: none")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run QA agents against swarm outputs.")
    parser.add_argument(
        "--module-plan",
        required=True,
        help="Path to module-plan-*.json generated by swarm orchestrator.",
    )
    parser.add_argument(
        "--output-dir",
        default="./outputs",
        help="Directory to write QA report artifacts.",
    )
    parser.add_argument(
        "--registry",
        default=None,
        help="Module registry JSON file (optional; auto-resolved from module plan version when omitted).",
    )
    parser.add_argument(
        "--workspace-root",
        default=str(Path(__file__).resolve().parents[2]),
        help="Project workspace root for architecture/codebase checks.",
    )
    args = parser.parse_args()

    module_plan_path = Path(args.module_plan)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    module_plan = json.loads(module_plan_path.read_text())
    resolved_registry = resolve_registry_path(
        str(module_plan.get("odoo_version", "")),
        args.registry or module_plan.get("module_registry"),
    )
    registry = ModuleRegistry.from_json(resolved_registry)
    orchestrator = QAOrchestrator(Path(args.workspace_root), registry)
    report = orchestrator.run(module_plan_path)
    report["registry"] = str(resolved_registry)

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    json_path = output_dir / f"qa-report-{timestamp}.json"
    md_path = output_dir / f"qa-report-{timestamp}.md"
    json_path.write_text(json.dumps(report, indent=2))
    md_path.write_text(_render_markdown(report))

    print("QA run complete.")
    print(f"QA JSON: {json_path}")
    print(f"QA Markdown: {md_path}")
    print(f"Overall status: {report['overall_status']}")


if __name__ == "__main__":
    main()
