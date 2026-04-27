"""
indexer.py — Constrói e persiste o índice TF-IDF para busca textual no DOM-BH.

O índice combina EMENTA + ASSUNTO + TIPO ATO + ÓRGÃO num único campo de busca,
com normalização de acentos e bigramas para cobrir expressões compostas
(ex: "copa 2014", "coleta seletiva", "poder executivo").

Uso:
    indice = IndiceDOM.construir(df)
    indice.salvar("cache/indice.pkl")

    indice = IndiceDOM.carregar("cache/indice.pkl")
"""

import pickle
import re
import unicodedata
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Stopwords mínimas em português (evita poluir o índice com termos genéricos)
_STOPWORDS_PT = {
    "a", "ao", "aos", "as", "com", "da", "das", "de", "do", "dos",
    "e", "em", "na", "nas", "no", "nos", "o", "os", "ou", "para",
    "pela", "pelas", "pelo", "pelos", "por", "que", "se", "um", "uma",
    "umas", "uns", "à", "às",
}


# ── Normalização de texto ─────────────────────────────────────────────────────

def normalizar(texto: str) -> str:
    """
    Normaliza texto para indexação e busca:
      - Remove acentos (NFD decomposition)
      - Minúsculas
      - Remove pontuação irrelevante
    """
    if not isinstance(texto, str):
        return ""
    # Remove acentos
    sem_acento = unicodedata.normalize("NFD", texto)
    sem_acento = "".join(c for c in sem_acento if unicodedata.category(c) != "Mn")
    # Minúsculas e remove caracteres não-alfanuméricos (mantém espaços)
    limpo = re.sub(r"[^a-z0-9\s]", " ", sem_acento.lower())
    # Colapsa espaços
    return re.sub(r"\s+", " ", limpo).strip()


def _combinar_campos(row: pd.Series) -> str:
    """
    Combina os campos textuais relevantes para indexação.

    Peso aplicado pela repetição:
      EMENTA × 2 (campo mais rico)
      ASSUNTO × 2 (taxonomia estruturada — muito útil para filtros)
      TIPO ATO × 1
      ÓRGÃO × 1
    """
    ementa  = str(row.get("EMENTA")   or "")
    assunto = str(row.get("ASSUNTO")  or "")
    tipo    = str(row.get("TIPO ATO") or "")
    orgao   = str(row.get("ÓRGÃO")    or "")
    return normalizar(" ".join([ementa, ementa, assunto, assunto, tipo, orgao]))


# ── Classe principal ──────────────────────────────────────────────────────────

class IndiceDOM:
    """
    Índice TF-IDF sobre os atos do DOM-BH.

    Mantém o DataFrame original para filtros de metadados (data, tipo, área)
    e a matriz TF-IDF para ranking textual.
    """

    def __init__(self) -> None:
        self.df: Optional[pd.DataFrame] = None
        self._vetorizador: Optional[TfidfVectorizer] = None
        self._matriz = None  # sparse matrix

    # ── Construção ────────────────────────────────────────────────────────────

    @classmethod
    def construir(cls, df: pd.DataFrame) -> "IndiceDOM":
        """Constrói o índice a partir de um DataFrame já com datas convertidas."""
        inst = cls()
        inst.df = df.reset_index(drop=True).copy()

        textos = df.apply(_combinar_campos, axis=1).tolist()

        inst._vetorizador = TfidfVectorizer(
            ngram_range=(1, 2),    # unigramas + bigramas
            min_df=1,
            max_df=0.90,
            sublinear_tf=True,     # log(TF+1) suaviza termos muito frequentes
            stop_words=list(_STOPWORDS_PT),
        )
        inst._matriz = inst._vetorizador.fit_transform(textos)
        return inst

    # ── Persistência ──────────────────────────────────────────────────────────

    def salvar(self, caminho: str) -> None:
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
        with open(caminho, "wb") as f:
            pickle.dump(self, f, protocol=pickle.HIGHEST_PROTOCOL)

    @staticmethod
    def carregar(caminho: str) -> "IndiceDOM":
        with open(caminho, "rb") as f:
            return pickle.load(f)

    # ── Busca ─────────────────────────────────────────────────────────────────

    def scores(self, query: str) -> np.ndarray:
        """Retorna vetor de scores cosine (um por documento no índice)."""
        q_norm = normalizar(query)
        if not q_norm.strip():
            return np.zeros(len(self.df))
        q_vec = self._vetorizador.transform([q_norm])
        return cosine_similarity(q_vec, self._matriz).flatten()

    def n_docs(self) -> int:
        return len(self.df) if self.df is not None else 0
