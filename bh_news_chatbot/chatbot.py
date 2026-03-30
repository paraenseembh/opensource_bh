"""
Chatbot de notícias de Belo Horizonte.

Recebe os artigos raspados como contexto e responde perguntas sobre BH.
Suporta múltiplos provedores de LLM via LLMProvider (Anthropic, Gemini…).
"""

import logging
import os
from typing import Optional

from llm_provider import LLMProvider, create_provider

log = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """Você é um assistente especializado em notícias de Belo Horizonte (BH), Minas Gerais.

Você foi treinado com as seguintes notícias recentes, organizadas por área temática:

{news_context}

---

INSTRUÇÕES:
- Responda SEMPRE em português do Brasil.
- Baseie suas respostas nas notícias fornecidas acima.
- Se a informação pedida não estiver nas notícias, diga claramente que não encontrou essa informação nas fontes disponíveis.
- Ao citar uma notícia, mencione a área temática, as categorias (se disponíveis) e o título.
- Seja objetivo, informativo e amigável.
- Você pode cruzar informações de diferentes áreas quando fizer sentido.
- Se perguntado sobre um tema amplo, faça um resumo das notícias relevantes.
- Quando o usuário perguntar por uma categoria específica (ex: "Saúde", "Meio Ambiente"), filtre as notícias pelo campo de categorias.
"""


class BHNewsChatbot:
    """Chatbot de notícias de BH com suporte a múltiplos provedores de LLM."""

    def __init__(
        self,
        articles: list[dict],
        provider: Optional[LLMProvider] = None,
        # Parâmetros legados para retrocompatibilidade
        api_key: Optional[str] = None,
    ):
        """
        Args:
            articles: lista de artigos com chaves url, title, date, body, area
            provider: instância de LLMProvider (Anthropic, Gemini, etc.)
                      Se None, usa AnthropicProvider com ANTHROPIC_API_KEY.
            api_key: (legado) chave Anthropic. Ignorado se provider for passado.
        """
        from news_scraper import format_articles_for_context

        if provider is None:
            provider = create_provider("anthropic", api_key=api_key)

        self._provider = provider
        self._articles = articles
        self._news_context = format_articles_for_context(articles)
        self._system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            news_context=self._news_context
        )
        self._history: list[dict] = []

    def chat(self, user_message: str) -> str:
        """Envia uma mensagem e retorna a resposta. Mantém histórico."""
        self._history.append({"role": "user", "content": user_message})
        response = self._provider.complete(self._system_prompt, self._history)
        self._history.append({"role": "assistant", "content": response})
        return response

    def chat_stream(self, user_message: str):
        """
        Versão streaming do chat. Gera tokens à medida que chegam.
        Uso: for token in chatbot.chat_stream("pergunta"): print(token, end="")
        """
        self._history.append({"role": "user", "content": user_message})
        full_response = ""
        for token in self._provider.stream(self._system_prompt, self._history):
            full_response += token
            yield token
        self._history.append({"role": "assistant", "content": full_response})

    def reset_history(self):
        """Reinicia o histórico da conversa."""
        self._history = []

    def get_areas(self) -> list[str]:
        """Retorna as áreas temáticas disponíveis nas notícias."""
        return sorted({art.get("area", "Geral") for art in self._articles})

    def get_articles_summary(self) -> str:
        """Retorna um resumo dos artigos carregados."""
        by_area: dict[str, int] = {}
        for art in self._articles:
            area = art.get("area", "Geral")
            by_area[area] = by_area.get(area, 0) + 1

        lines = [f"Notícias carregadas ({self._provider.name}):"]
        for area, count in sorted(by_area.items()):
            lines.append(f"  • {area}: {count} artigo(s)")
        lines.append(f"  Total: {len(self._articles)} artigos")
        return "\n".join(lines)
