"""
Scraper de notícias: baixa o conteúdo textual de cada URL de notícia.

Usa requests + BeautifulSoup para extrair título, data e corpo da matéria.
Salva um cache local em JSON para evitar re-downloads.
"""

import json
import logging
import re
import time
from pathlib import Path
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from html.parser import HTMLParser

log = logging.getLogger(__name__)

CACHE_FILE = Path(__file__).parent / "cache" / "news_cache.json"
REQUEST_DELAY = 1.0  # segundos entre requisições
REQUEST_TIMEOUT = 20
MAX_CONTENT_LENGTH = 8000  # chars por artigo (evita contextos gigantes)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}


# ---------------------------------------------------------------------------
# Parser HTML simples (sem dependência de bs4 se não instalada)
# ---------------------------------------------------------------------------

def _try_bs4(html: str) -> Optional[dict]:
    """Tenta usar BeautifulSoup para extrair conteúdo."""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")

        # Remove elementos de ruído
        for tag in soup(["script", "style", "nav", "footer", "header",
                          "aside", "form", "noscript", "iframe"]):
            tag.decompose()

        # Título
        title = ""
        if soup.title:
            title = soup.title.get_text(strip=True)
        if not title and soup.find("h1"):
            title = soup.find("h1").get_text(strip=True)

        # Data (busca padrões comuns)
        date = ""
        for selector in [
            "time", "[class*='date']", "[class*='data']",
            "[class*='published']", "[class*='time']",
        ]:
            el = soup.select_one(selector)
            if el:
                date = el.get_text(strip=True)
                if date:
                    break

        # Corpo do artigo — tenta seletores semânticos
        body = ""
        for selector in [
            "article", "[class*='article-body']", "[class*='article_body']",
            "[class*='materia']", "[class*='content']", "[class*='texto']",
            "main", ".post-content", ".entry-content",
        ]:
            el = soup.select_one(selector)
            if el:
                body = el.get_text(separator="\n", strip=True)
                if len(body) > 200:
                    break

        # Fallback: body inteiro
        if not body and soup.body:
            body = soup.body.get_text(separator="\n", strip=True)

        # Limpa espaços excessivos
        body = re.sub(r"\n{3,}", "\n\n", body).strip()

        return {"title": title, "date": date, "body": body}
    except ImportError:
        return None


class _TextExtractor(HTMLParser):
    """Extrator de texto HTML sem dependências externas."""

    def __init__(self):
        super().__init__()
        self._skip = False
        self._parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "footer", "header"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "footer", "header"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            stripped = data.strip()
            if stripped:
                self._parts.append(stripped)

    def get_text(self) -> str:
        return "\n".join(self._parts)


def _extract_with_stdlib(html: str) -> dict:
    """Extração básica de texto usando apenas stdlib."""
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass
    body = re.sub(r"\n{3,}", "\n\n", parser.get_text()).strip()

    # Título a partir de <title>
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip() if title_match else ""

    return {"title": title, "date": "", "body": body}


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _fetch_html(url: str) -> Optional[str]:
    """Baixa o HTML de uma URL."""
    try:
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if "text/html" not in content_type and "text/plain" not in content_type:
                log.debug("Ignorando %s (Content-Type: %s)", url, content_type)
                return None
            raw = resp.read()
            # Detecta encoding
            charset = re.search(r"charset=([^\s;]+)", content_type)
            enc = charset.group(1) if charset else "utf-8"
            return raw.decode(enc, errors="replace")
    except HTTPError as e:
        log.warning("HTTP %s para %s", e.code, url)
    except URLError as e:
        log.warning("Erro de rede para %s: %s", url, e.reason)
    except Exception as e:
        log.warning("Erro inesperado para %s: %s", url, e)
    return None


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _load_cache() -> dict:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def scrape_article(url: str, cache: dict) -> Optional[dict]:
    """
    Raspa um artigo de notícia. Usa cache se disponível.
    Retorna dict com chaves: url, title, date, body, area (preenchida externamente).
    """
    if url in cache:
        return cache[url]

    html = _fetch_html(url)
    if not html:
        cache[url] = None
        return None

    result = _try_bs4(html) or _extract_with_stdlib(html)
    result["url"] = url

    # Trunca body para economizar tokens
    if len(result.get("body", "")) > MAX_CONTENT_LENGTH:
        result["body"] = result["body"][:MAX_CONTENT_LENGTH] + "\n[...conteúdo truncado]"

    cache[url] = result
    return result


def scrape_all(
    news_by_area: dict[str, list[str]],
    max_per_area: int = 10,
    use_cache: bool = True,
) -> list[dict]:
    """
    Raspa todas as notícias organizadas por área.

    Args:
        news_by_area: {area: [url, ...]}
        max_per_area: máximo de artigos por área (evita sobrecarga)
        use_cache: se True, carrega/salva cache local

    Returns:
        Lista de artigos com chaves: url, title, date, body, area
    """
    cache = _load_cache() if use_cache else {}
    articles: list[dict] = []
    total_areas = len(news_by_area)

    for i, (area, urls) in enumerate(news_by_area.items(), 1):
        log.info("[%d/%d] Raspando área '%s' (%d links)...", i, total_areas, area, len(urls))
        area_urls = urls[:max_per_area]

        for j, url in enumerate(area_urls, 1):
            log.info("  [%d/%d] %s", j, len(area_urls), url[:80])
            article = scrape_article(url, cache)
            if article:
                article = dict(article)  # cópia
                article["area"] = area
                articles.append(article)
            if use_cache and j % 5 == 0:
                _save_cache(cache)
            time.sleep(REQUEST_DELAY)

    if use_cache:
        _save_cache(cache)

    log.info("Total de artigos raspados: %d", len(articles))
    return articles


def format_articles_for_context(articles: list[dict], max_total_chars: int = 80000) -> str:
    """
    Formata os artigos como texto estruturado para o contexto do chatbot.
    Respeita um limite máximo de caracteres total.
    """
    parts = []
    total = 0

    for art in articles:
        area = art.get("area", "Geral")
        title = art.get("title", "(sem título)")
        date = art.get("date", "")
        url = art.get("url", "")
        body = art.get("body", "")

        section = (
            f"--- NOTÍCIA ---\n"
            f"Área: {area}\n"
            f"Título: {title}\n"
            + (f"Data: {date}\n" if date else "")
            + f"URL: {url}\n\n"
            f"{body}\n\n"
        )

        if total + len(section) > max_total_chars:
            break
        parts.append(section)
        total += len(section)

    return "\n".join(parts)


if __name__ == "__main__":
    # Teste rápido com uma URL de exemplo
    import pprint
    test_cache = {}
    art = scrape_article("https://agenciabrasil.ebc.com.br", test_cache)
    pprint.pprint(art)
