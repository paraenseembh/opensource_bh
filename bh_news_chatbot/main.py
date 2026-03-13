#!/usr/bin/env python3
"""
Chatbot de Notícias de Belo Horizonte
======================================

Lê uma planilha do Google Sheets com links de notícias de BH (organizadas
por área), raspa o conteúdo das matérias e sobe um chatbot interativo
alimentado pela API do Claude (Anthropic).

Uso:
    python main.py [--refresh] [--max-per-area N] [--api-key KEY]

Variáveis de ambiente:
    ANTHROPIC_API_KEY  — chave de API da Anthropic (obrigatório)
    BH_SHEET_ID        — ID da planilha (opcional, usa o padrão se omitido)
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Garante que o diretório do pacote esteja no path
sys.path.insert(0, str(Path(__file__).parent))

from sheets_reader import load_all_news_links, SPREADSHEET_ID
from news_scraper import scrape_all, CACHE_FILE
from chatbot import BHNewsChatbot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

BANNER = r"""
╔══════════════════════════════════════════════════════════╗
║     🏙️  Chatbot de Notícias de Belo Horizonte 🏙️        ║
║         Alimentado pelo Claude (Anthropic)               ║
╚══════════════════════════════════════════════════════════╝
"""

HELP_TEXT = """
Comandos especiais:
  /ajuda      — mostra esta mensagem
  /areas      — lista as áreas temáticas disponíveis
  /resumo     — mostra quantos artigos foram carregados por área
  /reiniciar  — reinicia o histórico da conversa
  /sair       — encerra o chatbot

Exemplos de perguntas:
  "Quais são as últimas notícias de saúde em BH?"
  "O que está acontecendo no transporte público?"
  "Resumo das notícias de educação"
"""


def parse_args():
    parser = argparse.ArgumentParser(
        description="Chatbot de notícias de BH baseado em planilha do Google Sheets"
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Força re-download das notícias (ignora cache)",
    )
    parser.add_argument(
        "--max-per-area",
        type=int,
        default=10,
        metavar="N",
        help="Máximo de artigos por área temática (padrão: 10)",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("ANTHROPIC_API_KEY", ""),
        help="Chave da API Anthropic (ou use ANTHROPIC_API_KEY)",
    )
    parser.add_argument(
        "--sheet-id",
        default=os.environ.get("BH_SHEET_ID", SPREADSHEET_ID),
        help="ID da planilha do Google Sheets",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Nível de log (padrão: INFO)",
    )
    return parser.parse_args()


def load_articles(args) -> list[dict]:
    """Carrega e raspa os artigos de notícias."""
    use_cache = not args.refresh

    if use_cache and CACHE_FILE.exists():
        import json
        log.info("Cache encontrado em %s", CACHE_FILE)
        cache_data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        # Reconstrói lista de artigos a partir do cache
        articles = [
            v for v in cache_data.values()
            if v is not None and isinstance(v, dict) and v.get("body")
        ]
        if articles:
            log.info("Artigos carregados do cache: %d", len(articles))
            return articles
        log.info("Cache vazio ou inválido, buscando novamente...")

    log.info("Lendo planilha do Google Sheets (ID: %s)...", args.sheet_id)
    news_by_area = load_all_news_links(sheet_id=args.sheet_id)

    if not news_by_area:
        log.error(
            "Nenhum link encontrado na planilha. "
            "Verifique se a planilha é pública e o ID está correto."
        )
        sys.exit(1)

    log.info("Raspando artigos (máx. %d por área)...", args.max_per_area)
    articles = scrape_all(
        news_by_area,
        max_per_area=args.max_per_area,
        use_cache=use_cache,
    )

    if not articles:
        log.error("Nenhum artigo foi raspado com sucesso.")
        sys.exit(1)

    return articles


def run_interactive(chatbot: BHNewsChatbot):
    """Loop interativo do chatbot."""
    print(BANNER)
    print(chatbot.get_articles_summary())
    print(HELP_TEXT)
    print("─" * 60)

    while True:
        try:
            user_input = input("\n🧑 Você: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nAté logo!")
            break

        if not user_input:
            continue

        cmd = user_input.lower()

        if cmd in ("/sair", "/exit", "/quit"):
            print("Até logo!")
            break
        elif cmd in ("/ajuda", "/help"):
            print(HELP_TEXT)
            continue
        elif cmd in ("/areas",):
            areas = chatbot.get_areas()
            print("\n📋 Áreas disponíveis:")
            for area in areas:
                print(f"  • {area}")
            continue
        elif cmd in ("/resumo",):
            print("\n" + chatbot.get_articles_summary())
            continue
        elif cmd in ("/reiniciar", "/reset"):
            chatbot.reset_history()
            print("✅ Histórico reiniciado.")
            continue

        print("\n🤖 Assistente: ", end="", flush=True)
        try:
            for token in chatbot.chat_stream(user_input):
                print(token, end="", flush=True)
            print()  # nova linha após resposta
        except Exception as e:
            print(f"\n❌ Erro na API: {e}")
            log.debug("Detalhe do erro:", exc_info=True)


def main():
    args = parse_args()

    # Configura nível de log
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    # Valida API key
    if not args.api_key:
        print(
            "❌ Chave da API Anthropic não encontrada.\n"
            "   Defina a variável ANTHROPIC_API_KEY ou use --api-key KEY"
        )
        sys.exit(1)

    # Carrega artigos
    articles = load_articles(args)

    # Inicia chatbot
    log.info("Inicializando chatbot com %d artigos...", len(articles))
    try:
        bot = BHNewsChatbot(articles=articles, api_key=args.api_key)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)

    # Loop interativo
    run_interactive(bot)


if __name__ == "__main__":
    main()
