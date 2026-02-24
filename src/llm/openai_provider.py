"""
OpenAI/ChatGPT Provider for LLM operations.

Supports:
- OpenAI API (standard)
- Azure OpenAI
- ChatGPT Enterprise (via API)
"""

import os
from typing import Optional, List, Dict, Any

from .base import LLMProvider, LLMConfig, LLMResponse, Message, ProviderStatus


class OpenAIProvider(LLMProvider):
    """
    OpenAI/ChatGPT provider using the official OpenAI API.

    Supports ChatGPT Enterprise accounts via API key.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o",
        base_url: Optional[str] = None,
        organization: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize OpenAI provider.

        Args:
            api_key: OpenAI API key (or set OPENAI_API_KEY env var)
            model: Model to use (gpt-4o, gpt-4o-mini, gpt-4-turbo, etc.)
            base_url: Custom base URL (for Azure or enterprise endpoints)
            organization: OpenAI organization ID (optional)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.organization = organization or os.getenv("OPENAI_ORG_ID")

        config = LLMConfig(
            provider_name="openai",
            model=model,
            api_key=self.api_key,
            base_url=self.base_url,
            **kwargs
        )
        super().__init__(config)

        # Try to import openai
        self._client = None
        self._init_client()

    def _init_client(self):
        """Initialize the OpenAI client."""
        # Check for API key first - if not set, just mark as not configured
        if not self.api_key:
            self._status = ProviderStatus.NOT_CONFIGURED
            return

        try:
            from openai import OpenAI

            client_kwargs = {
                "api_key": self.api_key,
            }

            if self.base_url and self.base_url != "https://api.openai.com/v1":
                client_kwargs["base_url"] = self.base_url

            if self.organization:
                client_kwargs["organization"] = self.organization

            self._client = OpenAI(**client_kwargs)
            self._status = ProviderStatus.AVAILABLE

        except ImportError:
            print("OpenAI SDK not installed. Install with: pip install openai")
            self._status = ProviderStatus.NOT_CONFIGURED
        except Exception as e:
            print(f"Failed to initialize OpenAI client: {e}")
            self._status = ProviderStatus.ERROR

    def is_available(self) -> bool:
        """Check if OpenAI is available and configured."""
        return self._client is not None and self.api_key is not None

    def chat(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """Send a chat completion request to OpenAI."""
        if not self.is_available():
            raise RuntimeError("OpenAI provider is not available. Check API key.")

        # Convert messages to OpenAI format
        openai_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]

        try:
            response = self._client.chat.completions.create(
                model=self.config.model,
                messages=openai_messages,
                temperature=temperature or self.config.temperature,
                max_tokens=max_tokens or self.config.max_tokens,
                **kwargs
            )

            content = response.choices[0].message.content or ""
            usage = {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            }

            return LLMResponse(
                content=content,
                model=response.model,
                provider="openai",
                usage=usage,
                finish_reason=response.choices[0].finish_reason or "stop",
                raw_response=response
            )

        except Exception as e:
            error_str = str(e).lower()
            # Check for rate limiting or quota exceeded
            if "rate_limit" in error_str or "429" in error_str:
                self._status = ProviderStatus.RATE_LIMITED
            elif "insufficient_quota" in error_str or "quota" in error_str:
                self._status = ProviderStatus.RATE_LIMITED
                print("⚠️ OpenAI quota exceeded. Add credits at https://platform.openai.com/account/billing")
            else:
                self._status = ProviderStatus.ERROR
            raise

    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """Simple completion with a single prompt."""
        messages = []

        if system_prompt:
            messages.append(Message(role="system", content=system_prompt))

        messages.append(Message(role="user", content=prompt))

        return self.chat(messages, **kwargs)

    def health_check(self) -> bool:
        """Perform a health check."""
        try:
            response = self.complete(
                "Respond with only the word 'ok'.",
                max_tokens=10
            )
            return "ok" in response.content.lower()
        except Exception:
            return False


class AzureOpenAIProvider(OpenAIProvider):
    """
    Azure OpenAI provider for enterprise deployments.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        azure_endpoint: Optional[str] = None,
        api_version: str = "2024-02-15-preview",
        deployment_name: str = "gpt-4o",
        **kwargs
    ):
        """
        Initialize Azure OpenAI provider.

        Args:
            api_key: Azure OpenAI API key
            azure_endpoint: Azure endpoint URL
            api_version: API version
            deployment_name: Deployment name (model alias)
        """
        self.azure_endpoint = azure_endpoint or os.getenv("AZURE_OPENAI_ENDPOINT")
        self.api_version = api_version
        self.deployment_name = deployment_name

        # Call parent but don't init client yet
        self.api_key = api_key or os.getenv("AZURE_OPENAI_API_KEY")

        config = LLMConfig(
            provider_name="azure_openai",
            model=deployment_name,
            api_key=self.api_key,
            base_url=self.azure_endpoint,
            **kwargs
        )
        # Skip OpenAI's __init__ to avoid double client init
        LLMProvider.__init__(self, config)

        self._client = None
        self._init_azure_client()

    def _init_azure_client(self):
        """Initialize the Azure OpenAI client."""
        try:
            from openai import AzureOpenAI

            if not self.azure_endpoint or not self.api_key:
                self._status = ProviderStatus.NOT_CONFIGURED
                return

            self._client = AzureOpenAI(
                api_key=self.api_key,
                api_version=self.api_version,
                azure_endpoint=self.azure_endpoint,
            )
            self._status = ProviderStatus.AVAILABLE

        except ImportError:
            print("OpenAI SDK not installed. Install with: pip install openai")
            self._status = ProviderStatus.NOT_CONFIGURED
        except Exception as e:
            print(f"Failed to initialize Azure OpenAI client: {e}")
            self._status = ProviderStatus.ERROR


def get_openai_provider(
    api_key: Optional[str] = None,
    model: str = "gpt-4o",
    use_azure: bool = False,
    **kwargs
) -> OpenAIProvider:
    """
    Factory function to get an OpenAI provider.

    Args:
        api_key: API key (or set via environment)
        model: Model to use
        use_azure: Use Azure OpenAI instead of standard OpenAI
        **kwargs: Additional provider arguments

    Returns:
        Configured OpenAI provider
    """
    if use_azure:
        return AzureOpenAIProvider(api_key=api_key, deployment_name=model, **kwargs)
    return OpenAIProvider(api_key=api_key, model=model, **kwargs)
