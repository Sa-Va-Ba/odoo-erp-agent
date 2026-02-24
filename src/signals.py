"""
Shared signal detection for interview response analysis.

Central module for detecting business domain signals from text responses.
Used by interview agents, normalizer, and spec generation.

Key improvement over the previous approach:
- Negation-aware: "We don't manufacture" won't trigger manufacturing
- Confidence scoring: positive, negative, planned/future
- Single source of truth for all pattern matching
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SignalStrength(Enum):
    """How confident we are about a detected signal."""
    POSITIVE = "positive"      # Clearly confirmed: "We manufacture electronics"
    PLANNED = "planned"        # Future intent: "We plan to start manufacturing"
    NEGATIVE = "negative"      # Explicitly denied: "We don't manufacture"
    MENTION = "mention"        # Mentioned but unclear: "manufacturing is common in our industry"


@dataclass
class SignalMatch:
    """A single detected signal with context."""
    domain: str
    strength: SignalStrength
    matched_pattern: str
    context_snippet: str  # The sentence/clause where it was found
    confidence: float     # 0.0 to 1.0


@dataclass
class SignalResult:
    """Aggregated signal detection result for a piece of text."""
    signals: dict[str, int] = field(default_factory=dict)           # domain -> positive count
    negative_signals: dict[str, int] = field(default_factory=dict)  # domain -> negative count
    planned_signals: dict[str, int] = field(default_factory=dict)   # domain -> planned count
    evidence: dict[str, list[str]] = field(default_factory=dict)    # domain -> evidence snippets
    matches: list[SignalMatch] = field(default_factory=list)        # all individual matches

    @property
    def active_signals(self) -> dict[str, int]:
        """Signals that are confirmed (positive or planned, not negated)."""
        active = {}
        for domain, count in self.signals.items():
            neg_count = self.negative_signals.get(domain, 0)
            # Only count as active if positives outweigh negatives
            net = count - neg_count + self.planned_signals.get(domain, 0)
            if net > 0:
                active[domain] = net
        return active

    def is_confirmed(self, domain: str) -> bool:
        """Check if a domain is positively confirmed."""
        return self.signals.get(domain, 0) > self.negative_signals.get(domain, 0)

    def is_denied(self, domain: str) -> bool:
        """Check if a domain is explicitly denied."""
        return (
            self.negative_signals.get(domain, 0) > 0
            and self.signals.get(domain, 0) == 0
        )

    def is_planned(self, domain: str) -> bool:
        """Check if a domain is planned for the future."""
        return self.planned_signals.get(domain, 0) > 0


# ── Pattern definitions ──────────────────────────────────────────────────────

SIGNAL_PATTERNS: dict[str, list[str]] = {
    "ecommerce": [
        "ecommerce", "e-commerce", "online store", "webshop",
        "online sales", "web shop", "online shop",
    ],
    "website": [
        "website", "web presence", "landing page",
    ],
    "subscriptions": [
        "subscription", "recurring", "monthly plan", "annual plan",
        "renewal", "recurring revenue", "saas",
    ],
    "manufacturing": [
        "manufacturing", "manufacture", "production", "assembly", "bom",
        "bill of materials", "make to order", "we manufacture",
        "we produce", "factory", "fabricat",
    ],
    "outsourced_manufacturing": [
        "third-party manufacturer", "contract manufacturer",
        "co-manufacturer", "outsourced production",
        "external manufacturer", "subcontract",
    ],
    "inventory": [
        "inventory", "warehouse", "stock", "fulfillment",
        "logistics", "storage", "shelf", "bin", "pick and pack",
    ],
    "purchase": [
        "supplier", "vendor", "purchase order", "procure",
        "procurement", "buying", "sourcing", "reorder",
    ],
    "accounting": [
        "accounting", "bookkeeping", "general ledger",
        "accounts payable", "accounts receivable", "financial reporting",
        "chart of accounts", "reconciliation",
    ],
    "finance": [
        "invoice", "invoicing", "payment", "tax", "vat",
        "payable", "receivable", "budget", "p&l",
        "profit and loss", "balance sheet",
    ],
    "crm": [
        "crm", "lead", "opportunity", "pipeline", "sales team",
        "customer relationship", "prospect", "lead nurturing",
    ],
    "sales": [
        "sales", "selling", "quotation", "pricing", "b2b", "b2c",
        "wholesale", "retail", "deal", "proposal", "quote",
    ],
    "project": [
        "project", "timesheet", "billable", "milestone",
        "deliverable", "client work", "consultant",
    ],
    "hr": [
        "employee", "payroll", "recruit", "hiring", "staff",
        "workforce", "human resources", "fte", "leave",
        "vacation", "attendance", "department",
    ],
    "support": [
        "support", "helpdesk", "ticket", "customer service",
        "issue tracking", "service desk",
    ],
    "shipping": [
        "shipping", "carrier", "delivery", "dispatch",
        "courier", "freight", "tracking number",
    ],
    "pos": [
        "point of sale", "pos system", "retail store",
        "cash register", "checkout counter",
    ],
    "quality": [
        "quality control", "inspection", "qc",
        "quality assurance", "quality check",
    ],
    "maintenance": [
        "maintenance", "equipment", "repair",
        "preventive maintenance", "asset management",
    ],
    "marketing": [
        "marketing automation", "campaign", "email marketing",
        "lead nurturing", "newsletter", "marketing campaign",
    ],
    "data_migration": [
        "migrate", "migration", "import data", "legacy system",
        "data transfer", "existing data", "historical data",
    ],
    "integration": [
        "integrate", "api", "connector", "sync",
        "integration", "external system", "third-party",
    ],
}

# Negation indicators — if these appear within NEGATION_WINDOW words
# before a pattern match, the signal is treated as negative
NEGATION_WORDS = {
    "don't", "dont", "do not", "doesn't", "doesnt", "does not",
    "didn't", "didnt", "did not", "won't", "wont", "will not",
    "wouldn't", "wouldnt", "would not", "can't", "cant", "cannot",
    "aren't", "arent", "are not", "isn't", "isnt", "is not",
    "haven't", "havent", "have not", "hasn't", "hasnt", "has not",
    "never", "no", "not", "without", "lack", "neither", "nor",
    "stop", "stopped", "quit", "dropped", "eliminated",
}

# Future/planned indicators — signal is real but not current
FUTURE_WORDS = {
    "plan to", "planning to", "want to", "going to", "will",
    "hope to", "looking to", "considering", "thinking about",
    "next year", "in the future", "eventually", "soon",
    "might", "maybe", "potentially", "explore",
}

# Words that look like domain terms but are too generic to be meaningful
FALSE_POSITIVE_CONTEXTS = {
    "sales": ["after-sales", "for sale"],  # "for sale" is generic
    "project": ["project manager position"],  # HR context, not PM module
    "support": ["support team member"],  # could be generic
}

NEGATION_WINDOW = 8  # words before the match to scan for negation


# ── Core detection logic ─────────────────────────────────────────────────────

def _split_sentences(text: str) -> list[str]:
    """Split text into sentences for per-sentence analysis."""
    # Split on sentence-ending punctuation, keeping the delimiter
    parts = re.split(r'(?<=[.!?])\s+', text)
    # Also split on semicolons and newlines
    sentences = []
    for part in parts:
        sentences.extend(re.split(r'[;\n]+', part))
    return [s.strip() for s in sentences if s.strip()]


_CLAUSE_BOUNDARIES = {"but", "however", "although", "though", "yet", "whereas", "while", "instead"}

def _check_negation(text_lower: str, match_start: int) -> bool:
    """Check if there's a negation within NEGATION_WINDOW words before the match.

    Stops at clause boundaries (but, however, etc.) so negation
    in one clause doesn't bleed into a contrasting clause.
    """
    # Get the text before the match
    prefix = text_lower[:match_start]
    # Get the last N words
    words_before = prefix.split()[-NEGATION_WINDOW:]

    # Truncate at the last clause boundary (if any)
    for i in range(len(words_before) - 1, -1, -1):
        if words_before[i].strip(",.;:") in _CLAUSE_BOUNDARIES:
            words_before = words_before[i + 1:]
            break

    prefix_text = " ".join(words_before)

    for neg in NEGATION_WORDS:
        if neg in prefix_text:
            return True
    return False


def _check_future(text_lower: str, match_start: int) -> bool:
    """Check if there's a future/planning indicator near the match."""
    # Check a window around the match (before and after)
    window_start = max(0, match_start - 60)
    window_end = min(len(text_lower), match_start + 60)
    window = text_lower[window_start:window_end]

    for fut in FUTURE_WORDS:
        if fut in window:
            return True
    return False


