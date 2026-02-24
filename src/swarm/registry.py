"""Module registry loader and lookup utilities."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ModuleDefinition:
    technical_name: str
    name: str
    domain: str
    description: str
    dependencies: list[str]
    tags: list[str]
    requires_enterprise: bool
    supported_versions: list[str]
    community_alternatives: list[str]
    configuration_steps: list[str]
    conflicts_with: list[str]


class ModuleRegistry:
    def __init__(self, modules: dict[str, ModuleDefinition], source_path: str = ""):
        self._modules = modules
        self.source_path = source_path

    @classmethod
    def from_json(cls, path: str | Path) -> "ModuleRegistry":
        path_obj = Path(path)
        data = json.loads(path_obj.read_text())
        modules: dict[str, ModuleDefinition] = {}
        for item in data:
            modules[item["technical_name"]] = ModuleDefinition(
                technical_name=item["technical_name"],
                name=item["name"],
                domain=item["domain"],
                description=item.get("description", ""),
                dependencies=item.get("dependencies", []),
                tags=item.get("tags", []),
                requires_enterprise=bool(item.get("requires_enterprise", False)),
                supported_versions=item.get("supported_versions", []),
                community_alternatives=item.get("community_alternatives", []),
                configuration_steps=item.get("configuration_steps", []),
                conflicts_with=item.get("conflicts_with", []),
            )
        return cls(modules, source_path=str(path_obj.resolve()))

    def get(self, technical_name: str) -> ModuleDefinition | None:
        return self._modules.get(technical_name)

    def list_all(self) -> list[ModuleDefinition]:
        return list(self._modules.values())

    def find_by_tag(self, tag: str) -> list[ModuleDefinition]:
        return [m for m in self._modules.values() if tag in m.tags]

    def is_compatible(self, technical_name: str, target_version: str) -> bool:
        module = self.get(technical_name)
        if not module:
            return False
        supported_versions = module.supported_versions
        if not supported_versions:
            return True
        return any(self._matches_version_pattern(pattern, target_version) for pattern in supported_versions)

    @staticmethod
    def _matches_version_pattern(pattern: str, target_version: str) -> bool:
        normalized_pattern = pattern.strip().lower()
        normalized_target = target_version.strip().lower()
        if not normalized_pattern or not normalized_target:
            return False
        if normalized_pattern == normalized_target:
            return True
        if normalized_pattern.endswith(".x"):
            return normalized_target.startswith(normalized_pattern[:-1])
        if normalized_pattern.endswith("*"):
            return normalized_target.startswith(normalized_pattern[:-1])
        if "." not in normalized_pattern and normalized_pattern.isdigit():
            return normalized_target == normalized_pattern or normalized_target.startswith(f"{normalized_pattern}.")
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            name: {
                "technical_name": mod.technical_name,
                "name": mod.name,
                "domain": mod.domain,
                "description": mod.description,
                "dependencies": mod.dependencies,
                "tags": mod.tags,
                "requires_enterprise": mod.requires_enterprise,
                "supported_versions": mod.supported_versions,
                "community_alternatives": mod.community_alternatives,
                "configuration_steps": mod.configuration_steps,
                "conflicts_with": mod.conflicts_with,
            }
            for name, mod in self._modules.items()
        }
