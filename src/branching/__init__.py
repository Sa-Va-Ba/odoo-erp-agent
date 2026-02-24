"""
Branching logic for intelligent interview flow control.

This module provides:
- Response quality analysis
- Domain-specific trigger rules
- Adaptive question selection
- Follow-up question generation
"""

from .analyzer import ResponseAnalyzer, ResponseQuality, ResponseAnalysis
from .triggers import TriggerRule, DomainTriggers, load_domain_triggers
from .engine import BranchingEngine, NextAction, ActionType

__all__ = [
    "ResponseAnalyzer",
    "ResponseQuality",
    "ResponseAnalysis",
    "TriggerRule",
    "DomainTriggers",
    "load_domain_triggers",
    "BranchingEngine",
    "NextAction",
    "ActionType"
]
