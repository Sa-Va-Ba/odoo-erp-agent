"""Helpers for resolving module registry files by target Odoo version."""

from __future__ import annotations

from pathlib import Path


KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "knowledge"
DEFAULT_REGISTRY = KNOWLEDGE_DIR / "odoo_modules.json"
REGISTRY_5_3 = KNOWLEDGE_DIR / "odoo_modules_5_3.json"


def resolve_registry_path(odoo_version: str, explicit_registry: str | None = None) -> Path:
    if explicit_registry:
        return Path(explicit_registry).expanduser().resolve()

    version = (odoo_version or "").strip()
    if version.startswith("5.") or version == "5":
        return REGISTRY_5_3

    return DEFAULT_REGISTRY
