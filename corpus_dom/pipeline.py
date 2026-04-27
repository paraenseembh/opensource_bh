"""
pipeline.py — Orquestração principal do pipeline DOM-BH.

Etapas executadas em ordem:
  1.  Ingestão do CSV exportado do DOM-BH
  2.  Conversão de datas e cálculo de lag de publicação
  3.  Parsing e enriquecimento da ementa (verbo, refs, valor)
  4.  Separação de ASSUNTO em área e subtema
  5.  Normalização de ÓRGÃO
  6.  Scraping cache-aware (HTML, PDF, DOCX) — só busca o que não está no cache
  7.  Limpeza e deduplicação do texto coletado
  8.  Chunking para RAG → corpus_chunks.jsonl
  9.  Exportação JSONL / CSV (opcional)
  10. Carga no MySQL (opcional)

Execute com:
    python pipeline.py [--csv CAMINHO]
                       [--cache CAMINHO]          # default: corpus/corpus.jsonl
                       [--forcar-re-scraping]     # ignora cache; re-faz tudo
                       [--sem-scraping]
                       [--sem-limpeza]
                       [--sem-chunking]
                       [--chunks CAMINHO]         # default: corpus/corpus_chunks.jsonl
                       [--chunk-tamanho N]        # default: 1500 chars
                       [--chunk-overlap N]        # default: 150 chars
                       [--exportar-jsonl CAMINHO]
                       [--exportar-csv CAMINHO]
                       [--sem-carga]
"""

import argparse
import logging
import os
import sys

import pandas as pd
from dotenv import load_dotenv

