"""
app_turma.py — Saúde da Base de Turmas
Pode rodar standalone:  streamlit run app_turma.py
Ou ser chamado pelo vitrine.py via render()

Lê os arquivos gerados pelo processar.py:
    resultados/resumo.parquet                (histórico empilhado por dt_referencia; o app usa SÓ a data mais recente)
    resultados/totais.parquet                (total de turmas ativas)

Todos os números, gráficos e o detalhamento vêm da dt_referencia mais recente do resumo.parquet,
inclusive a lista de professores do top 10 (antes vinha de professores_excedentes.parquet, que é
sobrescrito a cada execução e podia divergir do resumo ao reprocessar uma data antiga).
"""

import base64
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ── Paleta SEDU (mesma do app_frequencia) ────────────────────────────────────
TEAL_DARK  = "#1a6b7a"
TEAL       = "#1e8fa5"
TEAL_MID   = "#2aabc4"
TEAL_LIGHT = "#c8eaf0"
TEAL_PALE  = "#eaf6f9"
YELLOW       = "#EAB308"
YELLOW_DARK  = "#A16207"
YELLOW_MID   = "#FACC15"
YELLOW_PALE  = "#FEF9C3"
MUTED      = "#718096"
TEXT       = "#2d3748"
PRIO_HIGH    = "#e05a6d"
PRIO_HIGH_BG = "#fdeef0"
PRIO_MED     = "#9f9f1a"
PRIO_MED_BG  = "#e6f4f8"
PRIO_LOW     = "#1D9E75"
PRIO_LOW_BG  = "#e3f5ee"

# ── Ícones por tipo de alerta de turma ────────────────────────────────────────
ALERTA_ICON_TURMA = {
    "Número total de Turmas": "👩‍🏫",
}

# ── Metadados dos alertas (chave = nome no parquet -> (rótulo, prioridade)) ──
# Nome tem que bater com o NOME do módulo em validacoes/. Prioridade: "alta" | "média" | "baixa".
ALERTA_META_TURMA = {
    "Número total de Turmas": ("Número total de Turmas", "média"),
}

