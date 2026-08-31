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
FORMATO_CACHE = 2

# Abaixo desta distância entre futuro e strike a opção é tratada como "no
# dinheiro" — chamar de dentro ou fora uma diferença de 0,3% engana mais do
# que informa.
PERTO_DO_DINHEIRO = 0.005


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
def _vencimentos(ativo: str, formato: int = FORMATO_CACHE):
    """Vencimentos e strikes que a B3 lista hoje -> {(ano, mês): {tipo: [R$]}}.

    Alimenta as listas da tela para que só apareça o que existe de verdade.
    Devolve {} se a B3 não responder — aí a tela cai para listas genéricas e
    quem valida é a busca.
    """
    try:
        pregao = fontes.ultimo_pregao(_hoje_no_brasil())
        cadastro = fontes.instrumentos(pregao, ativo)
    except (fontes.SemDados, OSError):
        return {}

    cotacao = opcoes.ATIVOS[ativo]["cotacao_por"]
    catalogo = {}
    for ticker, registro in cadastro.items():
        if not registro["OptnTp"] or not registro["ExrcPric"]:
            continue
        try:
            partes = opcoes.ler_codigo(ticker)
        except opcoes.CodigoInvalido:
            continue
        chave = (partes["ano"], partes["mes"])
        strikes = catalogo.setdefault(chave, {"call": set(), "put": set()})
        strikes[partes["tipo"]].add(int(registro["ExrcPric"]) / cotacao)
    return {
        chave: {tipo: sorted(valores) for tipo, valores in tipos.items()}
        for chave, tipos in catalogo.items()
    }


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


def _por_dolar(pontos: float, r: dict) -> float:
    """Pontos (reais por US$ 1.000) -> reais por dólar."""
    return pontos / r["cotacao_por"]


