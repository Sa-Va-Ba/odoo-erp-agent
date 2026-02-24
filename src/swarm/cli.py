"""CLI for running the module-selection swarm."""

from __future__ import annotations

import argparse

from .orchestrator import SwarmOrchestrator
from .registry import ModuleRegistry
from .registry_resolver import resolve_registry_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Odoo module selection swarm",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.swarm.cli --input outputs/requirements-interview-20260205183339.json
  python -m src.swarm.cli --input outputs/requirements.json --edition enterprise
  python -m src.swarm.cli --input outputs/requirements.json --odoo-version 5.3
        """,
    )

    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Path to interview output JSON",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        default="./outputs",
        help="Output directory",
    )
    parser.add_argument(
        "--registry",
        default=None,
        help="Module registry JSON file (optional; auto-selected from --odoo-version when omitted)",
    )
    parser.add_argument(
        "--edition",
        default="community",
        choices=["unknown", "community", "enterprise"],
        help="Odoo edition (affects enterprise module flags)",
    )
    parser.add_argument(
        "--odoo-version",
        default="17.0",
        help="Target Odoo version for planning metadata (for example: 17.0, 16.0, 5.3)",
    )

    args = parser.parse_args()

    registry_path = resolve_registry_path(args.odoo_version, args.registry)
    registry = ModuleRegistry.from_json(registry_path)
    orchestrator = SwarmOrchestrator(
        registry,
        edition=args.edition,
        odoo_version=args.odoo_version,
    )
    output = orchestrator.run(args.input, args.output_dir)

    print("\nSwarm run complete.")
    print(f"Module plan: {output.module_plan_path}")
    print(f"Config tasks: {output.config_tasks_path}")
    print(f"Implementation spec: {output.implementation_spec_path}")
    print(f"Audit log: {output.audit_path}")
    print(f"Registry: {registry_path}")


if __name__ == "__main__":
    main()