import cache as cache_mod
import chunker
import cleaner
import extractor
import loader
import scraper

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

    # Entrada
    parser.add_argument("--csv", default=None,
                        help="Caminho para o CSV do DOM-BH (sobrepõe CSV_PATH do .env)")

    # Cache local
    parser.add_argument("--cache", default=None, metavar="CAMINHO",
                        help="Caminho do corpus.jsonl local (default: corpus/corpus.jsonl)")
    parser.add_argument("--forcar-re-scraping", action="store_true",
                        help="Ignora o cache e re-faz todas as requisições HTTP")

    # Scraping
    parser.add_argument("--sem-scraping", action="store_true",
                        help="Pula a etapa de scraping do texto completo")

    # Limpeza
    parser.add_argument("--sem-limpeza", action="store_true",
                        help="Pula a etapa de limpeza e deduplicação do texto")

    # Chunking RAG
    parser.add_argument("--sem-chunking", action="store_true",
                        help="Pula a geração de chunks para RAG")
    parser.add_argument("--chunks", default=None, metavar="CAMINHO",
                        help="Caminho do corpus_chunks.jsonl (default: corpus/corpus_chunks.jsonl)")
    parser.add_argument("--chunk-tamanho", type=int, default=None, metavar="N",
                        help="Caracteres por chunk (default: 1500)")
    parser.add_argument("--chunk-overlap", type=int, default=None, metavar="N",
                        help="Sobreposição entre chunks em chars (default: 150)")

    # Exportação
    parser.add_argument("--exportar-jsonl", default=None, metavar="CAMINHO",
                        help="Exporta corpus em JSONL para o caminho indicado")
    parser.add_argument("--exportar-csv", default=None, metavar="CAMINHO",
                        help="Exporta corpus em CSV (UTF-8 BOM) para o caminho indicado")

    # MySQL
    parser.add_argument("--sem-carga", action="store_true",
                        help="Pula a etapa de carga no MySQL (útil para debug)")

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

    csv_path      = args.csv or os.environ.get("CSV_PATH", "dados/indice_dom_bh.csv")
    delay         = float(os.environ.get("SCRAPING_DELAY", 1.5))
    max_retries   = int(os.environ.get("SCRAPING_MAX_RETRIES", 3))
    timeout       = int(os.environ.get("SCRAPING_TIMEOUT", 30))
    cache_path    = args.cache or os.environ.get("CACHE_PATH", "corpus/corpus.jsonl")
    chunks_path   = args.chunks or os.environ.get("CHUNKS_PATH", "corpus/corpus_chunks.jsonl")
    chunk_tamanho = args.chunk_tamanho or int(os.environ.get("CHUNK_SIZE", 1500))
    chunk_overlap = args.chunk_overlap or int(os.environ.get("CHUNK_OVERLAP", 150))

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

    # ── Etapa 6: Scraping cache-aware ────────────────────────────────────────
    if not args.sem_scraping:
        logger.info("=== Etapa 6: Scraping cache-aware ===")
        scraper.verificar_lexml_disponivel()

        # Inicializa cache (None se --forcar-re-scraping)
        cache_inst = None
        if not args.forcar_re_scraping:
            cache_inst = cache_mod.CacheLocal(cache_path)
            stats = cache_inst.estatisticas()
            logger.info("Cache inicializado: %d documentos em '%s'.",
                        stats["total_no_cache"], stats["caminho"])
        else:
            logger.info("--forcar-re-scraping ativo: cache ignorado.")

        df = scraper.scrape_todos(
            df,
            delay=delay,
            max_retries=max_retries,
            timeout=timeout,
            cache=cache_inst,
        )
    else:
        logger.info("=== Etapa 6: Scraping pulado (--sem-scraping) ===")
        df["texto_completo"] = None

    # ── Etapa 7: Limpeza e deduplicação ──────────────────────────────────────
    if not args.sem_limpeza:
        logger.info("=== Etapa 7: Limpeza e deduplicação do texto ===")
        df = cleaner.limpar_dataframe(df)
    else:
        logger.info("=== Etapa 7: Limpeza pulada (--sem-limpeza) ===")

    # ── Etapa 8: Chunking para RAG ────────────────────────────────────────────
    if not args.sem_chunking:
        logger.info("=== Etapa 8: Chunking para RAG → %s ===", chunks_path)
        # Usa o corpus.jsonl do cache como entrada (mais completo que o df atual)
        import os as _os
        if _os.path.exists(cache_path):
            total_chunks = chunker.chunkar_corpus(
                caminho_entrada=cache_path,
                caminho_saida=chunks_path,
                tamanho=chunk_tamanho,
                sobreposicao=chunk_overlap,
            )
            logger.info("Chunks gerados: %d → '%s'", total_chunks, chunks_path)
        else:
            logger.warning(
                "Cache '%s' não encontrado para chunking. "
                "Execute sem --sem-scraping primeiro, ou use --cache.",
                cache_path,
            )
    else:
        logger.info("=== Etapa 8: Chunking pulado (--sem-chunking) ===")

    # ── Etapa 9: Exportação JSONL / CSV ──────────────────────────────────────
    if args.exportar_jsonl:
        logger.info("=== Etapa 9a: Exportação JSONL → %s ===", args.exportar_jsonl)
        loader.exportar_jsonl(df, args.exportar_jsonl)

    if args.exportar_csv:
        logger.info("=== Etapa 9b: Exportação CSV → %s ===", args.exportar_csv)
        loader.exportar_csv_corpus(df, args.exportar_csv)

    # ── Etapa 10: Carga no MySQL ──────────────────────────────────────────────
    if not args.sem_carga:
        logger.info("=== Etapa 10: Carga no MySQL ===")
        conn = loader.criar_conexao()
        try:
            loader.garantir_tabela(conn)
            loader.carregar_dataframe(df, conn)
        finally:
            conn.close()
            logger.info("Conexão MySQL encerrada.")
    else:
        logger.info("=== Etapa 10: Carga MySQL pulada (--sem-carga) ===")

    logger.info("Pipeline concluído com sucesso.")


if __name__ == "__main__":
    executar(_parse_args())
