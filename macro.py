"""Séries macroeconômicas: CDI, IPCA e CPI.

Nenhuma delas existe no Yahoo Finance. Cada uma vem de uma fonte pública e é
devolvida como uma série de *nível* — um número índice — para poder ser
tratada igual a um preço: o retorno do período é o nível do fim dividido pelo
nível do começo.

| Série | Fonte                          | Reservas, em ordem                  |
|-------|--------------------------------|-------------------------------------|
| CDI   | Banco Central, SGS 12 (diária) | SGS 4391 (mensal) → IPEA (mensal)   |
| IPCA  | Banco Central, SGS 433         | IBGE 1737/2266 → IPEA               |
| CPI   | BLS, CUUR0000SA0               | —                                   |

As reservas existem porque o WAF do Banco Central responde 406 a pedidos
vindos de servidores em nuvem: de uma máquina doméstica a API abre
normalmente, do Streamlit Cloud não.

**O IPEA saiu do ar em 30/08/2026** e com ele foi a única reserva que havia —
CDI e IPCA quebraram no app publicado. Daí as duas mudanças:

1. O **IBGE entrou como reserva do IPCA**, e é a fonte primária dele: o
   agregado 1737 dá o número-índice (variável 2266) de 1979 em diante, num
   pedido pequeno, de um provedor que não tem nada a ver com o Banco Central.
   Reserva boa é reserva que cai junto com o titular por motivos diferentes.
2. O CDI ganhou o **SGS 4391** (acumulado no mês) antes do IPEA. Mesmo host,
   então não escapa do bloqueio por IP, mas é um pedido muito menor.

**O 406 tem duas causas, e uma delas era defeito daqui.** Além do bloqueio por
IP, o SGS recusa série diária longa num pedido só: 20 anos de CDI davam 406 em
0,1s, e 10 anos levavam 19s — mais que o timeout de 15s deste módulo, ou seja,
falhavam de qualquer jeito. Por isso `_variacoes_sgs()` fatia o período em
blocos de `ANOS_POR_FATIA`. As mesmas duas décadas, em quatro fatias, vêm
inteiras.
"""

import gzip
import json
import urllib.request
import zlib
from datetime import timedelta

import pandas as pd

SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados"
IPEA = "https://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='{codigo}')"
BLS = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
IBGE = ("https://servicodados.ibge.gov.br/api/v3/agregados/{agregado}"
        "/periodos/{inicio}-{fim}/variaveis/{variavel}?localidades=N1")
