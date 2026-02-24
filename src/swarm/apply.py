"""Apply a generated module plan to an Odoo/OpenERP instance via XML-RPC."""

from __future__ import annotations

import argparse
import json
import os
import time
import xmlrpc.client
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


class ApplyError(Exception):
    """Application-level error for module plan execution."""


def _parse_major(version: str) -> int | None:
    version = (version or "").strip()
    if not version:
        return None
    head = version.split(".", 1)[0]
    if head.isdigit():
        return int(head)
    return None


@dataclass
class RPCConfig:
    url: str
    database: str
    username: str
    password: str
    odoo_version: str = "17.0"


class OdooRPC:
    """XML-RPC adapter supporting both legacy OpenERP and modern Odoo endpoints."""

    def __init__(self, config: RPCConfig):
        self.config = config
        self.base_url = config.url.rstrip("/")
        major = _parse_major(config.odoo_version)
        self.legacy = major is not None and major < 8

        if self.legacy:
            common_url = f"{self.base_url}/xmlrpc/common"
            object_url = f"{self.base_url}/xmlrpc/object"
        else:
            common_url = f"{self.base_url}/xmlrpc/2/common"
            object_url = f"{self.base_url}/xmlrpc/2/object"

        self.common = xmlrpc.client.ServerProxy(common_url, allow_none=True)
        self.models = xmlrpc.client.ServerProxy(object_url, allow_none=True)
        self.uid: int | None = None

    def login(self) -> None:
        if self.legacy:
            uid = self.common.login(
                self.config.database,
                self.config.username,
                self.config.password,
            )
        else:
            uid = self.common.authenticate(
                self.config.database,
                self.config.username,
                self.config.password,
                {},
            )
        if not uid:
            raise ApplyError("Authentication failed for provided Odoo credentials.")
        self.uid = int(uid)

    def _execute(self, model: str, method: str, *args: Any, **kwargs: Any) -> Any:
        if self.uid is None:
            raise ApplyError("Not authenticated. Call login() first.")
        if self.legacy:
            return self.models.execute(
                self.config.database,
                self.uid,
                self.config.password,
                model,
                method,
                *args,
            )
        return self.models.execute_kw(
            self.config.database,
            self.uid,
            self.config.password,
            model,
            method,
            list(args),
            kwargs or {},
        )

    def update_module_list(self) -> None:
        try:
            self._execute("ir.module.module", "update_list")
        except xmlrpc.client.Fault as exc:
            raise ApplyError(f"Failed to update module list: {exc}") from exc

    def find_module_id(self, technical_name: str) -> int | None:
        ids = self._execute("ir.module.module", "search", [("name", "=", technical_name)])
        if not ids:
            return None
        return int(ids[0])

    def get_module_state(self, module_id: int) -> str:
        rows = self._execute("ir.module.module", "read", [module_id], ["state"])
        if isinstance(rows, dict):
            return str(rows.get("state", "unknown"))
        if isinstance(rows, list) and rows:
            return str(rows[0].get("state", "unknown"))
        return "unknown"

    def install_module(self, module_id: int) -> None:
        # Newer Odoo supports immediate install, legacy does not.
        if not self.legacy:
            try:
                self._execute("ir.module.module", "button_immediate_install", [module_id])
                return
            except xmlrpc.client.Fault:
                pass
        self._execute("ir.module.module", "button_install", [module_id])


@dataclass
class ModuleApplyResult:
    technical_name: str
    status: str
    details: str = ""


@dataclass
class ApplyReport:
    module_plan: str
    dry_run: bool
    odoo_version: str
    odoo_edition: str
    target_url: str = ""
    target_database: str = ""
    registry: str = ""
    install_order: list[str] = field(default_factory=list)
    results: list[ModuleApplyResult] = field(default_factory=list)
    started_at: str = ""
    completed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["results"] = [asdict(r) for r in self.results]
        return payload


