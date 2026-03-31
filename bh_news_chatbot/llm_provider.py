"""
Abstração de provedores de LLM.

Suporta Anthropic (Claude) e Google (Gemini).
Novos provedores podem ser adicionados implementando LLMProvider.
"""

import logging
import os
from abc import ABC, abstractmethod
from typing import Iterator, Optional

log = logging.getLogger(__name__)

# Modelos padrão por provedor
ANTHROPIC_CHAT_MODEL = "claude-sonnet-4-6"
ANTHROPIC_FAST_MODEL = "claude-haiku-4-5-20251001"
GEMINI_CHAT_MODEL = "gemini-1.5-pro"
GEMINI_FAST_MODEL = "gemini-1.5-flash"


class LLMProvider(ABC):
    """Interface comum para provedores de LLM."""

    @abstractmethod
    def complete(self, system: str, messages: list[dict]) -> str:
        """Resposta única (não-streaming)."""
        ...

    @abstractmethod
    def stream(self, system: str, messages: list[dict]) -> Iterator[str]:
        """Resposta em streaming, gerando tokens à medida que chegam."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Nome legível do provedor."""
        ...


# ---------------------------------------------------------------------------
# Anthropic (Claude)
# ---------------------------------------------------------------------------

class AnthropicProvider(LLMProvider):
    """Provedor usando a API da Anthropic (Claude)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = ANTHROPIC_CHAT_MODEL,
        max_tokens: int = 2048,
    ):
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "Chave da API Anthropic não encontrada. "
                "Defina ANTHROPIC_API_KEY ou use --api-key."
            )
        self._model = model
        self._max_tokens = max_tokens
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    @property
    def name(self) -> str:
        return f"Anthropic ({self._model})"

    def complete(self, system: str, messages: list[dict]) -> str:
        client = self._get_client()
        response = client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=messages,
        )
        return response.content[0].text

    def stream(self, system: str, messages: list[dict]) -> Iterator[str]:
        client = self._get_client()
        with client.messages.stream(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=messages,
        ) as s:
            yield from s.text_stream


# ---------------------------------------------------------------------------
# Google Gemini
# ---------------------------------------------------------------------------

def _to_gemini_history(messages: list[dict]) -> list[dict]:
    """Converte histórico no formato Anthropic para o formato Gemini."""
    result = []
    for msg in messages:
        role = "model" if msg["role"] == "assistant" else "user"
        result.append({"role": role, "parts": [msg["content"]]})
    return result


class GeminiProvider(LLMProvider):
    """Provedor usando a API do Google Gemini."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = GEMINI_CHAT_MODEL,
        max_tokens: int = 2048,
    ):
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "Chave da API Gemini não encontrada. "
                "Defina GEMINI_API_KEY ou use --gemini-key."
            )
        self._model = model
        self._max_tokens = max_tokens
        self._configured = False

    def _configure(self):
        if not self._configured:
            import google.generativeai as genai
            genai.configure(api_key=self._api_key)
            self._configured = True

    def _build_model(self, system: str):
        import google.generativeai as genai
        self._configure()
        return genai.GenerativeModel(
            model_name=self._model,
            system_instruction=system,
            generation_config={"max_output_tokens": self._max_tokens},
        )

    @property
    def name(self) -> str:
        return f"Google Gemini ({self._model})"

    def complete(self, system: str, messages: list[dict]) -> str:
        model = self._build_model(system)
        history = _to_gemini_history(messages[:-1])
        chat = model.start_chat(history=history)
        response = chat.send_message(messages[-1]["content"])
        return response.text

    def stream(self, system: str, messages: list[dict]) -> Iterator[str]:
        model = self._build_model(system)
        history = _to_gemini_history(messages[:-1])
        chat = model.start_chat(history=history)
        response = chat.send_message(messages[-1]["content"], stream=True)
        for chunk in response:
            text = getattr(chunk, "text", None)
            if text:
                yield text


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_provider(
    provider: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    fast: bool = False,
    max_tokens: int = 2048,
) -> LLMProvider:
    """
    Cria um provedor de LLM pelo nome.

    Args:
        provider: "anthropic" ou "gemini"
        api_key: chave da API (lê variável de ambiente se None)
        model: modelo específico (usa padrão do provedor se None)
        fast: usa modelo mais rápido/barato (ex.: haiku, flash)
        max_tokens: limite de tokens na resposta

    Returns:
        Instância de LLMProvider pronta para uso.
    """
    p = provider.lower()

    if p in ("anthropic", "claude"):
        default_model = ANTHROPIC_FAST_MODEL if fast else ANTHROPIC_CHAT_MODEL
        return AnthropicProvider(
            api_key=api_key,
            model=model or default_model,
            max_tokens=max_tokens,
        )

    if p in ("gemini", "google"):
        default_model = GEMINI_FAST_MODEL if fast else GEMINI_CHAT_MODEL
        return GeminiProvider(
            api_key=api_key,
            model=model or default_model,
            max_tokens=max_tokens,
        )

    raise ValueError(
        f"Provedor desconhecido: '{provider}'. Use 'anthropic' ou 'gemini'."
    )
