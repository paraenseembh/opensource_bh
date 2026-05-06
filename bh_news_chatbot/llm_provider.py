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
GEMINI_CHAT_MODEL    = "gemini-3.1-flash"
GEMINI_FAST_MODEL    = "gemini-3.1-flash"
MARITACA_BASE_URL    = "https://chat.maritaca.ai/api"
MARITACA_CHAT_MODEL  = "sabia-4"
MARITACA_FAST_MODEL  = "sabiazinho-4"

# Limite de contexto em chars por provedor
# (janela de tokens × ~3,5 chars/token, com margem de segurança)
CONTEXT_LIMIT_CHARS = {
    "anthropic": 680_000,   # 200K tokens
    "gemini":    3_500_000, # 1M tokens
    "maritaca":  430_000,   # 128K tokens
}


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

def _to_gemini_contents(messages: list[dict]):
    """Converte histórico no formato Anthropic para lista de Content do google.genai."""
    from google.genai import types
    return [
        types.Content(
            role="model" if msg["role"] == "assistant" else "user",
            parts=[types.Part(text=msg["content"])],
        )
        for msg in messages
    ]


class GeminiProvider(LLMProvider):
    """Provedor usando a API do Google Gemini (SDK google-genai)."""

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
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def _config(self, system: str):
        from google.genai import types
        return types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=self._max_tokens,
        )

    @property
    def name(self) -> str:
        return f"Google Gemini ({self._model})"

    def complete(self, system: str, messages: list[dict]) -> str:
        client = self._get_client()
        response = client.models.generate_content(
            model=self._model,
            config=self._config(system),
            contents=_to_gemini_contents(messages),
        )
        return response.text

    def stream(self, system: str, messages: list[dict]) -> Iterator[str]:
        client = self._get_client()
        for chunk in client.models.generate_content_stream(
            model=self._model,
            config=self._config(system),
            contents=_to_gemini_contents(messages),
        ):
            if chunk.text:
                yield chunk.text


# ---------------------------------------------------------------------------
# Maritaca (Sabiá)
# ---------------------------------------------------------------------------

class MariticaProvider(LLMProvider):
    """Provedor usando a API da Maritaca.ai (Sabiá), compatível com OpenAI."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = MARITACA_CHAT_MODEL,
        max_tokens: int = 2048,
    ):
        self._api_key = api_key or os.environ.get("MARITACA_KEY", "")
        if not self._api_key:
            raise ValueError(
                "Chave da API Maritaca não encontrada. "
                "Defina MARITACA_KEY ou use --maritaca-key."
            )
        self._model = model
        self._max_tokens = max_tokens
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self._api_key, base_url=MARITACA_BASE_URL)
        return self._client

    @property
    def name(self) -> str:
        return f"Maritaca ({self._model})"

    def complete(self, system: str, messages: list[dict]) -> str:
        msgs = [{"role": "system", "content": system}] + messages
        resp = self._get_client().chat.completions.create(
            model=self._model,
            messages=msgs,
            max_tokens=self._max_tokens,
        )
        return resp.choices[0].message.content

    def stream(self, system: str, messages: list[dict]) -> Iterator[str]:
        msgs = [{"role": "system", "content": system}] + messages
        for chunk in self._get_client().chat.completions.create(
            model=self._model,
            messages=msgs,
            max_tokens=self._max_tokens,
            stream=True,
        ):
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


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

    if p in ("maritaca", "sabia"):
        default_model = MARITACA_FAST_MODEL if fast else MARITACA_CHAT_MODEL
        return MariticaProvider(
            api_key=api_key,
            model=model or default_model,
            max_tokens=max_tokens,
        )

    raise ValueError(
        f"Provedor desconhecido: '{provider}'. Use 'anthropic', 'gemini' ou 'maritaca'."
    )
