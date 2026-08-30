"""Black-76: precificação de opção europeia sobre um preço futuro.

Módulo puro — não busca nada na rede e não depende de biblioteca externa.
Recebe os cinco insumos e devolve prêmio, gregas e volatilidade implícita.

O modelo de Black (1976) é a adaptação de Black-Scholes para quando o objeto
da opção é um *futuro*, e não um ativo à vista: o preço a termo já embute o
custo de carregamento, então o juro entra só no desconto do prêmio.

    d1 = [ln(F/K) + (sigma^2 / 2) * T] / (sigma * raiz(T))
    d2 = d1 - sigma * raiz(T)

    call = exp(-r*T) * [F * N(d1) - K * N(d2)]
    put  = exp(-r*T) * [K * N(-d2) - F * N(-d1)]

**Garman-Kohlhagen é este mesmo modelo.** O manual da B3 (§2.1) escreve o
prêmio de referência da opção de dólar na forma de câmbio,

    c = S*exp(-rf*T)*N(d1) - K*exp(-r*T)*N(d2)

com S sendo o dólar à vista, r o juro doméstico (DI) e rf o juro estrangeiro
(cupom cambial). Isso não é um modelo diferente: como
`S*exp((r-rf)*T)` é o preço a termo, basta pôr `F = S*exp((r-rf)*T)` e as
duas fórmulas viram a mesma. Por isso aqui existe só o Black-76, e o câmbio
entra por `forward_paridade()` — que constrói esse F. Um único caminho de
código para precificar, sem fórmula duplicada para divergir com o tempo.

**Convenção de prazo.** O módulo não decide a base: `prazo_em_anos()` aceita
252 (dias úteis, padrão do DI) ou 365 (dias corridos). Quem chama escolhe, e
a escolha tem que casar com a base em que a volatilidade foi medida — é o
σ·raiz(T) que sente a diferença.

**Convenção de juro, e a armadilha de trocar a base do prazo.** A taxa
brasileira é efetiva ao ano base 252: o DI de 13,64% quer dizer que R$1 vira
R$1,1364 em 252 dias úteis. A fórmula acima pede taxa contínua, e o desconto
correto é sempre `(1+i)^(-du/252)`, independente da base escolhida para T.

Se T passa a ser dias corridos e a taxa for convertida ingenuamente com
ln(1+i), o desconto muda junto — e o prêmio se mexe por um motivo errado, que
não tem nada a ver com difusão. `taxa_continua_para()` resolve: devolve a
taxa contínua que, naquele T, reproduz exatamente o desconto da curva. Aí
trocar a base de T mexe só no σ·raiz(T), que é o que se queria.
"""

import math
from statistics import NormalDist

DIAS_UTEIS_ANO = 252
DIAS_CORRIDOS_ANO = 365
_NORMAL = NormalDist()

TIPOS = ("call", "put")


def taxa_continua(taxa_ano: float) -> float:
    """Converte taxa efetiva ao ano (0.139 = 13,9%) em taxa contínua."""
    if taxa_ano <= -1:
        raise ValueError("taxa efetiva ao ano precisa ser maior que -100%")
    return math.log1p(taxa_ano)


def prazo_em_anos(dias: float, base: int = DIAS_UTEIS_ANO) -> float:
    """Dias até o vencimento -> anos. `base` é 252 (úteis) ou 365 (corridos)."""
    if base <= 0:
        raise ValueError("a base do ano precisa ser positiva")
    return dias / base


def taxa_continua_para(taxa_ano: float, dias_uteis: float, prazo: float) -> float:
    """Taxa contínua que reproduz o desconto da curva no prazo dado.

    O desconto da curva de DI é `(1+i)^(-du/252)` e não depende da base
    escolhida para T. Esta função devolve o r tal que `exp(-r*prazo)` é
    exatamente esse valor — assim dá para medir o prazo em dias corridos,
    para casar com a base da volatilidade, sem mexer no desconto.
    """
    if prazo <= 0:
        raise ValueError("o prazo precisa ser positivo")
    return dias_uteis * math.log1p(taxa_ano) / (DIAS_UTEIS_ANO * prazo)


def taxa_continua_linear(taxa_ano: float, dias_corridos: float,
                         prazo: float) -> float:
    """Taxa contínua de uma taxa linear base 360 — o caso do cupom cambial.

    O cupom capitaliza `1 + i*dc/360`, e não `(1+i)^(du/252)` como o DI.
    Devolve o rf tal que `exp(-rf*prazo)` reproduz esse fator, que é a
    equação (2.6) do manual da B3.
    """
    if prazo <= 0:
        raise ValueError("o prazo precisa ser positivo")
    fator = 1 + taxa_ano * dias_corridos / 360
    if fator <= 0:
        raise ValueError("fator de cupom cambial não positivo")
    return math.log(fator) / prazo


def forward_paridade(spot: float, juro: float, juro_estrangeiro: float,
                     prazo: float) -> float:
    """Preço a termo por paridade coberta: S * exp((r - rf) * T).

    É o F que a forma de câmbio do manual (§2.1) usa implicitamente. Só vale
    o que valem os insumos: com o dólar à vista errado por 0,25%, o F sai
    errado por 0,25%. Quando existe futuro de mesmo vencimento, o ajuste dele
    é a medida direta do mesmo número — e é o que o próprio manual manda usar
    na §6.1.
    """
    if spot <= 0:
        raise ValueError("o dólar à vista precisa ser positivo")
    return spot * math.exp((juro - juro_estrangeiro) * prazo)