# ── CSS (classes .freq-* mantidas de propósito: mesmo visual do painel de frequência) ──
CSS = f"""
<style>
  .block-container {{ padding-top: 1.25rem !important; padding-left: 3rem !important; padding-right: 3rem !important; max-width: 100% !important; }}
  section[data-testid="stSidebar"] {{ display: none; }}
  header[data-testid="stHeader"]   {{ display: none; }}
  footer {{ display: none; }}

  /* Header — verde, igual ao painel de frequência */
  .freq-header {{
    background: {YELLOW_DARK};
    padding: 14px 22px;
    display: flex; align-items: center; justify-content: space-between;
    min-height: 60px; border-radius: 10px;
  }}
  .freq-header-left {{ display: flex; align-items: center; gap: 14px; }}
  .freq-header-divider {{ width: 1px; height: 32px; background: rgba(255,255,255,0.25); }}
  .freq-header-title {{ font-size: 18px; font-weight: 600; color: #fff; margin: 0; }}
  .freq-header-sub   {{ font-size: 11px; color: rgba(255,255,255,0.6); margin: 2px 0 0 0; }}
  .freq-badge {{
    font-size: 11px; color: rgba(255,255,255,0.75);
    background: rgba(255,255,255,0.12); border-radius: 20px;
    padding: 4px 12px; display: flex; align-items: center; gap: 6px;
  }}
  .freq-dot {{ width: 7px; height: 7px; border-radius: 50%; background: #5DCAA5; display: inline-block; }}

  /* Banner */
  .freq-banner {{
    background: linear-gradient(135deg, {YELLOW_DARK} 0%, {YELLOW} 100%);
    padding: 16px 22px; display: flex; align-items: center; gap: 14px; border-radius: 10px;
  }}
  .freq-banner-num   {{ font-size: 26px !important; font-weight: 600 !important; color: #fff !important; margin: 0 !important; line-height: 1.1 !important; }}
  .freq-banner-label {{ font-size: 11px !important; color: rgba(255,255,255,0.8) !important; margin: 2px 0 0 0 !important; }}
  .freq-banner-chips {{ margin-left: auto; display: flex; gap: 10px; align-items: center; }}
  .freq-chip {{
    display: flex; flex-direction: column; align-items: center;
    background: rgba(255,255,255,0.14); border-radius: 10px; padding: 7px 16px; min-width: 78px;
  }}
  .freq-chip-num   {{ font-size: 17px; font-weight: 700; color: #fff; line-height: 1.1; }}
  .freq-chip-label {{ font-size: 9px; letter-spacing: 0.05em; text-transform: uppercase; color: rgba(255,255,255,0.75); margin-top: 2px; }}
  .freq-chip-dot   {{ display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 4px; vertical-align: middle; }}

  /* Corpo */
  .freq-body {{ padding: 1.25rem 0 2rem; }}
  .freq-section-title {{
    font-size: 10px; font-weight: 600; letter-spacing: 0.07em; color: {YELLOW_DARK};
    text-transform: uppercase; margin: 1.25rem 0 0.75rem 0;
    padding-bottom: 6px; border-bottom: 2px solid #f9e79f;
  }}

  /* Cards */
  .freq-cards-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 12px; margin-top: 0.25rem; }}
  .freq-card {{
    position: relative; background: #fff; border: 0.5px solid #b2e5d0;
    border-radius: 10px; border-top: 3px solid {YELLOW};
    padding: 12px 14px 14px; overflow: hidden; cursor: default;
    transition: transform .16s ease, box-shadow .16s ease;
  }}
  .freq-card::after {{
    content: ""; position: absolute; right: -28px; bottom: -28px;
    width: 78px; height: 78px; border-radius: 50%; background: {YELLOW_PALE}; opacity: .55;
  }}
  .freq-card:hover {{ transform: translateY(-3px); box-shadow: 0 8px 22px rgba(15,110,86,0.16); }}
  .freq-card.warn {{ border-top-color: {PRIO_HIGH}; }}
  .freq-card.warn::after {{ background: {PRIO_HIGH_BG}; }}
  .freq-card.ok   {{ border-top-color: {PRIO_LOW}; }}
  .freq-card.ok::after {{ background: {PRIO_LOW_BG}; }}
  .freq-card-top {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; position: relative; z-index: 1; }}
  .freq-card-icon  {{ font-size: 16px; line-height: 1; flex-shrink: 0; }}
  .freq-card-badge {{ font-size: 9px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; padding: 2px 7px; border-radius: 20px; white-space: nowrap; }}
  .freq-card-badge.high {{ background: {PRIO_HIGH_BG}; color: {PRIO_HIGH}; }}
  .freq-card-badge.med  {{ background: {PRIO_MED_BG};  color: {PRIO_MED}; }}
  .freq-card-badge.low  {{ background: {PRIO_LOW_BG};  color: {PRIO_LOW}; }}
  .freq-card-label {{
    position: relative; z-index: 1; font-size: 11px; color: {MUTED};
    margin: 8px 0 4px 0; line-height: 1.3;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    overflow: hidden; min-height: 2.6em;
  }}
  .freq-card-value {{ position: relative; z-index: 1; font-size: 26px; font-weight: 700; color: {YELLOW_DARK}; margin: 0; line-height: 1.1; }}
  .freq-card-value.warn {{ color: {PRIO_HIGH}; }}

  /* Placeholder */
  .freq-placeholder {{
    background: linear-gradient(135deg, {YELLOW_DARK}12 0%, {YELLOW}08 100%);
    border: 1.5px dashed {YELLOW}; border-radius: 12px;
    padding: 40px 32px; text-align: center; color: {YELLOW_DARK}; margin: 16px 0;
  }}
  .freq-placeholder h2 {{ font-size: 20px; margin: 0 0 10px; font-weight: 700; }}
  .freq-placeholder p  {{ font-size: 13px; color: {MUTED}; margin: 0; line-height: 1.6; }}

  /* Pill */
  .pill {{ font-size: 10px; padding: 2px 8px; border-radius: 20px; font-weight: 600; margin-left: 6px; vertical-align: middle; }}
  .pill.high {{ background: {PRIO_HIGH_BG}; color: {PRIO_HIGH}; }}
  .pill.med  {{ background: {PRIO_MED_BG};  color: {PRIO_MED}; }}
  .pill.low  {{ background: {PRIO_LOW_BG};  color: {PRIO_LOW}; }}

  div[data-testid="stPlotlyChart"] {{
    background: #fff;
    border-radius: 14px;
    padding: 0px;
  }}
</style>
"""

