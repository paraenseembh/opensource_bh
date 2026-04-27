"""
pipeline.py — Orquestração principal do pipeline DOM-BH.

Etapas executadas em ordem:
  1. Ingestão e limpeza do CSV exportado do DOM-BH
  2. Parsing e enriquecimento da ementa (verbo, refs, valor)
  3. Separação de ASSUNTO em área e subtema
  4. Normalização de ÓRGÃO
  5. Verificação de API/LexML e scraping do texto completo
  6. Carga no MySQL

Execute com:
    python pipeline.py [--csv CAMINHO] [--sem-scraping] [--sem-carga]
"""

import argparse
import logging
import os
import sys

import pandas as pd
from dotenv import load_dotenv

import extractor
import scraper
import loader

# ── Configuração de logging ───────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("pipeline.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


# ── Argumentos CLI ────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pipeline DOM-BH")
    parser.add_argument(
        "--csv",
        default=None,
        help="Caminho para o CSV do DOM-BH (sobrepõe CSV_PATH do .env)",
    )
    parser.add_argument(
        "--sem-scraping",
        action="store_true",
        help="Pula a etapa de scraping do texto completo",
    )
    parser.add_argument(
        "--sem-carga",
        action="store_true",
        help="Pula a etapa de carga no MySQL (útil para debug)",
    )
    return parser.parse_args()


# ── Ingestão do CSV ───────────────────────────────────────────────────────────

def ingerir_csv(caminho: str) -> pd.DataFrame:
    """
    Lê o CSV exportado do DOM-BH.

    Tenta utf-8-sig primeiro (BOM do Excel); cai para latin-1 como fallback,
    que é o encoding mais comum em portais de governo brasileiros.
    """
    for enc in ("utf-8-sig", "latin-1"):
        try:
            df = pd.read_csv(caminho, encoding=enc, sep=";", dtype=str)
            logger.info("CSV lido com encoding '%s': %d registros, %d colunas.", enc, len(df), len(df.columns))
            return df
        except UnicodeDecodeError:
            logger.debug("Encoding '%s' falhou. Tentando próximo.", enc)
        except Exception as exc:
            logger.error("Erro ao ler CSV com encoding '%s': %s", enc, exc)
            raise

    raise ValueError(f"Não foi possível ler o arquivo '{caminho}' com os encodings tentados.")


def validar_colunas(df: pd.DataFrame) -> None:
    """Alerta para colunas esperadas que não foram encontradas no CSV."""
    esperadas = {
        "TIPO ATO", "ÓRGÃO", "Nº", "DATA ASSINATURA",
        "EMENTA", "DATA DOM", "OBSERVAÇÃO", "ASSUNTO", "LINK",
    }
    faltando = esperadas - set(df.columns)
    if faltando:
        logger.warning("Colunas esperadas ausentes no CSV: %s", faltando)


# ── Pipeline principal ────────────────────────────────────────────────────────

def executar(args: argparse.Namespace) -> None:
    load_dotenv()

    csv_path = args.csv or os.environ.get("CSV_PATH", "dados/indice_dom_bh.csv")
    delay = float(os.environ.get("SCRAPING_DELAY", 1.5))
    max_retries = int(os.environ.get("SCRAPING_MAX_RETRIES", 3))
    timeout = int(os.environ.get("SCRAPING_TIMEOUT", 30))

    # ── Etapa 1: Ingestão ────────────────────────────────────────────────────
    logger.info("=== Etapa 1: Ingestão do CSV ===")
    df = ingerir_csv(csv_path)
    validar_colunas(df)

    # ── Etapa 2: Datas e lag ─────────────────────────────────────────────────
    logger.info("=== Etapa 2: Conversão de datas e cálculo de lag ===")
    df = extractor.converter_datas(df)
    df = extractor.calcular_lag(df)

    # ── Etapa 3: Enriquecimento da ementa ────────────────────────────────────
    logger.info("=== Etapa 3: Parsing da ementa ===")
    df = extractor.enriquecer_ementa(df)

    # ── Etapa 4: ASSUNTO → área + subtema ────────────────────────────────────
    logger.info("=== Etapa 4: Separação de ASSUNTO ===")
    df = extractor.processar_assunto(df)

    # ── Etapa 5: Normalização de ÓRGÃO ───────────────────────────────────────
    logger.info("=== Etapa 5: Normalização de ÓRGÃO ===")
    df = extractor.processar_orgao(df)

    # ── Etapa 6: Scraping do texto completo ──────────────────────────────────
    if not args.sem_scraping:
        logger.info("=== Etapa 6: Verificação de API e scraping ===")
        scraper.verificar_lexml_disponivel()
        df = scraper.scrape_todos(
            df,
            delay=delay,
            max_retries=max_retries,
            timeout=timeout,
        )
    else:
        logger.info("=== Etapa 6: Scraping pulado (--sem-scraping) ===")
        df["texto_completo"] = None

    # ── Etapa 7: Carga no MySQL ───────────────────────────────────────────────
    if not args.sem_carga:
        logger.info("=== Etapa 7: Carga no MySQL ===")
        conn = loader.criar_conexao()
        try:
            loader.garantir_tabela(conn)
            loader.carregar_dataframe(df, conn)
        finally:
            conn.close()
            logger.info("Conexão MySQL encerrada.")
    else:
        logger.info("=== Etapa 7: Carga MySQL pulada (--sem-carga) ===")

    logger.info("Pipeline concluído com sucesso.")


if __name__ == "__main__":
    executar(_parse_args())