def _conferir(futuro, strike, prazo, vol):
    if futuro <= 0:
        raise ValueError("o preço do futuro precisa ser positivo")
    if strike <= 0:
        raise ValueError("o strike precisa ser positivo")
    if prazo < 0:
        raise ValueError("o prazo não pode ser negativo")
    if vol < 0:
        raise ValueError("a volatilidade não pode ser negativa")


def _d1_d2(futuro, strike, prazo, vol):
    desvio = vol * math.sqrt(prazo)
    d1 = (math.log(futuro / strike) + (vol * vol / 2) * prazo) / desvio
    return d1, d1 - desvio


def _no_vencimento(tipo, futuro, strike):
    """Valor intrínseco — usado quando prazo ou volatilidade zeram."""
    return max(futuro - strike, 0.0) if tipo == "call" else max(strike - futuro, 0.0)


def preco(tipo: str, futuro: float, strike: float, prazo: float,
          juro: float, vol: float) -> float:
    """Prêmio da opção, na mesma unidade de `futuro` e `strike`.

    `prazo` em anos (252 dias úteis), `juro` contínuo ao ano, `vol` anualizada
    em decimal (0.15 = 15%).
    """
    tipo = tipo.lower()
    if tipo not in TIPOS:
        raise ValueError(f"tipo precisa ser 'call' ou 'put', veio {tipo!r}")
    _conferir(futuro, strike, prazo, vol)

    desconto = math.exp(-juro * prazo)
    if prazo == 0 or vol == 0:
        return desconto * _no_vencimento(tipo, futuro, strike)

    d1, d2 = _d1_d2(futuro, strike, prazo, vol)
    if tipo == "call":
        return desconto * (futuro * _NORMAL.cdf(d1) - strike * _NORMAL.cdf(d2))
    return desconto * (strike * _NORMAL.cdf(-d2) - futuro * _NORMAL.cdf(-d1))


def gregas(tipo: str, futuro: float, strike: float, prazo: float,
           juro: float, vol: float, base_theta: int = DIAS_UTEIS_ANO) -> dict:
    """Sensibilidades do prêmio, em unidades de leitura direta.

    - `delta`: variação do prêmio por 1 ponto de variação do futuro.
    - `gama`: variação do delta por 1 ponto de variação do futuro.
    - `vega`: variação do prêmio por **1 ponto percentual** de volatilidade.
    - `theta`: variação do prêmio a cada dia que passa, na base de
      `base_theta` (252 = dia útil, 365 = dia corrido). Negativa quase
      sempre — é o tempo corroendo o prêmio.
    - `rho`: variação do prêmio por 1 ponto percentual de juro.
    """
    tipo = tipo.lower()
    if tipo not in TIPOS:
        raise ValueError(f"tipo precisa ser 'call' ou 'put', veio {tipo!r}")
    _conferir(futuro, strike, prazo, vol)

    desconto = math.exp(-juro * prazo)
    premio = preco(tipo, futuro, strike, prazo, juro, vol)

    if prazo == 0 or vol == 0:
        dentro = _no_vencimento(tipo, futuro, strike) > 0
        delta = desconto * (1.0 if tipo == "call" else -1.0) if dentro else 0.0
        return {"delta": delta, "gama": 0.0, "vega": 0.0,
                "theta": 0.0, "rho": -prazo * premio}

    d1, d2 = _d1_d2(futuro, strike, prazo, vol)
    densidade = _NORMAL.pdf(d1)
    raiz = math.sqrt(prazo)

    if tipo == "call":
        delta = desconto * _NORMAL.cdf(d1)
    else:
        delta = -desconto * _NORMAL.cdf(-d1)

    gama = desconto * densidade / (futuro * vol * raiz)
    vega = futuro * desconto * densidade * raiz
    theta = -futuro * desconto * densidade * vol / (2 * raiz) + juro * premio

    return {
        "delta": delta,
        "gama": gama,
        "vega": vega / 100,                 # por ponto percentual de vol
        "theta": theta / base_theta,        # por dia da base escolhida
        "rho": -prazo * premio / 100,       # por ponto percentual de juro
    }


def vol_implicita(tipo: str, premio: float, futuro: float, strike: float,
                  prazo: float, juro: float,
                  minimo: float = 1e-6, maximo: float = 5.0,
                  tolerancia: float = 1e-8, voltas: int = 200):
    """Volatilidade que faz o modelo devolver `premio`. None se não existir.

    Bissecção, não Newton: é mais lenta e não erra. O prêmio cresce sempre
    com a volatilidade, então basta fechar o intervalo. Devolve None quando o
    prêmio está fora da faixa que o modelo consegue produzir — abaixo do valor
    intrínseco descontado ou acima do teto de 500% de volatilidade —, que é o
    caso de prêmio mal digitado ou de opção sem negócio.
    """
    tipo = tipo.lower()
    if tipo not in TIPOS:
        raise ValueError(f"tipo precisa ser 'call' ou 'put', veio {tipo!r}")
    _conferir(futuro, strike, prazo, 0.0)
    if prazo <= 0 or premio <= 0:
        return None

    piso = preco(tipo, futuro, strike, prazo, juro, minimo)
    teto = preco(tipo, futuro, strike, prazo, juro, maximo)
    if not (piso <= premio <= teto):
        return None

    baixo, alto = minimo, maximo
    for _ in range(voltas):
        meio = (baixo + alto) / 2
        if preco(tipo, futuro, strike, prazo, juro, meio) < premio:
            baixo = meio
        else:
            alto = meio
        if alto - baixo < tolerancia:
            break
    return (baixo + alto) / 2
