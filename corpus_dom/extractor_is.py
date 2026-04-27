"""
extractor_is.py — Extração estruturada de Instruções de Serviço (IS) do DOM-BH.

Cinco camadas de dados por documento:
  1. Metadados do portal   — header do card (tipo, número, órgão, datas)
  2. Corpo narrativo       — macroprocesso, artigos/dispositivos, assinatura
  3. Tabelas de unidades   — criadas / alteradas / excluídas  (3 tabelas HTML)
  4. Bases legais          — normas referenciadas no "Considerando"
  5. Anexos                — arquivos listados no rodapé do documento

Ponto de entrada principal:
    resultado = extrair_is(html, ato_id)
    # resultado: dict com chaves 'metadados', 'dispositivos',
    #            'unidades', 'bases_legais', 'anexos'
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

# Mapeamento posição-da-tabela → valor do ENUM operacao
_OPERACAO_POR_POSICAO = {0: "CRIADA", 1: "ALTERADA", 2: "EXCLUÍDA"}

# Padrão de código OPUS: 13 dígitos (pode ter separadores como pontos)
_RE_OPUS = re.compile(r"\b(\d[\d\.]{10,16}\d)\b")

# Padrão de bases legais: Lei/Decreto/Portaria/IS + identificador
_RE_BASE_LEGAL = re.compile(
    r"(?:Lei|Decreto(?:-Lei)?|Portaria|Instrução de Serviço|IS|Resolução|Deliberação)"
    r"(?:\s+(?:Federal|Estadual|Municipal|Complementar))?"
    r"\s+n[º°\.]?\s*[\d\.]+(?:[\/\-]\d+)?",
    re.IGNORECASE,
)


# ── Estruturas de dados ───────────────────────────────────────────────────────

@dataclass
class UnidadeOrg:
    ato_id: int
    operacao: str                         # CRIADA | ALTERADA | EXCLUÍDA
    denominacao: Optional[str] = None
    sigla: Optional[str] = None
    codigo_opus: Optional[str] = None
    digito_verificador: Optional[str] = None
    nivel: Optional[str] = None
    tipo_unidade: Optional[str] = None
    vinculacao: Optional[str] = None
    # Preenchido apenas quando operacao == 'ALTERADA'
    denominacao_anterior: Optional[str] = None
    sigla_anterior: Optional[str] = None
    codigo_opus_anterior: Optional[str] = None


@dataclass
class Dispositivo:
    ato_id: int
    numero: Optional[int]
    conteudo: str


@dataclass
class BaseLegal:
    ato_id: int
    referencia: str


@dataclass
class Anexo:
    ato_id: int
    nome: str
    url: Optional[str] = None


# ── Utilitários internos ──────────────────────────────────────────────────────

def _texto(tag: Optional[Tag]) -> Optional[str]:
    """Retorna o texto limpo de uma tag ou None se tag for None/vazia."""
    if tag is None:
        return None
    t = tag.get_text(separator=" ", strip=True)
    return t if t else None


def _celulas(linha: Tag) -> list[str]:
    """Retorna lista de textos limpos das células (td ou th) de uma linha."""
    return [c.get_text(separator=" ", strip=True) for c in linha.find_all(["td", "th"])]


def _separar_opus(codigo_bruto: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """
    Separa código OPUS do dígito verificador.

    O HTML do DOM-BH apresenta o código em duas células adjacentes:
      '6801001600000' | '3'
    Esta função também lida com o caso em que chegam concatenados.
    """
    if not codigo_bruto:
        return None, None
    codigo_bruto = codigo_bruto.strip().replace(".", "").replace("-", "")
    if len(codigo_bruto) == 14:
        return codigo_bruto[:13], codigo_bruto[13]
    if len(codigo_bruto) == 13:
        return codigo_bruto, None
    return codigo_bruto, None


# ── 1. Metadados do portal ────────────────────────────────────────────────────

def extrair_metadados(soup: BeautifulSoup) -> dict:
    """
    Extrai os metadados do card de cabeçalho da página do DOM-BH.

    Tenta múltiplos seletores para cobrir variações de layout do portal.
    """
    meta: dict = {}

    # Seletor principal: div ou table com classe contendo 'card' ou 'ato'
    card = (
        soup.find("div", class_=re.compile(r"card|ato|header", re.I))
        or soup.find("table", class_=re.compile(r"card|ato|cabec", re.I))
    )
    if card is None:
        logger.debug("Card de metadados não encontrado; tentando <dl> genérico.")
        card = soup

    # Pares rótulo → valor em <dl><dt><dd> (estrutura semântica ideal)
    for dt in card.find_all("dt"):
        rotulo = _texto(dt)
        dd = dt.find_next_sibling("dd")
        if rotulo and dd:
            meta[rotulo.lower().rstrip(":")] = _texto(dd)

    # Fallback: tabela de duas colunas (rótulo | valor)
    if not meta:
        for tr in card.find_all("tr"):
            celulas = _celulas(tr)
            if len(celulas) == 2:
                meta[celulas[0].lower().rstrip(":")] = celulas[1]

    return meta


# ── 2. Corpo narrativo ────────────────────────────────────────────────────────

def extrair_macroprocesso(soup: BeautifulSoup) -> Optional[str]:
    """Busca o campo 'Macroprocesso' no corpo do documento."""
    # Padrão comum: célula rotulada seguida de célula com valor
    for tag in soup.find_all(string=re.compile(r"macroprocesso", re.I)):
        pai = tag.parent
        if pai:
            proximo = pai.find_next_sibling()
            if proximo:
                return _texto(proximo)
    return None


def extrair_dispositivos(soup: BeautifulSoup, ato_id: int) -> list[Dispositivo]:
    """
    Extrai os artigos/dispositivos do corpo narrativo da IS.

    Padrões reconhecidos:
      - 'Art. 1º  …'  com número explícito
      - Parágrafos sem numeração (número = None)
    """
    dispositivos: list[Dispositivo] = []
    _RE_ART = re.compile(r"^Art\.?\s*(\d+)[°º]?\s*[–\-—]?\s*", re.IGNORECASE)

    # Tenta localizar o bloco de artigos pelo padrão textual
    for tag in soup.find_all(["p", "div", "li"]):
        texto = tag.get_text(separator=" ", strip=True)
        if not texto or len(texto) < 10:
            continue
        m = _RE_ART.match(texto)
        if m:
            numero = int(m.group(1))
            conteudo = _RE_ART.sub("", texto).strip()
            dispositivos.append(Dispositivo(ato_id=ato_id, numero=numero, conteudo=conteudo))

    return dispositivos


def extrair_assinatura(soup: BeautifulSoup) -> Optional[str]:
    """Retorna o bloco de assinatura (nome + cargo) ao final do documento."""
    # Heurística: último parágrafo com letras maiúsculas isolado
    candidatos = [
        t.get_text(strip=True)
        for t in soup.find_all(["p", "div"])
        if t.get_text(strip=True).isupper() and len(t.get_text(strip=True)) > 5
    ]
    return candidatos[-1] if candidatos else None


# ── 3. Tabelas de unidades organizacionais ────────────────────────────────────

def _inferir_operacao_pelo_cabecalho(cabecalho: list[str]) -> Optional[str]:
    """
    Detecta operação pelos rótulos das colunas quando a posição não é confiável.
    Tabelas ALTERADA têm colunas 'DE' e 'PARA' (ou 'ANTERIOR' / 'NOVO').
    """
    texto_cabec = " ".join(cabecalho).upper()
    if re.search(r"\bDE\b.*\bPARA\b|\bANTERIOR\b|\bNOVO\b", texto_cabec):
        return "ALTERADA"
    if re.search(r"EXCLU[IÍ]", texto_cabec):
        return "EXCLUÍDA"
    if re.search(r"CRIA[DR]", texto_cabec):
        return "CRIADA"
    return None


def _mapear_colunas(cabecalho: list[str]) -> dict[str, int]:
    """
    Cria mapa {nome_normalizado: índice_coluna} a partir do cabeçalho.

    Normalização: minúsculas, sem acentos simples, trim.
    """
    mapa: dict[str, int] = {}
    for i, col in enumerate(cabecalho):
        chave = col.lower().strip()
        mapa[chave] = i
    return mapa


def _col(celulas: list[str], mapa: dict[str, int], *chaves: str) -> Optional[str]:
    """Retorna o valor da primeira chave encontrada no mapa de colunas."""
    for chave in chaves:
        idx = mapa.get(chave)
        if idx is not None and idx < len(celulas):
            val = celulas[idx].strip()
            return val if val else None
    return None


def _parse_tabela_unidades(
    tabela: Tag,
    ato_id: int,
    operacao: str,
) -> list[UnidadeOrg]:
    """
    Converte uma <table> HTML em lista de UnidadeOrg.

    Tabela ALTERADA: colunas duplicadas (DE / PARA) — cada par vira uma linha
    com os campos _anterior preenchidos.
    """
    linhas = tabela.find_all("tr")
    if not linhas:
        return []

    cabecalho = _celulas(linhas[0])

    # Redetecta operação pelo cabeçalho se a posição for ambígua
    operacao_detectada = _inferir_operacao_pelo_cabecalho(cabecalho)
    if operacao_detectada:
        operacao = operacao_detectada

    mapa = _mapear_colunas(cabecalho)
    unidades: list[UnidadeOrg] = []

    for tr in linhas[1:]:
        celulas = _celulas(tr)
        if not any(celulas):
            continue

        # Código OPUS pode estar em duas células adjacentes
        # Tenta extrair pela coluna 'código opus' ou por regex
        codigo_raw = _col(celulas, mapa, "código opus", "codigo opus", "código", "opus")
        digito_raw = _col(celulas, mapa, "dv", "dígito", "digito verificador", "d.v.")

        # Se o dígito não tem coluna própria, tenta extrair da próxima célula ao código
        if codigo_raw and not digito_raw:
            idx_opus = mapa.get("código opus") or mapa.get("codigo opus") or mapa.get("código")
            if idx_opus is not None and idx_opus + 1 < len(celulas):
                possivel_dv = celulas[idx_opus + 1].strip()
                if re.match(r"^\d$", possivel_dv):
                    digito_raw = possivel_dv

        codigo_opus, digito_vf = _separar_opus(codigo_raw)
        if digito_raw and not digito_vf:
            digito_vf = digito_raw.strip()

        u = UnidadeOrg(
            ato_id=ato_id,
            operacao=operacao,
            denominacao=_col(celulas, mapa,
                             "denominação", "denominacao", "nome", "para denominação", "para denominacao"),
            sigla=_col(celulas, mapa, "sigla", "para sigla"),
            codigo_opus=codigo_opus,
            digito_verificador=digito_vf,
            nivel=_col(celulas, mapa, "nível", "nivel"),
            tipo_unidade=_col(celulas, mapa, "tipo", "tipo de unidade", "tipo unidade"),
            vinculacao=_col(celulas, mapa, "vinculação", "vinculacao", "vinculada a"),
        )

        if operacao == "ALTERADA":
            u.denominacao_anterior = _col(celulas, mapa,
                                          "de denominação", "de denominacao", "denominação anterior")
            u.sigla_anterior = _col(celulas, mapa, "de sigla", "sigla anterior")
            codigo_ant_raw = _col(celulas, mapa,
                                  "de código opus", "de codigo opus", "código opus anterior")
            u.codigo_opus_anterior, _ = _separar_opus(codigo_ant_raw)

        unidades.append(u)

    return unidades


def extrair_unidades(soup: BeautifulSoup, ato_id: int) -> list[UnidadeOrg]:
    """
    Localiza as 3 tabelas de unidades via seletor 'center > table' e as parseia.

    Ordem esperada no HTML: [0]=CRIADA  [1]=ALTERADA  [2]=EXCLUÍDA
    """
    tabelas = soup.select("center > table")
    if not tabelas:
        # Fallback: qualquer tabela que contenha 'sigla' no cabeçalho
        tabelas = [
            t for t in soup.find_all("table")
            if any("sigla" in c.get_text(strip=True).lower() for c in t.find_all("th"))
        ]

    unidades: list[UnidadeOrg] = []
    for i, tabela in enumerate(tabelas):
        operacao_padrao = _OPERACAO_POR_POSICAO.get(i, "CRIADA")
        unidades.extend(_parse_tabela_unidades(tabela, ato_id, operacao_padrao))

    logger.debug("IS %d: %d unidades extraídas de %d tabelas.", ato_id, len(unidades), len(tabelas))
    return unidades


# ── 4. Bases legais ───────────────────────────────────────────────────────────

def extrair_bases_legais(soup: BeautifulSoup, ato_id: int) -> list[BaseLegal]:
    """
    Extrai referências normativas do bloco 'Considerando' e do cabeçalho.

    Usa regex sobre o texto completo para não depender de marcação específica.
    """
    texto_completo = soup.get_text(separator=" ", strip=True)
    refs = _RE_BASE_LEGAL.findall(texto_completo)
    # Deduplica mantendo ordem de aparição
    vistas: set[str] = set()
    bases: list[BaseLegal] = []
    for ref in refs:
        ref_norm = re.sub(r"\s+", " ", ref).strip()
        if ref_norm not in vistas:
            vistas.add(ref_norm)
            bases.append(BaseLegal(ato_id=ato_id, referencia=ref_norm))
    return bases


# ── 5. Anexos ─────────────────────────────────────────────────────────────────

def extrair_anexos(soup: BeautifulSoup, ato_id: int) -> list[Anexo]:
    """
    Extrai links para anexos (.xls, .xlsx, .pdf, .doc, .docx) do documento.
    """
    _EXT = re.compile(r"\.(xls[xm]?|pdf|docx?|csv|ods)$", re.IGNORECASE)
    anexos: list[Anexo] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if _EXT.search(href):
            nome = _texto(a) or href.split("/")[-1]
            anexos.append(Anexo(ato_id=ato_id, nome=nome, url=href))
    return anexos


# ── Ponto de entrada ──────────────────────────────────────────────────────────

def extrair_is(html: str, ato_id: int) -> dict:
    """
    Extrai todas as camadas de uma Instrução de Serviço.

    Parâmetros
    ----------
    html    : HTML da página do ato no portal DOM-BH
    ato_id  : PK do registro correspondente em atos_dom_bh

    Retorna
    -------
    {
      'metadados':   dict,
      'macroprocesso': str | None,
      'dispositivos': list[Dispositivo],
      'assinatura':  str | None,
      'unidades':    list[UnidadeOrg],
      'bases_legais': list[BaseLegal],
      'anexos':      list[Anexo],
    }
    """
    soup = BeautifulSoup(html, "lxml")

    resultado = {
        "metadados":     extrair_metadados(soup),
        "macroprocesso": extrair_macroprocesso(soup),
        "dispositivos":  extrair_dispositivos(soup, ato_id),
        "assinatura":    extrair_assinatura(soup),
        "unidades":      extrair_unidades(soup, ato_id),
        "bases_legais":  extrair_bases_legais(soup, ato_id),
        "anexos":        extrair_anexos(soup, ato_id),
    }

    logger.info(
        "IS ato_id=%d: %d unidades | %d dispositivos | %d bases legais | %d anexos",
        ato_id,
        len(resultado["unidades"]),
        len(resultado["dispositivos"]),
        len(resultado["bases_legais"]),
        len(resultado["anexos"]),
    )
    return resultado
