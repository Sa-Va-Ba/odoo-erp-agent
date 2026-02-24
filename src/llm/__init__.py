"""
LLM Provider modules for Odoo ERP Implementation Agents.

Supports multiple free LLM providers:
- Groq (primary, cloud-based, free tier)
- Ollama (fallback, local, 100% free)
- OpenRouter (backup, cloud-based, free tier)
"""

from .base import LLMProvider, LLMResponse, LLMConfig
from .groq_provider import GroqProvider
from .ollama_provider import OllamaProvider
from .manager import LLMManager

__all__ = [
    "LLMProvider",
    "LLMResponse",
    "LLMConfig",
    "GroqProvider",
    "OllamaProvider",
    "LLMManager"
]