ESPERA = 20         # segundos para a fonte principal
ESPERA_RESERVA = 8  # a reserva desiste rápido: a tela já esperou a principal
ANOS_POR_FATIA = 5  # o SGS recusa (406) série diária longa num pedido só

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
        "sgs_mensal": 4391,          # CDI acumulado no mês
        "ipea": "BM12_TJCDI12",
        "cor": "#7E8CA0",
    },
    "IPCA": {
        "nome": "IPCA — inflação oficial do Brasil",
        "tipo": "variacao",
        "sgs": 433,
        "ibge": {"agregado": 1737, "variavel": 2266},   # número-índice
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


def _descomprimir(bruto: bytes, codificacao: str = "") -> bytes:
    """Desfaz gzip/deflate quando a fonte comprime a resposta.

    O `urllib` não descomprime sozinho. O IBGE responde com gzip de forma
    intermitente — o CDN decide a cada pedido —, então o mesmo endereço às
    vezes decodifica e às vezes explode com UnicodeDecodeError. Olhar só o
    cabeçalho não basta: aqui vale também o número mágico do gzip.
    """
    if codificacao == "gzip" or bruto[:2] == b"\x1f\x8b":
        return gzip.decompress(bruto)
    if codificacao == "deflate":
        try:
            return zlib.decompress(bruto)
        except zlib.error:
            return zlib.decompress(bruto, -zlib.MAX_WBITS)   # deflate cru
    return bruto


def _baixar(url: str, corpo=None, espera: int = ESPERA):
    dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
    cabecalhos = dict(CABECALHOS)
    if dados:
        cabecalhos["Content-Type"] = "application/json"
    pedido = urllib.request.Request(url, data=dados, headers=cabecalhos)
    with urllib.request.urlopen(pedido, timeout=espera) as resposta:
        bruto = resposta.read()
        codificacao = (resposta.headers.get("Content-Encoding") or "").lower()
    return json.loads(_descomprimir(bruto, codificacao).decode("utf-8"))


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


def _fatias(inicio, fim, anos: int = ANOS_POR_FATIA):
    """Quebra o período em blocos de no máximo `anos`, sem sobrepor."""
    blocos = []
    passo = pd.DateOffset(years=anos)
    corte = pd.Timestamp(inicio)
    limite = pd.Timestamp(fim)
    while corte <= limite:
        fim_bloco = min(corte + passo - pd.Timedelta(days=1), limite)
        blocos.append((corte, fim_bloco))
        corte = fim_bloco + pd.Timedelta(days=1)
    return blocos


def _variacoes_sgs(serie: int, inicio, fim):
    """Variações da série no SGS, pedidas em fatias.

    Um pedido só cobrindo décadas é recusado com 406, e mesmo dez anos passam
    do tempo de espera. Em blocos, cada pedido volta em segundos.
    """
    pedacos = []
    for comeco, termino in _fatias(inicio, fim):
        url = SGS.format(serie=serie) + (
            f"?formato=json&dataInicial={comeco:%d/%m/%Y}"
            f"&dataFinal={termino:%d/%m/%Y}"
        )
        dados = _baixar(url)
        if not dados:
            continue
        datas = _sem_fuso(
            pd.to_datetime([x["data"] for x in dados], format="%d/%m/%Y")
        )
        pedacos.append(
            pd.Series([float(x["valor"]) for x in dados], index=datas)
        )
    if not pedacos:
        return None
    juntas = pd.concat(pedacos).sort_index()
    return juntas[~juntas.index.duplicated(keep="first")]


def _nivel_ibge(config: dict, inicio, fim):
    """Número-índice do IPCA direto do IBGE, que é quem apura o índice.

    O agregado devolve os meses como {"202601": "7427.72"}. Já vem em nível,
    então não passa pela composição de variações.
    """
    # a mesma folga que as fontes de variação usam, para as séries começarem
    # no mesmo mês e o acumulado não depender de qual fonte respondeu
    desde = (pd.Timestamp(inicio) - pd.Timedelta(days=45)).strftime("%Y%m")
    ate = pd.Timestamp(fim).strftime("%Y%m")
    resposta = _baixar(IBGE.format(inicio=desde, fim=ate, **config))
    if not resposta:
        return None
    try:
        bruto = resposta[0]["resultados"][0]["series"][0]["serie"]
    except (KeyError, IndexError, TypeError) as erro:
        raise RuntimeError(f"IBGE devolveu formato inesperado: {erro}") from erro

    pontos = {}
    for periodo, valor in bruto.items():
        try:
            pontos[pd.Timestamp(int(periodo[:4]), int(periodo[4:]), 1)] = float(valor)
        except (TypeError, ValueError):
            continue          # mês sem apuração vem como "..." ou "-"
    if not pontos:
        return None
    serie = pd.Series(pontos).sort_index()
    serie.index = _sem_fuso(serie.index)
    if float(serie.max()) < 50:
        raise RuntimeError(
            "IBGE: a série não parece número-índice "
            f"(máximo de {float(serie.max()):.2f}) — variável errada?"
        )
    return serie[serie.index <= pd.Timestamp(fim)]


def _variacoes_ipea(codigo: str, inicio, fim):
    """Variações mensais do IPEA. O OData devolve a série inteira; recorto aqui.

    Espera curta de propósito: o IPEA é a última reserva e saiu do ar em
    30/08/2026 sem recusar a conexão — ele simplesmente não responde. Com a
    espera cheia, cada consulta ficava 20 segundos parada antes de desistir,
    e o usuário via a tela travar a cada clique.
    """
    dados = _baixar(IPEA.format(codigo=codigo), espera=ESPERA_RESERVA)["value"]
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


def _de_variacoes(taxas, nome: str):
    """Variações percentuais -> número índice base 100. None se vier vazio."""
    taxas = _conferir_variacoes(taxas, nome)
    if taxas is None or taxas.empty:
        return None
    return (1 + taxas / 100).cumprod() * 100


def _fontes_de(nome: str, config: dict, inicio, fim) -> list:
    """As fontes da série, da melhor para a última -> [(rótulo, função)].

    O rótulo vai para a tela, e "reserva" nele é o que faz o app avisar que
    não veio da fonte principal. A ordem é deliberada: primeiro o Banco
    Central, que é diário no CDI; depois o IBGE, que apura o IPCA e não
    compartilha infraestrutura com o BCB; e só então as reservas mensais.
    """
    desde = inicio - timedelta(days=45)
    tentativas = [(
        "Banco Central",
        lambda: _de_variacoes(_variacoes_sgs(config["sgs"], desde, fim), nome),
    )]
    if config.get("ibge"):
        tentativas.append((
            "IBGE (reserva)",
            lambda: _nivel_ibge(config["ibge"], inicio, fim),
        ))
    if config.get("sgs_mensal"):
        tentativas.append((
            "Banco Central mensal (reserva)",
            lambda: _de_variacoes(
                _variacoes_sgs(config["sgs_mensal"], desde, fim), nome
            ),
        ))
    if config.get("ipea"):
        tentativas.append((
            "IPEA mensal (reserva)",
            lambda: _de_variacoes(_variacoes_ipea(config["ipea"], inicio, fim), nome),
        ))
    return tentativas


def nivel(nome: str, inicio, fim):
    """Série de nível (número índice) da série macro. -> (Series, origem).

    Tenta as fontes em ordem e devolve a primeira que responder, junto do
    rótulo dela. Se nenhuma responder, levanta com o motivo de cada uma —
    sem isso, um índice mudo na tela não diz se a fonte caiu, recusou o
    pedido ou simplesmente não cobre o período.

    Para CDI e IPCA o nível sai da composição das variações, em base 100;
    para o CPI e para o IBGE a fonte já entrega o número índice.
    """
    config = SERIES[nome]

    if config["tipo"] == "nivel":
        serie = _nivel_bls(config["bls"], inicio, fim)
        if serie is None or serie.empty:
            raise RuntimeError(f"{nome}: BLS sem dados no período")
        return serie, "BLS"

    falhas = []
    for rotulo, buscar in _fontes_de(nome, config, inicio, fim):
        try:
            serie = buscar()
        except Exception as erro:
            falhas.append(f"{rotulo}: {type(erro).__name__}: {erro}")
            continue
        if serie is None or serie.empty:
            falhas.append(f"{rotulo}: sem dados no período")
            continue
        return serie, rotulo

    raise RuntimeError(f"{nome}: nenhuma fonte respondeu — " + "; ".join(falhas))