def detect_signals(text: str) -> SignalResult:
    """
    Detect business domain signals from text with negation awareness.

    Args:
        text: The response text to analyze

    Returns:
        SignalResult with positive, negative, and planned signal counts
    """
    result = SignalResult()
    text_lower = text.lower()
    sentences = _split_sentences(text_lower)

    for domain, patterns in SIGNAL_PATTERNS.items():
        for pattern in patterns:
            # Find all occurrences of the pattern
            start = 0
            while True:
                idx = text_lower.find(pattern, start)
                if idx == -1:
                    break
                start = idx + 1

                # Determine which sentence contains this match
                context = text_lower[max(0, idx - 50):min(len(text_lower), idx + len(pattern) + 50)]

                # Check for negation
                is_negated = _check_negation(text_lower, idx)
                is_future = _check_future(text_lower, idx)

                if is_negated:
                    strength = SignalStrength.NEGATIVE
                    result.negative_signals[domain] = result.negative_signals.get(domain, 0) + 1
                elif is_future and not _text_has_current_confirmation(text_lower, domain, patterns):
                    strength = SignalStrength.PLANNED
                    result.planned_signals[domain] = result.planned_signals.get(domain, 0) + 1
                else:
                    strength = SignalStrength.POSITIVE
                    result.signals[domain] = result.signals.get(domain, 0) + 1

                match = SignalMatch(
                    domain=domain,
                    strength=strength,
                    matched_pattern=pattern,
                    context_snippet=context.strip(),
                    confidence=0.8 if strength == SignalStrength.POSITIVE else 0.5,
                )
                result.matches.append(match)

                # Store evidence (max 3 per domain)
                if domain not in result.evidence:
                    result.evidence[domain] = []
                if len(result.evidence[domain]) < 3:
                    # Use original text for evidence
                    orig_context = text[max(0, idx - 50):min(len(text), idx + len(pattern) + 50)].strip()
                    result.evidence[domain].append(orig_context)

                # Only count each pattern once per domain per text
                break

    return result


