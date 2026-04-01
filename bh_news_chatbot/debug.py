#!/usr/bin/env python3
"""
debug.py — Inspeciona o cache de artigos e categorias do chatbot de BH.

Uso:
    python bh_news_chatbot/debug.py
    python bh_news_chatbot/debug.py --verbose
    python bh_news_chatbot/debug.py --url https://...
    python bh_news_chatbot/debug.py --export artigos.json
"""

import argparse
import json
import sys
from pathlib import Path

CACHE_FILE      = Path(__file__).parent / "cache" / "news_cache.json"
CAT_CACHE_FILE  = Path(__file__).parent / "cache" / "categories_cache.json"

SEP  = "─" * 60
SEP2 = "═" * 60


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"[ERRO] Não foi possível ler {path}: {e}")
        return {}


def status_icon(article) -> str:
    if article is None:
        return "✗"
    body = article.get("body", "")
    if not body:
        return "⚠"
    return "✓"


def print_summary(cache: dict, cat_cache: dict):
    total     = len(cache)
    ok        = sum(1 for v in cache.values() if v and v.get("body"))
    failed    = sum(1 for v in cache.values() if v is None)
    empty     = total - ok - failed
    cat_count = len(cat_cache)

    by_area: dict[str, int] = {}
    for v in cache.values():
        if v and v.get("body"):
            area = v.get("area", "(sem área)")
            by_area[area] = by_area.get(area, 0) + 1

    print(SEP2)
    print("  RESUMO DO CACHE")
    print(SEP2)
    print(f"  Arquivo:       {CACHE_FILE}")
    print(f"  Tamanho:       {CACHE_FILE.stat().st_size / 1024:.1f} KB" if CACHE_FILE.exists() else "  Arquivo:       (não existe)")
    print(f"  Total de URLs: {total}")
    print(f"  ✓ Com conteúdo: {ok}")
    print(f"  ⚠ Sem body:     {empty}")
    print(f"  ✗ Falhou:       {failed}")
    print(f"  Categorizados: {cat_count}")
    print()

    if by_area:
        print("  Artigos por área:")
        for area, count in sorted(by_area.items()):
            bar = "█" * min(count, 25)
            print(f"    {area:<30} {bar} {count}")
    print(SEP2)


def print_articles(cache: dict, cat_cache: dict, verbose: bool = False):
    articles = [(url, v) for url, v in cache.items() if v and v.get("body")]
    articles.sort(key=lambda x: x[1].get("area", ""))

    print(f"\n  ARTIGOS COM CONTEÚDO ({len(articles)})\n{SEP}")

    for url, art in articles:
        icon       = status_icon(art)
        title      = art.get("title") or "(sem título)"
        area       = art.get("area") or "(sem área)"
        date       = art.get("date") or ""
        body       = art.get("body") or ""
        categories = cat_cache.get(url, [])
        cats_str   = ", ".join(categories) if categories else "—"

        print(f"\n{icon} {title}")
        print(f"   Área:       {area}")
        if date:
            print(f"   Data:       {date}")
        print(f"   URL:        {url[:80]}{'…' if len(url) > 80 else ''}")
        print(f"   Categorias: {cats_str}")
        print(f"   Body:       {len(body):,} chars", end="")

        if body:
            preview = body[:120].replace("\n", " ").strip()
            print(f"\n   Preview:    {preview}…" if len(body) > 120 else f"\n   Preview:    {preview}")
        else:
            print()

        if verbose:
            print(f"\n{'-'*50}")
            print(body[:2000])
            if len(body) > 2000:
                print(f"\n  [...{len(body) - 2000:,} chars restantes]")
            print(f"{'-'*50}")


def print_failures(cache: dict):
    failed = [(url, v) for url, v in cache.items() if v is None]
    empty  = [(url, v) for url, v in cache.items() if v and not v.get("body")]

    if not failed and not empty:
        print("\n  Nenhuma falha registrada.")
        return

    if failed:
        print(f"\n  FALHAS ({len(failed)}) — URLs que não puderam ser acessadas\n{SEP}")
        for url, _ in failed:
            print(f"  ✗ {url}")

    if empty:
        print(f"\n  SEM CONTEÚDO ({len(empty)}) — URLs acessadas mas sem body extraído\n{SEP}")
        for url, art in empty:
            title = (art or {}).get("title", "(sem título)")
            print(f"  ⚠ {title}")
            print(f"    {url}")


def inspect_url(url: str, cache: dict, cat_cache: dict):
    art = cache.get(url)
    if art is None and url not in cache:
        print(f"URL não encontrada no cache: {url}")
        return

    if art is None:
        print(f"✗ URL falhou ao ser raspada: {url}")
        return

    cats = cat_cache.get(url, [])
    print(SEP2)
    print(f"  URL:        {url}")
    print(f"  Título:     {art.get('title', '(sem título)')}")
    print(f"  Área:       {art.get('area', '(sem área)')}")
    print(f"  Data:       {art.get('date', '—')}")
    print(f"  Categorias: {', '.join(cats) if cats else '—'}")
    print(f"  Body:       {len(art.get('body', '')):,} chars")
    print(SEP2)
    print()
    print(art.get("body", "(sem conteúdo)"))


def export_articles(cache: dict, cat_cache: dict, output: str):
    articles = []
    for url, art in cache.items():
        if art and art.get("body"):
            entry = dict(art)
            entry["categories"] = cat_cache.get(url, [])
            articles.append(entry)

    Path(output).write_text(
        json.dumps(articles, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"✓ {len(articles)} artigos exportados para: {output}")


def main():
    parser = argparse.ArgumentParser(
        description="Inspeciona o cache de artigos do chatbot de BH"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Exibe o conteúdo completo de cada artigo",
    )
    parser.add_argument(
        "--url",
        metavar="URL",
        help="Inspeciona uma URL específica do cache",
    )
    parser.add_argument(
        "--failures",
        action="store_true",
        help="Exibe apenas URLs que falharam ou ficaram sem conteúdo",
    )
    parser.add_argument(
        "--export",
        metavar="ARQUIVO.json",
        help="Exporta os artigos para um arquivo JSON",
    )
    args = parser.parse_args()

    cache     = load_json(CACHE_FILE)
    cat_cache = load_json(CAT_CACHE_FILE)

    if not cache:
        print("Cache vazio ou não encontrado.")
        print(f"Execute primeiro: python main.py --max-per-area 3")
        sys.exit(0)

    if args.url:
        inspect_url(args.url, cache, cat_cache)
        return

    if args.export:
        export_articles(cache, cat_cache, args.export)
        return

    print_summary(cache, cat_cache)

    if args.failures:
        print_failures(cache)
    else:
        print_articles(cache, cat_cache, verbose=args.verbose)
        print_failures(cache)


if __name__ == "__main__":
    main()
