#!/usr/bin/env python3
"""
Chatbot de Decretos Municipais de Belo Horizonte
=================================================

Lê uma planilha do Google Sheets com links de decretos e atos normativos
do município de BH (organizados por área), raspa o conteúdo dos documentos
e sobe um chatbot interativo alimentado pela API do Claude ou Gemini.

Uso:
    python main.py [--refresh] [--max-per-area N] [--api-key KEY]

Variáveis de ambiente:
    ANTHROPIC_API_KEY  — chave de API da Anthropic (obrigatório se --provider anthropic)
    GEMINI_API_KEY     — chave de API do Google Gemini (obrigatório se --provider gemini)
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
from csv_loader import load_articles_from_csv, DEFAULT_CSV
from chatbot import BHNewsChatbot
from categorizer import categorize_articles, print_category_report
from llm_provider import create_provider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

BANNER = r"""
╔══════════════════════════════════════════════════════════╗
║   🏛️  Chatbot de Decretos Municipais de BH  🏛️          ║
║        Alimentado pelo Claude / Gemini                   ║
╚══════════════════════════════════════════════════════════╝
"""

HELP_TEXT = """
Comandos especiais:
  /ajuda        — mostra esta mensagem
  /areas        — lista as áreas da planilha
  /documentos   — lista todos os documentos carregados (lê da memória, não do LLM)
  /documentos <área> — filtra documentos por área (ex: /documentos Orçamento)
  /categorias   — mostra distribuição de decretos por categoria legislativa
  /resumo       — mostra quantos documentos foram carregados por área
  /reiniciar    — reinicia o histórico da conversa
  /sair         — encerra o chatbot

Exemplos de perguntas:
  "Quais decretos tratam de urbanismo e zoneamento?"
  "Há atos normativos sobre licitações recentes?"
  "Resumo dos decretos de habitação e regularização fundiária"
  "Quais documentos falam sobre meio ambiente e saneamento?"
