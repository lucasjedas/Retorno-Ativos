"""Retorno acumulado de ativos — versão web (feita para usar no celular).

Rodar localmente:   .venv/bin/streamlit run app.py
Fonte dos dados:    Yahoo Finance.
"""

from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from financeiro import (
    SIMBOLO_MOEDA,
    buscar_historico,
    calcular,
    data_br,
    dinheiro,
    pct,
)
from tickers import normalizar, sugerir

st.set_page_config(
    page_title="Retorno de Ativos",
    page_icon="📈",
    layout="centered",
    initial_sidebar_state="collapsed",
)

VERDE = "#3A9E6E"   # ganho
VERMELHO = "#C9483B"  # perda

def _hoje_no_brasil() -> date:
    """Data de hoje em Brasília.

    O servidor do Streamlit Cloud roda em UTC: depois das 21h daqui, um
    date.today() cru já virou o dia seguinte e o app oferecia uma data
    'de hoje' que ainda não teve pregão.
    """
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    except Exception:
        return date.today()


PERIODOS = {
    "1 ano": 365,
    "3 anos": 365 * 3,
    "5 anos": 365 * 5,
    "10 anos": 365 * 10,
}


class SemDados(Exception):
    """Nenhum candidato devolveu histórico. Carrega o porquê de cada tentativa."""

    def __init__(self, motivos):
        super().__init__("sem dados")
        self.motivos = motivos


@st.cache_data(ttl=1800, show_spinner=False)
def buscar(entrada: str, inicio: date, fim: date):
    """Mesma busca do programa de terminal, com cache de 30 minutos.

    A falha sai como exceção de propósito: o cache do Streamlit não guarda
    chamadas que levantam erro, e uma recusa passageira do Yahoo não deve
    ficar 30 minutos grudada na tela.
    """
    motivos = []
    simbolo, df, moeda, nome = buscar_historico(
        entrada, datetime.combine(inicio, datetime.min.time()),
        datetime.combine(fim, datetime.min.time()),
        diagnostico=motivos,
    )
    if df is None:
        raise SemDados(motivos)
    return simbolo, df, moeda, nome


# --------------------------------------------------------------------------
# Entrada
# --------------------------------------------------------------------------
st.title("📈 Retorno acumulado")
st.caption("Ações, ETFs, FIIs, BDRs, índices (BR/EUA), câmbio e cripto · dados do Yahoo Finance")

hoje = _hoje_no_brasil()
st.session_state.setdefault("data_inicio", hoje - timedelta(days=365))
st.session_state.setdefault("data_fim", hoje)

ativo = st.text_input(
    "Ativo",
    value="PETR4",
    placeholder="PETR4, BOVA11, IBOV, AAPL, SPY, HGLG11, BTC...",
).strip()

atalho = st.segmented_control(
    "Período rápido", list(PERIODOS) + ["No ano"], default=None, key="atalho"
)
if atalho:
    st.session_state["data_fim"] = hoje
    st.session_state["data_inicio"] = (
        date(hoje.year, 1, 1) if atalho == "No ano"
        else hoje - timedelta(days=PERIODOS[atalho])
    )

col_ini, col_fim = st.columns(2)
inicio = col_ini.date_input(
    "Início", key="data_inicio", format="DD/MM/YYYY",
    min_value=date(1960, 1, 1), max_value=hoje,
)
fim = col_fim.date_input(
    "Fim", key="data_fim", format="DD/MM/YYYY",
    min_value=date(1960, 1, 1), max_value=hoje,
)

calcular_agora = st.button("Calcular", type="primary", width="stretch")

