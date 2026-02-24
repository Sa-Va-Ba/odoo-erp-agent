"""
Groq LLM Provider.

Groq offers ultra-fast inference with a generous free tier:
- 1,000 requests/day
- 6,000 tokens/minute
- No credit card required

Sign up at: https://console.groq.com
"""

import os
from typing import Optional, List, Dict, Any

from .base import (
    LLMProvider,
    LLMConfig,
    LLMResponse,
    Message,
    ProviderStatus
)


class GroqProvider(LLMProvider):
    """
    Groq LLM Provider using their Python SDK.

    Groq provides the fastest inference speeds in the market
    with a free tier suitable for development and small-scale use.
    """

    DEFAULT_MODEL = "llama-3.3-70b-versatile"

    # Available models on Groq (as of 2026)
    AVAILABLE_MODELS = [
        "llama-3.3-70b-versatile",    # Best general purpose
        "llama-3.1-8b-instant",       # Fast, smaller
        "mixtral-8x7b-32768",         # Good for longer context
        "gemma2-9b-it",               # Google's model
        "deepseek-r1-distill-llama-70b",  # Reasoning focused
    ]

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        **kwargs
    ):
        """
        Initialize Groq provider.

        Args:
            api_key: Groq API key (or set GROQ_API_KEY env var)
            model: Model to use (default: llama-3.3-70b-versatile)
            **kwargs: Additional config options
        """
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")

        config = LLMConfig(
            provider_name="groq",
            model=model,
            api_key=self.api_key,
            base_url="https://api.groq.com/openai/v1",
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens", 2000),
            timeout=kwargs.get("timeout", 30)
        )
        super().__init__(config)

        self._client = None
        self._initialize_client()

    def _initialize_client(self):
        """Initialize the Groq client."""
        if not self.api_key:
            self._status = ProviderStatus.NOT_CONFIGURED
            return

        try:
            # Try to import groq package
            from groq import Groq
            self._client = Groq(api_key=self.api_key)
            self._status = ProviderStatus.AVAILABLE
        except ImportError:
            # Groq package not installed, use requests fallback
            self._client = None
            self._status = ProviderStatus.AVAILABLE  # Can still work via HTTP

    def is_available(self) -> bool:
        """Check if Groq is available."""
        if not self.api_key:
            return False
        return self._status == ProviderStatus.AVAILABLE

    def _chat_with_sdk(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """Chat using the official Groq SDK."""
        from groq import Groq

        if not isinstance(self._client, Groq):
            raise RuntimeError("Groq client not initialized")

        # Convert messages to dict format
        msg_dicts = [{"role": m.role, "content": m.content} for m in messages]

        response = self._client.chat.completions.create(
            model=self.config.model,
            messages=msg_dicts,
            temperature=temperature or self.config.temperature,
            max_tokens=max_tokens or self.config.max_tokens,
            **kwargs
        )

        return LLMResponse(
            content=response.choices[0].message.content,
            model=response.model,
            provider="groq",
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            },
            finish_reason=response.choices[0].finish_reason,
            raw_response=response
        )

    def _chat_with_http(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """Chat using HTTP requests (fallback if SDK not installed)."""
        import requests

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        msg_dicts = [{"role": m.role, "content": m.content} for m in messages]

        payload = {
            "model": self.config.model,
            "messages": msg_dicts,
            "temperature": temperature or self.config.temperature,
            "max_tokens": max_tokens or self.config.max_tokens
        }

        response = requests.post(
            f"{self.config.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=self.config.timeout
        )

        if response.status_code == 429:
            self._status = ProviderStatus.RATE_LIMITED
            raise Exception("Groq rate limit exceeded")

        response.raise_for_status()
        data = response.json()

        return LLMResponse(
            content=data["choices"][0]["message"]["content"],
            model=data["model"],
            provider="groq",
            usage=data.get("usage", {}),
            finish_reason=data["choices"][0].get("finish_reason", "stop"),
            raw_response=data
        )

    def chat(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Send a chat completion request to Groq.

        Args:
            messages: List of conversation messages
            temperature: Override default temperature (0-2)
            max_tokens: Override default max tokens
            **kwargs: Additional parameters

        Returns:
            LLMResponse with the model's response
        """
        if not self.is_available():
            raise RuntimeError(
                "Groq not available. Set GROQ_API_KEY environment variable.\n"
                "Get your free API key at: https://console.groq.com"
            )

        try:
            if self._client is not None:
                return self._chat_with_sdk(messages, temperature, max_tokens, **kwargs)
            else:
                return self._chat_with_http(messages, temperature, max_tokens, **kwargs)
        except Exception as e:
            if "rate" in str(e).lower():
                self._status = ProviderStatus.RATE_LIMITED
            else:
                self._status = ProviderStatus.ERROR
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


def create_groq_provider(model: str = GroqProvider.DEFAULT_MODEL) -> Optional[GroqProvider]:
    """
    Factory function to create a Groq provider if configured.

    Returns:
        GroqProvider if GROQ_API_KEY is set, None otherwise
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None

    return GroqProvider(api_key=api_key, model=model)
