"""Opção de dólar da B3: lê o código, busca os insumos e roda o Black-76.

Você dá a data de referência e o código da opção (ex: `DOLN27P005200`) e
recebe o prêmio teórico, as gregas e de onde veio cada número.

**O código.** `DOL` + mês + ano + `C`/`P` + strike de 6 dígitos com zeros à
esquerda, em pontos (reais por US$ 1.000). `DOLN27P005200` é a put de
vencimento julho/2027 com strike 5200 pontos, ou seja R$ 5,20 por dólar.
Também é aceito o strike escrito com os centavos à mostra (`DOLN27P520000`),
que dá no mesmo — mas o código canônico, o que existe no arquivo da B3, é o
de 6 dígitos, e é ele que o resultado devolve.

**Convenção de prazo: dias corridos.** O manual da B3 calcula o prêmio de
referência com o prazo "em anos do calendário" (§2.1) e diz que a
volatilidade da superfície é a que alimenta essas equações (§2.2) — então a
sigma publicada só faz sentido com um T em dias corridos. Medir o prazo em
dias úteis com uma vol calibrada em dias corridos subestima o prêmio em torno
de 2%. O desconto continua saindo da curva de DI em base 252, como manda a
curva: `black76.taxa_continua_para()` mantém `exp(-r*T)` idêntico a
`(1+i)^(-du/252)`, então trocar a base do prazo mexe só na difusão.

**Por que Black-76 e não Black-Scholes.** Estas são opções europeias sobre o
disponível de dólar (`OPTIONS ON SPOT`, `OptnStyle=EURO` no cadastro da B3),
liquidadas contra a PTAX no vencimento. O futuro de mesmo vencimento é o
preço a termo que o mercado está praticando e já carrega o diferencial de
juros entre real e dólar — então ele entra como F e o juro fica só no
desconto. Usar o dólar à vista no lugar do futuro erraria o prêmio pela
diferença toda do cupom cambial.

**A volatilidade vem da superfície da B3, e só dela** (`superficie.py`):
volatilidade implícita de mercado, coletada de um pool de informantes e
ajustada por SVI. É o preço que o mercado está cobrando pelo risco à frente,
que é o que interessa para precificar. `vol`, se você passar, vence.

Houve uma reserva com volatilidade histórica da PTAX; foi retirada de
propósito. Ela olha para trás e ficava bem abaixo da implícita — em
28/08/2026, 9,44% contra 13,50% na DOLN27P005200, prêmio quase pela metade.
Precificar com ela era barato do jeito errado.

**O preço disso:** a B3 sobrescreve o arquivo da superfície todo dia e não
guarda histórico, então só dá para precificar o pregão mais recente. Data
passada só com `vol` na mão.

O open data da B3 não cobre esse buraco: dos instrumentos DOL com preço no
arquivo de negócios, nenhum é opção, só futuro — não há prêmio nem implícita
por série.
"""

import re
from datetime import date

import black76
import fontes
import superficie

CODIGO = re.compile(r"^(?P<ativo>[A-Z]{3})(?P<mes>[FGHJKMNQUVXZ])(?P<ano>\d{2})"
                    r"(?P<tipo>[CP])(?P<strike>\d{1,6})$")

