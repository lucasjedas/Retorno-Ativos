"""Índices de comparação para o gráfico: CDI, IPCA, Ibovespa e S&P 500.

Ibovespa e S&P 500 saem do Yahoo, pela mesma busca do financeiro.py.

CDI e IPCA não existem no Yahoo e vêm de duas fontes públicas, em cascata:

1. SGS, do Banco Central — séries diárias, é o dado preferido;
2. IPEA Data — as mesmas taxas em base mensal.

A cascata existe porque o WAF do Banco Central responde 406 a pedidos vindos
de servidores em nuvem: da máquina de casa a API abre normalmente, do
Streamlit Cloud não. O IPEA atende os dois. Quando a segunda fonte é usada, a
tela diz — a curva fica em degraus mensais e o acumulado muda um pouco, já
que meses inteiros entram no lugar das datas exatas.

Toda curva devolvida aqui é retorno acumulado em %, começando em zero na
primeira data do ativo, para poder ser desenhada no mesmo eixo.
"""

import json
import urllib.request
from datetime import datetime, timedelta

import pandas as pd

from financeiro import buscar_historico

SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados"
IPEA = "https://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='{codigo}')"
ESPERA = 15  # segundos; tela parada esperando fonte fora do ar não ajuda

CABECALHOS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}

# Ordem aqui é a ordem da legenda e das cores no gráfico.
BENCHMARKS = {
    "CDI":      {"fonte": "taxa",  "sgs": 12,  "ipea": "BM12_TJCDI12",    "cor": "#7E8CA0"},
    "IPCA":     {"fonte": "taxa",  "sgs": 433, "ipea": "PRECOS12_IPCAG12", "cor": "#C79A3C"},
    "Ibovespa": {"fonte": "yahoo", "simbolo": "^BVSP", "cor": "#4B7BE5"},
    "S&P 500":  {"fonte": "yahoo", "simbolo": "^GSPC", "cor": "#9B59B6"},
}


def _sem_fuso(datas) -> pd.DatetimeIndex:
    """DatetimeIndex sem fuso, na meia-noite do dia.

    Cada fonte data de um jeito: o IPEA manda offset (-03:00), o Yahoo manda o
    fuso da bolsa, o BCB manda só a data. Alinhar um índice com fuso contra um
    sem fuso devolve um Index de objetos no pandas 2 e levanta TypeError no
    pandas 3 — que é o que o Streamlit Cloud instala. Passar por UTC e zerar a
    hora deixa as três fontes no mesmo formato.
    """
    return pd.DatetimeIndex(pd.to_datetime(datas, utc=True)).tz_convert(None).normalize()


def _baixar(url: str):
    pedido = urllib.request.Request(url, headers=CABECALHOS)
    with urllib.request.urlopen(pedido, timeout=ESPERA) as resposta:
        return json.loads(resposta.read().decode("utf-8"))


def _taxas_sgs(serie: int, inicio, fim):
    """Série de variações % do Banco Central (diária, no caso do CDI)."""
    url = SGS.format(serie=serie) + (
        f"?formato=json&dataInicial={inicio:%d/%m/%Y}&dataFinal={fim:%d/%m/%Y}"
    )
    dados = _baixar(url)
    if not dados:
        return None
    datas = _sem_fuso(pd.to_datetime([x["data"] for x in dados], format="%d/%m/%Y"))
    return pd.Series([float(x["valor"]) for x in dados], index=datas).sort_index()


def _taxas_ipea(codigo: str, inicio, fim):
    """Série de variações % mensais do IPEA Data.

    O OData devolve a série inteira (desde os anos 80), então o recorte é
    feito aqui mesmo — são poucas centenas de pontos.
    """
    dados = _baixar(IPEA.format(codigo=codigo))["value"]
    if not dados:
        return None
    validos = [x for x in dados if x.get("VALVALOR") is not None]
    if not validos:
        return None
    serie = pd.Series(
        [float(x["VALVALOR"]) for x in validos],
        index=_sem_fuso([x["VALDATA"] for x in validos]),
    ).sort_index()

    # Margem para trás: as taxas são datadas no dia 1º, então sem folga o mês
    # em que o período começa ficaria de fora. Recorte por máscara, e não por
    # fatia de texto, que muda de comportamento entre versões do pandas.
    desde = pd.Timestamp(inicio) - pd.Timedelta(days=45)
    ate = pd.Timestamp(fim)
    return serie[(serie.index >= desde) & (serie.index <= ate)]


