"""Séries macroeconômicas: CDI, IPCA e CPI.

Nenhuma delas existe no Yahoo Finance. Cada uma vem de uma fonte pública e é
devolvida como uma série de *nível* — um número índice — para poder ser
tratada igual a um preço: o retorno do período é o nível do fim dividido pelo
nível do começo.

| Série | Fonte                          | Reserva                    |
|-------|--------------------------------|----------------------------|
| CDI   | Banco Central, SGS 12 (diária) | IPEA BM12_TJCDI12 (mensal) |
| IPCA  | Banco Central, SGS 433         | IPEA PRECOS12_IPCAG12      |
| CPI   | BLS, CUUR0000SA0               | —                          |

A reserva existe porque o WAF do Banco Central responde 406 a pedidos vindos
de servidores em nuvem: de uma máquina doméstica a API abre normalmente, do
Streamlit Cloud não.
"""

import json
import urllib.request
from datetime import timedelta

import pandas as pd

SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados"
IPEA = "https://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='{codigo}')"
BLS = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
ESPERA = 15  # segundos; tela parada esperando fonte fora do ar não ajuda

CABECALHOS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}

SERIES = {
    "CDI": {
        "nome": "CDI — Certificado de Depósito Interbancário",
        "tipo": "variacao",          # a fonte dá a variação de cada período
        "sgs": 12,
        "ipea": "BM12_TJCDI12",
        "cor": "#7E8CA0",
    },
    "IPCA": {
        "nome": "IPCA — inflação oficial do Brasil",
        "tipo": "variacao",
        "sgs": 433,
        "ipea": "PRECOS12_IPCAG12",
        "cor": "#C79A3C",
    },
    "CPI": {
        "nome": "CPI — inflação ao consumidor dos EUA",
        "tipo": "nivel",             # a fonte já dá o número índice
        "bls": "CUUR0000SA0",
        "cor": "#B5654A",
    },
}


def _sem_fuso(datas) -> pd.DatetimeIndex:
    """DatetimeIndex sem fuso, na meia-noite do dia.

    Cada fonte data de um jeito: o IPEA manda offset (-03:00), o Yahoo manda o
    fuso da bolsa, o BCB e o BLS mandam só a data. Alinhar um índice com fuso
    contra um sem fuso devolve um Index de objetos no pandas 2 e levanta
    TypeError no pandas 3 — que é o que o Streamlit Cloud instala.
    """
    return pd.DatetimeIndex(pd.to_datetime(datas, utc=True)).tz_convert(None).normalize()


def _baixar(url: str, corpo=None):
    dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
    cabecalhos = dict(CABECALHOS)
    if dados:
        cabecalhos["Content-Type"] = "application/json"
    pedido = urllib.request.Request(url, data=dados, headers=cabecalhos)
    with urllib.request.urlopen(pedido, timeout=ESPERA) as resposta:
        return json.loads(resposta.read().decode("utf-8"))


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


def _variacoes_sgs(serie: int, inicio, fim):
    url = SGS.format(serie=serie) + (
        f"?formato=json&dataInicial={inicio:%d/%m/%Y}&dataFinal={fim:%d/%m/%Y}"
    )
    dados = _baixar(url)
    if not dados:
        return None
    datas = _sem_fuso(pd.to_datetime([x["data"] for x in dados], format="%d/%m/%Y"))
    return pd.Series([float(x["valor"]) for x in dados], index=datas).sort_index()


def _variacoes_ipea(codigo: str, inicio, fim):
    """Variações mensais do IPEA. O OData devolve a série inteira; recorto aqui."""
    dados = _baixar(IPEA.format(codigo=codigo))["value"]
    validos = [x for x in dados if x.get("VALVALOR") is not None]
    if not validos:
        return None
    serie = pd.Series(
        [float(x["VALVALOR"]) for x in validos],
        index=_sem_fuso([x["VALDATA"] for x in validos]),
    ).sort_index()
    desde = pd.Timestamp(inicio) - pd.Timedelta(days=45)
    ate = pd.Timestamp(fim)
    return serie[(serie.index >= desde) & (serie.index <= ate)]


def _nivel_bls(codigo: str, inicio, fim):
    """Número índice do CPI, direto da fonte oficial americana.

    A API pública aceita no máximo dez anos por chamada e devolve os meses em
    ordem inversa, um registro por mês, com o período no formato "M07".
    """
    blocos = []
    ano_ini, ano_fim = inicio.year, fim.year
    for comeco in range(ano_ini, ano_fim + 1, 10):
        fatia_fim = min(comeco + 9, ano_fim)
        resposta = _baixar(BLS, {
            "seriesid": [codigo],
            "startyear": str(comeco),
            "endyear": str(fatia_fim),
        })
        if resposta.get("status") != "REQUEST_SUCCEEDED":
            raise RuntimeError(f"BLS: {'; '.join(resposta.get('message') or ['recusou'])}")
        for serie in resposta["Results"]["series"]:
            blocos.extend(serie.get("data") or [])

    pontos = {}
    for x in blocos:
        periodo = x.get("period", "")
        if not periodo.startswith("M") or periodo == "M13":  # M13 é a média anual
            continue
        try:
            valor = float(x["value"])
        except (TypeError, ValueError):
            continue  # meses sem apuração vêm como "-"
        pontos[pd.Timestamp(int(x["year"]), int(periodo[1:]), 1)] = valor
    if not pontos:
        return None
    serie = pd.Series(pontos).sort_index()
    serie.index = _sem_fuso(serie.index)
    desde = pd.Timestamp(inicio) - pd.Timedelta(days=45)
    return serie[(serie.index >= desde) & (serie.index <= pd.Timestamp(fim))]


def nivel(nome: str, inicio, fim):
    """Série de nível (número índice) da série macro. -> (Series, origem).

    Levanta exceção se nenhuma fonte responder; quem chama decide o que
    mostrar. Para CDI e IPCA o nível sai da composição das variações, em
    base 100; para o CPI a fonte já entrega o número índice.
    """
    config = SERIES[nome]

    if config["tipo"] == "nivel":
        serie = _nivel_bls(config["bls"], inicio, fim)
        if serie is None or serie.empty:
            raise RuntimeError(f"{nome}: BLS sem dados no período")
        return serie, "BLS"

    try:
        taxas = _conferir_variacoes(
            _variacoes_sgs(config["sgs"], inicio - timedelta(days=45), fim), nome
        )
        if taxas is not None and not taxas.empty:
            return (1 + taxas / 100).cumprod() * 100, "Banco Central"
        falha = "resposta vazia"
    except Exception as erro:
        falha = f"{type(erro).__name__}: {erro}"

    taxas = _conferir_variacoes(_variacoes_ipea(config["ipea"], inicio, fim), nome)
    if taxas is None or taxas.empty:
        raise RuntimeError(f"{nome}: Banco Central ({falha}) e IPEA sem dados")
    return (1 + taxas / 100).cumprod() * 100, f"IPEA (mensal) — Banco Central recusou: {falha}"