def _topological_order(selected_modules: list[dict[str, Any]]) -> list[str]:
    dependency_map: dict[str, set[str]] = {}
    for module in selected_modules:
        name = str(module.get("technical_name", "")).strip()
        if not name:
            continue
        dependency_map[name] = set(module.get("dependencies", []))

    selected_names = set(dependency_map)
    for name in list(dependency_map):
        dependency_map[name] = {dep for dep in dependency_map[name] if dep in selected_names}

    order: list[str] = []
    temporary: set[str] = set()
    permanent: set[str] = set()

    def _sort_key(name: str) -> tuple[int, str]:
        return (0, name) if name == "base" else (1, name)

    def visit(node: str) -> None:
        if node in permanent:
            return
        if node in temporary:
            raise ApplyError(f"Dependency cycle detected at module '{node}'.")
        temporary.add(node)
        for dep in sorted(dependency_map.get(node, set()), key=_sort_key):
            visit(dep)
        temporary.remove(node)
        permanent.add(node)
        order.append(node)

    for module_name in sorted(dependency_map, key=_sort_key):
        visit(module_name)
    return order


def _wait_until_installed(
    rpc: OdooRPC,
    module_id: int,
    technical_name: str,
    timeout_seconds: int,
    poll_seconds: int,
) -> tuple[bool, str]:
    start = time.time()
    while (time.time() - start) <= timeout_seconds:
        state = rpc.get_module_state(module_id)
        if state == "installed":
            return True, "installed"
        if state in {"uninstallable"}:
            return False, state
        time.sleep(poll_seconds)
    return False, "timeout"


def apply_module_plan(
    module_plan_path: Path,
    dry_run: bool,
    rpc_config: RPCConfig | None,
    update_module_list: bool,
    fail_on_missing: bool,
    timeout_seconds: int,
    poll_seconds: int,
) -> ApplyReport:
    plan = json.loads(module_plan_path.read_text())
    selected_modules = plan.get("selected_modules", [])
    install_order = _topological_order(selected_modules)

    report = ApplyReport(
        module_plan=str(module_plan_path),
        dry_run=dry_run,
        odoo_version=str(plan.get("odoo_version", "")),
        odoo_edition=str(plan.get("odoo_edition", "")),
        target_url=rpc_config.url if rpc_config else "",
        target_database=rpc_config.database if rpc_config else "",
        registry=str(plan.get("module_registry", "")),
        install_order=install_order,
        started_at=datetime.now().isoformat(),
    )

    selected_by_name = {
        str(module.get("technical_name")): module
        for module in selected_modules
        if module.get("technical_name")
    }

    if dry_run:
        for module_name in install_order:
            report.results.append(
                ModuleApplyResult(
                    technical_name=module_name,
                    status="dry_run",
                    details="Planned installation only; no RPC actions executed.",
                )
            )
        report.completed_at = datetime.now().isoformat()
        return report

    if rpc_config is None:
        raise ApplyError("RPC configuration is required unless running in --dry-run mode.")

    rpc = OdooRPC(rpc_config)
    rpc.login()

    if update_module_list:
        rpc.update_module_list()

    for module_name in install_order:
        module_id = rpc.find_module_id(module_name)
        if module_id is None:
            status = "missing"
            details = "Module not found in target instance."
            report.results.append(ModuleApplyResult(module_name, status, details))
            if fail_on_missing:
                raise ApplyError(
                    f"Module '{module_name}' not found in target instance and --fail-on-missing was enabled."
                )
            continue

        current_state = rpc.get_module_state(module_id)
        if current_state == "installed":
            report.results.append(
                ModuleApplyResult(module_name, "already_installed", "Module already installed.")
            )
            continue

        try:
            rpc.install_module(module_id)
        except xmlrpc.client.Fault as exc:
            report.results.append(
                ModuleApplyResult(module_name, "failed", f"Install RPC failed: {exc}")
            )
            continue

        success, state = _wait_until_installed(
            rpc,
            module_id,
            module_name,
            timeout_seconds=timeout_seconds,
            poll_seconds=poll_seconds,
        )
        if success:
            report.results.append(ModuleApplyResult(module_name, "installed", "Installed successfully."))
        else:
            report.results.append(
                ModuleApplyResult(
                    module_name,
                    "failed",
                    f"Did not reach installed state (last state: {state}).",
                )
            )

    report.completed_at = datetime.now().isoformat()
    return report


