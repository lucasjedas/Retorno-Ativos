"""Página de opções de dólar do app web — Black-76 com dados da B3.

Vive separada do retorno acumulado: o `app.py` só chama `render()` quando o
botão "Opções" foi apertado. Nada aqui roda enquanto a outra página está na
tela, o que importa porque os arquivos da B3 são grandes.

**O que muda por rodar no Streamlit Cloud:**

1. O `InstrumentsConsolidated` passa de 30 MB. Todo acesso à B3 vai para
   dentro de `@st.cache_data`, senão cada clique rebaixaria tudo.
2. A PTAX vem do Banco Central, que responde 406 a IP de datacenter. Ela é
   usada só na conferência de paridade, que já falha sozinha e devolve o
   motivo — a precificação não depende dela.
3. Nada aqui usa pandas para calcular, então a diferença de versão entre o
   Cloud e a máquina de casa não alcança esta página.
"""

from datetime import date, datetime

import pandas as pd
import streamlit as st

import fontes
import opcoes
import superficie
# Os formatadores no padrão brasileiro já existem no programa de terminal e
# são funções puras; importar evita manter duas versões que divergem.
from opcao import data_br, num, pct

# Mesmo papel do FORMATO_CACHE do app.py: entra na chave para o Cloud não
# servir, depois de um deploy, um resultado gravado no formato anterior.
FORMATO_CACHE = 1

EXEMPLOS = ["DOLN27P005200", "DOLN27C006000", "DOLF28C006500", "WDOF27C005250"]


def _hoje_no_brasil() -> date:
    """Hoje em Brasília — o servidor do Cloud roda em UTC."""
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    except Exception:
        return date.today()


@st.cache_data(ttl=1800, show_spinner=False)
def _precificar(codigo: str, quando: date, vol, forward: str,
                formato: int = FORMATO_CACHE):
    """Precificação em cache -> (resultado, erro). Nunca levanta."""
    try:
        return opcoes.precificar(codigo, quando, vol=vol, forward=forward), None
    except (opcoes.CodigoInvalido, fontes.SemDados) as erro:
        return None, str(erro)
    except OSError as erro:
        return None, f"não consegui falar com a fonte: {erro}"


@st.cache_data(ttl=1800, show_spinner=False)
def _referencia_superficie(formato: int = FORMATO_CACHE):
    """Data da superfície publicada. None se ela não abrir."""
    try:
        return superficie.carregar()["referencia"]
    except (fontes.SemDados, OSError):
        return None


def _tabela(linhas):
    st.dataframe(
        pd.DataFrame(linhas, columns=["Item", "Valor"]),
        hide_index=True,
        width="stretch",
    )


