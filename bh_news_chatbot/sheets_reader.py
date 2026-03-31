"""
Lê a planilha do Google Sheets com links de notícias de BH organizados por área.

A planilha deve ser pública (File → Share → "Anyone with the link" → Viewer)
OU publicada na web (File → Publish to web → CSV).

Este módulo tenta descobrir as abas via HTML da planilha e baixar o CSV
usando dois formatos de URL suportados pelo Google Sheets.
"""

import csv
import io
import re
import time
import logging
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

log = logging.getLogger(__name__)

SPREADSHEET_ID = "1eP6k-lPjkqxYR7BsTMF9xGFSQhGUhxul"
DEFAULT_GID = "139172426"

# URL via gviz — funciona para planilhas públicas sem autenticação
GVIZ_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/{sheet_id}"
    "/gviz/tq?tqx=out:csv&gid={gid}"
)

# URL via export — alternativa (requer "Publicar na web")
EXPORT_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/{sheet_id}"
    "/export?format=csv&gid={gid}"
)

# HTML da planilha — usado para descobrir nomes e GIDs das abas
HTML_VIEW_URL = "https://docs.google.com/spreadsheets/d/{sheet_id}/htmlview"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}


def _fetch_url(url: str, timeout: int = 20) -> Optional[str]:
    """Faz uma requisição HTTP e retorna o conteúdo como string."""
    try:
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except HTTPError as e:
        log.warning("HTTP %s ao acessar %s", e.code, url)
    except URLError as e:
        log.warning("Erro de URL ao acessar %s: %s", url, e.reason)
    except Exception as e:
        log.warning("Erro inesperado ao acessar %s: %s", url, e)
    return None


# ---------------------------------------------------------------------------
# Descoberta de abas
# ---------------------------------------------------------------------------

def list_sheet_gids(sheet_id: str = SPREADSHEET_ID) -> list[dict]:
    """
    Descobre as abas (nome + gid) da planilha via HTML público.

    Retorna lista de dicts: [{"title": "Noticias", "gid": "0"}, ...]
    Fallback para GID padrão se a descoberta falhar.
    """
    url = HTML_VIEW_URL.format(sheet_id=sheet_id)
    log.debug("Buscando abas em: %s", url)
    html = _fetch_url(url)

    if not html:
        log.warning(
            "Não foi possível acessar a planilha. "
            "Verifique se ela está pública (compartilhada como 'Qualquer pessoa com o link')."
        )
        return [{"title": "Noticias", "gid": DEFAULT_GID}]

    sheets = _parse_gids_from_html(html)

    if not sheets:
        log.warning("Não foi possível detectar abas no HTML — usando GID padrão.")
        return [{"title": "Noticias", "gid": DEFAULT_GID}]

    return sheets


def _parse_gids_from_html(html: str) -> list[dict]:
    """
    Extrai nomes e GIDs das abas a partir do HTML da planilha.

    O Google Sheets embute os dados das abas em vários formatos no HTML;
    tentamos os mais comuns em ordem de confiabilidade.
    """
    sheets = []

    # Padrão 1: data-sheet-id="<gid>" com label próximo
    # <div ... data-sheet-id="0" ...><span ...>NomeAba</span>
    pattern1 = re.compile(
        r'data-sheet-id=["\'](\d+)["\'][^>]*>.*?<span[^>]*>([^<]+)</span>',
        re.DOTALL,
    )
    for m in pattern1.finditer(html):
        gid, title = m.group(1), m.group(2).strip()
        if title and {"title": title, "gid": gid} not in sheets:
            sheets.append({"title": title, "gid": gid})

    if sheets:
        return sheets

    # Padrão 2: id="sheet-button-<gid>" com texto da aba
    pattern2 = re.compile(
        r'id=["\']sheet-button-(\d+)["\'][^>]*>.*?([A-Za-zÀ-ÿ0-9 _\-]{2,40})',
        re.DOTALL,
    )
    for m in pattern2.finditer(html):
        gid, title = m.group(1), m.group(2).strip()
        if title and {"title": title, "gid": gid} not in sheets:
            sheets.append({"title": title, "gid": gid})

    if sheets:
        return sheets

    # Padrão 3: "sheetId":<gid>,"title":"<nome>" (JSON embutido no HTML)
    pattern3 = re.compile(r'"sheetId"\s*:\s*(\d+).*?"title"\s*:\s*"([^"]+)"', re.DOTALL)
    for m in pattern3.finditer(html):
        gid, title = m.group(1), m.group(2).strip()
        if title and {"title": title, "gid": gid} not in sheets:
            sheets.append({"title": title, "gid": gid})

    return sheets