def _report_exit_code(report: ApplyReport) -> int:
    has_failed = any(result.status == "failed" for result in report.results)
    if has_failed:
        return 2
    return 0


def _load_rpc_config(args: argparse.Namespace, module_plan: dict[str, Any]) -> RPCConfig | None:
    if args.dry_run:
        return None

    url = args.url or os.getenv("ODOO_URL") or os.getenv("OPENERP_URL")
    database = args.database or os.getenv("ODOO_DB") or os.getenv("OPENERP_DB")
    username = args.username or os.getenv("ODOO_USER") or os.getenv("OPENERP_USER")
    password = args.password or os.getenv("ODOO_PASSWORD") or os.getenv("OPENERP_PASSWORD")

    missing = [
        field
        for field, value in {
            "url": url,
            "database": database,
            "username": username,
            "password": password,
        }.items()
        if not value
    ]
    if missing:
        missing_text = ", ".join(missing)
        raise ApplyError(
            "Missing RPC credentials for non-dry-run apply: "
            f"{missing_text}. Provide flags or environment variables "
            "(ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PASSWORD)."
        )

    return RPCConfig(
        url=str(url),
        database=str(database),
        username=str(username),
        password=str(password),
        odoo_version=str(module_plan.get("odoo_version", "17.0")),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply a swarm module plan to Odoo/OpenERP via XML-RPC.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.swarm.apply --module-plan outputs/module-plan-20260205195122.json --dry-run
  python -m src.swarm.apply --module-plan outputs/module-plan-20260205195122.json --url http://localhost:8069 --database mydb --username admin --password admin
        """,
    )
    parser.add_argument("--module-plan", required=True, help="Path to module-plan-*.json.")
    parser.add_argument("--dry-run", action="store_true", help="Do not call RPC; only validate and plan order.")
    parser.add_argument("--url", help="Odoo base URL (or env ODOO_URL).")
    parser.add_argument("--database", help="Odoo database name (or env ODOO_DB).")
    parser.add_argument("--username", help="Odoo login username (or env ODOO_USER).")
    parser.add_argument("--password", help="Odoo login password (or env ODOO_PASSWORD).")
    parser.add_argument(
        "--output-dir",
        default="./outputs",
        help="Directory where apply report JSON is written.",
    )
    parser.add_argument(
        "--skip-module-list-update",
        action="store_true",
        help="Skip ir.module.module.update_list before applying modules.",
    )
    parser.add_argument(
        "--fail-on-missing",
        action="store_true",
        help="Stop immediately if any selected module is missing on target instance.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=300,
        help="Max wait time per module for installed state.",
    )
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=5,
        help="Polling interval while waiting for module install completion.",
    )
    args = parser.parse_args()

    module_plan_path = Path(args.module_plan).resolve()
    if not module_plan_path.exists():
        raise SystemExit(f"Module plan not found: {module_plan_path}")

    plan = json.loads(module_plan_path.read_text())
    try:
        rpc_config = _load_rpc_config(args, plan)
        report = apply_module_plan(
            module_plan_path=module_plan_path,
            dry_run=args.dry_run,
            rpc_config=rpc_config,
            update_module_list=not args.skip_module_list_update,
            fail_on_missing=args.fail_on_missing,
            timeout_seconds=args.timeout_seconds,
            poll_seconds=args.poll_seconds,
        )
    except ApplyError as exc:
        raise SystemExit(str(exc)) from exc

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    report_path = output_dir / f"apply-report-{timestamp}.json"
    report_path.write_text(json.dumps(report.to_dict(), indent=2))

    print("Apply run complete.")
    print(f"Report: {report_path}")
    installed = sum(1 for result in report.results if result.status == "installed")
    skipped = sum(1 for result in report.results if result.status == "already_installed")
    missing = sum(1 for result in report.results if result.status == "missing")
    failed = sum(1 for result in report.results if result.status == "failed")
    dry = sum(1 for result in report.results if result.status == "dry_run")
    print(
        "Summary: "
        f"installed={installed}, already_installed={skipped}, "
        f"missing={missing}, failed={failed}, dry_run={dry}"
    )
    raise SystemExit(_report_exit_code(report))


if __name__ == "__main__":
    main()
