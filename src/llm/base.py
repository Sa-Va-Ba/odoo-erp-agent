"""
Base classes for LLM providers.

Provides a unified interface for different LLM backends,
allowing easy switching between Groq, Ollama, OpenRouter, etc.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum


class ProviderStatus(str, Enum):
    """Status of an LLM provider."""
    AVAILABLE = "available"
    RATE_LIMITED = "rate_limited"
    ERROR = "error"
    NOT_CONFIGURED = "not_configured"


@dataclass
class LLMConfig:
    """Configuration for an LLM provider."""
    provider_name: str
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 2000
    timeout: int = 30
    extra_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Message:
    """A single message in a conversation."""
    role: str  # "system", "user", "assistant"
    content: str


@dataclass
class LLMResponse:
    """Response from an LLM provider."""
    content: str
    model: str
    provider: str
    usage: Dict[str, int] = field(default_factory=dict)  # tokens used
    finish_reason: str = "stop"
    raw_response: Optional[Any] = None

    @property
    def tokens_used(self) -> int:
        """Total tokens used in this request."""
        return self.usage.get("total_tokens", 0)


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.

    All providers (Groq, Ollama, OpenRouter, etc.) must implement this interface.
    """

    def __init__(self, config: LLMConfig):
        self.config = config
        self._status = ProviderStatus.NOT_CONFIGURED

    @property
    def name(self) -> str:
        """Provider name."""
        return self.config.provider_name

    @property
    def model(self) -> str:
        """Current model."""
        return self.config.model

    @property
    def status(self) -> ProviderStatus:
        """Current provider status."""
        return self._status

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is available and configured."""
        pass

    @abstractmethod
    def chat(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Send a chat completion request.

        Args:
            messages: List of conversation messages
            temperature: Override default temperature
            max_tokens: Override default max tokens
            **kwargs: Provider-specific parameters

        Returns:
            LLMResponse with the model's response
        """
        pass

    @abstractmethod
    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Simple completion with a single prompt.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            **kwargs: Additional parameters

        Returns:
            LLMResponse with the model's response
        """
        pass

    def health_check(self) -> bool:
        """
        Perform a health check on the provider.

        Returns:
            True if provider is healthy and responding
        """
        try:
            response = self.complete("Say 'ok' and nothing else.")
            return "ok" in response.content.lower()
        except Exception:
            return False


@dataclass
class ProviderInfo:
    """Information about a provider for selection."""
    name: str
    priority: int  # Lower = higher priority
    is_local: bool
    rate_limit_requests_per_day: int
    rate_limit_tokens_per_minute: int
    models: List[str]
    requires_api_key: bool
    status: ProviderStatus = ProviderStatus.NOT_CONFIGURED


# Provider metadata for auto-selection
PROVIDER_INFO = {
    "openai": ProviderInfo(
        name="openai",
        priority=0,  # Highest priority for ChatGPT Enterprise
        is_local=False,
        rate_limit_requests_per_day=10000,  # Enterprise typically has higher limits
        rate_limit_tokens_per_minute=150000,
        models=["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
        requires_api_key=True
    ),
    "groq": ProviderInfo(
        name="groq",
        priority=1,
        is_local=False,
        rate_limit_requests_per_day=1000,
        rate_limit_tokens_per_minute=6000,
        models=["llama-3.3-70b-versatile", "mixtral-8x7b-32768", "gemma2-9b-it"],
        requires_api_key=True
    ),
    "ollama": ProviderInfo(
        name="ollama",
        priority=2,
        is_local=True,
        rate_limit_requests_per_day=999999,  # Unlimited (local)
        rate_limit_tokens_per_minute=999999,
        models=["mistral:7b", "llama3.2:7b", "qwen2.5:7b"],
        requires_api_key=False
    ),
    "openrouter": ProviderInfo(
        name="openrouter",
        priority=3,
        is_local=False,
        rate_limit_requests_per_day=200,
        rate_limit_tokens_per_minute=10000,
        models=["mistralai/mistral-7b-instruct", "meta-llama/llama-3.3-70b-instruct"],
        requires_api_key=True
    ),
}
