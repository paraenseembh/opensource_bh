"""
scraper.py — Coleta do texto completo dos atos normativos via portal DOM-BH.

Responsabilidades:
  - Verificar disponibilidade de API ou exportação estruturada (LexML)
  - Fazer GET em cada LINK com delay configurável e retry exponencial
  - Extrair o texto principal do HTML com BeautifulSoup
  - Registrar falhas em log sem interromper o pipeline
"""

import logging
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# User-agent discreto para não ser bloqueado por rate-limit simples
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; DOM-BH-Pesquisa/1.0; "
        "+https://github.com/paraenseembh/opensource_bh)"
    )
}

# Endpoint LexML do Município de BH (verificar disponibilidade antes do scraping HTML)
_LEXML_ENDPOINT = "https://www.lexml.gov.br/urn/urn:lex:br;belo.horizonte:municipal"


# ── Verificação de API / LexML ────────────────────────────────────────────────

def verificar_lexml_disponivel(timeout: int = 10) -> bool:
    """
    Testa se o endpoint LexML do município de BH responde.
    Se disponível, preferir exportação estruturada ao scraping HTML.
    """
    try:
        resp = requests.get(_LEXML_ENDPOINT, headers=_HEADERS, timeout=timeout)
        disponivel = resp.status_code == 200
        if disponivel:
            logger.info("LexML disponível em %s — considere usar exportação estruturada.", _LEXML_ENDPOINT)
        else:
            logger.info("LexML retornou status %d. Prosseguindo com scraping HTML.", resp.status_code)
        return disponivel
    except requests.RequestException as exc:
        logger.info("LexML inacessível (%s). Prosseguindo com scraping HTML.", exc)
        return False


# ── Scraping HTML ─────────────────────────────────────────────────────────────

def _extrair_texto_html(html: str) -> str:
    """
    Extrai o texto principal de uma página do portal DOM-BH.

    O portal geralmente envolve o conteúdo em <div class="content"> ou similar;
    como fallback usa o <body> inteiro sem scripts e estilos.
    """
    soup = BeautifulSoup(html, "lxml")

    # Remove elementos que não fazem parte do corpo do ato
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()

    # Seletores em ordem de prioridade (ajustar conforme estrutura real do portal)
    candidatos = [
        soup.find("div", class_=re.compile(r"content|texto|ato|decreto", re.I)),
        soup.find("article"),
        soup.find("main"),
        soup.find("body"),
    ]
    for elemento in candidatos:
        if elemento:
            texto = elemento.get_text(separator="\n", strip=True)
            if len(texto) > 100:  # descarta páginas de erro / redirecionamento
                return texto

    return ""


import re  # movido para cá por ser usado em _extrair_texto_html


def buscar_texto(
    url: str,
    delay: float = 1.5,
    max_retries: int = 3,
    timeout: int = 30,
) -> Optional[str]:
    """
    Faz GET na URL e retorna o texto extraído do HTML.

    Parâmetros
    ----------
    url         : URL do ato no portal DOM-BH
    delay       : segundos de espera após cada requisição bem-sucedida
    max_retries : número máximo de tentativas em caso de falha
    timeout     : timeout da requisição HTTP em segundos

    Retorna None em caso de falha definitiva após todas as tentativas.
    """
    for tentativa in range(1, max_retries + 1):
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=timeout)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding  # lida com latin-1 do portal
            texto = _extrair_texto_html(resp.text)
            time.sleep(delay)
            return texto if texto else None

        except requests.HTTPError as exc:
            # Erros 4xx não adianta retentar
            if exc.response is not None and exc.response.status_code < 500:
                logger.error("Erro HTTP %d em %s — não será refeita.", exc.response.status_code, url)
                return None
            logger.warning("Tentativa %d/%d falhou (HTTP %s) para %s.", tentativa, max_retries, exc, url)

        except requests.RequestException as exc:
            logger.warning("Tentativa %d/%d falhou (%s) para %s.", tentativa, max_retries, exc, url)

        if tentativa < max_retries:
            espera = 2 ** tentativa  # backoff exponencial: 2s, 4s, 8s
            logger.debug("Aguardando %ds antes da próxima tentativa.", espera)
            time.sleep(espera)

    logger.error("Falha definitiva ao coletar %s após %d tentativas.", url, max_retries)
    return None


def scrape_todos(
    df,
    col_link: str = "LINK",
    col_destino: str = "texto_completo",
    delay: float = 1.5,
    max_retries: int = 3,
    timeout: int = 30,
):
    """
    Itera sobre o DataFrame e preenche col_destino com o texto coletado.

    Registra progresso a cada 50 registros para facilitar monitoramento.
    """
    if col_link not in df.columns:
        logger.error("Coluna '%s' não encontrada. Abortando scraping.", col_link)
        return df

    total = len(df)
    df[col_destino] = None

    for idx, row in df.iterrows():
        url = row.get(col_link)
        if not isinstance(url, str) or not url.startswith("http"):
            logger.debug("Linha %d: URL inválida ou ausente (%s). Pulando.", idx, url)
            continue

        texto = buscar_texto(url, delay=delay, max_retries=max_retries, timeout=timeout)
        df.at[idx, col_destino] = texto

        if (idx + 1) % 50 == 0:
            coletados = df[col_destino].notna().sum()
            logger.info("Progresso: %d/%d registros processados (%d coletados).", idx + 1, total, coletados)

    coletados_total = df[col_destino].notna().sum()
    logger.info("Scraping concluído: %d/%d textos coletados.", coletados_total, total)
    return df
