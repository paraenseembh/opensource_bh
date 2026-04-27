"""
cache.py — Cache local JSONL incremental para documentos coletados do DOM-BH.

Evita re-consultas à API: antes de cada requisição HTTP, o scraper verifica
se o documento já existe no cache. Novos documentos são gravados imediatamente
após a coleta — se o pipeline falhar no meio, o progresso é preservado.

Uso típico:
    cache = CacheLocal("corpus/corpus.jsonl")
    pendentes = cache.pendentes(lista_de_urls)   # só as URLs não coletadas
    # ... scraping ...
    cache.salvar(url, texto, metadados)           # append imediato
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class CacheLocal:
    """
    Gerenciador de cache append-only baseado em arquivo JSONL.

    Cada linha do arquivo é um documento:
      {"url": "...", "texto": "...", "tipo_ato": "...", "numero": "...",
       "data_dom": "...", "orgao": "...", "ementa": "...", "coletado_em": "..."}

    O índice {url → record} é mantido em memória para lookup O(1).
    """

    def __init__(self, caminho: str = "corpus/corpus.jsonl") -> None:
        self._caminho = Path(caminho)
        self._caminho.parent.mkdir(parents=True, exist_ok=True)
        self._indice: dict[str, dict] = {}
        self._carregar_indice()

    # ── Inicialização ─────────────────────────────────────────────────────────

    def _carregar_indice(self) -> None:
        """Lê o JSONL existente e constrói o índice em memória."""
        if not self._caminho.exists():
            logger.info("Cache: arquivo '%s' não existe ainda — iniciando vazio.", self._caminho)
            return

        duplicatas = 0
        with self._caminho.open(encoding="utf-8") as f:
            for i, linha in enumerate(f, start=1):
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    record = json.loads(linha)
                    url = record.get("url", "")
                    if url in self._indice:
                        duplicatas += 1
                    self._indice[url] = record
                except json.JSONDecodeError:
                    logger.warning("Cache: linha %d inválida (ignorada).", i)

        logger.info(
            "Cache carregado: %d documentos em '%s'%s.",
            len(self._indice),
            self._caminho,
            f" ({duplicatas} duplicatas descartadas)" if duplicatas else "",
        )

    # ── Interface pública ─────────────────────────────────────────────────────

    def existe(self, url: str) -> bool:
        """Retorna True se a URL já está no cache."""
        return url in self._indice

    def ler(self, url: str) -> Optional[dict]:
        """Retorna o record completo da URL ou None se não existir."""
        return self._indice.get(url)

    def salvar(self, url: str, texto: str, metadados: dict) -> None:
        """
        Grava um novo documento no cache.

        O registro é adicionado ao final do arquivo JSONL imediatamente.
        Se a URL já existe no índice, atualiza apenas em memória (não re-grava
        no arquivo para manter o append-only; a versão mais recente prevalece
        no índice em RAM).
        """
        record = {
            "url":         url,
            "texto":       texto,
            "tipo_ato":    metadados.get("TIPO ATO") or metadados.get("tipo_ato", ""),
            "numero":      str(metadados.get("Nº") or metadados.get("numero", "")),
            "data_dom":    str(metadados.get("DATA DOM") or metadados.get("data_dom", "")),
            "orgao":       metadados.get("ÓRGÃO") or metadados.get("orgao", ""),
            "ementa":      metadados.get("EMENTA") or metadados.get("ementa", ""),
            "coletado_em": datetime.now(tz=timezone.utc).isoformat(),
        }

        if url not in self._indice:
            # Só faz append se é documento novo (evita crescimento ilimitado do arquivo)
            with self._caminho.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        self._indice[url] = record

    def pendentes(self, urls: list[str]) -> list[str]:
        """Retorna somente as URLs que ainda não estão no cache."""
        return [u for u in urls if u not in self._indice]

    def estatisticas(self) -> dict:
        """Retorna contagens úteis para log."""
        return {
            "total_no_cache":  len(self._indice),
            "com_texto":       sum(1 for r in self._indice.values() if r.get("texto")),
            "caminho":         str(self._caminho),
        }
