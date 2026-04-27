"""
app.py — Interface Streamlit para busca inteligente no DOM-BH.

Execute com:
    streamlit run app.py

O índice TF-IDF é construído automaticamente na primeira execução
e persistido em cache/indice.pkl para reutilização.
"""

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Garante imports locais independente do diretório de trabalho
sys.path.insert(0, str(Path(__file__).parent))

from indexer import IndiceDOM
from search import buscar, listar_areas, listar_tipos_ato, intervalo_datas

# ── Configuração da página ────────────────────────────────────────────────────

st.set_page_config(
    page_title="Busca DOM-BH",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

_CACHE_INDICE = Path(__file__).parent / "cache" / "indice.pkl"
_CSV_PADRAO   = Path(__file__).parent.parent / "legislacao_2026_04.csv"


# ── Carregamento de dados (cacheado pela sessão Streamlit) ────────────────────

@st.cache_resource(show_spinner="Construindo índice de busca...")
def carregar_indice(csv_path: str) -> IndiceDOM:
    """
    Carrega ou constrói o índice TF-IDF.
    O resultado é mantido em memória durante toda a sessão Streamlit.
    """
    if _CACHE_INDICE.exists():
        try:
            indice = IndiceDOM.carregar(str(_CACHE_INDICE))
            st.toast(f"Índice carregado do cache ({indice.n_docs()} atos).", icon="✅")
            return indice
        except Exception:
            pass  # índice corrompido — reconstrói

    # Lê CSV com fallback de encoding
    df = None
    for enc in ("utf-8-sig", "latin-1"):
        try:
            df = pd.read_csv(csv_path, encoding=enc, sep=";", dtype=str)
            break
        except Exception:
            continue
    if df is None:
        st.error(f"Não foi possível ler o arquivo: {csv_path}")
        st.stop()

    # Remove colunas sem nome (pandas renomeia para "Unnamed: N" ao ler Excel)
    df = df.loc[:, ~df.columns.str.startswith("Unnamed:")]

    # Remove espaços extras em todas as colunas de texto (ex: "DECRETO " → "DECRETO")
    str_cols = [c for c in df.columns if df[c].dtype == object]
    for col in str_cols:
        df[col] = df[col].str.strip()

    # Converte datas
    for col in ("DATA ASSINATURA", "DATA DOM"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], format="%d/%m/%Y", errors="coerce")

    indice = IndiceDOM.construir(df)
    indice.salvar(str(_CACHE_INDICE))
    return indice


# ── Sidebar: carregamento do CSV e filtros ────────────────────────────────────

with st.sidebar:
    st.title("DOM-BH · Busca")
    st.caption("Diário Oficial do Município de Belo Horizonte")

    csv_path = st.text_input(
        "Caminho do CSV",
        value=str(_CSV_PADRAO),
        help="Arquivo exportado do portal DOM-BH (separador ;)",
    )

    if not Path(csv_path).exists():
        st.warning("Arquivo não encontrado. Informe o caminho correto.")
        st.stop()

    indice = carregar_indice(csv_path)
    df = indice.df

    st.success(f"{indice.n_docs():,} atos indexados")
    st.divider()

    # ── Filtros de metadados ──────────────────────────────────────────────────
    st.subheader("Filtros")

    tipos_disponiveis = listar_tipos_ato(df)
    tipos_sel = st.multiselect(
        "Tipo de ato",
        options=tipos_disponiveis,
        default=[],
        placeholder="Todos os tipos",
    )

    areas_disponiveis = listar_areas(df)
    areas_sel = st.multiselect(
        "Área (ASSUNTO)",
        options=areas_disponiveis,
        default=[],
        placeholder="Todas as áreas",
    )

    orgao_sel = st.text_input("Órgão (busca parcial)", placeholder="ex: SMAM, SMAAS")

    ano_min, ano_max = intervalo_datas(df)
    if ano_min and ano_max:
        anos_sel = st.slider(
            "Período (DATA DOM)",
            min_value=ano_min,
            max_value=ano_max,
            value=(ano_min, ano_max),
        )
    else:
        anos_sel = (None, None)

    top_k = st.number_input("Máximo de resultados", min_value=5, max_value=100, value=20, step=5)

    st.divider()
    if st.button("Limpar índice (reconstrói)", use_container_width=True):
        if _CACHE_INDICE.exists():
            _CACHE_INDICE.unlink()
        st.cache_resource.clear()
        st.rerun()


# ── Área principal: campo de busca ────────────────────────────────────────────

st.title("Busca no Diário Oficial de BH")
st.caption(
    "Pesquise por texto da ementa, assunto ou tipo de ato. "
    "Você pode incluir o ano diretamente na busca: *'coleta seletiva 2015'*."
)

col_busca, col_btn = st.columns([5, 1])
with col_busca:
    query = st.text_input(
        "O que você quer buscar?",
        placeholder="Ex: regulamenta coleta seletiva, transferências de pessoal 2012, copa 2014...",
        label_visibility="collapsed",
    )
with col_btn:
    buscar_btn = st.button("Buscar", type="primary", use_container_width=True)

