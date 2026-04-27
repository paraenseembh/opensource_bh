"""
cleaner.py — Limpeza, normalização e deduplicação do texto coletado.

Responsabilidades:
  - Remover cabeçalhos, rodapés e numeração de páginas
  - Normalizar espaços em branco e codificação UTF-8
  - Detectar e remover registros duplicados por hash de conteúdo
  - Aplicar pipeline de limpeza ao DataFrame inteiro
"""

import hashlib
import logging
import re
import unicodedata

import pandas as pd

logger = logging.getLogger(__name__)

# Padrões recorrentes em documentos do DOM-BH que não fazem parte do corpo do ato
_PADROES_REMOVER = [
    # Numeração de página: "Página 3 de 47", "pág. 3", "- 3 -", "3 / 47"
    re.compile(r"p[áa]g(?:ina)?\.?\s*\d+(?:\s*(?:de|/)\s*\d+)?", re.IGNORECASE),
    re.compile(r"-\s*\d+\s*-"),
    re.compile(r"\b\d+\s*/\s*\d+\b"),
    # Rodapé padrão DOM-BH
    re.compile(r"Diário Oficial do Município.*", re.IGNORECASE),
    re.compile(r"Prefeitura Municipal de Belo Horizonte.*", re.IGNORECASE),
    re.compile(r"www\.pbh\.gov\.br.*", re.IGNORECASE),
    # Carimbo de autenticidade / hash de documento digital
    re.compile(r"Código de autenticidade[\s\S]{0,120}", re.IGNORECASE),
    re.compile(r"Assinado digitalmente.*", re.IGNORECASE),
    # Linhas só com traços ou asteriscos (separadores visuais)
    re.compile(r"^[\-_\*=]{3,}\s*$", re.MULTILINE),
]


def limpar_texto(texto: str) -> str:
    """
    Aplica os padrões de limpeza ao texto e normaliza espaços em branco.

    Não remove conteúdo substantivo — apenas ruído estrutural (cabeçalhos,
    rodapés, numeração de página, marcas de assinatura digital).
    """
    if not isinstance(texto, str):
        return ""

    for padrao in _PADROES_REMOVER:
        texto = padrao.sub("", texto)

    # Colapsa linhas em branco múltiplas em no máximo uma
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    # Remove espaços horizontais múltiplos
    texto = re.sub(r"[ \t]{2,}", " ", texto)

    return texto.strip()


def normalizar_para_utf8(texto: str) -> str:
    """
    Normaliza o texto para NFC (forma canônica Unicode) e garante UTF-8 limpo.

    Útil quando o texto veio de PDF escaneado ou de conversão latin-1 → utf-8.
    """
    if not isinstance(texto, str):
        return ""
    return unicodedata.normalize("NFC", texto)


def hash_conteudo(texto: str) -> str:
    """Retorna SHA-256 dos primeiros 5000 caracteres — suficiente para deduplificação."""
    amostra = texto[:5000] if isinstance(texto, str) else ""
    return hashlib.sha256(amostra.encode("utf-8", errors="replace")).hexdigest()


def remover_duplicatas(df: pd.DataFrame, col: str = "texto_completo") -> pd.DataFrame:
    """
    Remove linhas com conteúdo textual idêntico (mesmo hash SHA-256).

    Mantém a primeira ocorrência. Registros sem texto_completo não são afetados.
    """
    if col not in df.columns:
        logger.warning("Coluna '%s' não encontrada. Deduplicação pulada.", col)
        return df

    mascara_com_texto = df[col].notna() & (df[col] != "")
    df_com = df[mascara_com_texto].copy()
    df_sem = df[~mascara_com_texto]

    df_com["_hash"] = df_com[col].apply(hash_conteudo)
    antes = len(df_com)
    df_com = df_com.drop_duplicates(subset="_hash", keep="first")
    df_com = df_com.drop(columns=["_hash"])
    removidos = antes - len(df_com)

    if removidos:
        logger.info("%d registros duplicados removidos por hash de conteúdo.", removidos)

    return pd.concat([df_com, df_sem], ignore_index=True)


def limpar_dataframe(df: pd.DataFrame, col: str = "texto_completo") -> pd.DataFrame:
    """
    Aplica limpeza completa ao DataFrame:
      1. Normalização UTF-8 (NFC)
      2. Remoção de ruído estrutural
      3. Deduplicação por hash de conteúdo

    Retorna novo DataFrame com a coluna limpa.
    """
    if col not in df.columns:
        logger.warning("Coluna '%s' não encontrada. Limpeza pulada.", col)
        return df

    df = df.copy()
    df[col] = df[col].apply(
        lambda t: limpar_texto(normalizar_para_utf8(t)) if isinstance(t, str) else t
    )
    df = remover_duplicatas(df, col=col)
    logger.info("Limpeza concluída: %d registros com texto após limpeza.", df[col].notna().sum())
    return df
