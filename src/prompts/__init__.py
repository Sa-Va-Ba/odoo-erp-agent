"""
Prompt templates for Odoo ERP Implementation Agents.
"""

from .interview_agent_prompt import (
    INTERVIEW_AGENT_SYSTEM_PROMPT,
    create_domain_prompt,
    create_domain_summary_prompt,
    create_interview_completion_prompt
)

__all__ = [
    "INTERVIEW_AGENT_SYSTEM_PROMPT",
    "create_domain_prompt",
    "create_domain_summary_prompt",
    "create_interview_completion_prompt"
]
