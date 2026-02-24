"""Moderation and consolidation of agent outputs."""

from __future__ import annotations

from collections import defaultdict

from .registry import ModuleRegistry
from .types import AgentResult, ModuleCandidate, SwarmDecision


class SwarmModerator:
    def __init__(
        self,
        registry: ModuleRegistry,
        edition: str = "community",
        odoo_version: str = "17.0",
    ):
        self.registry = registry
        self.edition = edition.lower()
        self.odoo_version = odoo_version

    def consolidate(self, results: list[AgentResult]) -> SwarmDecision:
        module_buckets: dict[str, list[ModuleCandidate]] = defaultdict(list)
        notes: list[str] = []
        risks: list[str] = []

        for result in results:
            if result.notes:
                notes.extend(result.notes)
            for candidate in result.module_candidates:
                module_buckets[candidate.technical_name].append(candidate)

        selected: list[ModuleCandidate] = []
        rejected: list[ModuleCandidate] = []
        open_questions: list[str] = []
        coverage_map: dict[str, list[str]] = defaultdict(list)

        for tech_name, candidates in module_buckets.items():
            best = max(candidates, key=lambda c: c.confidence)
            evidence = []
            reasons = []
            conflicts = set(best.conflicts_with)
            requires_enterprise = best.requires_enterprise
            for cand in candidates:
                evidence.extend(cand.evidence)
                reasons.append(cand.reason)
                conflicts.update(cand.conflicts_with)
                if cand.requires_enterprise:
                    requires_enterprise = True
            aggregated = ModuleCandidate(
                technical_name=best.technical_name,
                name=best.name,
                domain=best.domain,
                reason=" / ".join(sorted(set(reasons))),
                confidence=best.confidence,
                evidence=list(dict.fromkeys(evidence))[:5],
                dependencies=best.dependencies,
                priority=best.priority,
                requires_enterprise=requires_enterprise,
                conflicts_with=sorted(conflicts),
            )

            if requires_enterprise and self.edition == "unknown":
                open_questions.append(
                    f"Confirm Odoo edition for enterprise module '{aggregated.name}' ({aggregated.technical_name})."
                )
            if requires_enterprise and self.edition == "community":
                rejected.append(aggregated)
                alternatives = self._find_community_alternatives(aggregated)
                if alternatives:
                    notes.append(
                        f"Excluded enterprise module '{aggregated.technical_name}' in community mode. "
                        f"Consider: {', '.join(alternatives)}."
                    )
                else:
                    notes.append(
                        f"Excluded enterprise module '{aggregated.technical_name}' in community mode."
                    )
                    open_questions.append(
                        f"No free alternative mapped for '{aggregated.technical_name}'. "
                        "Confirm custom implementation scope."
                    )
                continue

            if not self.registry.is_compatible(aggregated.technical_name, self.odoo_version):
                rejected.append(aggregated)
                open_questions.append(
                    f"Module '{aggregated.technical_name}' is not mapped for Odoo {self.odoo_version}. "
                    "Confirm alternate module or custom implementation."
                )
                notes.append(
                    f"Excluded incompatible module '{aggregated.technical_name}' for Odoo {self.odoo_version}."
                )
                continue

            selected.append(aggregated)

        selected, conflict_questions = self._resolve_conflicts(selected)
        open_questions.extend(conflict_questions)
        for module in selected:
            coverage_map[module.domain].append(module.technical_name)

        if notes:
            risks.extend([note for note in notes if "Detected" in note])

        return SwarmDecision(
            selected_modules=sorted(selected, key=lambda c: c.technical_name),
            rejected_modules=rejected,
            open_questions=sorted(set(open_questions)),
            risks=sorted(set(risks)),
            notes=sorted(set(notes)),
            coverage_map={k: sorted(set(v)) for k, v in coverage_map.items()},
            agent_results=results,
        )

    def _find_community_alternatives(self, enterprise_module: ModuleCandidate) -> list[str]:
        mapped = self.registry.get(enterprise_module.technical_name)
        if mapped and mapped.community_alternatives:
            explicit: list[str] = []
            for alternative_name in mapped.community_alternatives:
                alternative_module = self.registry.get(alternative_name)
                if alternative_module and not alternative_module.requires_enterprise:
                    explicit.append(alternative_name)
            if explicit:
                return sorted(set(explicit))

        alternatives: list[str] = []
        for module in self.registry.list_all():
            if module.technical_name == enterprise_module.technical_name:
                continue
            if module.domain != enterprise_module.domain:
                continue
            if module.requires_enterprise:
                continue
            alternatives.append(module.technical_name)
        return sorted(set(alternatives))

    def _resolve_conflicts(self, selected: list[ModuleCandidate]) -> tuple[list[ModuleCandidate], list[str]]:
        selected_by_name = {m.technical_name: m for m in selected}
        open_questions: list[str] = []
        to_remove: set[str] = set()

        for module in selected:
            for conflict in module.conflicts_with:
                if conflict in selected_by_name and conflict not in to_remove:
                    other = selected_by_name[conflict]
                    if module.confidence >= other.confidence:
                        to_remove.add(other.technical_name)
                        open_questions.append(
                            f"Conflict between '{module.technical_name}' and '{other.technical_name}'. Confirm preferred approach."
                        )
                    else:
                        to_remove.add(module.technical_name)
                        open_questions.append(
                            f"Conflict between '{other.technical_name}' and '{module.technical_name}'. Confirm preferred approach."
                        )

        filtered = [m for m in selected if m.technical_name not in to_remove]
        return filtered, open_questions
