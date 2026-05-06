"""
Carrega artigos de legislação diretamente do arquivo CSV local.

O CSV (separado por ponto-e-vírgula) tem as colunas:
  TIPO ATO · ÓRGÃO · Nº · DATA ASSINATURA · EMENTA
  DATA DOM · OBSERVAÇÃO · ASSUNTO · LINK

Cada linha vira um artigo no formato esperado pelo BHNewsChatbot, usando a
EMENTA como corpo — sem precisar raspar nenhuma página web.
"""

import csv
import logging
from datetime import date, datetime
from pathlib import Path

log = logging.getLogger(__name__)

# Caminho padrão: legislacao_2026_04.csv na raiz do repositório
DEFAULT_CSV = Path(__file__).parent.parent / "legislacao_2026_04.csv"


def _parse_date(date_str: str) -> date:
    """Converte DD/MM/YYYY em date para ordenação. Datas inválidas vão para o fim."""
    try:
        return datetime.strptime(date_str.strip(), "%d/%m/%Y").date()
    except ValueError:
        return date.min


def _normalize_area(assunto: str) -> str:
    """Retorna a primeira parte do ASSUNTO (antes de ' - ') como área temática."""
    if not assunto:
        return "Outros"
    return assunto.split(" - ")[0].strip().title() or "Outros"


def _build_title(row: dict) -> str:
    tipo = row.get("TIPO ATO", "").strip()
    numero = row.get("Nº", "").strip()
    ementa = row.get("EMENTA", "").strip()
    parts = [p for p in [tipo, numero] if p]
    prefix = " ".join(parts)
    short_ementa = ementa[:100] + "…" if len(ementa) > 100 else ementa
    return f"{prefix} — {short_ementa}" if prefix else short_ementa


def _build_body(row: dict) -> str:
    ementa = row.get("EMENTA", "").strip()
    orgao = row.get("ÓRGÃO", "").strip()
    obs = row.get("OBSERVAÇÃO", "").strip()
    assunto = row.get("ASSUNTO", "").strip()

    lines = []
    if ementa:
        lines.append(ementa)
    if orgao:
        lines.append(f"Órgão: {orgao}")
    if assunto:
        lines.append(f"Assunto: {assunto}")
    if obs:
        lines.append(f"Observação: {obs}")
    return "\n".join(lines)


def load_articles_from_csv(path: Path | str = DEFAULT_CSV) -> list[dict]:
    """
    Lê o CSV de legislação e retorna lista de artigos prontos para o chatbot.

    Cada artigo tem: url, title, date, body, area.
    Linhas sem EMENTA são ignoradas.
    """
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Arquivo CSV não encontrado: {csv_path}")

    articles: list[dict] = []
    skipped = 0

    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        # Remove colunas vazias geradas por ponto-e-vírgulas extras no final
        reader = csv.DictReader(fh, delimiter=";")
        for row in reader:
            ementa = row.get("EMENTA", "").strip()
            if not ementa:
                skipped += 1
                continue

            articles.append({
                "url":   row.get("LINK", "").strip(),
                "title": _build_title(row),
                "date":  row.get("DATA ASSINATURA", "").strip() or row.get("DATA DOM", "").strip(),
                "body":  _build_body(row),
                "area":  _normalize_area(row.get("ASSUNTO", "")),
            })

    # Ordena do mais recente para o mais antigo para que o contexto do LLM
    # priorize a legislação mais atual dentro do limite de tokens.
    articles.sort(key=lambda a: _parse_date(a["date"]), reverse=True)

    log.info(
        "CSV carregado: %d registros válidos, %d ignorados (sem ementa) — %s",
        len(articles), skipped, csv_path.name,
    )
    return articles