def _text_has_current_confirmation(text_lower: str, domain: str, patterns: list[str]) -> bool:
    """Check if there's also a current-tense confirmation of this domain elsewhere."""
    # Look for patterns that are NOT preceded by future words
    for pattern in patterns:
        idx = text_lower.find(pattern)
        if idx != -1:
            if not _check_future(text_lower, idx) and not _check_negation(text_lower, idx):
                return True
    return False


def detect_signals_multi(responses: list[str]) -> SignalResult:
    """
    Detect signals across multiple response texts and aggregate.

    Args:
        responses: List of response texts

    Returns:
        Aggregated SignalResult
    """
    combined = SignalResult()

    for response in responses:
        result = detect_signals(response)

        for domain, count in result.signals.items():
            combined.signals[domain] = combined.signals.get(domain, 0) + count
        for domain, count in result.negative_signals.items():
            combined.negative_signals[domain] = combined.negative_signals.get(domain, 0) + count
        for domain, count in result.planned_signals.items():
            combined.planned_signals[domain] = combined.planned_signals.get(domain, 0) + count

        for domain, snippets in result.evidence.items():
            if domain not in combined.evidence:
                combined.evidence[domain] = []
            for snippet in snippets:
                if len(combined.evidence[domain]) < 3:
                    combined.evidence[domain].append(snippet)

        combined.matches.extend(result.matches)

    return combined


# ── Domain mapping helpers ───────────────────────────────────────────────────

# Maps signal domains to phased interview expert domains
SIGNAL_TO_INTERVIEW_DOMAIN: dict[str, str] = {
    "sales": "sales",
    "crm": "sales",
    "ecommerce": "ecommerce",
    "website": "ecommerce",
    "inventory": "inventory",
    "shipping": "inventory",
    "purchase": "purchase",
    "accounting": "finance",
    "finance": "finance",
    "manufacturing": "manufacturing",
    "outsourced_manufacturing": "manufacturing",
    "hr": "hr",
    "project": "project",
    "support": "support",
    "pos": "sales",
    "quality": "manufacturing",
    "maintenance": "manufacturing",
    "marketing": "sales",
    "subscriptions": "sales",
    "data_migration": None,  # Cross-cutting, not a domain
    "integration": None,     # Cross-cutting, not a domain
}

# Maps interview domains to Odoo module technical names
DOMAIN_TO_MODULES: dict[str, list[str]] = {
    "sales": ["sale_management", "crm"],
    "inventory": ["stock", "delivery"],
    "finance": ["account", "account_followup"],
    "purchase": ["purchase"],
    "manufacturing": ["mrp", "mrp_workorder"],
    "hr": ["hr", "hr_holidays", "hr_attendance"],
    "project": ["project", "hr_timesheet"],
    "ecommerce": ["website_sale", "website"],
    "support": ["helpdesk"],
}
