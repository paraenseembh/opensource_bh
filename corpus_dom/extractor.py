"""
extractor.py — Parsing e enriquecimento dos campos textuais do DOM-BH.

Responsabilidades:
  - Normalizar datas e calcular lag de publicação
  - Extrair verbo principal, referências legais e valor monetário da ementa
  - Separar ASSUNTO em área e subtema
  - Normalizar ÓRGÃO
"""

import re
import logging
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ── Verbos de abertura mais comuns em atos normativos municipais ──────────────
_VERBOS = [
    "Dá nova redação",
    "Regulamenta",
    "Regulamento",
    "Aprova",
    "Abre",
    "Fixa",
    "Institui",
    "Autoriza",
    "Estabelece",
    "Dispõe",
    "Cria",
    "Altera",
    "Denomina",
    "Revoga",
    "Designa",
    "Nomeia",
    "Exonera",
    "Concede",
    "Ratifica",
    "Declara",
]

# Padrão para referências a outras normas (Lei, Decreto, Portaria, etc.)
_RE_REFS = re.compile(
    r"(?:Lei|Decreto|Portaria|Resolução|Deliberação|Emenda)\s+"
    r"(?:Federal|Estadual|Municipal|Complementar|Orgânica)?\s*"
    r"n[º°\.]?\s*[\d\.]+(?:/\d+)?",
    re.IGNORECASE,
)

# Padrão para valores monetários no formato R$ X.XXX.XXX,XX
_RE_VALOR = re.compile(
    r"R\$\s*[\d\.]+,\d{2}",
    re.IGNORECASE,
)

# Separador canônico da coluna ASSUNTO
_SEP_ASSUNTO = " - "


# ── Datas ─────────────────────────────────────────────────────────────────────

def converter_datas(df: pd.DataFrame) -> pd.DataFrame:
    """Converte DATA ASSINATURA e DATA DOM de DD/MM/YYYY para datetime.date."""
    for col in ("DATA ASSINATURA", "DATA DOM"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], format="%d/%m/%Y", errors="coerce")
            invalidas = df[col].isna().sum()
            if invalidas:
                logger.warning("Coluna '%s': %d datas não convertidas (NaT).", col, invalidas)
    return df


def calcular_lag(df: pd.DataFrame) -> pd.DataFrame:
    """Adiciona lag_publicacao_dias = DATA DOM − DATA ASSINATURA."""
    if "DATA ASSINATURA" in df.columns and "DATA DOM" in df.columns:
        delta = df["DATA DOM"] - df["DATA ASSINATURA"]
        df["lag_publicacao_dias"] = delta.dt.days
        negativos = (df["lag_publicacao_dias"] < 0).sum()
        if negativos:
            logger.warning("%d registros com lag negativo (publicação antes da assinatura).", negativos)
    return df


# ── Ementa ────────────────────────────────────────────────────────────────────

def extrair_verbo_principal(ementa: Optional[str]) -> Optional[str]:
    """Retorna o primeiro verbo de abertura encontrado na ementa."""
    if not isinstance(ementa, str):
        return None
    for verbo in _VERBOS:
        if re.search(rf"\b{re.escape(verbo)}\b", ementa, re.IGNORECASE):
            return verbo
    return None


def extrair_refs_legais(ementa: Optional[str]) -> list[str]:
    """Retorna lista de referências a outras normas encontradas na ementa."""
    if not isinstance(ementa, str):
        return []
    return _RE_REFS.findall(ementa)