def _situacao(r: dict) -> tuple:
    """Onde a opção está em relação ao futuro, em português de gente.

    -> (título, explicação). O empate é o preço em que o resultado no
    vencimento zera: quem compra a opção paga o prêmio hoje, então precisa
    que o dólar passe do strike por pelo menos esse tanto.
    """
    futuro = _por_dolar(r["futuro"], r)
    strike = _por_dolar(r["strike"], r)
    premio = _por_dolar(r["premio"], r)
    call = r["tipo"] == "call"
    mes = opcoes.NOMES_MES[r["vencimento"].month - 1]
    quando = f"{mes}/{r['vencimento'].year}"

    distancia = abs(futuro / strike - 1)
    if distancia < PERTO_DO_DINHEIRO:
        titulo = "No dinheiro"
    elif (futuro > strike) if call else (futuro < strike):
        titulo = "Dentro do dinheiro"
    else:
        titulo = "Fora do dinheiro"

    empate = strike + premio if call else strike - premio
    direcao = "subir acima de" if call else "cair abaixo de"
    virar = "acima" if call else "abaixo"
    lado = "acima disso" if call else "abaixo disso"

    if titulo == "Dentro do dinheiro":
        posicao = (f"e o futuro já está {virar} disso hoje — o que conta, "
                   "porém, é onde o dólar estiver no vencimento")
    elif titulo == "No dinheiro":
        posicao = "e o futuro está praticamente colado nesse valor"
    else:
        posicao = (f"e ela só vale alguma coisa no vencimento se o dólar "
                   f"estiver {virar} disso")

    explicacao = (
        f"O futuro de {quando} está em **R$ {num(futuro, 4)}** e o strike é "
        f"**R$ {num(strike, 2)}**. "
        f"Como é uma {'call' if call else 'put'}, ela dá o direito de "
        f"{'comprar' if call else 'vender'} dólar a R$ {num(strike, 2)}, "
        f"{posicao}.\n\n"
        f"Pagando R$ {num(premio, 4)} por dólar de prêmio, o negócio empata "
        f"em **R$ {num(empate, 4)}** — {lado} é lucro. "
        f"Ou seja, o dólar precisa {direcao} R$ {num(empate, 4)} até "
        f"{data_br(r['vencimento'])}."
    )
    return titulo, explicacao


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

    uma, duas, tres = st.columns(3)
    uma.metric("Prêmio por dólar", f"R$ {num(_por_dolar(r['premio'], r), 4)}")
    duas.metric(f"Por contrato ({r['tamanho']})", f"R$ {num(r['premio_reais'])}")
    tres.metric("Na tela da B3", f"{num(r['premio'], 3)} pts")
    st.caption(
        "A B3 cota o prêmio em pontos, que são reais por US$ 1.000. "
        f"Os {num(r['premio'], 3)} pontos são R$ {num(_por_dolar(r['premio'], r), 4)} "
        f"por dólar, e o contrato tem {r['tamanho']}."
    )

    titulo, explicacao = _situacao(r)
    (st.success if titulo == "Dentro do dinheiro" else st.info)(
        f"**{titulo}.** {explicacao}"
    )

    if r["futuro_ajuste"]:
        st.metric(
            f"Futuro {r['futuro_ticker']} ({data_br(r['vencimento'])})",
            f"R$ {num(_por_dolar(r['futuro_ajuste'], r), 4)} por dólar",
            help=f"Preço de ajuste da B3 em {data_br(r['pregao'])}: "
                 f"{num(r['futuro_ajuste'], 3)} pontos. É o preço a termo que "
                 "o mercado pratica para essa data, e é dele que sai o F do modelo.",
        )

    _tabela([
        ("F — preço a termo", f"{num(r['futuro'], 3)} pts = R$ {num(_por_dolar(r['futuro'], r), 4)}/dólar"),
        ("   origem", r["origem_futuro"]),
        ("K — strike", f"{num(r['strike'], 0)} pts = R$ {num(_por_dolar(r['strike'], r), 2)}/dólar"),
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

    st.markdown("**Monte a opção**")
    coluna_a, coluna_b = st.columns(2)
    ativo = coluna_a.selectbox(
        "Ativo", list(opcoes.ATIVOS), key="opcao_ativo",
        format_func=lambda a: f"{a} — {opcoes.ATIVOS[a]['nome']}",
        help="DOL é o contrato cheio (US$ 50.000); WDO é o mini (US$ 10.000).",
    )
    tipo = coluna_b.selectbox(
        "Call ou Put", ["call", "put"], key="opcao_tipo",
        format_func=lambda t: ("Call — direito de comprar" if t == "call"
                               else "Put — direito de vender"),
    )

    catalogo = _vencimentos(ativo)
    anos_listados = sorted({ano for ano, _ in catalogo} | {hoje.year})
    anos = [a for a in anos_listados if a >= hoje.year] or [hoje.year]

    coluna_c, coluna_d = st.columns(2)
    ano = coluna_d.selectbox("Ano de vencimento", anos, key="opcao_ano")
    meses_do_ano = sorted({m for a, m in catalogo if a == ano})
    if not meses_do_ano:
        meses_do_ano = list(range(1, 13))
    mes = coluna_c.selectbox(
        "Mês de vencimento", meses_do_ano, key="opcao_mes",
        format_func=lambda m: opcoes.NOMES_MES[m - 1].capitalize(),
    )

    disponiveis = (catalogo.get((ano, mes)) or {}).get(tipo, [])
    padrao = disponiveis[len(disponiveis) // 2] if disponiveis else 5.00
    coluna_e, coluna_f = st.columns(2)
    strike = coluna_e.number_input(
        "Strike (R$ por dólar)", key="opcao_strike",
        min_value=0.01, max_value=99.99, value=float(padrao), step=0.05,
        format="%.2f",
        help="O preço de exercício, em reais por dólar. Ex: 5,20.",
    )
    quando = coluna_f.date_input(
        "Data de referência", key="opcao_data", format="DD/MM/YYYY",
        min_value=date(2020, 1, 1), max_value=hoje,
    )

    strike_existe = True
    if disponiveis:
        perto = sorted(disponiveis, key=lambda k: abs(k - strike))[:7]
        st.caption(
            f"{len(disponiveis)} strikes listados neste vencimento. "
            "Perto do seu: " + " · ".join(f"R$ {num(k)}" for k in sorted(perto))
        )
        strike_existe = strike in disponiveis

    try:
        codigo = opcoes.montar_codigo(ativo, tipo, mes, ano, strike)
        st.caption(f"Código montado: **{codigo}**")
    except opcoes.CodigoInvalido as erro:
        st.error(str(erro))
        return

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

    calcular = st.button("Calcular", type="primary", width="stretch")

    if not (calcular or st.session_state.get("opcao_ja_calculou")):
        return
    st.session_state["opcao_ja_calculou"] = True

    if not strike_existe:
        # a busca só devolveria o mesmo recado em pontos, que não ajuda quem
        # digitou reais — melhor parar aqui, com a sugestão na mesma unidade
        mais_perto = min(disponiveis, key=lambda k: abs(k - strike))
        st.warning(
            f"A B3 não lista o strike R$ {num(strike)} para "
            f"{opcoes.NOMES_MES[mes - 1]}/{ano}. O mais próximo é "
            f"**R$ {num(mais_perto)}** — ajuste o campo e calcule de novo."
        )
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
