"""
loader.py — Carga dos dados processados no MySQL.

Responsabilidades:
  - Criar conexão com o banco a partir de variáveis de ambiente
  - Criar a tabela atos_dom_bh se ainda não existir
  - Inserir ou atualizar (upsert) registros via INSERT … ON DUPLICATE KEY UPDATE
  - Serializar campos JSON (refs_legais) e tratar tipos Python/MySQL
"""

import json
import logging
import os
from typing import Optional

import mysql.connector
from mysql.connector import MySQLConnection

logger = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS atos_dom_bh (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    tipo_ato            VARCHAR(50),
    orgao_raw           VARCHAR(150),
    orgao_norm          VARCHAR(150),
    numero              INT,
    data_assinatura     DATE,
    data_dom            DATE,
    lag_publicacao_dias INT,
    ementa              TEXT,
    verbo_principal     VARCHAR(50),
    refs_legais         JSON,
    valor_monetario     DECIMAL(15,2),
    observacao          TEXT,
    area                VARCHAR(100),
    subtema             VARCHAR(150),
    link                VARCHAR(255),
    texto_completo      LONGTEXT,
    scraped_em          DATETIME DEFAULT NOW(),
    UNIQUE KEY uq_link (link)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

_UPSERT = """
INSERT INTO atos_dom_bh (
    tipo_ato, orgao_raw, orgao_norm, numero,
    data_assinatura, data_dom, lag_publicacao_dias,
    ementa, verbo_principal, refs_legais, valor_monetario,
    observacao, area, subtema, link, texto_completo
) VALUES (
    %(tipo_ato)s, %(orgao_raw)s, %(orgao_norm)s, %(numero)s,
    %(data_assinatura)s, %(data_dom)s, %(lag_publicacao_dias)s,
    %(ementa)s, %(verbo_principal)s, %(refs_legais)s, %(valor_monetario)s,
    %(observacao)s, %(area)s, %(subtema)s, %(link)s, %(texto_completo)s
) ON DUPLICATE KEY UPDATE
    orgao_norm        = VALUES(orgao_norm),
    lag_publicacao_dias = VALUES(lag_publicacao_dias),
    verbo_principal   = VALUES(verbo_principal),
    refs_legais       = VALUES(refs_legais),
    valor_monetario   = VALUES(valor_monetario),
    area              = VALUES(area),
    subtema           = VALUES(subtema),
    texto_completo    = COALESCE(VALUES(texto_completo), texto_completo),
    scraped_em        = IF(VALUES(texto_completo) IS NOT NULL, NOW(), scraped_em);
"""


# ── Conexão ───────────────────────────────────────────────────────────────────

def criar_conexao() -> MySQLConnection:
    """Cria e retorna uma conexão MySQL usando variáveis de ambiente."""
    conn = mysql.connector.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", 3306)),
        database=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        charset="utf8mb4",
        use_unicode=True,
    )
    logger.info("Conexão MySQL estabelecida com %s/%s.", os.environ["DB_HOST"], os.environ["DB_NAME"])
    return conn


def garantir_tabela(conn: MySQLConnection) -> None:
    """Cria a tabela atos_dom_bh caso não exista."""
    with conn.cursor() as cur:
        cur.execute(_DDL)
    conn.commit()
    logger.info("Tabela atos_dom_bh verificada/criada.")


# ── Serialização de linha ─────────────────────────────────────────────────────

def _none_if_nat(valor):
    """Converte pandas NaT e float('nan') para None (compatível com MySQL)."""
    import pandas as pd
    if valor is None:
        return None
    try:
        if pd.isna(valor):
            return None
    except (TypeError, ValueError):
        pass
    return valor


def _linha_para_dict(row) -> dict:
    """
    Converte uma linha do DataFrame no dicionário esperado pelo upsert.
    Mapeia nomes de colunas pandas → colunas MySQL.
    """
    import pandas as pd

    def col(nome: str):
        val = row.get(nome)
        return _none_if_nat(val)

    # refs_legais é lista Python → serializar para JSON string
    refs = col("refs_legais")
    refs_json = json.dumps(refs, ensure_ascii=False) if isinstance(refs, list) else "[]"

    # numero pode vir como float por causa de NaN no pandas
    numero_raw = col("Nº")
    try:
        numero = int(numero_raw) if numero_raw is not None else None
    except (ValueError, TypeError):
        numero = None

    # Datas: converter Timestamp para date nativo Python
    def to_date(val):
        if val is None:
            return None
        if hasattr(val, "date"):
            return val.date()
        return val

    return {
        "tipo_ato":            col("TIPO ATO"),
        "orgao_raw":           col("ÓRGÃO"),
        "orgao_norm":          col("orgao_norm"),
        "numero":              numero,
        "data_assinatura":     to_date(col("DATA ASSINATURA")),
        "data_dom":            to_date(col("DATA DOM")),
        "lag_publicacao_dias": col("lag_publicacao_dias"),
        "ementa":              col("EMENTA"),
        "verbo_principal":     col("verbo_principal"),
        "refs_legais":         refs_json,
        "valor_monetario":     col("valor_monetario"),
        "observacao":          col("OBSERVAÇÃO"),
        "area":                col("area"),
        "subtema":             col("subtema"),
        "link":                col("LINK"),
        "texto_completo":      col("texto_completo"),
    }


# ── Carga em lote ─────────────────────────────────────────────────────────────

def carregar_dataframe(df, conn: MySQLConnection, tamanho_lote: int = 200) -> int:
    """
    Insere/atualiza todos os registros do DataFrame no MySQL em lotes.

    Retorna o total de linhas afetadas.
    """
    total_afetadas = 0
    lote: list[dict] = []

    def _flush(lote: list[dict]) -> int:
        if not lote:
            return 0
        with conn.cursor() as cur:
            cur.executemany(_UPSERT, lote)
        conn.commit()
        return cur.rowcount

    for _, row in df.iterrows():
        lote.append(_linha_para_dict(row))
        if len(lote) >= tamanho_lote:
            afetadas = _flush(lote)
            total_afetadas += afetadas
            logger.debug("Lote de %d registros inserido (%d afetadas).", len(lote), afetadas)
            lote = []

    # Último lote residual
    if lote:
        afetadas = _flush(lote)
        total_afetadas += afetadas

    logger.info("Carga concluída: %d linhas afetadas no total.", total_afetadas)
    return total_afetadas
