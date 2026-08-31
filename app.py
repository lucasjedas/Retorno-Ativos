"""Retorno acumulado de ativos — versão web (feita para usar no celular).

Rodar localmente:   .venv/bin/streamlit run app.py
Fonte dos dados:    Yahoo Finance.
"""

import traceback
from datetime import date, datetime, timedelta

import altair as alt
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
from indices import BENCHMARKS, curva as curva_indice, fator as fator_indice
from tickers import normalizar, sugerir

st.set_page_config(
    page_title="Retorno de Ativos",
    page_icon="📈",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# --------------------------------------------------------------------------
# Navegação
# --------------------------------------------------------------------------
# Duas telas no mesmo script, escolhidas por session_state em vez da pasta
# pages/ do Streamlit: a pasta abre barra lateral, e este app é feito para o
# celular. A página de opções é importada só quando é a vez dela — ela puxa
# arquivos grandes da B3 e não tem por que carregar quem só quer o retorno.
st.session_state.setdefault("pagina", "retorno")

if st.session_state["pagina"] == "opcoes":
    import pagina_opcoes

    pagina_opcoes.render()
    st.stop()

# Suba este número sempre que o formato devolvido pelas funções em cache
# mudar. Ele entra na chave, e é o que impede o Streamlit de servir, depois
# de um deploy, um resultado gravado no formato anterior — o corpo da função
# em cache pode continuar idêntico enquanto o que ela devolve mudou.
FORMATO_CACHE = 4


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


def grafico_curvas(colunas: dict, cores: list):
    """Linhas do retorno acumulado, com leitura pelo mouse.

    O st.line_chart mostra no tooltip só a série mais próxima do cursor. Aqui
    uma régua vertical acompanha o mouse e o tooltip traz a data e o retorno
    de todas as linhas de uma vez — que é o que serve para comparar.

    Duas decisões que parecem rodeio e não são:

    1. O texto do tooltip sai pronto do pandas, uma coluna por série. O Vega
       formata número no padrão dos EUA e o Streamlit não deixa trocar o
       idioma dele; passando texto, sai "+10,96%" e não "0.109604671771".
    2. Quem carrega o tooltip é a camada invisível que captura o mouse, não a
       régua. Com 'nearest', o Vega divide o gráfico inteiro em faixas — uma
       por data — e é essa faixa que fica debaixo do cursor em qualquer ponto
       do gráfico. A régua tem 1px: só apareceria acertando o pixel dela.
    """
    nomes = list(colunas)
    largo = pd.DataFrame(colunas)
    largo.index.name = "Data"
    # Em fração, e não em pontos percentuais, para o eixo poder usar o formato
    # de porcentagem do Vega e sair "+25%" em vez de "25".
    longo = (largo / 100).reset_index().melt(
        id_vars="Data", var_name="Série", value_name="Retorno"
    )

    # Uma linha por data, com a data e cada série já escritas em português.
    rotulos = pd.DataFrame({"Data": largo.index})
    rotulos["Dia"] = [data_br(d) for d in largo.index]
    for nome in nomes:
        rotulos[nome] = [
            "—" if pd.isna(v) else pct(v / 100) for v in largo[nome]
        ]

    escala = alt.Scale(domain=nomes, range=cores)
    base = alt.Chart(longo).encode(x=alt.X("Data:T", title=None))

    # tooltip=None nas camadas de baixo: o tema do Streamlit liga o tooltip
    # automático do Vega, que mostrava o valor cru por cima do texto formatado.
    linhas = base.mark_line(strokeWidth=2).encode(
        y=alt.Y("Retorno:Q", title=None, axis=alt.Axis(format="+.0%")),
        color=alt.Color(
            "Série:N", scale=escala,
            legend=alt.Legend(orient="bottom", title=None),
        ),
        tooltip=alt.value(None),
    )

    # Ponto de referência: o mais próximo do cursor no eixo do tempo.
    perto = alt.selection_point(
        fields=["Data"], nearest=True, on="pointerover",
        clear="pointerout", empty=False,
    )

    marcas = linhas.mark_point(filled=True, size=70).encode(
        opacity=alt.condition(perto, alt.value(1), alt.value(0)),
        tooltip=alt.value(None),
    )

    regua = alt.Chart(rotulos).mark_rule(
        color="#9AA0A6", strokeWidth=1
    ).encode(
        x=alt.X("Data:T", title=None),
        opacity=alt.condition(perto, alt.value(0.7), alt.value(0)),
        tooltip=alt.value(None),
    )

    # Por último, para ficar por cima de todo o resto e receber o mouse antes
    # das outras camadas.
    sensor = alt.Chart(rotulos).mark_point().encode(
        x=alt.X("Data:T", title=None),
        opacity=alt.value(0),
        tooltip=[alt.Tooltip("Dia:N", title="Data")]
        + [alt.Tooltip(f"{nome}:N", title=nome) for nome in nomes],
    ).add_params(perto)

    return alt.layer(linhas, marcas, regua, sensor).properties(height=300)


def taxa(valor, sufixo):
    """Formata uma taxa equivalente; '—' quando o período é curto demais."""
    return f"{pct(valor)} {sufixo}" if valor is not None else "—"


def meses_br(meses: float) -> str:
    return "1 mês" if round(meses) == 1 else f"{meses:.1f} meses".replace(".", ",")


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
def buscar(entrada: str, inicio: date, fim: date, formato: int = FORMATO_CACHE):
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


@st.cache_data(ttl=1800, show_spinner=False)
def buscar_indice(nome: str, inicio: date, fim: date, formato: int = FORMATO_CACHE):
    """Série bruta do índice, guardada por 30 minutos.

    Sem isto, cada clique na tela refaria as quatro consultas de rede — o que
    é lento e ainda aumenta a chance de o Yahoo recusar o próximo pedido.
    """
    return fator_indice(nome, inicio, fim)


# --------------------------------------------------------------------------
# Entrada
# --------------------------------------------------------------------------
st.title("📈 Retorno acumulado")
st.caption("Ações, ETFs, FIIs, BDRs, índices (BR/EUA), câmbio e cripto · dados do Yahoo Finance")

if st.button("🎯 Opções", width="stretch"):
    st.session_state["pagina"] = "opcoes"
    st.rerun()

hoje = _hoje_no_brasil()
st.session_state.setdefault("data_inicio", hoje - timedelta(days=365))
st.session_state.setdefault("data_fim", hoje)

st.session_state.setdefault("ativo", "PETR4")
ativo = st.text_input(
    "Ativo",
    key="ativo",
    placeholder="PETR4, BOVA11, IBOV, AAPL, SPY, HGLG11, BTC...",
).strip()

def _soltar_atalho():
    """Mexer numa data na mão desmarca o período rápido.

    Sem isto o botão continuaria aceso mostrando um período que não é mais o
    que está nos campos.
    """
    st.session_state["atalho"] = None
    st.session_state["atalho_aplicado"] = None


st.segmented_control(
    "Período rápido", list(PERIODOS) + ["No ano"], key="atalho"
)
atalho = st.session_state.get("atalho")

# Aplicar só quando a escolha muda. Regravar a cada execução desfazia
# qualquer ajuste manual nas datas: bastava recalcular para o período voltar
# ao do botão que continuava selecionado.
if atalho and atalho != st.session_state.get("atalho_aplicado"):
    st.session_state["atalho_aplicado"] = atalho
    st.session_state["data_fim"] = hoje
    st.session_state["data_inicio"] = (
        date(hoje.year, 1, 1) if atalho == "No ano"
        else hoje - timedelta(days=PERIODOS[atalho])
    )

col_ini, col_fim = st.columns(2)
inicio = col_ini.date_input(
    "Início", key="data_inicio", format="DD/MM/YYYY",
    min_value=date(1960, 1, 1), max_value=hoje,
    on_change=_soltar_atalho,
)
fim = col_fim.date_input(
    "Fim", key="data_fim", format="DD/MM/YYYY",
    min_value=date(1960, 1, 1), max_value=hoje,
    on_change=_soltar_atalho,
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
            simbolo, df, moeda, nome = buscar(ativo, inicio, fim, FORMATO_CACHE)
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
        f"{m['pregoes']} {m['cadencia']}"
    )

    if m["tem_proventos"]:
        st.info(
            f"O retorno abaixo considera **proventos reinvestidos**. "
            f"Só a variação de preço foi de {pct(m['retorno_preco'])}."
        )

    a, b = st.columns(2)
    a.metric("Retorno acumulado", pct(m["retorno_total"]))
    b.metric("Queda máxima", pct(m["drawdown"]))

    c, d = st.columns(2)
    c.metric("Retorno médio mensal", taxa(m["mensal"], "a.m."))
    d.metric("Retorno médio anual", taxa(m["anualizado"], "a.a."))
    st.caption(
        f"Taxas equivalentes por juros compostos: aplicadas mês a mês "
        f"(ou ano a ano) ao longo dos {meses_br(m['meses'])} do período, "
        f"chegam ao mesmo retorno acumulado acima."
    )

    st.markdown(
        f"**{dinheiro(1000, cifra)}** investidos no início virariam "
        f"**{dinheiro(1000 * (1 + m['retorno_total']), cifra)}** no fim."
    )

    # Curva do retorno acumulado, com os índices escolhidos no mesmo eixo.
    # O fuso sai da própria série: passar um 'index=' diferente do índice dela
    # faria o pandas realinhar pelos rótulos e devolver a coluna toda em NaN.
    serie = m["serie"]
    if serie.index.tz is not None:
        serie = serie.tz_localize(None)

    # Caixas de marcar em cima do gráfico: ticar redesenha na hora, sobre o
    # mesmo período já calculado — a busca do ativo está em cache, então
    # marcar e desmarcar não refaz a consulta das cotações.
    st.caption("Comparar com")
    caixas = st.columns(len(BENCHMARKS))
    comparar = [
        nome
        for nome, coluna in zip(BENCHMARKS, caixas)
        if coluna.checkbox(nome, key=f"comparar_{nome}")
    ]

    rotulo_ativo = normalizar(ativo)
    colunas = {rotulo_ativo: (serie / serie.iloc[0] - 1) * 100}
    cores = [VERDE if ganhou else VERMELHO]
    avisos, falhas = [], []

    if comparar:
        with st.spinner("Buscando os índices..."):
            for nome in comparar:
                # Um índice que quebra não pode levar a página junto: o
                # resultado do ativo já está calculado e é o que o usuário
                # veio ver. A falha vira aviso, com o traceback à mão.
                try:
                    linha, recado = curva_indice(
                        nome, inicio, fim, serie.index,
                        bruto=buscar_indice(nome, inicio, fim, FORMATO_CACHE),
                    )
                except Exception as erro:
                    falhas.append(
                        (nome, f"{nome}: {type(erro).__name__}: {erro}\n"
                               f"{traceback.format_exc()}")
                    )
                    continue
                if linha is None:
                    falhas.append((nome, recado))
                    continue
                colunas[nome] = linha
                cores.append(BENCHMARKS[nome]["cor"])
                if recado:
                    avisos.append(recado)

    st.altair_chart(grafico_curvas(colunas, cores), use_container_width=True)
    st.caption(
        "Retorno acumulado em %, todos partindo de zero na data inicial. "
        "Passe o mouse sobre o gráfico para ver a data e o valor de cada linha."
    )

    if "S&P 500" in colunas and moeda == "BRL":
        avisos.append(
            "S&P 500 está em dólar e o ativo em real — a diferença entre as "
            "duas curvas não inclui a variação do câmbio no período."
        )

    for recado in avisos:
        st.caption(f"⚠️ {recado}")
    if falhas:
        st.warning(
            "Não consegui traçar: " + "; ".join(nome for nome, _ in falhas)
        )
        with st.expander("Por que o índice não apareceu"):
            st.code("\n".join(motivo for _, motivo in falhas), language="text")

    # Placar do período — só faz sentido quando há com quem comparar.
    if len(colunas) > 1:
        placar = pd.DataFrame(
            [
                {
                    "": nome,
                    "No período": pct(valores.iloc[-1] / 100),
                    "Diferença": (
                        "—" if nome == rotulo_ativo
                        else pct((colunas[rotulo_ativo].iloc[-1] - valores.iloc[-1]) / 100)
                    ),
                }
                for nome, valores in colunas.items()
            ]
        )
        st.dataframe(placar, hide_index=True, width="stretch")
        st.caption(
            f"“Diferença” é quanto **{rotulo_ativo}** rendeu a mais (ou a menos) "
            f"que o índice, em pontos percentuais."
        )

    with st.expander("Mais detalhes"):
        linhas = [
            ("Preço inicial", dinheiro(m["preco_ini"], cifra)),
            ("Preço final", dinheiro(m["preco_fim"], cifra)),
            ("Máxima no período", dinheiro(m["maxima"], cifra)),
            ("Mínima no período", dinheiro(m["minima"], cifra)),
        ]
        linhas.append(("Prazo do período", f"{meses_br(m['meses'])} ({m['anos']:.2f} anos)".replace(".", ",")))
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
