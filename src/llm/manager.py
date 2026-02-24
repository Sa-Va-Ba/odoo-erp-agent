"""
LLM Manager - Unified interface for multiple LLM providers.

Handles automatic provider selection, failover, and rate limit management.
"""

import os
import time
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .base import (
    LLMProvider,
    LLMResponse,
    Message,
    ProviderStatus,
    PROVIDER_INFO
)
from .groq_provider import GroqProvider, create_groq_provider
from .ollama_provider import OllamaProvider, create_ollama_provider


@dataclass
class ProviderUsage:
    """Track usage for rate limit management."""
    requests_today: int = 0
    tokens_today: int = 0
    last_request: Optional[datetime] = None
    rate_limit_reset: Optional[datetime] = None
    errors: int = 0
    successes: int = 0
    last_error: Optional[str] = None


@dataclass
class LLMManagerConfig:
    """Configuration for the LLM Manager."""
    # Provider preferences (in order of preference)
    # Using only free/open-source providers: Groq (free tier) and Ollama (local)
    provider_priority: List[str] = field(default_factory=lambda: ["groq", "ollama"])

    # Auto-fallback when rate limited
    auto_fallback: bool = True

    # Default model preferences per provider
    default_models: Dict[str, str] = field(default_factory=lambda: {
        "groq": "llama-3.3-70b-versatile",
        "ollama": "mistral:latest"
    })

    # Rate limit buffer (don't use last 10% of quota)
    rate_limit_buffer: float = 0.1