MESES = {"F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6,
         "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12}

STRIKE_EM_CENTAVOS = 20_000   # acima disso o strike veio com centavos à mostra

TIPO_POR_LETRA = {"C": "call", "P": "put"}


class CodigoInvalido(Exception):
    """O texto não tem cara de código de opção da B3."""


def ler_codigo(texto: str) -> dict:
    """'DOLN27P005200' -> partes do código, com o strike já em pontos."""
    texto = (texto or "").strip().upper().replace(" ", "")
    achado = CODIGO.match(texto)
    if not achado:
        raise CodigoInvalido(
            f"{texto!r} não é um código de opção. O formato é DOL + mês + ano "
            "+ C/P + strike, como DOLN27P005200 (put de jul/27, strike 5200)."
        )
    strike = int(achado["strike"])
    if strike > STRIKE_EM_CENTAVOS:      # 520000 é o 5200 com os centavos
        strike, resto = divmod(strike, 100)
        if resto:
            raise CodigoInvalido(
                f"strike {achado['strike']} não vira um valor em pontos: "
                "acima de 20000 ele é lido como centavos e precisa terminar "
                "em dois zeros."
            )
    tipo = TIPO_POR_LETRA[achado["tipo"]]
    return {
        "ativo": achado["ativo"],
        "tipo": tipo,
        "strike": strike,
        "mes": MESES[achado["mes"]],
        "ano": 2000 + int(achado["ano"]),
        "vencimento_codigo": f"{achado['mes']}{achado['ano']}",
        "ticker": f"{achado['ativo']}{achado['mes']}{achado['ano']}"
                  f"{achado['tipo']}{strike:06d}",
        "futuro": f"{achado['ativo']}{achado['mes']}{achado['ano']}",
        "digitado": texto,
    }


def _strikes_vizinhos(cadastro: dict, partes: dict, quantos: int = 8) -> list:
    """Strikes que existem no mesmo vencimento e tipo, perto do pedido."""
    inicio = f"{partes['ativo']}{partes['vencimento_codigo']}" \
             f"{'C' if partes['tipo'] == 'call' else 'P'}"
    disponiveis = sorted(
        int(reg["ExrcPric"])
        for tic, reg in cadastro.items()
        if tic.startswith(inicio) and reg.get("ExrcPric")
    )
    if not disponiveis:
        return []
    alvo = partes["strike"]
    return sorted(sorted(disponiveis, key=lambda k: abs(k - alvo))[:quantos])



def _paridade(pregao, vencimento, dias_corridos, prazo, juro, futuro_ajuste):
    """Refaz o preço a termo pela forma de câmbio do manual (§2.1).

    Devolve o F por paridade e o quanto ele difere do ajuste do futuro. Serve
    de conferência: se os dois se afastam muito num dia, alguma das pontas
    está estranha. Nunca derruba a precificação — se faltar cupom ou PTAX,
    volta None com o motivo.
    """
    try:
        cupom, origem_cupom = fontes.cupom_ate(pregao, vencimento, "FRC")
        spot, data_spot = fontes.ptax(pregao)
    except (fontes.SemDados, OSError) as erro:
        return {"erro": str(erro)}

    spot_pontos = spot * 1000
    juro_estrangeiro = black76.taxa_continua_linear(cupom, dias_corridos, prazo)
    futuro = black76.forward_paridade(
        spot_pontos, juro, juro_estrangeiro, prazo
    )
    return {
        "erro": None,
        "futuro": futuro,
        "spot": spot_pontos,
        "data_spot": data_spot,
        "cupom": cupom,
        "origem_cupom": origem_cupom,
        "juro_estrangeiro": juro_estrangeiro,
        "diferenca": futuro / futuro_ajuste - 1,
    }


def precificar(codigo: str, data_referencia: date, vol: float = None,
               premio_mercado: float = None, forward: str = "futuro") -> dict:
    """Roda o Black-76 na opção, com os insumos das fontes oficiais.

    - `data_referencia`: o dia em que se está precificando. Se não houver
      pregão, recua para o pregão anterior (e diz isso no resultado).
    - `vol`: volatilidade anualizada em decimal (0.12 = 12%). None lê a
      superfície da B3.
    - `premio_mercado`: prêmio observado, em pontos. Se vier, o resultado
      também traz a volatilidade implícita dele.
    - `forward`: "futuro" usa o preço de ajuste do futuro de mesmo
      vencimento, que é o que o manual da B3 manda na §6.1; "paridade"
      constrói o termo com dólar à vista e cupom cambial, na forma da §2.1.
      A paridade é calculada e devolvida nos dois casos, como conferência.
    """
    if forward not in ("futuro", "paridade"):
        raise ValueError("forward precisa ser 'futuro' ou 'paridade'")
    partes = ler_codigo(codigo)
    pregao = fontes.ultimo_pregao(data_referencia)

    cadastro = fontes.instrumentos(pregao, partes["ativo"])
    registro = cadastro.get(partes["ticker"])
    if registro is None:
        vizinhos = _strikes_vizinhos(cadastro, partes)
        dica = f" Strikes perto, nesse vencimento: {vizinhos}." if vizinhos else ""
        raise fontes.SemDados(
            f"a B3 não listava {partes['ticker']} em {pregao:%d/%m/%Y}.{dica}"
        )

    dias_uteis = int(registro["WrkgDays"])
    dias_corridos = int(registro["ClnrDays"])
    # prazo em dias corridos: é a base das equações 2.1/2.2 do manual da B3,
    # que são as que a volatilidade da superfície alimenta (§2.2). O desconto
    # não muda por isso — quem cuida disso é taxa_continua_para().
    prazo = black76.prazo_em_anos(dias_corridos, black76.DIAS_CORRIDOS_ANO)
    strike = float(registro["ExrcPric"])          # o da B3, não o do texto
    multiplicador = float(registro["CtrctMltplr"])

    vencimento = date.fromisoformat(registro["XprtnDt"])
    precos = fontes.ajustes(pregao, partes["ativo"])
    futuro_ajuste = precos.get(partes["futuro"])
    futuro = futuro_ajuste
    if futuro is None:
        raise fontes.SemDados(
            f"sem preço de ajuste do futuro {partes['futuro']} em "
            f"{pregao:%d/%m/%Y} — é dele que sai o F do modelo."
        )

    try:
        taxa, origem_juro = fontes.juro_ate(pregao, vencimento)
    except fontes.SemDados as erro:
        taxa, data_cdi = fontes.cdi_ao_ano(pregao)
        origem_juro = f"CDI à vista de {data_cdi:%d/%m/%Y} — sem DI1: {erro}"
    juro = black76.taxa_continua_para(taxa, dias_uteis, prazo)

    paridade = _paridade(pregao, vencimento, dias_corridos, prazo, juro,
                         futuro_ajuste)
    origem_futuro = f"ajuste do futuro {partes['futuro']}"
    if forward == "paridade":
        if paridade["erro"]:
            raise fontes.SemDados(
                f"sem paridade: {paridade['erro']}. Use o futuro de ajuste."
            )
        futuro = paridade["futuro"]
        origem_futuro = (
            f"paridade: PTAX de {paridade['data_spot']:%d/%m/%Y} e "
            f"{paridade['origem_cupom']}"
        )

    smile = None

    if vol is not None:
        origem_vol = "informada"
    else:
        try:
            smile = superficie.volatilidade(
                vencimento, futuro, prazo, strike, pregao=pregao
            )
        except fontes.SemDados as erro:
            raise fontes.SemDados(
                f"{erro}. Sem superfície não há volatilidade: informe uma "
                "à mão para precificar esta data."
            ) from erro
        vol = smile["vol"]
        origem_vol = (
            f"superfície da B3 de {smile['referencia']:%d/%m/%Y}"
            + ("" if smile["dentro_da_faixa"] else ", strike fora da "
               "faixa dos deltas 1%-99% (repetiu a ponta)")
        )

    premio = black76.preco(partes["tipo"], futuro, strike, prazo, juro, vol)
    sensibilidades = black76.gregas(
        partes["tipo"], futuro, strike, prazo, juro, vol,
        base_theta=black76.DIAS_CORRIDOS_ANO,
    )

    implicita = None
    if premio_mercado is not None:
        implicita = black76.vol_implicita(
            partes["tipo"], premio_mercado, futuro, strike, prazo, juro
        )

    return {
        "ticker": partes["ticker"],
        "digitado": partes["digitado"],
        "tipo": partes["tipo"],
        "estilo": registro["OptnStyle"],
        "mercado": registro["MktNm"],
        "vencimento": vencimento,
        "pregao": pregao,
        "recuou": pregao != data_referencia,
        "dias_uteis": dias_uteis,
        "dias_corridos": dias_corridos,
        "prazo_anos": prazo,
        "base_prazo": black76.DIAS_CORRIDOS_ANO,
        "futuro_ticker": partes["futuro"],
        "futuro": futuro,
        "futuro_ajuste": futuro_ajuste,
        "origem_futuro": origem_futuro,
        "paridade": paridade,
        "strike": strike,
        "taxa": taxa,
        "origem_juro": origem_juro,
        "juro_continuo": juro,
        "vol": vol,
        "origem_vol": origem_vol,
        "smile": smile,
        "multiplicador": multiplicador,
        "premio": premio,
        "premio_reais": premio * multiplicador,
        "gregas": sensibilidades,
        "premio_mercado": premio_mercado,
        "vol_implicita": implicita,
        "moneyness": futuro / strike,
    }