def extrair_valor_monetario(ementa: Optional[str]) -> Optional[float]:
    """
    Retorna o primeiro valor monetário encontrado na ementa.
    Converte 'R$ 1.234.567,89' → 1234567.89 (float).
    """
    if not isinstance(ementa, str):
        return None
    match = _RE_VALOR.search(ementa)
    if not match:
        return None
    raw = match.group().replace("R$", "").strip()
    # Remove separadores de milhar e converte vírgula decimal
    raw = raw.replace(".", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        logger.debug("Não foi possível converter valor monetário: %s", match.group())
        return None


def enriquecer_ementa(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica os três extratores de ementa e adiciona as colunas ao DataFrame."""
    col = "EMENTA"
    if col not in df.columns:
        logger.warning("Coluna '%s' não encontrada. Pulando enriquecimento de ementa.", col)
        return df
    df["verbo_principal"] = df[col].apply(extrair_verbo_principal)
    df["refs_legais"] = df[col].apply(extrair_refs_legais)
    df["valor_monetario"] = df[col].apply(extrair_valor_monetario)
    return df


# ── ASSUNTO ───────────────────────────────────────────────────────────────────

def separar_assunto(assunto: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """
    Divide 'ÁREA - SUBTEMA' em (area, subtema).
    Retorna (assunto, None) quando o separador não está presente.
    """
    if not isinstance(assunto, str) or not assunto.strip():
        return None, None
    if _SEP_ASSUNTO in assunto:
        partes = assunto.split(_SEP_ASSUNTO, maxsplit=1)
        return partes[0].strip(), partes[1].strip()
    return assunto.strip(), None


def processar_assunto(df: pd.DataFrame) -> pd.DataFrame:
    """Adiciona colunas 'area' e 'subtema' ao DataFrame."""
    col = "ASSUNTO"
    if col not in df.columns:
        logger.warning("Coluna '%s' não encontrada. Pulando separação de assunto.", col)
        return df
    df[["area", "subtema"]] = df[col].apply(
        lambda v: pd.Series(separar_assunto(v))
    )
    return df


# ── ÓRGÃO ─────────────────────────────────────────────────────────────────────

def normalizar_orgao(orgao_raw: Optional[str], tipo_ato: Optional[str]) -> str:
    """
    Preenche órgão vazio com 'PODER EXECUTIVO MUNICIPAL' quando TIPO ATO = DECRETO.
    Mantém o valor original nos demais casos.
    """
    if isinstance(orgao_raw, str) and orgao_raw.strip():
        return orgao_raw.strip()
    if isinstance(tipo_ato, str) and tipo_ato.strip().upper() == "DECRETO":
        return "PODER EXECUTIVO MUNICIPAL"
    return orgao_raw if isinstance(orgao_raw, str) else ""


def processar_orgao(df: pd.DataFrame) -> pd.DataFrame:
    """Adiciona coluna 'orgao_norm' ao DataFrame."""
    col_orgao = "ÓRGÃO"
    col_tipo = "TIPO ATO"
    if col_orgao not in df.columns:
        logger.warning("Coluna '%s' não encontrada. Pulando normalização de órgão.", col_orgao)
        return df
    df["orgao_norm"] = df.apply(
        lambda row: normalizar_orgao(row.get(col_orgao), row.get(col_tipo)),
        axis=1,
    )
    return df


# ── Extração específica de decretos de crédito ───────────────────────────────

# Padrão de dotação orçamentária: XX.XXX.XXXX.XXXX.XXXX (BH)
_RE_DOTACAO = re.compile(r"\d{2}\.\d{3}\.\d{4}\.\d{4}\.\d{4}")

def extrair_dotacao_orcamentaria(texto: Optional[str]) -> list[str]:
    """Extrai códigos de dotação orçamentária do texto completo do decreto."""
    if not isinstance(texto, str):
        return []
    return _RE_DOTACAO.findall(texto)


def extrair_fonte_recurso(texto: Optional[str]) -> Optional[str]:
    """
    Tenta extrair 'Fonte de Recurso' do texto completo.
    Busca padrões como 'Fonte: XXX' ou 'Fonte de Recurso: XXX'.
    """
    if not isinstance(texto, str):
        return None
    match = re.search(
        r"Fonte(?:\s+de\s+Recurso)?[:\s]+([^\n\.;]{3,60})",
        texto,
        re.IGNORECASE,
    )
    return match.group(1).strip() if match else None