def _conferir_variacoes(taxas, nome: str):
    """Recusa série que não seja variação percentual.

    O IPEA publica o IPCA nas duas formas, e os códigos diferem por uma letra:
    PRECOS12_IPCAG12 é a variação mensal, PRECOS12_IPCA12 é o número índice
    (na casa dos 7.600). Compor 7.600 como se fosse "+7.600% no mês" produz um
    acumulado de 10²² por cento — grande demais para passar despercebido, mas
    o formato do erro é o de um dado plausível, então fica esta trava.
    """
    if taxas is None or taxas.empty:
        return taxas
    extremo = float(taxas.abs().max())
    if extremo > 50:
        raise RuntimeError(
            f"{nome}: a série não parece variação percentual "
            f"(valor de {extremo:.1f} no período)"
        )
    return taxas


def _fator_taxa(config, inicio, fim):
    """Fator acumulado de CDI/IPCA, com a fonte de reserva. -> (Series, origem)."""
    nome = config["ipea"]
    try:
        taxas = _conferir_variacoes(
            _taxas_sgs(config["sgs"], inicio - timedelta(days=45), fim), nome
        )
        if taxas is not None and not taxas.empty:
            return (1 + taxas / 100).cumprod(), "Banco Central"
        falha_bcb = "resposta vazia"
    except Exception as erro:
        falha_bcb = f"{type(erro).__name__}: {erro}"

    taxas = _conferir_variacoes(_taxas_ipea(nome, inicio, fim), nome)
    if taxas is None or taxas.empty:
        raise RuntimeError(f"Banco Central ({falha_bcb}) e IPEA sem dados")
    return (1 + taxas / 100).cumprod(), f"IPEA (mensal) — Banco Central recusou: {falha_bcb}"


def _fator_yahoo(simbolo: str, inicio, fim):
    _, df, _, _ = buscar_historico(
        simbolo,
        datetime.combine(inicio, datetime.min.time()),
        datetime.combine(fim, datetime.min.time()),
    )
    if df is None:
        return None, "Yahoo Finance"
    coluna = "Adj Close" if "Adj Close" in df.columns else "Close"
    serie = df[coluna].dropna()
    serie.index = _sem_fuso(serie.index)
    return serie, "Yahoo Finance"


def fator(nome: str, inicio, fim):
    """Série bruta do índice. -> (Series, origem, motivo da falha).

    Só isto depende da rede, então é o que vale a pena guardar em cache — o
    alinhamento muda a cada ativo. O motivo vem junto porque um índice mudo
    na tela não diz se a fonte caiu, recusou o pedido ou não tem o período.
    """
    config = BENCHMARKS[nome]
    try:
        if config["fonte"] == "taxa":
            serie, origem = _fator_taxa(config, inicio, fim)
        else:
            serie, origem = _fator_yahoo(config["simbolo"], inicio, fim)
    except Exception as erro:
        return None, "", f"{nome}: {type(erro).__name__}: {erro}"

    if serie is None or serie.empty:
        return None, origem, f"{nome}: a fonte respondeu sem dados para o período"
    return serie, origem, ""


def curva(nome: str, inicio, fim, datas_alvo, bruto=None):
    """Retorno acumulado em %, alinhado às datas de pregão do ativo.

    Devolve (Series, aviso) — o aviso conta quando a curva termina antes do
    fim do período (IPCA sai com defasagem) ou quando a fonte de reserva
    entrou no lugar da principal. Devolve (None, motivo) se nada respondeu.
    """
    serie, origem, motivo = bruto if bruto is not None else fator(nome, inicio, fim)

    if serie is None or serie.empty:
        return None, motivo or f"{nome}: sem dados no período"

    # Alinha ao calendário do ativo: repete o último valor conhecido nos dias
    # sem cotação (fim de semana, feriado, mês ainda não divulgado). Os dois
    # lados passam pelo mesmo formato de data antes de se encontrarem.
    serie = serie.copy()
    serie.index = _sem_fuso(serie.index)
    alvo = _sem_fuso(datas_alvo)

    unido = serie.index.union(alvo)
    alinhado = serie.reindex(unido).ffill().reindex(alvo).ffill().bfill()
    # De volta ao índice original: é ele que casa com a curva do ativo no gráfico.
    alinhado.index = datas_alvo
    if alinhado.isna().all():
        return None, f"{nome}: sem sobreposição com o período"

    base = alinhado.iloc[0]
    if not base or pd.isna(base):
        return None, f"{nome}: série inconsistente"

    avisos = []
    if origem.startswith("IPEA"):
        avisos.append(f"{nome} veio do {origem}")
    ultima = serie.index[-1]
    if ultima < alvo[-1] - pd.Timedelta(days=20):
        avisos.append(f"{nome} vai até {ultima:%d/%m/%Y} (divulgação com defasagem)")

    return (alinhado / base - 1) * 100, "; ".join(avisos)
