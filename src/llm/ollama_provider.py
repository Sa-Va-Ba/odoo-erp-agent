"""
Ollama LLM Provider.

Ollama runs LLMs locally on your machine - completely free with no API limits.
- Works offline
- Complete data privacy
- No rate limits
- Requires 8GB+ RAM (16GB recommended)

Install: brew install ollama (or download from https://ollama.ai)
Pull a model: ollama pull mistral:7b
"""

import os
import subprocess
from typing import Optional, List, Dict, Any

from .base import (
    LLMProvider,
    LLMConfig,
    LLMResponse,
    Message,
    ProviderStatus
)


class OllamaProvider(LLMProvider):
    """
    Ollama LLM Provider for local model inference.

    Ollama allows running open-source LLMs locally with zero cost.
    Perfect as a fallback when cloud providers are rate-limited.
    """

    DEFAULT_MODEL = "mistral:7b"
    DEFAULT_HOST = "http://localhost:11434"

    # Recommended models for interview tasks (sorted by quality/speed tradeoff)
    RECOMMENDED_MODELS = [
        "mistral:7b",       # Best balance of quality and speed
        "llama3.2:7b",      # Good general purpose
        "qwen2.5:7b",       # Excellent for structured tasks
        "phi3:mini",        # Fast, lower quality
        "gemma2:9b",        # Google's model
    ]

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        host: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize Ollama provider.

        Args:
            model: Model to use (default: mistral:7b)
            host: Ollama server URL (default: http://localhost:11434)
            **kwargs: Additional config options
        """
        self.host = host or os.environ.get("OLLAMA_HOST", self.DEFAULT_HOST)

        config = LLMConfig(
            provider_name="ollama",
            model=model,
            base_url=self.host,
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens", 2000),
            timeout=kwargs.get("timeout", 120)  # Local inference can be slower
        )
        super().__init__(config)

        self._check_availability()

    def _check_availability(self):
        """Check if Ollama is running and model is available."""
        try:
            import requests
            response = requests.get(
                f"{self.host}/api/tags",
                timeout=5
            )
            if response.status_code == 200:
                self._status = ProviderStatus.AVAILABLE
                # Check if our model is installed
                models = response.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                if not any(self.config.model in name for name in model_names):
                    print(f"Warning: Model '{self.config.model}' not found locally.")
                    print(f"Available models: {model_names}")
                    print(f"Pull it with: ollama pull {self.config.model}")
            else:
                self._status = ProviderStatus.ERROR
        except Exception:
            self._status = ProviderStatus.NOT_CONFIGURED

    def is_available(self) -> bool:
        """Check if Ollama is available."""
        return self._status == ProviderStatus.AVAILABLE

    def _ensure_model_pulled(self) -> bool:
        """Ensure the model is pulled locally."""
        try:
            import requests
            # Check if model exists
            response = requests.post(
                f"{self.host}/api/show",
                json={"name": self.config.model},
                timeout=5
            )
            if response.status_code == 200:
                return True

            # Model not found, try to pull it
            print(f"Model '{self.config.model}' not found. Attempting to pull...")
            pull_response = requests.post(
                f"{self.host}/api/pull",
                json={"name": self.config.model},
                stream=True,
                timeout=600  # 10 min timeout for pulling
            )
            # Stream the pull progress
            for line in pull_response.iter_lines():
                if line:
                    print(".", end="", flush=True)
            print("\nModel pulled successfully!")
            return True

        except Exception as e:
            print(f"Failed to pull model: {e}")
            return False

    def chat(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Send a chat completion request to Ollama.

        Args:
            messages: List of conversation messages
            temperature: Override default temperature
            max_tokens: Override default max tokens
            **kwargs: Additional parameters

        Returns:
            LLMResponse with the model's response
        """
        if not self.is_available():
            raise RuntimeError(
                "Ollama not available. Please ensure Ollama is running.\n"
                "Install: brew install ollama\n"
                "Start: ollama serve\n"
                "Pull model: ollama pull mistral:7b"
            )

        import requests

        # Convert messages to Ollama format
        msg_dicts = [{"role": m.role, "content": m.content} for m in messages]

        payload = {
            "model": self.config.model,
            "messages": msg_dicts,
            "stream": False,
            "options": {
                "temperature": temperature or self.config.temperature,
                "num_predict": max_tokens or self.config.max_tokens
            }
        }

        try:
            response = requests.post(
                f"{self.host}/api/chat",
                json=payload,
                timeout=self.config.timeout
            )
            response.raise_for_status()
            data = response.json()

            return LLMResponse(
                content=data["message"]["content"],
                model=data.get("model", self.config.model),
                provider="ollama",
                usage={
                    "prompt_tokens": data.get("prompt_eval_count", 0),
                    "completion_tokens": data.get("eval_count", 0),
                    "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0)
                },
                finish_reason=data.get("done_reason", "stop"),
                raw_response=data
            )

        except requests.exceptions.Timeout:
            raise RuntimeError(
                f"Ollama request timed out after {self.config.timeout}s. "
                "Local inference can be slow. Try a smaller model like 'phi3:mini'."
            )
        except Exception as e:
            self._status = ProviderStatus.ERROR
            raise RuntimeError(f"Ollama request failed: {e}")

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

    def list_local_models(self) -> List[str]:
        """List all locally available models."""
        try:
            import requests
            response = requests.get(f"{self.host}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get("models", [])
                return [m.get("name", "") for m in models]
        except Exception:
            pass
        return []

    @staticmethod
    def is_ollama_installed() -> bool:
        """Check if Ollama is installed on the system."""
        try:
            result = subprocess.run(
                ["which", "ollama"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def start_ollama_server() -> bool:
        """Attempt to start the Ollama server."""
        try:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            import time
            time.sleep(2)  # Wait for server to start
            return True
        except Exception:
            return False


def create_ollama_provider(model: str = OllamaProvider.DEFAULT_MODEL) -> Optional[OllamaProvider]:
    """
    Factory function to create an Ollama provider if available.

    Returns:
        OllamaProvider if Ollama is running, None otherwise
    """
    provider = OllamaProvider(model=model)
    if provider.is_available():
        return provider

    # Try to start Ollama if it's installed but not running
    if OllamaProvider.is_ollama_installed():
        print("Ollama installed but not running. Attempting to start...")
        if OllamaProvider.start_ollama_server():
            provider = OllamaProvider(model=model)
            if provider.is_available():
                return provider

    return None
