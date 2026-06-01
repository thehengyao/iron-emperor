"""
Unified LLM client — Claude (Anthropic) or DeepSeek.

Usage:
    client = get_llm_client()
    resp = client.messages.create(model=..., max_tokens=..., system=..., messages=[...])
    text = resp.content[0].text

Switch provider:
    HWB_MODEL=claude-opus-4-6    → Anthropic
    HWB_MODEL=deepseek-chat      → DeepSeek
    HWB_MODEL=deepseek-reasoner  → DeepSeek (reasoning model)
"""
import os
from dataclasses import dataclass
from typing import Any


@dataclass
class _Content:
    text: str


@dataclass
class _Response:
    content: list[_Content]


class _AnthropicMessages:
    def __init__(self, client):
        self._client = client

    def create(self, *, model: str, max_tokens: int, system: str,
               messages: list[dict], **kwargs) -> _Response:
        resp = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            **kwargs,
        )
        return _Response(content=[_Content(text=resp.content[0].text)])


class _DeepSeekMessages:
    def __init__(self, client):
        self._client = client

    def create(self, *, model: str, max_tokens: int, system: str,
               messages: list[dict], **kwargs) -> _Response:
        full_messages = [{"role": "system", "content": system}] + messages
        resp = self._client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=full_messages,
        )
        return _Response(content=[_Content(text=resp.choices[0].message.content)])


class UnifiedLLMClient:
    """Presents Anthropic's messages.create() interface for both Claude and DeepSeek."""

    def __init__(self, provider: str):
        self.provider = provider
        if provider == "anthropic":
            import anthropic
            self.messages = _AnthropicMessages(anthropic.Anthropic())
        else:
            from openai import OpenAI
            key = os.environ.get("DEEPSEEK_API_KEY")
            if not key:
                raise RuntimeError(
                    "DEEPSEEK_API_KEY not set. Export it or set HWB_MODEL=claude-opus-4-6 to use Claude."
                )
            self.messages = _DeepSeekMessages(
                OpenAI(api_key=key, base_url="https://api.deepseek.com/v1")
            )


def get_llm_client() -> UnifiedLLMClient:
    """Return a unified client based on HWB_MODEL env var."""
    model = os.getenv("HWB_MODEL", "claude-opus-4-6")
    provider = "deepseek" if model.startswith("deepseek") else "anthropic"
    return UnifiedLLMClient(provider)