# ---------------------------------------------------------------------------
# Download de CSV
# ---------------------------------------------------------------------------

def _fetch_csv(sheet_id: str, gid: str) -> Optional[str]:
    """
    Tenta baixar o CSV de uma aba usando múltiplos formatos de URL.
    Retorna o conteúdo CSV ou None se todos falharem.
    """
    candidates = [
        GVIZ_CSV_URL.format(sheet_id=sheet_id, gid=gid),
        EXPORT_CSV_URL.format(sheet_id=sheet_id, gid=gid),
    ]

    for url in candidates:
        log.info("  Tentando: %s", url)
        content = _fetch_url(url)
        if content and not content.strip().startswith("<!DOCTYPE"):
            return content
        if content and content.strip().startswith("<!DOCTYPE"):
            log.warning("  Recebeu página HTML em vez de CSV — planilha pode não ser pública.")

    return None


def read_sheet_csv(sheet_id: str, gid: str) -> list[dict]:
    """Exporta uma aba como CSV e retorna lista de dicts."""
    content = _fetch_csv(sheet_id, gid)
    if not content:
        return []
    try:
        reader = csv.DictReader(io.StringIO(content))
        return [row for row in reader]
    except Exception as e:
        log.warning("Erro ao parsear CSV (gid=%s): %s", gid, e)
        return []


# ---------------------------------------------------------------------------
# Extração de URLs
# ---------------------------------------------------------------------------

def _extract_urls(value: str) -> list[str]:
    """Extrai todas as URLs encontradas numa string."""
    url_pattern = re.compile(r"https?://[^\s,;\"\'\]>)]+", re.IGNORECASE)
    return url_pattern.findall(value)


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def load_all_news_links(
    sheet_id: str = SPREADSHEET_ID,
    extra_gids: Optional[list[dict]] = None,
) -> dict[str, list[str]]:
    """
    Retorna {area: [url1, url2, ...]} com todos os links de notícias da planilha.

    Args:
        sheet_id: ID da planilha do Google Sheets.
        extra_gids: lista de {"title": ..., "gid": ...} para sobrescrever
                    a descoberta automática de abas.

    Pré-requisito:
        A planilha deve estar acessível publicamente. Para garantir:
        1. Abra a planilha no Google Sheets
        2. Arquivo → Compartilhar → "Qualquer pessoa com o link" → Leitor
        OU
        2. Arquivo → Publicar na web → Selecione a aba → Formato CSV → Publicar
    """
    sheets = extra_gids if extra_gids else list_sheet_gids(sheet_id)
    log.info("Abas encontradas: %s", [s["title"] for s in sheets])

    news_by_area: dict[str, list[str]] = {}

    for sheet_info in sheets:
        area = sheet_info["title"]
        gid = sheet_info["gid"]
        rows = read_sheet_csv(sheet_id, gid)

        urls: list[str] = []
        for row in rows:
            for value in row.values():
                if value:
                    urls.extend(_extract_urls(str(value)))

        # Remove duplicatas mantendo ordem
        seen: set[str] = set()
        unique_urls = [u for u in urls if not (u in seen or seen.add(u))]  # type: ignore[func-returns-value]

        if unique_urls:
            news_by_area[area] = unique_urls
            log.info("  %s: %d links encontrados", area, len(unique_urls))
        else:
            log.info("  %s: nenhum link encontrado", area)

        time.sleep(0.3)

    if not news_by_area:
        log.error(
            "Nenhum link encontrado. Verifique se a planilha está pública:\n"
            "  1. Abra a planilha no Google Sheets\n"
            "  2. Arquivo → Compartilhar → 'Qualquer pessoa com o link' → Leitor\n"
            "  OU\n"
            "  2. Arquivo → Publicar na web → CSV → Publicar\n"
            "  3. Confirme que o ID da planilha está correto: %s",
            sheet_id,
        )

    return news_by_area


if __name__ == "__main__":
    import pprint
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    links = load_all_news_links()
    pprint.pprint(links)
