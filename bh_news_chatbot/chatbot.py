"""
Chatbot de notícias de Belo Horizonte alimentado pela API do Claude (Anthropic).

Recebe os artigos raspados como contexto e responde perguntas sobre BH.
"""

import logging
import os
from typing import Optional

log = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """Você é um assistente especializado em notícias de Belo Horizonte (BH), Minas Gerais.

Você foi treinado com as seguintes notícias recentes, organizadas por área temática:

{news_context}

---

INSTRUÇÕES:
- Responda SEMPRE em português do Brasil.
- Baseie suas respostas nas notícias fornecidas acima.
- Se a informação pedida não estiver nas notícias, diga claramente que não encontrou essa informação nas fontes disponíveis.
- Ao citar uma notícia, mencione a área temática e o título.
- Seja objetivo, informativo e amigável.
- Você pode cruzar informações de diferentes áreas quando fizer sentido.
- Se perguntado sobre um tema amplo, faça um resumo das notícias relevantes.
"""

MODEL = "claude-sonnet-4-6"


class BHNewsChatbot:
    """Chatbot de notícias de BH usando a API do Claude."""

    def __init__(self, articles: list[dict], api_key: Optional[str] = None):
        """
        Args:
            articles: lista de artigos com chaves url, title, date, body, area
            api_key: chave da API Anthropic (lê ANTHROPIC_API_KEY se None)
        """
        from news_scraper import format_articles_for_context

        self._key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not self._key:
            raise ValueError(
                "Chave da API Anthropic não encontrada. "
                "Defina a variável de ambiente ANTHROPIC_API_KEY."
            )

        self._articles = articles
        self._news_context = format_articles_for_context(articles)
        self._system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            news_context=self._news_context
        )
        self._history: list[dict] = []
        self._client = None

    def _get_client(self):
        """Cria o cliente Anthropic de forma lazy."""
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self._key)
        return self._client

    def chat(self, user_message: str) -> str:
        """
        Envia uma mensagem e retorna a resposta do chatbot.
        Mantém histórico da conversa.
        """
        self._history.append({"role": "user", "content": user_message})

        client = self._get_client()
        import anthropic

        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=self._system_prompt,
            messages=self._history,
        )

        assistant_message = response.content[0].text
        self._history.append({"role": "assistant", "content": assistant_message})
        return assistant_message

    def chat_stream(self, user_message: str):
        """
        Versão streaming do chat. Gera tokens à medida que chegam.
        Uso: for token in chatbot.chat_stream("pergunta"): print(token, end="")
        """
        self._history.append({"role": "user", "content": user_message})

        client = self._get_client()
        full_response = ""

        with client.messages.stream(
            model=MODEL,
            max_tokens=2048,
            system=self._system_prompt,
            messages=self._history,
        ) as stream:
            for text in stream.text_stream:
                full_response += text
                yield text

        self._history.append({"role": "assistant", "content": full_response})

    def reset_history(self):
        """Reinicia o histórico da conversa."""
        self._history = []

    def get_areas(self) -> list[str]:
        """Retorna as áreas temáticas disponíveis nas notícias."""
        areas = sorted({art.get("area", "Geral") for art in self._articles})
        return areas

    def get_articles_summary(self) -> str:
        """Retorna um resumo dos artigos carregados."""
        by_area: dict[str, int] = {}
        for art in self._articles:
            area = art.get("area", "Geral")
            by_area[area] = by_area.get(area, 0) + 1

        lines = ["📰 Notícias carregadas:"]
        for area, count in sorted(by_area.items()):
            lines.append(f"  • {area}: {count} artigo(s)")
        lines.append(f"  Total: {len(self._articles)} artigos")
        return "\n".join(lines)