# ── Helpers ───────────────────────────────────────────────────────────────────
fmt  = lambda v: f"{v:,}".replace(",", ".")
_BASE = Path(__file__).resolve().parent
_RESULTADOS = _BASE / "resultados"


def _get_logo() -> str:
    p = _BASE / "logo.png"
    if not p.exists():
        return ""
    with open(p, "rb") as f:
        return base64.b64encode(f.read()).decode()


# ── Carregamento de dados ─────────────────────────────────────────────────────
DT_COL = "dt_referencia"


@st.cache_data(ttl=300)
def _ler_resumo_atual():
    """
    Lê o resumo.parquet (histórico empilhado) e devolve SÓ a dt_referencia mais recente.
    Retorna (DataFrame, dt_referencia | None).
    Se o arquivo ainda está no formato antigo (sem dt_referencia, ou todas nulas),
    devolve tudo como está e dt_referencia = None.
    """
    caminho = _RESULTADOS / "resumo.parquet"
    if not caminho.exists():
        return pd.DataFrame(), None

    df = pd.read_parquet(caminho)
    df.columns = df.columns.str.strip()
    if DT_COL not in df.columns or df.empty:
        return df, None

    dts = pd.to_datetime(df[DT_COL], errors="coerce")
    ultima = dts.max()
    if pd.isna(ultima):
        return df, None

    return df[dts == ultima].reset_index(drop=True), ultima.date()


@st.cache_data(ttl=300)
def _carregar_resumo_turma():
    """Agrega o resumo.parquet por tipo de alerta (turmas distintas afetadas)."""
    vazio = pd.DataFrame(columns=["alerta", "qtd", "pct", "prioridade"])
    caminho = _RESULTADOS / "resumo.parquet"
    if not caminho.exists():
        return vazio

    df_raw, _ = _ler_resumo_atual()
    if df_raw.empty or "alerta" not in df_raw.columns:
        return vazio

    chave = df_raw["alerta"].astype(str).str.strip()

    # nao_mapeados = set(chave.unique()) - set(ALERTA_META_TURMA.keys())
    # if nao_mapeados:
    #     st.warning(f"Alertas sem mapeamento em ALERTA_META_TURMA: {nao_mapeados}")

    df_raw["prioridade"] = chave.map(lambda x: ALERTA_META_TURMA.get(x, (x, "baixa"))[1])
    df_raw["alerta"]     = chave.map(lambda x: ALERTA_META_TURMA.get(x, (x, "baixa"))[0])

    df_agg = (
        df_raw.groupby(["alerta", "prioridade"], as_index=False)
        .agg(qtd=("id_turma", "nunique"))
    )

    total_qtd = df_agg["qtd"].sum()
    df_agg["pct"] = (df_agg["qtd"] / total_qtd * 100).round(1) if total_qtd > 0 else 0.0

    return df_agg[["alerta", "qtd", "pct", "prioridade"]].sort_values("qtd", ascending=False).reset_index(drop=True)


@st.cache_data(ttl=300)
def _carregar_resultados_turma():
    """
    Lê o mesmo parquet (linha a linha) usado para o detalhamento.
    Mapeia 'alerta' para o rótulo amigável e deriva 'prioridade' (para as pills),
    de forma consistente com os cards de visão geral.
    """
    caminho = _RESULTADOS / "resumo.parquet"
    if not caminho.exists():
        return pd.DataFrame()

    df, _ = _ler_resumo_atual()
    if df.empty:
        return pd.DataFrame()

    if "alerta" in df.columns:
        chave = df["alerta"].astype(str).str.strip()
        df["prioridade"] = chave.map(lambda x: ALERTA_META_TURMA.get(x, (x, "baixa"))[1])
        df["alerta"]     = chave.map(lambda x: ALERTA_META_TURMA.get(x, (x, "baixa"))[0])
    else:
        df["prioridade"] = "baixa"

    return df