"""


def parse_args():
    parser = argparse.ArgumentParser(
        description="Chatbot de decretos municipais de BH baseado em planilha do Google Sheets"
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Força re-download dos documentos (ignora cache)",
    )
    parser.add_argument(
        "--max-per-area",
        type=int,
        default=10,
        metavar="N",
        help="Máximo de artigos por área temática (padrão: 10)",
    )
    parser.add_argument(
        "--provider",
        default="anthropic",
        choices=["anthropic", "gemini", "maritaca"],
        help="Provedor de LLM: 'anthropic' (padrão), 'gemini' ou 'maritaca'",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("ANTHROPIC_API_KEY", ""),
        help="Chave da API Anthropic (ou use ANTHROPIC_API_KEY)",
    )
    parser.add_argument(
        "--gemini-key",
        default=os.environ.get("GEMINI_API_KEY", ""),
        help="Chave da API Google Gemini (ou use GEMINI_API_KEY)",
    )
    parser.add_argument(
        "--maritaca-key",
        default=os.environ.get("MARITACA_KEY", ""),
        help="Chave da API Maritaca (ou use MARITACA_KEY)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Modelo específico a usar (ex: gemini-1.5-pro, claude-sonnet-4-6)",
    )
    parser.add_argument(
        "--sheet-id",
        default=os.environ.get("BH_SHEET_ID", SPREADSHEET_ID),
        help="ID da planilha do Google Sheets",
    )
    parser.add_argument(
        "--csv",
        metavar="ARQUIVO",
        default=None,
        help=(
            f"Carrega legislação diretamente de um CSV local em vez do Google Sheets "
            f"(padrão quando omitido: {DEFAULT_CSV.name})"
        ),
    )
    parser.add_argument(
        "--use-local-csv",
        action="store_true",
        help=f"Atalho: usa o CSV local padrão ({DEFAULT_CSV.name}) como fonte de dados",
    )
    parser.add_argument(
        "--categorize",
        action="store_true",
        help="Categoriza os artigos por conteúdo usando Claude antes de iniciar o chat",
    )
    parser.add_argument(
        "--only-categorize",
        action="store_true",
        help="Apenas categoriza e exibe o relatório, sem iniciar o chatbot",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Nível de log (padrão: INFO)",
    )
    return parser.parse_args()


def _csv_path(args) -> "Path | None":
    """Retorna o caminho do CSV a usar, ou None se a fonte for o Google Sheets."""
    from pathlib import Path
    if args.csv:
        return Path(args.csv)
    if args.use_local_csv:
        return DEFAULT_CSV
    return None


def load_articles(args) -> list[dict]:
    """Carrega artigos: do CSV local (se --csv/--use-local-csv) ou do Google Sheets."""
    csv_path = _csv_path(args)

    if csv_path is not None:
        log.info("Fonte: CSV local (%s)", csv_path)
        try:
            articles = load_articles_from_csv(csv_path)
        except FileNotFoundError as e:
            log.error("%s", e)
            sys.exit(1)
        if not articles:
            log.error("Nenhum registro válido encontrado no CSV.")
            sys.exit(1)
        return articles

    # ── Fonte: Google Sheets + scraping ────────────────────────────────────
    use_cache = not args.refresh

    if use_cache and CACHE_FILE.exists():
        import json
        log.info("Cache encontrado em %s", CACHE_FILE)
        cache_data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
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


def _cmd_list_documents(articles: list[dict], area_filter: str | None = None):
    """Lista todos os documentos da memória (não do contexto do LLM)."""
    if area_filter:
        subset = [
            a for a in articles
            if area_filter.lower() in a.get("area", "").lower()
        ]
        if not subset:
            print(f"\n⚠️  Nenhum documento encontrado para a área '{area_filter}'.")
            print("    Use /areas para ver as áreas disponíveis.")
            return
        title = f"📄 Documentos — área '{area_filter}' ({len(subset)} de {len(articles)})"
    else:
        subset = articles
        title = f"📄 Todos os documentos ({len(subset)} no total)"

    print(f"\n{title}")
    print("─" * 60)

    by_area: dict[str, list[dict]] = {}
    for art in subset:
        by_area.setdefault(art.get("area", "Geral"), []).append(art)

    for area in sorted(by_area):
        print(f"\n  [{area}] — {len(by_area[area])} doc(s)")
        for art in by_area[area]:
            date = art.get("date", "")
            title_str = art.get("title", "(sem título)")
            date_str = f"[{date}] " if date else ""
            print(f"    • {date_str}{title_str}")

    print()


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
        cmd_base = cmd.split()[0] if cmd.split() else ""

        if cmd in ("/sair", "/exit", "/quit"):
            print("Até logo!")
            break
        elif cmd in ("/ajuda", "/help"):
            print(HELP_TEXT)
            continue
        elif cmd in ("/areas",):
            areas = chatbot.get_areas()
            print("\n📋 Áreas disponíveis (da planilha):")
            for area in areas:
                print(f"  • {area}")
            continue
        elif cmd_base == "/documentos":
            area_filter = user_input[len("/documentos"):].strip() or None
            _cmd_list_documents(chatbot._articles, area_filter)
            continue
        elif cmd in ("/categorias",):
            if any(a.get("categories") for a in chatbot._articles):
                print_category_report(chatbot._articles)
            else:
                print(
                    "\n⚠️  Artigos ainda não categorizados.\n"
                    "   Reinicie com --categorize para ativar a categorização."
                )
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

    # Cria provedor de LLM
    try:
        key_map = {
            "anthropic": args.api_key,
            "gemini":    args.gemini_key,
            "maritaca":  args.maritaca_key,
        }
        key = key_map.get(args.provider, args.api_key)
        chat_provider = create_provider(args.provider, api_key=key, model=args.model)
        # Categorização usa modelo rápido/barato do mesmo provedor
        fast_provider = create_provider(args.provider, api_key=key, fast=True)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)

    log.info("Provedor: %s", chat_provider.name)

    # Carrega artigos
    articles = load_articles(args)

    # Categoriza se solicitado
    if args.categorize or args.only_categorize:
        log.info("Categorizando artigos por conteúdo...")
        categorize_articles(articles, provider=fast_provider)
        print_category_report(articles)
        if args.only_categorize:
            return

    # Inicia chatbot
    log.info("Inicializando chatbot com %d artigos...", len(articles))
    try:
        bot = BHNewsChatbot(articles=articles, provider=chat_provider)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)

    # Loop interativo
    run_interactive(bot)


if __name__ == "__main__":
    main()