# Exemplos rápidos
with st.expander("Exemplos de busca"):
    exemplos = [
        "coleta seletiva",
        "transferências de pessoal 2012",
        "copa 2014",
        "conselho tutelar",
        "estrutura organizacional SMAM",
        "processo disciplinar",
        "habitação 2015",
    ]
    cols = st.columns(4)
    for i, ex in enumerate(exemplos):
        if cols[i % 4].button(ex, key=f"ex_{i}", use_container_width=True):
            query = ex
            buscar_btn = True

# ── Execução da busca ─────────────────────────────────────────────────────────

if buscar_btn or query:
    # Monta filtros de data a partir do slider
    data_inicio = f"{anos_sel[0]}-01-01" if anos_sel[0] else None
    data_fim    = f"{anos_sel[1]}-12-31" if anos_sel[1] else None

    # Não aplica filtro de data se o range é o range total (sem restrição)
    if anos_sel == (ano_min, ano_max):
        data_inicio = data_fim = None

    with st.spinner("Buscando..."):
        resultado = buscar(
            query=query,
            indice=indice,
            top_k=int(top_k),
            data_inicio=data_inicio,
            data_fim=data_fim,
            tipos_ato=tipos_sel if tipos_sel else None,
            areas=areas_sel if areas_sel else None,
            orgao=orgao_sel if orgao_sel.strip() else None,
        )

    # ── Exibição dos resultados ───────────────────────────────────────────────
    if resultado.empty:
        st.warning("Nenhum resultado encontrado. Tente termos mais genéricos ou remova filtros.")
    else:
        n = len(resultado)
        score_medio = resultado["_score"].mean() if "_score" in resultado.columns else 0
        col1, col2, col3 = st.columns(3)
        col1.metric("Resultados", n)
        col2.metric("Score médio", f"{score_medio:.3f}" if score_medio > 0 else "—")
        col3.metric("Filtros ativos",
                    sum([bool(tipos_sel), bool(areas_sel), bool(orgao_sel.strip()),
                         anos_sel != (ano_min, ano_max)]))

        st.divider()

        # Renderiza cada resultado como card expandível
        for _, row in resultado.iterrows():
            score = row.get("_score", 0)
            tipo  = row.get("TIPO ATO", "ATO")
            num   = row.get("Nº", "")
            data  = row.get("DATA DOM")
            data_fmt = data.strftime("%d/%m/%Y") if pd.notna(data) and hasattr(data, "strftime") else str(data or "")
            ementa = str(row.get("EMENTA") or "")[:200]
            assunto = str(row.get("ASSUNTO") or "")
            orgao_r = str(row.get("ÓRGÃO") or "")
            link  = str(row.get("LINK") or "")

            titulo = f"**{tipo}** nº {num} · {data_fmt}"
            if orgao_r:
                titulo += f" · {orgao_r}"
            if score > 0:
                titulo += f" · relevância {score:.3f}"

            with st.expander(titulo):
                st.markdown(f"**Ementa:** {ementa}{'...' if len(str(row.get('EMENTA') or '')) > 200 else ''}")
                if assunto:
                    st.markdown(f"**Assunto:** `{assunto}`")
                if link and link.startswith("http"):
                    st.markdown(f"[Abrir no portal DOM-BH]({link})")
                else:
                    st.caption("Link não disponível")

        # Tabela completa (colapsável)
        with st.expander("Ver como tabela"):
            colunas_tabela = [c for c in ["TIPO ATO", "Nº", "DATA DOM", "EMENTA", "ASSUNTO", "LINK"]
                              if c in resultado.columns]
            df_tabela = resultado[colunas_tabela].copy()
            if "DATA DOM" in df_tabela.columns:
                df_tabela["DATA DOM"] = df_tabela["DATA DOM"].apply(
                    lambda d: d.strftime("%d/%m/%Y") if pd.notna(d) and hasattr(d, "strftime") else d
                )
            if "LINK" in df_tabela.columns:
                df_tabela["LINK"] = df_tabela["LINK"].apply(
                    lambda l: f'<a href="{l}" target="_blank">abrir</a>' if isinstance(l, str) and l.startswith("http") else ""
                )
            st.write(df_tabela.to_html(escape=False, index=False), unsafe_allow_html=True)

else:
    # Estado inicial — mostra estatísticas do dataset
    st.info("Digite um termo de busca ou use os filtros na barra lateral.")

    st.subheader("Resumo do acervo")
    col1, col2, col3 = st.columns(3)
    col1.metric("Total de atos", f"{indice.n_docs():,}")

    if "TIPO ATO" in df.columns:
        dist = df["TIPO ATO"].value_counts().head(6)
        col2.metric("Tipos distintos", df["TIPO ATO"].nunique())
        with col3:
            st.bar_chart(dist, height=180)

    if "DATA DOM" in df.columns:
        datas = pd.to_datetime(df["DATA DOM"], errors="coerce")
        por_ano = datas.dt.year.value_counts().sort_index()
        st.subheader("Distribuição por ano (DATA DOM)")
        st.bar_chart(por_ano, height=200)
