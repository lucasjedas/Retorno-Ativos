"""Índices de comparação para o gráfico: CDI, IPCA, Ibovespa e S&P 500.

CDI e IPCA não existem no Yahoo Finance — vêm do SGS, a API pública de séries
temporais do Banco Central. Ibovespa e S&P 500 reaproveitam a busca do
financeiro.py.

Toda curva devolvida aqui é retorno acumulado em %, começando em zero na
primeira data do ativo, para poder ser desenhada no mesmo eixo.
"""

import json
import urllib.request
from datetime import timedelta

import pandas as pd

from financeiro import buscar_historico

SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados"

# Ordem aqui é a ordem da legenda e das cores no gráfico.
BENCHMARKS = {
    "CDI":       {"fonte": "bcb",    "serie": 12,  "cor": "#7E8CA0"},
    "IPCA":      {"fonte": "bcb",    "serie": 433, "cor": "#C79A3C"},
    "Ibovespa":  {"fonte": "yahoo",  "simbolo": "^BVSP", "cor": "#4B7BE5"},
    "S&P 500":   {"fonte": "yahoo",  "simbolo": "^GSPC", "cor": "#9B59B6"},
}


def _sgs(serie: int, inicio, fim):
    """Baixa uma série do Banco Central. Devolve Series (data -> valor %)."""
    url = SGS.format(serie=serie) + (
        f"?formato=json&dataInicial={inicio:%d/%m/%Y}&dataFinal={fim:%d/%m/%Y}"
    )
    pedido = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(pedido, timeout=15) as resposta:
        dados = json.loads(resposta.read().decode("utf-8"))

    if not dados:
        return None
    datas = pd.to_datetime([x["data"] for x in dados], format="%d/%m/%Y")
    valores = [float(x["valor"]) for x in dados]
    return pd.Series(valores, index=datas).sort_index()


def _fator_bcb(serie: int, inicio, fim):
    """Fator acumulado de uma série de variações percentuais do BCB.

    A margem para trás existe por causa do IPCA: ele é mensal e vem datado no
    dia 1º, então sem folga o mês em que o período começa ficaria de fora.
    """
    taxas = _sgs(serie, inicio - timedelta(days=45), fim)
    if taxas is None or taxas.empty:
        return None
    return (1 + taxas / 100).cumprod()


def _fator_yahoo(simbolo: str, inicio, fim):
    """Fator acumulado de um índice do Yahoo (preço normalizado)."""
    from datetime import datetime

    _, df, _, _ = buscar_historico(
        simbolo,
        datetime.combine(inicio, datetime.min.time()),
        datetime.combine(fim, datetime.min.time()),
    )
    if df is None:
        return None
    coluna = "Adj Close" if "Adj Close" in df.columns else "Close"
    serie = df[coluna].dropna()
    if serie.index.tz is not None:
        serie = serie.tz_localize(None)
    return serie


def fator(nome: str, inicio, fim):
    """Baixa a série bruta do índice. Devolve (Series, "") ou (None, motivo).

    Separado do alinhamento de propósito: só isto depende da rede, então é o
    que vale a pena guardar em cache. O motivo da falha vem junto porque um
    índice mudo na tela não diz se a fonte caiu, recusou o pedido ou apenas
    não tem dado para o período.
    """
    config = BENCHMARKS[nome]
    try:
        if config["fonte"] == "bcb":
            serie = _fator_bcb(config["serie"], inicio, fim)
        else:
            serie = _fator_yahoo(config["simbolo"], inicio, fim)
    except Exception as erro:
        return None, f"{nome}: {type(erro).__name__}: {erro}"

    if serie is None or serie.empty:
        return None, f"{nome}: a fonte respondeu sem dados para o período"
    return serie, ""


def curva(nome: str, inicio, fim, datas_alvo, serie_fator=None):
    # serie_fator, quando vem, é a tupla (Series, motivo) devolvida por fator().
    """Retorno acumulado em %, alinhado às datas de pregão do ativo.

    Devolve (Series, aviso) — o aviso conta quando a série termina antes do
    fim do período, como acontece com o IPCA, divulgado com defasagem.
    Devolve (None, motivo) se a fonte não respondeu.
    """
    if serie_fator is None:
        serie, motivo = fator(nome, inicio, fim)
    else:
        serie, motivo = serie_fator

    if serie is None or serie.empty:
        return None, motivo or f"{nome}: sem dados no período"

    # Alinha ao calendário do ativo: repete o último valor conhecido nos dias
    # sem cotação (fim de semana, feriado, mês do IPCA ainda não divulgado).
    unido = serie.index.union(datas_alvo)
    alinhado = serie.reindex(unido).ffill().reindex(datas_alvo)
    alinhado = alinhado.ffill().bfill()
    if alinhado.isna().all():
        return None, f"{nome}: sem sobreposição com o período"

    base = alinhado.iloc[0]
    if not base or pd.isna(base):
        return None, f"{nome}: série inconsistente"

    aviso = ""
    ultima = serie.index[-1]
    if ultima < datas_alvo[-1] - pd.Timedelta(days=20):
        aviso = f"{nome} vai até {ultima:%d/%m/%Y} (divulgação com defasagem)"

    return (alinhado / base - 1) * 100, aviso
