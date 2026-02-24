"""Normalize interview output into a consistent structure for agents."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .types import NormalizedInterview
from ..signals import (
    detect_signals_multi,
    SIGNAL_PATTERNS as _SIGNAL_PATTERNS,
)


def load_interview(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def normalize_interview(data: dict[str, Any]) -> NormalizedInterview:
    raw_responses = data.get("raw_responses", {}) or {}
    response_texts: list[str] = []
    for domain_entries in raw_responses.values():
        for entry in domain_entries or []:
            response = str(entry.get("response", "")).strip()
            if response:
                response_texts.append(response)

    raw_text = "\n".join(response_texts)

    # Use shared negation-aware signal detection
    signal_result = detect_signals_multi(response_texts)
    signals: dict[str, int] = {k: 0 for k in _SIGNAL_PATTERNS}
    signals.update(signal_result.active_signals)
    evidence_map: dict[str, list[str]] = {k: [] for k in _SIGNAL_PATTERNS}
    evidence_map.update(signal_result.evidence)

    company_profile = data.get("company_profile", {}) or {}
    requirements = data.get("requirements", {}) or {}

    # Extract employee count from raw text if not in profile
    if not company_profile.get("employee_count"):
        extracted_count = extract_employee_count(company_profile, raw_text)
        if extracted_count:
            company_profile["employee_count"] = extracted_count

    pain_points = data.get("pain_points", []) or []
    systems_mentioned = data.get("systems_mentioned", []) or []

    metadata: dict[str, Any] = {
        "interview_completed": data.get("interview_completed"),
        "llm_enhanced": data.get("llm_enhanced"),
        "interview_summary": data.get("interview_summary", {}),
    }

    return NormalizedInterview(
        project_id=str(data.get("project_id", "")),
        client_name=str(data.get("client_name", "")),
        industry=str(data.get("industry", "")),
        raw_text=raw_text,
        signals=signals,
        evidence_map=evidence_map,
        company_profile=company_profile,
        requirements=requirements,
        pain_points=pain_points,
        systems_mentioned=systems_mentioned,
        metadata=metadata,
    )


def extract_employee_count(profile: dict[str, Any], raw_text: str) -> int | None:
    if isinstance(profile.get("employee_count"), int) and profile.get("employee_count"):
        return int(profile["employee_count"])

    match = re.search(r"(\d{1,5})\s*(fte|employees|staff)", raw_text, re.IGNORECASE)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None