def _mostrar(r: dict):
    tipo = "Call" if r["tipo"] == "call" else "Put"
    st.subheader(f"{tipo} de dólar · strike {num(r['strike'], 0)}")
    st.caption(
        f"{r['ticker']} · vence {data_br(r['vencimento'])} · {r['estilo']} · "
        f"{r['dias_uteis']} dias úteis ({r['dias_corridos']} corridos)"
    )

    if r["digitado"] != r["ticker"]:
        st.info(f"Você digitou {r['digitado']} — o código da B3 é {r['ticker']}.")
    if r["recuou"]:
        st.caption(f"Sem pregão na data pedida; usando {data_br(r['pregao'])}.")

    esquerda, direita = st.columns(2)
    esquerda.metric("Prêmio", f"{num(r['premio'], 3)} pts")
    direita.metric("Por contrato", f"R$ {num(r['premio_reais'])}")

    _tabela([
        ("F — preço a termo", f"{num(r['futuro'], 3)} pts"),
        ("   origem", r["origem_futuro"]),
        ("K — strike", f"{num(r['strike'], 0)} pts"),
        ("T — prazo", f"{r['dias_corridos']}/365 = {num(r['prazo_anos'], 6)} ano"),
        ("r — juro até o vencimento", f"{pct(r['taxa'])} a.a."),
        ("   origem", r["origem_juro"]),
        ("σ — volatilidade", f"{pct(r['vol'])} a.a."),
        ("   origem", r["origem_vol"]),
    ])

    if not r["origem_vol"].startswith("superfície"):
        st.warning(
            "A volatilidade não veio da superfície da B3. "
            "Confira a origem acima antes de usar o número."
        )

    g = r["gregas"]
    with st.expander("Gregas"):
        _tabela([
            ("Delta", f"{num(g['delta'], 4, sinal=True)} por ponto do futuro"),
            ("Gama", f"{num(g['gama'], 6, sinal=True)} por ponto"),
            ("Vega", f"{num(g['vega'], 4, sinal=True)} por ponto de vol"),
            ("Theta", f"{num(g['theta'], 4, sinal=True)} por dia corrido"),
            ("Rho", f"{num(g['rho'], 4, sinal=True)} por ponto de juro"),
        ])

    smile = r["smile"]
    if smile:
        with st.expander("Sorriso de volatilidade"):
            st.caption(
                f"Superfície da B3 de {data_br(smile['referencia'])}, "
                f"vencimento {data_br(smile['vencimento'])}. As colunas de "
                "delta viram strikes; o strike da opção é interpolado."
            )
            curva = pd.DataFrame(
                {"Volatilidade (%)": [v * 100 for _, v in smile["smile"]]},
                index=[k for k, _ in smile["smile"]],
            )
            curva.index.name = "Strike"
            st.line_chart(curva)
            if not smile["dentro_da_faixa"]:
                st.warning(
                    f"O strike {num(r['strike'], 0)} está fora da faixa dos "
                    f"deltas 1%–99% ({num(smile['faixa'][0], 0)} a "
                    f"{num(smile['faixa'][1], 0)}). Pela regra da B3 repete-se "
                    "a volatilidade da ponta, o que subestima o prêmio."
                )

    par = r["paridade"]
    with st.expander("Conferência de paridade (cupom cambial)"):
        if par["erro"]:
            st.caption(f"Não deu para conferir: {par['erro']}")
        else:
            _tabela([
                (f"Dólar à vista (PTAX {data_br(par['data_spot'])})",
                 f"{num(par['spot'], 1)} pts"),
                ("Cupom cambial limpo", f"{pct(par['cupom'])} a.a. (base 360)"),
                ("   origem", par["origem_cupom"]),
                ("Termo por paridade", f"{num(par['futuro'], 3)} pts"),
                (f"Ajuste do futuro {r['futuro_ticker']}",
                 f"{num(r['futuro_ajuste'], 3)} pts"),
                ("Diferença", f"{num(par['diferenca'] * 100, 3, sinal=True)}%"),
            ])
            st.caption(
                "O resíduo é o horário do à vista: a B3 usa o fechamento das "
                "18h e a PTAX é a média apurada por volta das 13h."
            )

    st.caption(
        "Black-76, europeia sobre futuro, prazo em dias corridos/365. "
        "Fontes: B3 (cadastro, ajuste, curvas DI1 e FRC, superfície de "
        "volatilidade) e Banco Central (PTAX). Preço teórico, não executável."
    )


def render():
    """Desenha a página inteira. Chamada pelo app.py."""
    st.title("🎯 Opções de dólar")
    st.caption("Black-76 com dados oficiais da B3 · preço teórico")

    if st.button("← Voltar ao retorno acumulado", width="stretch"):
        st.session_state["pagina"] = "retorno"
        st.rerun()

    referencia = _referencia_superficie()
    if referencia:
        st.caption(f"Superfície de volatilidade da B3: {data_br(referencia)}")
    else:
        st.warning(
            "A superfície de volatilidade da B3 não abriu agora. Sem ela é "
            "preciso informar a volatilidade à mão, no menu abaixo."
        )

    hoje = _hoje_no_brasil()
    st.session_state.setdefault("opcao_codigo", EXEMPLOS[0])
    codigo = st.text_input(
        "Código da opção",
        key="opcao_codigo",
        placeholder="DOLN27P005200",
        help="DOL (ou WDO) + mês + ano + C/P + strike de 6 dígitos. "
             "DOLN27P005200 é a put de jul/27 com strike R$ 5,20.",
    ).strip()

    st.session_state.setdefault("opcao_data", hoje)
    quando = st.date_input(
        "Data de início", key="opcao_data", format="DD/MM/YYYY",
        min_value=date(2020, 1, 1), max_value=hoje,
    )

    with st.expander("Ajustes"):
        vol_digitada = st.number_input(
            "Volatilidade % a.a. (0 = usar a superfície da B3)",
            min_value=0.0, max_value=300.0, value=0.0, step=0.5,
            key="opcao_vol",
        )
        por_paridade = st.checkbox(
            "Construir o termo por paridade (dólar à vista + cupom cambial)",
            key="opcao_paridade",
            help="Por padrão o F é o preço de ajuste do futuro de mesmo "
                 "vencimento, que é o que o manual da B3 manda usar. A "
                 "paridade depende do dólar à vista e fica menos precisa.",
        )

    st.caption("Exemplos: " + " · ".join(EXEMPLOS))

    calcular = st.button("Calcular", type="primary", width="stretch")

    if not (calcular or st.session_state.get("opcao_ja_calculou")):
        return
    st.session_state["opcao_ja_calculou"] = True

    if not codigo:
        st.warning("Digite o código de uma opção.")
        return

    with st.spinner("Buscando na B3..."):
        resultado, erro = _precificar(
            codigo,
            quando,
            vol_digitada / 100 if vol_digitada > 0 else None,
            "paridade" if por_paridade else "futuro",
        )

    if erro:
        st.error(erro)
        return
    _mostrar(resultado)
