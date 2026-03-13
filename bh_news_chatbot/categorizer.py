"""
Categorizador de notícias de Belo Horizonte.

Usa a API do Claude para analisar o conteúdo de cada artigo e atribuir
uma ou mais categorias temáticas de um vocabulário controlado.

O processamento é feito em lotes para reduzir custo e latência.
O resultado é persistido no cache junto com os demais dados do artigo.
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# Modelo mais leve para classificação em lote (mais barato e rápido)
CATEGORIZER_MODEL = "claude-haiku-4-5-20251001"

# Taxonomia de categorias relevantes para BH
CATEGORIES = [
    "Saúde",
    "Educação",
    "Mobilidade e Transporte",
    "Segurança Pública",
    "Meio Ambiente",
    "Cultura e Lazer",
    "Política e Gestão Pública",
    "Economia e Emprego",
    "Habitação e Urbanismo",
    "Infraestrutura e Obras",
    "Esportes",
    "Tecnologia e Inovação",
    "Assistência Social",
    "Outros",
]

BATCH_SIZE = 15  # artigos por chamada à API

CATEGORIES_CACHE_FILE = Path(__file__).parent / "cache" / "categories_cache.json"

_SYSTEM_PROMPT = f"""\
Você é um classificador de notícias. Dada uma lista de artigos de Belo Horizonte (BH),
atribua a cada um entre 1 e 3 categorias do seguinte vocabulário controlado:

{json.dumps(CATEGORIES, ensure_ascii=False, indent=2)}

Responda SOMENTE com um objeto JSON no formato:
{{
  "<url>": ["Categoria1", "Categoria2"],
  "<url2>": ["Categoria1"]
}}

Regras:
- Use apenas categorias do vocabulário acima (exatamente como escritas).
- Atribua no mínimo 1 e no máximo 3 categorias por artigo.
- Se o conteúdo não se encaixar em nenhuma categoria, use "Outros".
- Não inclua explicações fora do JSON.
"""


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _load_categories_cache() -> dict[str, list[str]]:
    CATEGORIES_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if CATEGORIES_CACHE_FILE.exists():
        try:
            return json.loads(CATEGORIES_CACHE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_categories_cache(cache: dict[str, list[str]]) -> None:
    CATEGORIES_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CATEGORIES_CACHE_FILE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Classificação via API
# ---------------------------------------------------------------------------

def _build_batch_prompt(batch: list[dict]) -> str:
    """Monta o texto de entrada com os artigos do lote."""
    parts = []
    for art in batch:
        url = art.get("url", "")
        title = art.get("title", "(sem título)")
        # Usa apenas os primeiros 600 chars do corpo para economizar tokens
        body_snippet = (art.get("body") or "")[:600]
        parts.append(
            f"URL: {url}\n"
            f"Título: {title}\n"
            f"Trecho: {body_snippet}\n"
        )
    return "\n---\n".join(parts)


def _classify_batch(
    client,
    batch: list[dict],
) -> dict[str, list[str]]:
    """Envia um lote de artigos para classificação e retorna {url: [categorias]}."""
    prompt = _build_batch_prompt(batch)

    response = client.messages.create(
        model=CATEGORIZER_MODEL,
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()

    # Extrai JSON da resposta (pode vir com markdown code block)
    json_match = __import__("re").search(r"\{.*\}", raw, __import__("re").DOTALL)
    if not json_match:
        log.warning("Resposta inesperada da API (sem JSON): %s", raw[:200])
        return {}

    try:
        result = json.loads(json_match.group())
    except json.JSONDecodeError as e:
        log.warning("Erro ao parsear JSON de categorias: %s", e)
        return {}

    # Valida e sanitiza: garante que os valores são listas de strings do vocabulário
    valid = set(CATEGORIES)
    clean: dict[str, list[str]] = {}
    for url, cats in result.items():
        if not isinstance(cats, list):
            continue
        sanitized = [c for c in cats if isinstance(c, str) and c in valid]
        if not sanitized:
            sanitized = ["Outros"]
        clean[url] = sanitized

    return clean


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def categorize_articles(
    articles: list[dict],
    api_key: Optional[str] = None,
    use_cache: bool = True,
    batch_size: int = BATCH_SIZE,
) -> list[dict]:
    """
    Categoriza uma lista de artigos usando a API do Claude.

    Adiciona o campo ``categories`` (list[str]) a cada artigo (in-place).
    Artigos já categorizados no cache são ignorados (se use_cache=True).

    Args:
        articles: lista de dicts com chaves url, title, body.
        api_key: chave Anthropic (lê ANTHROPIC_API_KEY se None).
        use_cache: salva/carrega resultados em cache local.
        batch_size: artigos por chamada à API.

    Returns:
        A mesma lista com o campo ``categories`` preenchido.
    """
    import anthropic

    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise ValueError("ANTHROPIC_API_KEY não definida.")

    client = anthropic.Anthropic(api_key=key)
    cache = _load_categories_cache() if use_cache else {}

    # Separa artigos que ainda não foram categorizados
    pending = [a for a in articles if a.get("url") and a["url"] not in cache]

    if not pending:
        log.info("Todos os artigos já estão categorizados (cache).")
    else:
        log.info("Categorizando %d artigos em lotes de %d...", len(pending), batch_size)

    for i in range(0, len(pending), batch_size):
        batch = pending[i : i + batch_size]
        log.info(
            "  Lote %d/%d (%d artigos)...",
            i // batch_size + 1,
            -(-len(pending) // batch_size),
            len(batch),
        )
        try:
            result = _classify_batch(client, batch)
            cache.update(result)
            # Artigos sem retorno recebem "Outros"
            for art in batch:
                if art["url"] not in cache:
                    cache[art["url"]] = ["Outros"]
        except Exception as e:
            log.warning("Erro no lote %d: %s", i // batch_size + 1, e)
            for art in batch:
                cache.setdefault(art["url"], ["Outros"])

        if use_cache:
            _save_categories_cache(cache)

    # Aplica categorias nos artigos
    for art in articles:
        url = art.get("url", "")
        art["categories"] = cache.get(url, ["Outros"])

    log.info("Categorização concluída.")
    return articles


def summarize_by_category(articles: list[dict]) -> dict[str, list[dict]]:
    """
    Agrupa artigos por categoria.

    Returns:
        {categoria: [artigo, ...]} — um artigo pode aparecer em múltiplas categorias.
    """
    result: dict[str, list[dict]] = {}
    for art in articles:
        for cat in art.get("categories", ["Outros"]):
            result.setdefault(cat, []).append(art)
    return result


def print_category_report(articles: list[dict]) -> None:
    """Imprime um relatório textual de categorias no stdout."""
    by_cat = summarize_by_category(articles)
    print("\n📊 Distribuição por categoria:")
    print("─" * 45)
    for cat in CATEGORIES:
        count = len(by_cat.get(cat, []))
        if count:
            bar = "█" * min(count, 30)
            print(f"  {cat:<30} {bar} {count}")
    print("─" * 45)
    total = len(articles)
    categorized = sum(1 for a in articles if a.get("categories") and a["categories"] != ["Outros"])
    print(f"  Total: {total} artigos | Categorizados: {categorized}")
