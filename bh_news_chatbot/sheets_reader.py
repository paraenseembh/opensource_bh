"""
Lê a planilha do Google Sheets com links de notícias de BH organizados por área.

A planilha é pública e pode ser exportada como CSV diretamente.
Caso tenha múltiplas abas (por área), este módulo tenta descobrir todas as abas
via o feed público do Google Sheets ou aceita uma lista de GIDs manualmente.
"""

import csv
import io
import re
import json
import time
import logging
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

SPREADSHEET_ID = "1eP6k-lPjkqxYR7BsTMF9xGFSQhGUhxul"
DEFAULT_GID = "139172426"

# URL base para exportar CSV de uma aba específica
CSV_EXPORT_URL = (
    "https://docs.google.com/spreadsheets/d/{sheet_id}/export"
    "?format=csv&gid={gid}"
)

# Feed JSON público para listar todas as abas
SHEETS_FEED_URL = (
    "https://spreadsheets.google.com/feeds/worksheets"
    "/{sheet_id}/public/basic?alt=json"
)


def _fetch_url(url: str, timeout: int = 15) -> Optional[str]:
    """Faz uma requisição HTTP simples e retorna o conteúdo como string."""
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except HTTPError as e:
        log.warning("HTTP %s ao acessar %s", e.code, url)
    except URLError as e:
        log.warning("Erro de URL ao acessar %s: %s", url, e.reason)
    except Exception as e:
        log.warning("Erro inesperado ao acessar %s: %s", url, e)
    return None


def list_sheet_gids(sheet_id: str = SPREADSHEET_ID) -> list[dict]:
    """
    Tenta listar todas as abas (nome + gid) da planilha via feed público.
    Retorna lista de dicts: [{"title": "Saúde", "gid": "0"}, ...]
    """
    url = SHEETS_FEED_URL.format(sheet_id=sheet_id)
    content = _fetch_url(url)
    if not content:
        log.warning("Não foi possível listar abas — usando GID padrão.")
        return [{"title": "Noticias", "gid": DEFAULT_GID}]

    try:
        data = json.loads(content)
        entries = data.get("feed", {}).get("entry", [])
        sheets = []
        for entry in entries:
            title = entry.get("title", {}).get("$t", "Sem título")
            # O GID fica no link da aba: .../gid/12345
            links = entry.get("link", [])
            gid = None
            for link in links:
                match = re.search(r"/gid/(\d+)", link.get("href", ""))
                if match:
                    gid = match.group(1)
                    break
            if gid:
                sheets.append({"title": title, "gid": gid})
        return sheets if sheets else [{"title": "Noticias", "gid": DEFAULT_GID}]
    except (json.JSONDecodeError, KeyError) as e:
        log.warning("Erro ao parsear feed de abas: %s", e)
        return [{"title": "Noticias", "gid": DEFAULT_GID}]


def read_sheet_csv(sheet_id: str, gid: str) -> list[dict]:
    """
    Exporta uma aba como CSV e retorna lista de dicts com as colunas como chaves.
    """
    url = CSV_EXPORT_URL.format(sheet_id=sheet_id, gid=gid)
    log.info("Baixando aba gid=%s: %s", gid, url)
    content = _fetch_url(url)
    if not content:
        return []

    reader = csv.DictReader(io.StringIO(content))
    return [row for row in reader]


def _extract_urls(value: str) -> list[str]:
    """Extrai todas as URLs encontradas numa string."""
    url_pattern = re.compile(
        r"https?://[^\s,;\"\'\]>)]+",
        re.IGNORECASE,
    )
    return url_pattern.findall(value)


def load_all_news_links(
    sheet_id: str = SPREADSHEET_ID,
    extra_gids: Optional[list[dict]] = None,
) -> dict[str, list[str]]:
    """
    Retorna um dicionário {area: [url1, url2, ...]} com todos os links de
    notícias encontrados na planilha.

    Args:
        sheet_id: ID da planilha do Google Sheets.
        extra_gids: lista de {"title": ..., "gid": ...} para sobrescrever
                    a descoberta automática de abas.
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
        seen = set()
        unique_urls = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                unique_urls.append(u)

        if unique_urls:
            news_by_area[area] = unique_urls
            log.info("  %s: %d links encontrados", area, len(unique_urls))
        else:
            log.info("  %s: nenhum link encontrado", area)

        time.sleep(0.5)  # cortesia ao Google Sheets

    return news_by_area


if __name__ == "__main__":
    import pprint
    links = load_all_news_links()
    pprint.pprint(links)
