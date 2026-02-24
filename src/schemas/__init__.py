"""
Schema definitions for Odoo ERP Implementation System.
"""

from .shared_context import SharedContext, create_new_project
from .interview_domains import (
    InterviewDomain,
    DomainDefinition,
    Question,
    ALL_DOMAINS,
    get_domain,
    get_domain_by_index
)

__all__ = [
    "SharedContext",
    "create_new_project",
    "InterviewDomain",
    "DomainDefinition",
    "Question",
    "ALL_DOMAINS",
    "get_domain",
    "get_domain_by_index"
]
