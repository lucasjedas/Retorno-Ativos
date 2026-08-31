"""Curvas de comparação para o gráfico: CDI, IPCA, Ibovespa e S&P 500.

As séries em si vêm de outros dois módulos — CDI e IPCA do macro.py, os dois
índices de bolsa do financeiro.py. O que este arquivo faz é pô-las na mesma
régua: retorno acumulado em %, começando em zero na primeira data do ativo,
para poderem ser desenhadas no mesmo eixo.
"""

from datetime import datetime

import pandas as pd

import macro
from financeiro import buscar_historico
from macro import _sem_fuso

# Ordem aqui é a ordem das caixas de marcar, da legenda e das cores.
BENCHMARKS = {
    "CDI":      {"fonte": "macro", "cor": macro.SERIES["CDI"]["cor"]},
    "IPCA":     {"fonte": "macro", "cor": macro.SERIES["IPCA"]["cor"]},
    "Ibovespa": {"fonte": "yahoo", "simbolo": "^BVSP", "cor": "#4B7BE5"},
    "S&P 500":  {"fonte": "yahoo", "simbolo": "^GSPC", "cor": "#9B59B6"},
}


def _nivel_yahoo(simbolo: str, inicio, fim):
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
    """Série de nível do índice. -> (Series, origem, motivo da falha).

    Só isto depende da rede, então é o que vale a pena guardar em cache — o
    alinhamento muda a cada ativo. O motivo vem junto porque um índice mudo
    na tela não diz se a fonte caiu, recusou o pedido ou não tem o período.
    """
    config = BENCHMARKS[nome]
    try:
        if config["fonte"] == "macro":
            serie, origem = macro.nivel(nome, inicio, fim)
        else:
            serie, origem = _nivel_yahoo(config["simbolo"], inicio, fim)
    except Exception as erro:
        return None, "", f"{nome}: {type(erro).__name__}: {erro}"

    if serie is None or serie.empty:
        return None, origem, f"{nome}: a fonte respondeu sem dados para o período"
    return serie, origem, ""


def curva(nome: str, inicio, fim, datas_alvo, bruto=None):
    """Retorno acumulado em %, alinhado às datas de pregão do ativo.

    Devolve (Series, aviso) — o aviso conta quando a curva termina antes do
    fim do período (IPCA e CPI saem com defasagem) ou quando a fonte de
    reserva entrou no lugar da principal. Devolve (None, motivo) se nada
    respondeu.
    """
    # Um 'bruto' fora do formato esperado é entrada de cache gravada por uma
    # versão anterior deste arquivo: o Streamlit guarda o resultado por chave
    # de função e argumentos, e a função que chama esta aqui não mudou de
    # corpo quando o formato do retorno mudou. Buscar de novo é mais barato
    # que servir um dado que não dá para ler.
    if bruto is not None and len(bruto) == 3:
        serie, origem, motivo = bruto
    else:
        serie, origem, motivo = fator(nome, inicio, fim)

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
    if "reserva" in origem:
        avisos.append(f"{nome} veio de fonte de reserva: {origem}")
    ultima = serie.index[-1]
    if ultima < alvo[-1] - pd.Timedelta(days=20):
        avisos.append(f"{nome} vai até {ultima:%d/%m/%Y} (divulgação com defasagem)")

    return (alinhado / base - 1) * 100, "; ".join(avisos)