@st.cache_data(show_spinner=False, ttl=36000)
def _carregar_total_turmas():
    """
    Total de turmas ativas (gerado pelo processar.py em totais.parquet).
    Não é mais usado no gráfico de categorias (substituído pelo top 10 de disciplinas).
    """
    caminho = _RESULTADOS / "totais.parquet"
    if not caminho.exists():
        return None
    df = pd.read_parquet(caminho)
    if "total_turmas_ativas" in df.columns and len(df):
        return int(df["total_turmas_ativas"].iloc[0])
    return None


@st.cache_data(ttl=300)
def _carregar_excedentes_regional():
    """Professores excedentes e turmas afetadas por regional (a partir do resumo.parquet)."""
    colunas = ["nm_regional", "id_turma", "eh_excedente"]
    caminho = _RESULTADOS / "resumo.parquet"
    vazio = pd.DataFrame(columns=["regional", "excedentes", "turmas"])
    if not caminho.exists():
        return vazio

    df, _ = _ler_resumo_atual()
    if df.empty or any(c not in df.columns for c in colunas):
        return vazio

    df["nm_regional"] = df["nm_regional"].fillna("Sem regional")
    out = (
        df.groupby("nm_regional", as_index=False)
        .agg(excedentes=("eh_excedente", "sum"), turmas=("id_turma", "nunique"))
        .rename(columns={"nm_regional": "regional"})
        .sort_values("excedentes", ascending=False)
        .reset_index(drop=True)
    )
    return out


@st.cache_data(ttl=300)
def _carregar_professores():
    """Um registro por professor enturmado, da dt_referencia mais recente do resumo.parquet."""
    colunas = ["id_turma", "disciplina", "cpf_docente", "eh_excedente"]
    df, _ = _ler_resumo_atual()
    if df.empty or any(c not in df.columns for c in colunas):
        return pd.DataFrame(columns=colunas)
    if "script" in df.columns:
        df = df[df["script"] == "professores_excedentes"]
    return df[colunas].reset_index(drop=True)


# ── render() ─────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def _carregar_historico():
    """
    Série temporal por dt_referencia (TODAS as datas do resumo.parquet, não só a mais recente):
      - excedentes = soma de eh_excedente
      - turmas     = id_turma distintos
    """
    vazio = pd.DataFrame(columns=[DT_COL, "excedentes", "turmas"])
    caminho = _RESULTADOS / "resumo.parquet"
    if not caminho.exists():
        return vazio

    df = pd.read_parquet(caminho)
    df.columns = df.columns.str.strip()
    if any(c not in df.columns for c in (DT_COL, "eh_excedente", "id_turma")):
        return vazio

    df[DT_COL] = pd.to_datetime(df[DT_COL], errors="coerce")
    df = df.dropna(subset=[DT_COL])
    if df.empty:
        return vazio

    return (
        df.groupby(DT_COL, as_index=False)
        .agg(excedentes=("eh_excedente", "sum"), turmas=("id_turma", "nunique"))
        .sort_values(DT_COL)
        .reset_index(drop=True)
    )