# --------------------------------------------------------------------------
# Resultado
# --------------------------------------------------------------------------
if calcular_agora or st.session_state.get("ja_calculou"):
    st.session_state["ja_calculou"] = True

    if not ativo:
        st.warning("Digite o código de um ativo.")
        st.stop()
    if inicio >= fim:
        st.warning("A data de início precisa ser anterior à data de fim.")
        st.stop()

    try:
        with st.spinner(f"Buscando {normalizar(ativo)}..."):
            simbolo, df, moeda, nome = buscar(ativo, inicio, fim)
    except SemDados as falha:
        st.error(f"Não encontrei dados para **{normalizar(ativo)}** nesse período.")
        dica = sugerir(ativo)
        if dica:
            st.info(f"Você quis dizer: {dica}?")
        st.caption("Exemplos: PETR4, BOVA11, IBOV, AAPL, SPY, SP500, HGLG11, BTC")
        if st.button("Tentar de novo"):
            st.rerun()
        with st.expander("Detalhes técnicos"):
            st.caption(
                "Se aparecer 'Too Many Requests' ou 'rate limit', é o Yahoo "
                "recusando pedidos vindos do servidor — costuma passar em alguns "
                "minutos. O app já tenta 3 vezes antes de desistir."
            )
            st.code("\n".join(falha.motivos) or "sem detalhes", language="text")
        st.stop()

    m = calcular(df)
    cifra = SIMBOLO_MOEDA.get(moeda, moeda)
    ganhou = m["retorno_total"] >= 0

    st.divider()
    st.subheader(nome)
    st.caption(
        f"{simbolo} · {data_br(m['data_ini'])} → {data_br(m['data_fim'])} · "
        f"{m['pregoes']} pregões"
    )

    a, b, c = st.columns(3)
    a.metric("Retorno acumulado", pct(m["retorno_total"]))
    b.metric("Anualizado", pct(m["anualizado"]) + " a.a." if m["anualizado"] is not None else "—")
    c.metric("Queda máxima", pct(m["drawdown"]))

    st.markdown(
        f"**{dinheiro(1000, cifra)}** investidos no início virariam "
        f"**{dinheiro(1000 * (1 + m['retorno_total']), cifra)}** no fim."
    )

    # Curva do retorno acumulado — uma série só, por isso dispensa legenda.
    # O fuso sai da própria série: passar um 'index=' diferente do índice dela
    # faria o pandas realinhar pelos rótulos e devolver a coluna toda em NaN.
    serie = m["serie"]
    if serie.index.tz is not None:
        serie = serie.tz_localize(None)
    curva = pd.DataFrame({"Retorno acumulado (%)": (serie / serie.iloc[0] - 1) * 100})
    st.area_chart(
        curva,
        y="Retorno acumulado (%)",
        color=VERDE if ganhou else VERMELHO,
        height=260,
    )

    if m["tem_proventos"]:
        st.info(
            f"O retorno acima considera **proventos reinvestidos**. "
            f"Só a variação de preço foi de {pct(m['retorno_preco'])}."
        )

    with st.expander("Mais detalhes"):
        linhas = [
            ("Preço inicial", dinheiro(m["preco_ini"], cifra)),
            ("Preço final", dinheiro(m["preco_fim"], cifra)),
            ("Máxima no período", dinheiro(m["maxima"], cifra)),
            ("Mínima no período", dinheiro(m["minima"], cifra)),
        ]
        if m["volatilidade"] is not None:
            linhas.append(("Volatilidade anual", pct(m["volatilidade"], sinal=False)))
        if m["melhor_dia"]:
            linhas.append(("Melhor dia", f"{pct(m['melhor_dia'][1])} em {data_br(m['melhor_dia'][0])}"))
        if m["pior_dia"]:
            linhas.append(("Pior dia", f"{pct(m['pior_dia'][1])} em {data_br(m['pior_dia'][0])}"))

        st.dataframe(
            pd.DataFrame(linhas, columns=["Indicador", "Valor"]),
            hide_index=True,
            width="stretch",
        )

        st.download_button(
            "Baixar histórico (CSV)",
            df.to_csv().encode("utf-8"),
            file_name=f"{simbolo}_{inicio:%Y%m%d}_{fim:%Y%m%d}.csv",
            mime="text/csv",
            width="stretch",
        )

    st.caption(
        "Fonte: Yahoo Finance. Ativos em moeda estrangeira têm o retorno "
        "calculado na moeda de origem, sem a variação cambial."
    )
