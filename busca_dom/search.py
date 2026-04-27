"""
search.py — Motor de busca: combina ranking TF-IDF com filtros de metadados.

Suporta três tipos de busca, que podem ser combinados:
  - Textual  : correspondência semântica sobre EMENTA + ASSUNTO (TF-IDF cosine)
  - Temporal : filtro por DATA DOM (ano, intervalo, ou datas exatas)
  - Categorial: filtro por TIPO ATO e ÁREA (coluna ASSUNTO)

Extração automática de ano na query:
    "decretos sobre habitação em 2012" → ano=2012 extraído; query="decretos sobre habitação"

Uso:
    resultado = buscar(query="coleta seletiva", indice=indice, top_k=15, ano=2012)
"""

import re
from typing import Optional

import numpy as np
import pandas as pd

from indexer import IndiceDOM

# Colunas retornadas nos resultados (na ordem de exibição)
_COLUNAS_RESULTADO = [
    "TIPO ATO", "ÓRGÃO", "Nº", "DATA ASSINATURA", "DATA DOM",
    "EMENTA", "ASSUNTO", "LINK", "_score",
]

# Limiar mínimo de score para incluir um resultado (evita lixo)
_SCORE_MINIMO = 0.01


# ── Extração de metadados da query ────────────────────────────────────────────

def _extrair_ano_da_query(query: str) -> tuple[Optional[int], str]:
    """
    Detecta e remove uma expressão de ano da query.

    Exemplos reconhecidos:
      "habitação em 2012"     → (2012, "habitação")
      "decreto de 2015/2016"  → (2015, "decreto de /2016")  [primeiro ano]
      "copa 2014"             → (2014, "copa")
    """
    padrao = re.compile(r"\b(20\d{2}|19\d{2})\b")
    m = padrao.search(query)
    if not m:
        return None, query
    ano = int(m.group(1))
    query_sem_ano = (query[: m.start()] + query[m.end() :]).strip()
    # Remove palavras-conector que ficam soltas ("em", "de", "no")
    query_sem_ano = re.sub(r"\b(em|de|no|na|do|da|para|entre)\s*$", "", query_sem_ano).strip()
    return ano, query_sem_ano


def _normalizar_data(valor) -> Optional[pd.Timestamp]:
    if valor is None:
        return None
    if isinstance(valor, pd.Timestamp):
        return valor
    try:
        return pd.to_datetime(str(valor), format="%d/%m/%Y", errors="coerce")
    except Exception:
        return None


# ── Busca principal ───────────────────────────────────────────────────────────

def buscar(
    query: str = "",
    indice: Optional[IndiceDOM] = None,
    top_k: int = 15,
    # Filtros temporais
    ano: Optional[int] = None,
    data_inicio: Optional[str] = None,
    data_fim: Optional[str] = None,
    # Filtros categóricos
    tipos_ato: Optional[list[str]] = None,
    areas: Optional[list[str]] = None,
    orgao: Optional[str] = None,
) -> pd.DataFrame:
    """
    Busca inteligente sobre o índice DOM-BH.

    Parâmetros
    ----------
    query        : texto livre (EMENTA / ASSUNTO)
    indice       : instância de IndiceDOM (obrigatório)
    top_k        : máximo de resultados
    ano          : filtro por ano da DATA DOM
    data_inicio  : data mínima (DD/MM/YYYY ou YYYY-MM-DD)
    data_fim     : data máxima
    tipos_ato    : lista de tipos (ex: ["DECRETO", "PORTARIA"])
    areas        : lista de áreas (ex: ["ESTRUTURA", "PESSOAL"])
    orgao        : substring do órgão (ex: "SMAM")

    Retorna
    -------
    DataFrame com as colunas de _COLUNAS_RESULTADO + coluna _score.
    """
    if indice is None or indice.df is None:
        return pd.DataFrame()

    df = indice.df.copy()
    mascara = pd.Series(True, index=df.index)

    # ── Extração automática de ano da query ───────────────────────────────────
    query = query.strip()
    if query and ano is None and not data_inicio and not data_fim:
        ano_extraido, query = _extrair_ano_da_query(query)
        if ano_extraido:
            ano = ano_extraido

    # ── Filtros temporais ─────────────────────────────────────────────────────
    col_data = "DATA DOM"
    if col_data in df.columns:
        datas = pd.to_datetime(df[col_data], errors="coerce")

        if ano is not None:
            mascara &= datas.dt.year == ano

        ts_inicio = _normalizar_data(data_inicio)
        if ts_inicio is not None:
            mascara &= datas >= ts_inicio

        ts_fim = _normalizar_data(data_fim)
        if ts_fim is not None:
            mascara &= datas <= ts_fim

    # ── Filtros categóricos ───────────────────────────────────────────────────
    if tipos_ato and "TIPO ATO" in df.columns:
        tipos_upper = [t.upper() for t in tipos_ato]
        mascara &= df["TIPO ATO"].str.upper().isin(tipos_upper)

    if areas and "ASSUNTO" in df.columns:
        padrao_areas = "|".join(re.escape(a) for a in areas)
        mascara &= df["ASSUNTO"].str.contains(padrao_areas, case=False, na=False)

    if orgao and "ÓRGÃO" in df.columns:
        mascara &= df["ÓRGÃO"].str.contains(orgao, case=False, na=False)

    df_filtrado = df[mascara].copy()

    if df_filtrado.empty:
        return df_filtrado

    # ── Ranking textual ───────────────────────────────────────────────────────
    if query:
        scores_todos = indice.scores(query)
        df_filtrado["_score"] = scores_todos[mascara.values]
        df_filtrado = df_filtrado[df_filtrado["_score"] >= _SCORE_MINIMO]
        df_filtrado = df_filtrado.sort_values("_score", ascending=False)
    else:
        # Sem query textual: ordena por data decrescente
        df_filtrado["_score"] = 0.0
        if col_data in df_filtrado.columns:
            df_filtrado = df_filtrado.sort_values(col_data, ascending=False)

    # ── Seleciona colunas de saída ────────────────────────────────────────────
    colunas_disponiveis = [c for c in _COLUNAS_RESULTADO if c in df_filtrado.columns]
    return df_filtrado[colunas_disponiveis].head(top_k).reset_index(drop=True)


# ── Funções auxiliares para a UI ──────────────────────────────────────────────

def listar_tipos_ato(df: pd.DataFrame) -> list[str]:
    """Retorna tipos de ato únicos ordenados."""
    if "TIPO ATO" not in df.columns:
        return []
    return sorted(df["TIPO ATO"].dropna().unique().tolist())


def listar_areas(df: pd.DataFrame) -> list[str]:
    """Extrai áreas únicas (parte antes do ' - ' em ASSUNTO)."""
    if "ASSUNTO" not in df.columns:
        return []
    areas = (
        df["ASSUNTO"]
        .dropna()
        .str.split(" - ")
        .str[0]
        .str.strip()
        .unique()
    )
    return sorted(a for a in areas if a)


def intervalo_datas(df: pd.DataFrame) -> tuple[Optional[int], Optional[int]]:
    """Retorna (ano_min, ano_max) com base em DATA DOM."""
    if "DATA DOM" not in df.columns:
        return None, None
    datas = pd.to_datetime(df["DATA DOM"], errors="coerce").dropna()
    if datas.empty:
        return None, None
    return int(datas.dt.year.min()), int(datas.dt.year.max())
