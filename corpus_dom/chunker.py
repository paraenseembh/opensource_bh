"""
chunker.py — Fragmentação de texto para indexação em vector store (RAG).

Transforma documentos do corpus DOM-BH em chunks menores com metadados,
prontos para geração de embeddings e indexação em Chroma, pgvector etc.

Estratégia de split (em ordem de prioridade):
  1. Divide por parágrafos (\n\n)
  2. Se parágrafo ainda excede `tamanho`, divide por sentenças (. )
  3. Acumula blocos até atingir `tamanho`
  4. Aplica overlap copiando os últimos `sobreposicao` chars para o chunk seguinte
  5. Descarta chunks com menos de 100 chars (artefatos de limpeza)

Sem dependências externas — usa apenas re e json da stdlib.
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_TAMANHO_PADRAO = 1500   # caracteres por chunk
_OVERLAP_PADRAO = 150    # sobreposição entre chunks consecutivos
_CHUNK_MINIMO = 100      # chunks menores que isso são descartados


# ── Split em unidades textuais ────────────────────────────────────────────────

def _dividir_em_blocos(texto: str, tamanho: int) -> list[str]:
    """
    Divide o texto em blocos respeitando fronteiras naturais.

    Prioridade: parágrafo → sentença → caractere (último recurso).
    """
    if not texto:
        return []

    # Passo 1: dividir por parágrafos (linha em branco)
    paragrafos = [p.strip() for p in re.split(r"\n{2,}", texto) if p.strip()]

    blocos: list[str] = []
    for paragrafo in paragrafos:
        if len(paragrafo) <= tamanho:
            blocos.append(paragrafo)
        else:
            # Passo 2: dividir parágrafo longo por sentenças
            sentencas = re.split(r"(?<=[.!?])\s+", paragrafo)
            bloco_atual = ""
            for sentenca in sentencas:
                if len(sentenca) > tamanho:
                    # Passo 3 (último recurso): corte forçado por caractere
                    if bloco_atual:
                        blocos.append(bloco_atual)
                        bloco_atual = ""
                    for i in range(0, len(sentenca), tamanho):
                        blocos.append(sentenca[i : i + tamanho])
                elif len(bloco_atual) + len(sentenca) + 1 <= tamanho:
                    bloco_atual = (bloco_atual + " " + sentenca).strip()
                else:
                    if bloco_atual:
                        blocos.append(bloco_atual)
                    bloco_atual = sentenca
            if bloco_atual:
                blocos.append(bloco_atual)

    return blocos


# ── Montagem de chunks com overlap ───────────────────────────────────────────

def chunkar_texto(
    texto: str,
    tamanho: int = _TAMANHO_PADRAO,
    sobreposicao: int = _OVERLAP_PADRAO,
) -> list[str]:
    """
    Divide `texto` em chunks de no máximo `tamanho` caracteres.

    Aplica overlap: os últimos `sobreposicao` chars de cada chunk
    são copiados para o início do chunk seguinte, preservando contexto
    na fronteira entre fragmentos.

    Retorna lista de strings; chunks com menos de _CHUNK_MINIMO chars
    são descartados.
    """
    blocos = _dividir_em_blocos(texto, tamanho)
    if not blocos:
        return []

    chunks: list[str] = []
    acumulado = ""
    tail = ""  # overlap do chunk anterior

    for bloco in blocos:
        candidato = (tail + " " + bloco).strip() if tail else bloco
        if len(acumulado) + len(candidato) + 1 <= tamanho:
            acumulado = (acumulado + " " + candidato).strip()
        else:
            if acumulado and len(acumulado) >= _CHUNK_MINIMO:
                chunks.append(acumulado)
                tail = acumulado[-sobreposicao:] if sobreposicao else ""
            acumulado = candidato
            if len(acumulado) > tamanho:
                # bloco isolado maior que tamanho — força inclusão
                chunks.append(acumulado[:tamanho])
                tail = acumulado[:tamanho][-sobreposicao:] if sobreposicao else ""
                acumulado = acumulado[tamanho:]

    if acumulado and len(acumulado) >= _CHUNK_MINIMO:
        chunks.append(acumulado)

    return chunks


# ── Chunking de documento individual ─────────────────────────────────────────

def _gerar_chunk_id(record: dict, index: int) -> str:
    """Gera ID legível no formato TIPO_NUMERO_DATA_cNN."""
    tipo = re.sub(r"\s+", "_", (record.get("tipo_ato") or "ATO").upper())
    numero = record.get("numero") or "SN"
    data = (record.get("data_dom") or "SD")[:10].replace("-", "")
    return f"{tipo}_{numero}_{data}_c{index + 1:02d}"


def chunkar_documento(
    record: dict,
    tamanho: int = _TAMANHO_PADRAO,
    sobreposicao: int = _OVERLAP_PADRAO,
) -> list[dict]:
    """
    Fragmenta um record do corpus em chunks RAG-ready.

    Cada chunk retornado inclui o texto fragmentado mais todos os metadados
    do documento original, para que a busca semântica possa retornar contexto
    completo sem joins adicionais.

    Campos garantidos em cada chunk:
      chunk_id, chunk_index, total_chunks, texto,
      url, tipo_ato, numero, data_dom, orgao, ementa
    """
    texto = record.get("texto") or ""
    if not texto.strip():
        return []

    fragmentos = chunkar_texto(texto, tamanho=tamanho, sobreposicao=sobreposicao)
    total = len(fragmentos)
    chunks: list[dict] = []

    for i, fragmento in enumerate(fragmentos):
        chunk: dict = {
            "chunk_id":    _gerar_chunk_id(record, i),
            "chunk_index": i,
            "total_chunks": total,
            "texto":       fragmento,
            "url":         record.get("url", ""),
            "tipo_ato":    record.get("tipo_ato", ""),
            "numero":      record.get("numero", ""),
            "data_dom":    record.get("data_dom", ""),
            "orgao":       record.get("orgao", ""),
            "ementa":      record.get("ementa", ""),
        }
        chunks.append(chunk)

    return chunks


# ── Chunking de corpus completo ───────────────────────────────────────────────

def chunkar_corpus(
    caminho_entrada: str,
    caminho_saida: str,
    tamanho: int = _TAMANHO_PADRAO,
    sobreposicao: int = _OVERLAP_PADRAO,
) -> int:
    """
    Lê `caminho_entrada` (corpus.jsonl) e grava `caminho_saida` (corpus_chunks.jsonl).

    Cada linha de entrada → N linhas de saída (N chunks).
    Retorna o total de chunks gerados.
    """
    entrada = Path(caminho_entrada)
    if not entrada.exists():
        logger.error("Corpus de entrada não encontrado: '%s'", caminho_entrada)
        return 0

    Path(caminho_saida).parent.mkdir(parents=True, exist_ok=True)

    docs_processados = 0
    docs_sem_texto = 0
    total_chunks = 0

    with entrada.open(encoding="utf-8") as fin, \
         open(caminho_saida, "w", encoding="utf-8") as fout:

        for i, linha in enumerate(fin, start=1):
            linha = linha.strip()
            if not linha:
                continue
            try:
                record = json.loads(linha)
            except json.JSONDecodeError:
                logger.warning("chunker: linha %d inválida no corpus — ignorada.", i)
                continue

            if not record.get("texto"):
                docs_sem_texto += 1
                continue

            chunks = chunkar_documento(record, tamanho=tamanho, sobreposicao=sobreposicao)
            for chunk in chunks:
                fout.write(json.dumps(chunk, ensure_ascii=False) + "\n")

            total_chunks += len(chunks)
            docs_processados += 1

    logger.info(
        "Chunking concluído: %d documentos → %d chunks gravados em '%s'"
        " (%d documentos sem texto ignorados).",
        docs_processados, total_chunks, caminho_saida, docs_sem_texto,
    )
    return total_chunks