def render():
    st.markdown(CSS, unsafe_allow_html=True)

    df       = _carregar_resumo_turma()
    total    = int(df["qtd"].sum()) if not df.empty else 0
    logo_b64 = _get_logo()

    _qtd_prio = df.groupby("prioridade")["qtd"].sum() if not df.empty else {}
    qtd_alta  = int(_qtd_prio.get("alta",  0))
    qtd_media = int(_qtd_prio.get("média", 0))
    qtd_baixa = int(_qtd_prio.get("baixa", 0))

    _, dt_ref_base = _ler_resumo_atual()
    rotulo_base = (
        f"Base de {dt_ref_base:%d/%m/%Y}" if dt_ref_base
        else datetime.now().strftime("%d/%m/%Y · %H:%M")
    )

    logo_img = (
        f'<img src="data:image/png;base64,{logo_b64}" '
        f'style="width:130px;height:70px;object-fit:contain;" alt="SEDU"/>'
        if logo_b64 else ""
    )

    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown(f"""
    <div class="freq-header">
      <div class="freq-header-left">
        {logo_img}
        <div class="freq-header-divider"></div>
        <div>
          <p class="freq-header-title">Saúde da Base de Turmas — SEDU</p>
          <p class="freq-header-sub">Secretaria da Educação · ES</p>
        </div>
      </div>
      <div class="freq-badge">
        <span class="freq-dot"></span>
        {rotulo_base}
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Banner ────────────────────────────────────────────────────────────────
    total_str = fmt(total) if total > 0 else "—"
    st.markdown(f"""
    <div class="freq-banner">
      <div style="font-size:22px; color:rgba(255,255,255,0.85);">🏫</div>
      <div>
        <div class="freq-banner-num">{total_str}</div>
        <div class="freq-banner-label">turmas com alerta nesta atualização</div>
      </div>
      <div class="freq-banner-chips">
        <div class="freq-chip">
          <span class="freq-chip-num"><span class="freq-chip-dot" style="background:{PRIO_HIGH};"></span>{fmt(qtd_alta) if total > 0 else "—"}</span>
          <span class="freq-chip-label">Alta</span>
        </div>
        <div class="freq-chip">
          <span class="freq-chip-num"><span class="freq-chip-dot" style="background:#bdeaf2;"></span>{fmt(qtd_media) if total > 0 else "—"}</span>
          <span class="freq-chip-label">Média</span>
        </div>
        <div class="freq-chip">
          <span class="freq-chip-num"><span class="freq-chip-dot" style="background:#8fe3c4;"></span>{fmt(qtd_baixa) if total > 0 else "—"}</span>
          <span class="freq-chip-label">Baixa</span>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="freq-body">', unsafe_allow_html=True)

    # ── Dados reais (quando existirem) ou placeholder ─────────────────────────
    if not df.empty:
        # ── Cards ─────────────────────────────────────────────────────────────
        st.markdown('<p class="freq-section-title">visão geral</p>', unsafe_allow_html=True)

        CARD_CLS  = {"alta": "warn", "média": "", "baixa": "ok"}
        VAL_CLS   = {"alta": "warn", "média": "", "baixa": ""}
        BADGE_CLS = {"alta": "high", "média": "med", "baixa": "low"}
        BADGE_TXT = {"alta": "Alta", "média": "Média", "baixa": "Baixa"}

        cards_html = ['<div class="freq-cards-grid">']
        for row in df.itertuples():
            ccls = CARD_CLS[row.prioridade]
            vcls = VAL_CLS[row.prioridade]
            bcls = BADGE_CLS[row.prioridade]
            btxt = BADGE_TXT[row.prioridade]
            icon = ALERTA_ICON_TURMA.get(row.alerta, "•")
            cards_html.append(
                f'<div class="freq-card {ccls}">'
                f'<div class="freq-card-top">'
                f'<span class="freq-card-icon">{icon}</span>'
                f'<span class="freq-card-badge {bcls}">{btxt}</span>'
                f'</div>'
                f'<p class="freq-card-label" title="{row.alerta}">{row.alerta}</p>'
                f'<p class="freq-card-value {vcls}">{fmt(row.qtd)}</p>'
                f'</div>'
            )
        cards_html.append('</div>')
        st.markdown("".join(cards_html), unsafe_allow_html=True)

        # ── Evolução por dt_referencia (linhas com ponto) ─────────────────────
        st.markdown('<p class="freq-section-title" style="margin-top:1.5rem;">evolução por data de referência</p>', unsafe_allow_html=True)

        df_hist = _carregar_historico()
        if df_hist.empty:
            st.info("Sem histórico disponível para o gráfico de evolução.")
        else:
            xs = df_hist[DT_COL].dt.strftime("%d/%m/%Y")
            # Dois gráficos independentes (um eixo Y cada): eixo duplo fazia as linhas
            # parecerem correlacionadas só por causa da escala de cada eixo.
            col_exc, col_tur = st.columns(2)
            series_hist = [
                (col_exc, "Professores excedentes", df_hist["excedentes"], PRIO_HIGH, "hist_exc"),
                (col_tur, "Turmas com alerta",      df_hist["turmas"],     TEAL,      "hist_tur"),
            ]
            for col, nome, ys, cor, chave in series_hist:
                fig_h = go.Figure(go.Scatter(
                    x=xs, y=ys, mode="lines+markers+text",
                    line=dict(color=cor, width=3), marker=dict(size=9, color=cor),
                    text=[fmt(int(v)) for v in ys],
                    textposition="top center", textfont=dict(size=12, color=cor),
                    hovertemplate=f"<b>%{{x}}</b><br>%{{y:,}} {nome.lower()}<extra></extra>",
                ))
                ymax = float(ys.max()) if len(ys) else 0
                fig_h.update_layout(
                    height=300, margin=dict(l=10, r=20, t=10, b=10),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(family="sans-serif", size=12, color=MUTED),
                    xaxis=dict(type="category", showgrid=False, tickfont=dict(color=TEXT, size=12)),
                    yaxis=dict(gridcolor="#f0f4f5", zeroline=False,
                               range=[0, ymax * 1.18 if ymax > 0 else 1],
                               tickfont=dict(color=TEXT, size=12)),
                    showlegend=False,
                )
                with col:
                    st.markdown(
                        f'<p style="font-size:12px;font-weight:600;color:{cor};margin:0 0 4px;">{nome}</p>',
                        unsafe_allow_html=True,
                    )
                    st.plotly_chart(fig_h, use_container_width=True,
                                    config={"displayModeBar": False}, key=chave)

        # ── Top 10 disciplinas com mais professores excedentes ────────────────
        st.markdown('<p class="freq-section-title" style="margin-top:1.5rem;">top 10 disciplinas com mais professores excedentes</p>', unsafe_allow_html=True)

        df_prof = _carregar_professores()
        # Só excedentes (eh_excedente = 1)
        df_prof = df_prof[df_prof["eh_excedente"] == 1]

        if df_prof.empty:
            st.info("Sem dados de professores excedentes disponíveis para o gráfico.")
        else:
            c1, c2 = st.columns(2)
            sel_turma = c1.multiselect("id_turma", sorted(df_prof["id_turma"].dropna().unique()), key="top10_turma")
            sel_disc  = c2.multiselect("disciplina", sorted(df_prof["disciplina"].dropna().unique()), key="top10_disc")

            if sel_turma:
                df_prof = df_prof[df_prof["id_turma"].isin(sel_turma)]
            if sel_disc:
                df_prof = df_prof[df_prof["disciplina"].isin(sel_disc)]

            # Conta enturmações excedentes (professor x turma x disciplina), não CPFs distintos:
            # o mesmo professor excedente em várias turmas conta uma vez por turma.
            top10 = (
                df_prof.drop_duplicates(["id_turma", "disciplina", "cpf_docente"])
                .groupby("disciplina").size()
                .nlargest(10)
                .reset_index(name="qtd")
            )

            if top10.empty:
                st.info("Nenhum professor excedente para os filtros selecionados.")
            else:
                fig_bar = go.Figure(go.Bar(
                    x=top10["qtd"], y=top10["disciplina"], orientation="h",
                    marker=dict(color=PRIO_LOW, line=dict(width=0), cornerradius=4),
                    text=[fmt(int(v)) for v in top10["qtd"]],
                    textposition="outside", textfont=dict(size=12, color=TEXT),
                    hovertemplate="<b>%{y}</b><br>%{x:,} professores excedentes (enturmações)<extra></extra>",
                ))
                fig_bar.update_layout(
                    height=max(140, 40 * len(top10) + 40), margin=dict(l=0, r=80, t=10, b=10),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(family="sans-serif", size=12, color=MUTED),
                    xaxis=dict(gridcolor="#f0f4f5", showline=False, zeroline=False,
                               tickfont=dict(color=TEXT, size=12)),
                    yaxis=dict(autorange="reversed", showgrid=False, showline=False,
                               tickfont=dict(color=TEXT, size=13)),
                    showlegend=False,
                )
                st.plotly_chart(fig_bar, use_container_width=True, config={"displayModeBar": False})

        # ── Gráfico: professores excedentes por regional ─────────────────────────
        st.markdown('<p class="freq-section-title" style="margin-top:1.5rem;">professores excedentes por regional</p>', unsafe_allow_html=True)

        df_reg = _carregar_excedentes_regional()
        if not df_reg.empty:
            fig_reg = go.Figure(go.Bar(
                x=df_reg["excedentes"], y=df_reg["regional"], orientation="h",
                marker=dict(color=PRIO_HIGH, line=dict(width=0), cornerradius=4),
                text=[fmt(int(v)) for v in df_reg["excedentes"]],
                textposition="outside", textfont=dict(size=12, color=TEXT),
                customdata=df_reg["turmas"],
                hovertemplate="<b>%{y}</b><br>%{x:,} professores excedentes · "
                              "%{customdata:,} turmas afetadas<extra></extra>",
            ))
            fig_reg.update_layout(
                height=max(200, 36 * len(df_reg) + 40), margin=dict(l=0, r=80, t=10, b=10),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(family="sans-serif", size=12, color=MUTED),
                xaxis=dict(gridcolor="#f0f4f5", showline=False, zeroline=False,
                           tickfont=dict(color=TEXT, size=12)),
                yaxis=dict(autorange="reversed", showgrid=False, showline=False,
                           tickfont=dict(color=TEXT, size=13)),
                showlegend=False,
            )
            st.plotly_chart(fig_reg, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("Sem dados de professores excedentes por regional disponíveis para o gráfico.")



        
    else:
        # Placeholder visual enquanto o pipeline não gerou resultados
        st.markdown(f"""
        <div class="freq-placeholder">
          <h2>🏫 Saúde da Base de Turmas</h2>
          <p>
            Sem resultados para exibir.<br><br>
            Rode <code>python processar.py</code> para gerar o
            <b>resultados/resumo.parquet</b> deste painel.
          </p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<p class="freq-section-title" style="margin-top:1rem;">tipos de alerta previstos</p>', unsafe_allow_html=True)

        previstos = [
            (ALERTA_ICON_TURMA[nome], rotulo, prio)
            for nome, (rotulo, prio) in ALERTA_META_TURMA.items()
        ]
        BADGE_CLS = {"alta": "high", "média": "med", "baixa": "low"}
        BADGE_TXT = {"alta": "Alta", "média": "Média", "baixa": "Baixa"}
        CARD_CLS  = {"alta": "warn", "média": "", "baixa": "ok"}

        cards_prev = ['<div class="freq-cards-grid">']
        for icon, label, prio in previstos:
            cards_prev.append(
                f'<div class="freq-card {CARD_CLS[prio]}" style="opacity:0.5;">'
                f'<div class="freq-card-top">'
                f'<span class="freq-card-icon">{icon}</span>'
                f'<span class="freq-card-badge {BADGE_CLS[prio]}">{BADGE_TXT[prio]}</span>'
                f'</div>'
                f'<p class="freq-card-label">{label}</p>'
                f'<p class="freq-card-value" style="color:{MUTED};font-size:18px;">em breve</p>'
                f'</div>'
            )
        cards_prev.append('</div>')
        st.markdown("".join(cards_prev), unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)  # fecha freq-body


# ── Popup de erro ─────────────────────────────────────────────────────────────
CAMINHO_ERRO_PNG = Path(__file__).parent / "erro.png"

@st.dialog("Erro no painel")
def mostrar_erro(mensagem):
    if CAMINHO_ERRO_PNG.exists():
        st.image(str(CAMINHO_ERRO_PNG), use_container_width=True)
    st.error("Ocorreu um erro ao carregar o painel.")
    with st.expander("Detalhes técnicos"):
        st.code(mensagem)
    if st.button("Fechar"):
        st.rerun()

# ── Execução standalone ───────────────────────────────────────────────────────
if __name__ == "__main__" or not hasattr(st, "_is_running_with_vitrine"):
    st.set_page_config(
        page_title="Saúde da Base de Turmas — SEDU",
        page_icon="🏫",
        layout="wide",
    )
    try:
        render()
    except Exception as e:
        mostrar_erro(str(e))
