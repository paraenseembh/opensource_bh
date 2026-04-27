"""
scraper.py — Coleta do texto completo dos atos normativos via portal DOM-BH.

Responsabilidades:
  - Verificar disponibilidade de API ou exportação estruturada (LexML)
  - Fazer GET em cada LINK com delay configurável e retry exponencial
  - Detectar o tipo de conteúdo (HTML, PDF, DOCX) e rotear para o extrator correto
  - Registrar falhas em log sem interromper o pipeline
"""

import io
import logging
import re
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; DOM-BH-Pesquisa/1.0; "
        "+https://github.com/paraenseembh/opensource_bh)"
    )
}

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
            logger.info("LexML retornou status %d. Prosseguindo com scraping.", resp.status_code)
        return disponivel
    except requests.RequestException as exc:
        logger.info("LexML inacessível (%s). Prosseguindo com scraping.", exc)
        return False


# ── Extratores por tipo de conteúdo ──────────────────────────────────────────

def _extrair_texto_html(html: str) -> str:
    """Extrai texto principal de uma página HTML do portal DOM-BH."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()
    candidatos = [
        soup.find("div", class_=re.compile(r"content|texto|ato|decreto", re.I)),
        soup.find("article"),
        soup.find("main"),
        soup.find("body"),
    ]
    for elemento in candidatos:
        if elemento:
            texto = elemento.get_text(separator="\n", strip=True)
            if len(texto) > 100:
                return texto
    return ""


def _extrair_texto_pdf(content: bytes) -> str:
    """
    Extrai texto de um PDF usando pdfplumber.
    Retorna string vazia se pdfplumber não estiver instalado ou o PDF for ilegível.
    """
    try:
        import pdfplumber
    except ImportError:
        logger.warning("pdfplumber não instalado. Instale com: pip install pdfplumber")
        return ""

    try:
        texto_paginas: list[str] = []
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for pagina in pdf.pages:
                t = pagina.extract_text()
                if t:
                    texto_paginas.append(t)
        return "\n".join(texto_paginas)
    except Exception as exc:
        logger.warning("Falha ao extrair texto do PDF: %s", exc)
        return ""


def _extrair_texto_docx(content: bytes) -> str:
    """
    Extrai texto de um arquivo DOCX usando python-docx.
    Retorna string vazia se python-docx não estiver instalado.
    """
    try:
        from docx import Document
    except ImportError:
        logger.warning("python-docx não instalado. Instale com: pip install python-docx")
        return ""

    try:
        doc = Document(io.BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as exc:
        logger.warning("Falha ao extrair texto do DOCX: %s", exc)
        return ""


def _rotear_extracao(resp: requests.Response) -> str:
    """Detecta o tipo de conteúdo pela resposta HTTP e chama o extrator correto."""
    content_type = resp.headers.get("Content-Type", "").lower()

    if "pdf" in content_type or resp.url.lower().endswith(".pdf"):
        logger.debug("Conteúdo detectado como PDF.")
        return _extrair_texto_pdf(resp.content)

    if "wordprocessingml" in content_type or resp.url.lower().endswith(".docx"):
        logger.debug("Conteúdo detectado como DOCX.")
        return _extrair_texto_docx(resp.content)

    # Padrão: HTML
    resp.encoding = resp.apparent_encoding
    return _extrair_texto_html(resp.text)


# ── Coleta com retry ──────────────────────────────────────────────────────────

def buscar_texto(
    url: str,
    delay: float = 1.5,
    max_retries: int = 3,
    timeout: int = 30,
) -> Optional[str]:
    """
    Faz GET na URL e retorna o texto extraído (HTML, PDF ou DOCX).

    Aplica retry com backoff exponencial (2s, 4s, 8s) em falhas 5xx e de rede.
    Retorna None em caso de falha definitiva.
    """
    for tentativa in range(1, max_retries + 1):
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=timeout)
            resp.raise_for_status()
            texto = _rotear_extracao(resp)
            time.sleep(delay)
            return texto if texto else None

        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code < 500:
                logger.error("Erro HTTP %d em %s — não será refeita.", exc.response.status_code, url)
                return None
            logger.warning("Tentativa %d/%d falhou (HTTP %s) para %s.", tentativa, max_retries, exc, url)

        except requests.RequestException as exc:
            logger.warning("Tentativa %d/%d falhou (%s) para %s.", tentativa, max_retries, exc, url)

        if tentativa < max_retries:
            espera = 2 ** tentativa
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
    cache=None,
):
    """
    Itera sobre o DataFrame e preenche col_destino com o texto coletado.

    Se `cache` (instância de CacheLocal) for fornecido:
      - URLs já presentes no cache são preenchidas direto, sem requisição HTTP.
      - Novos textos são gravados no cache imediatamente após cada coleta.

    Registra progresso a cada 50 registros.
    """
    if col_link not in df.columns:
        logger.error("Coluna '%s' não encontrada. Abortando scraping.", col_link)
        return df

    total = len(df)
    df[col_destino] = None

    # Determina quais URLs precisam de requisição HTTP
    urls_validas = [
        row.get(col_link)
        for _, row in df.iterrows()
        if isinstance(row.get(col_link), str) and row.get(col_link, "").startswith("http")
    ]
    if cache:
        pendentes = set(cache.pendentes(urls_validas))
        cache_hits = len(urls_validas) - len(pendentes)
        logger.info(
            "Cache: %d/%d documentos já coletados. Requisições HTTP necessárias: %d.",
            cache_hits, len(urls_validas), len(pendentes),
        )
    else:
        pendentes = set(urls_validas)

    for idx, row in df.iterrows():
        url = row.get(col_link)
        if not isinstance(url, str) or not url.startswith("http"):
            logger.debug("Linha %d: URL inválida ou ausente (%s). Pulando.", idx, url)
            continue

        # Cache hit — preenche sem HTTP
        if cache and cache.existe(url):
            record = cache.ler(url)
            df.at[idx, col_destino] = record.get("texto") if record else None
            continue

        # Cache miss — faz a requisição
        texto = buscar_texto(url, delay=delay, max_retries=max_retries, timeout=timeout)
        df.at[idx, col_destino] = texto

        if cache and texto:
            metadados = {
                "TIPO ATO": row.get("TIPO ATO"),
                "Nº":       row.get("Nº"),
                "DATA DOM": str(row.get("DATA DOM") or ""),
                "ÓRGÃO":    row.get("ÓRGÃO") or row.get("orgao_norm", ""),
                "EMENTA":   row.get("EMENTA"),
            }
            cache.salvar(url, texto, metadados)

        if (idx + 1) % 50 == 0:
            coletados = df[col_destino].notna().sum()
            logger.info("Progresso: %d/%d registros processados (%d coletados).", idx + 1, total, coletados)

    coletados_total = df[col_destino].notna().sum()
    logger.info("Scraping concluído: %d/%d textos coletados.", coletados_total, total)
    return df