class LLMManager:
    """
    Manages multiple LLM providers with automatic selection and failover.

    Usage:
        manager = LLMManager()
        response = manager.chat([Message(role="user", content="Hello")])

    The manager will:
    1. Try providers in priority order
    2. Automatically switch on rate limits
    3. Track usage across providers
    4. Prefer local (Ollama) when cloud is limited
    """

    def __init__(self, config: Optional[LLMManagerConfig] = None):
        self.config = config or LLMManagerConfig()
        self._providers: Dict[str, LLMProvider] = {}
        self._usage: Dict[str, ProviderUsage] = {}
        self._current_provider: Optional[str] = None

        self._initialize_providers()

    def _initialize_providers(self):
        """Initialize all available providers."""
        # Try to initialize Groq (free tier - 1000 requests/day)
        groq = create_groq_provider(
            model=self.config.default_models.get("groq", GroqProvider.DEFAULT_MODEL)
        )
        if groq and groq.is_available():
            self._providers["groq"] = groq
            self._usage["groq"] = ProviderUsage()
            print("✓ Groq provider initialized (free tier, 1000 req/day)")

        # Try to initialize Ollama
        ollama = create_ollama_provider(
            model=self.config.default_models.get("ollama", OllamaProvider.DEFAULT_MODEL)
        )
        if ollama and ollama.is_available():
            self._providers["ollama"] = ollama
            self._usage["ollama"] = ProviderUsage()
            print("✓ Ollama provider initialized (local)")

        # Set initial provider
        self._select_provider()

    def _select_provider(self) -> Optional[str]:
        """Select the best available provider."""
        for provider_name in self.config.provider_priority:
            if provider_name in self._providers:
                provider = self._providers[provider_name]
                usage = self._usage.get(provider_name, ProviderUsage())

                # Check if rate limited
                if provider.status == ProviderStatus.RATE_LIMITED:
                    if usage.rate_limit_reset and datetime.now() < usage.rate_limit_reset:
                        continue  # Still rate limited
                    else:
                        # Reset rate limit status
                        provider._status = ProviderStatus.AVAILABLE

                # Check if approaching rate limit (for cloud providers)
                if provider_name in PROVIDER_INFO:
                    info = PROVIDER_INFO[provider_name]
                    if not info.is_local:
                        limit = info.rate_limit_requests_per_day
                        buffer = int(limit * self.config.rate_limit_buffer)
                        if usage.requests_today >= (limit - buffer):
                            continue  # Approaching limit, skip

                self._current_provider = provider_name
                return provider_name

        self._current_provider = None
        return None

    @property
    def current_provider(self) -> Optional[LLMProvider]:
        """Get the currently selected provider."""
        if self._current_provider:
            return self._providers.get(self._current_provider)
        return None

    @property
    def available_providers(self) -> List[str]:
        """List of available provider names."""
        return list(self._providers.keys())

    def get_status(self) -> Dict[str, Any]:
        """Get status of all providers."""
        status = {
            "current_provider": self._current_provider,
            "providers": {}
        }

        for name, provider in self._providers.items():
            usage = self._usage.get(name, ProviderUsage())
            info = PROVIDER_INFO.get(name)

            status["providers"][name] = {
                "status": provider.status.value,
                "model": provider.model,
                "is_local": info.is_local if info else False,
                "requests_today": usage.requests_today,
                "tokens_today": usage.tokens_today,
                "rate_limit": info.rate_limit_requests_per_day if info else "unlimited"
            }

        return status

    def _update_usage(self, provider_name: str, response: LLMResponse):
        """Update usage tracking after a request."""
        usage = self._usage.get(provider_name, ProviderUsage())
        usage.requests_today += 1
        usage.tokens_today += response.tokens_used
        usage.last_request = datetime.now()
        self._usage[provider_name] = usage

    def _handle_rate_limit(self, provider_name: str):
        """Handle rate limit by switching providers."""
        usage = self._usage.get(provider_name, ProviderUsage())
        usage.rate_limit_reset = datetime.now() + timedelta(hours=1)
        self._usage[provider_name] = usage

        if provider_name in self._providers:
            self._providers[provider_name]._status = ProviderStatus.RATE_LIMITED

        if self.config.auto_fallback:
            new_provider = self._select_provider()
            if new_provider:
                print(f"Switched to {new_provider} due to rate limit on {provider_name}")

    def chat(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        provider: Optional[str] = None,
        _retry_count: int = 0,
        **kwargs
    ) -> LLMResponse:
        """
        Send a chat completion request with retry and fallback.

        Args:
            messages: List of conversation messages
            temperature: Override default temperature
            max_tokens: Override default max tokens
            provider: Force a specific provider (optional)
            **kwargs: Additional parameters

        Returns:
            LLMResponse with the model's response

        Raises:
            RuntimeError: If no providers are available after retries
        """
        max_retries = 2

        # Use specified provider or auto-select
        if provider:
            if provider not in self._providers:
                raise RuntimeError(f"Provider '{provider}' not available")
            target_provider = provider
        else:
            target_provider = self._select_provider()

        if not target_provider:
            raise RuntimeError(
                "No LLM providers available.\n"
                "Please either:\n"
                "1. Set GROQ_API_KEY env var (get free key at console.groq.com)\n"
                "2. Install and run Ollama (brew install ollama && ollama serve)"
            )

        llm = self._providers[target_provider]

        try:
            response = llm.chat(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
            self._update_usage(target_provider, response)
            usage = self._usage.get(target_provider, ProviderUsage())
            usage.successes += 1
            return response

        except Exception as e:
            error_msg = str(e).lower()

            # Track the error
            usage = self._usage.get(target_provider, ProviderUsage())
            usage.errors += 1
            usage.last_error = str(e)[:200]
            self._usage[target_provider] = usage

            # Handle rate limits
            if "rate" in error_msg or "limit" in error_msg or "429" in error_msg:
                self._handle_rate_limit(target_provider)
                if self.config.auto_fallback:
                    new_provider = self._select_provider()
                    if new_provider and new_provider != target_provider:
                        print(f"  [LLM] Rate limited on {target_provider}, switching to {new_provider}")
                        return self.chat(
                            messages, temperature, max_tokens,
                            provider=new_provider, **kwargs
                        )

            # Retry with exponential backoff
            if _retry_count < max_retries:
                wait = (2 ** _retry_count) * 1.0  # 1s, 2s
                print(f"  [LLM] Error on {target_provider}, retrying in {wait}s ({_retry_count + 1}/{max_retries})")
                time.sleep(wait)
                return self.chat(
                    messages, temperature, max_tokens,
                    provider=provider, _retry_count=_retry_count + 1, **kwargs
                )

            # Try fallback provider after retries exhausted
            if self.config.auto_fallback and not provider:
                for fallback_name in self.config.provider_priority:
                    if fallback_name != target_provider and fallback_name in self._providers:
                        print(f"  [LLM] All retries failed on {target_provider}, falling back to {fallback_name}")
                        try:
                            return self.chat(
                                messages, temperature, max_tokens,
                                provider=fallback_name, **kwargs
                            )
                        except Exception:
                            continue

            raise

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
        messages = []
        if system_prompt:
            messages.append(Message(role="system", content=system_prompt))
        messages.append(Message(role="user", content=prompt))

        return self.chat(messages, **kwargs)

    @property
    def is_available(self) -> bool:
        """Check if any LLM provider is available."""
        return self._select_provider() is not None

    @property
    def session_stats(self) -> Dict[str, Any]:
        """Get session-level stats for reporting in interview output."""
        total_success = sum(u.successes for u in self._usage.values())
        total_errors = sum(u.errors for u in self._usage.values())
        return {
            "providers_available": list(self._providers.keys()),
            "current_provider": self._current_provider,
            "total_requests": total_success + total_errors,
            "successful_requests": total_success,
            "failed_requests": total_errors,
            "success_rate": round(total_success / max(total_success + total_errors, 1), 2),
        }

    def reset_daily_usage(self):
        """Reset daily usage counters (call at midnight)."""
        for name in self._usage:
            self._usage[name].requests_today = 0
            self._usage[name].tokens_today = 0


def get_llm_manager() -> LLMManager:
    """
    Get a configured LLM manager instance.

    This is the main entry point for using LLMs in the application.

    Returns:
        Configured LLMManager with available providers
    """
    return LLMManager()


# Convenience function for quick completions
def quick_complete(prompt: str, system_prompt: Optional[str] = None) -> str:
    """
    Quick completion without managing the manager instance.

    Args:
        prompt: The user prompt
        system_prompt: Optional system prompt

    Returns:
        The response content string
    """
    manager = get_llm_manager()
    response = manager.complete(prompt, system_prompt)
    return response.content
