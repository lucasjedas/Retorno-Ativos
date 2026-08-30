"""Superfície de volatilidade de dólar publicada pela B3.

A B3 coleta cotações de um pool de informantes às 18h, ajusta uma
parametrização SVI e publica uma superfície de referência **por delta**: onze
colunas (delta 1, 5, 10, 25, 37, 50, 63, 75, 90, 95 e 99, em %) contra uma
linha por vencimento. É volatilidade implícita de mercado — o que os
operadores estão realmente praticando —, e não uma medida do passado como a
volatilidade histórica da PTAX.

Fonte: "Superfície de volatilidade de dólar", em Market Data > Consultas >
Mercado de derivativos > Preços referenciais. Vem num .zip com um único
.xlsx, `Superficie_Vol_VTC_ddmmaaaa.xlsx`.

**Só existe o pregão mais recente.** O .zip é sobrescrito todo dia e não há
arquivo por data; pedir data antiga devolve 302. Então a superfície serve
para precificar hoje, e para data passada é preciso outra fonte de
volatilidade. A data de referência vem na primeira célula da planilha e é
sempre conferida antes do uso.

**Como sair do delta e chegar no strike** (manual de apreçamento da B3,
seção 6.1). Os deltas são de *opção de compra*, e o strike correspondente é

    K = A * exp(-sigma*raiz(T) * N⁻¹(delta) + sigma²*T/2)

onde A é, para opção sobre dólar à vista, "o preço de ajuste do futuro de
dólar com o mesmo vencimento da opção" — o mesmo F que o Black-76 usa. Todos
os vencimentos de opção de DOL têm futuro de mesma data, então A sai direto,
sem interpolar. Convertidos os onze pontos, sobra uma curva de volatilidade
contra strike; a seção 6.2 manda interpolar por spline cúbico monótono, e
repetir a ponta quando o strike cai fora da faixa de delta 1% a 99%.

A escolha do prazo aqui quase não pesa: com 206 dias úteis contra 307
corridos, a volatilidade interpolada muda na quarta casa decimal.

**Cache com regra de relógio.** A B3 publica uma vez por dia, a partir da
coleta das 18h, então não faz sentido bater na fonte a cada chamada. A
planilha fica guardada em `.cache_b3/` e `data_esperada()` diz qual pregão já
deveria estar publicado: hoje se passou das 18h em dia de semana, senão o dia
útil anterior. Só quando a cópia local está atrás disso é que há download.

O carimbo de última conferência vai para disco (`.superficie_conferida`), e
não só para a memória do processo — é o que faz o cache valer entre execuções
do terminal, que é onde ele importa. Em feriado, a B3 continua servindo o
arquivo do dia anterior e a conta de `data_esperada()` fica adiantada; o
carimbo evita insistir na fonte a cada chamada, esperando `RECHECAGEM` antes
de tentar de novo.

Sem dependência externa: o .xlsx é lido com `zipfile` e `xml`, que é o que
ele é por dentro.
"""

import io
import math
import re
import urllib.request
import zipfile
from datetime import date, datetime, timedelta
from statistics import NormalDist
from xml.etree import ElementTree as ET

from fontes import CABECALHOS, CACHE, SemDados

ZIP = ("https://www.b3.com.br/data/files/16/35/6A/F9/623589100A29E189AC094EA8/"
       "Superficie-de-volatilidade-de-dolar.zip")
ESPERA = 60
EPOCA_EXCEL = date(1899, 12, 30)
HORA_PUBLICACAO = 18            # a coleta dos informantes é às 18h
RECHECAGEM = timedelta(minutes=30)   # espera antes de insistir na fonte
CARIMBO = "superficie_conferida"
PLANILHA = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

_NORMAL = NormalDist()
_memoria = {}


def _celulas(folha) -> list:
    """Linhas da planilha como [{coluna: número}], na ordem do arquivo."""
    linhas = []
    for linha in folha.iter(PLANILHA + "row"):
        valores = {}
        for celula in linha.iter(PLANILHA + "c"):
            valor = celula.find(PLANILHA + "v")
            if valor is None:
                continue
            coluna = re.match(r"[A-Z]+", celula.get("r")).group(0)
            try:
                valores[coluna] = float(valor.text)
            except (TypeError, ValueError):
                continue
        if valores:
            linhas.append(valores)
    return linhas


def _data_excel(serie: float) -> date:
    return EPOCA_EXCEL + timedelta(days=int(serie))


def data_esperada(agora: datetime = None) -> date:
    """O pregão cuja superfície já deveria estar publicada.

    Depois das 18h de um dia de semana, é o próprio dia; antes disso, ou no
    fim de semana, é o dia útil anterior. Feriado não entra na conta — não há
    calendário aqui —, e por isso a conta pode ficar um dia adiantada; quem
    trata disso é o carimbo de conferência.
    """
    agora = agora or datetime.now()
    dia = agora.date()
    if agora.hour < HORA_PUBLICACAO:
        dia -= timedelta(days=1)
    while dia.weekday() >= 5:          # sábado e domingo
        dia -= timedelta(days=1)
    return dia


def _guardadas() -> list:
    return sorted(CACHE.glob("Superficie_Vol_*.xlsx"))


def _conferido_em():
    """Quando foi a última ida à fonte. None se nunca."""
    carimbo = CACHE / CARIMBO
    if not carimbo.exists():
        return None
    try:
        return datetime.fromisoformat(carimbo.read_text().strip())
    except (ValueError, OSError):
        return None


def _marcar_conferencia(quando: datetime):
    CACHE.mkdir(exist_ok=True)
    try:
        (CACHE / CARIMBO).write_text(quando.isoformat())
    except OSError:
        pass                            # cache é conforto, não requisito


def baixar() -> bytes:
    """Vai na B3 e devolve o .xlsx de dentro do .zip, guardando em disco."""
    pedido = urllib.request.Request(
        ZIP, headers={**CABECALHOS, "Referer": "https://www.b3.com.br/"}
    )
    with urllib.request.urlopen(pedido, timeout=ESPERA) as resposta:
        bruto = resposta.read()

    pacote = zipfile.ZipFile(io.BytesIO(bruto))
    nomes = [n for n in pacote.namelist() if n.lower().endswith(".xlsx")]
    if not nomes:
        raise SemDados("o .zip da superfície não trouxe planilha")
    dados = pacote.read(nomes[0])

    CACHE.mkdir(exist_ok=True)
    destino = CACHE / nomes[0]
    provisorio = destino.with_suffix(".parcial")
    provisorio.write_bytes(dados)
    provisorio.replace(destino)
    return dados


def _ler(dados: bytes) -> dict:
    """Planilha -> {referencia, deltas, vencimentos}."""
    pacote = zipfile.ZipFile(io.BytesIO(dados))
    folha = ET.fromstring(pacote.read("xl/worksheets/sheet1.xml"))
    linhas = _celulas(folha)
    if len(linhas) < 2:
        raise SemDados("a planilha da superfície veio vazia")

    colunas = sorted({c for l in linhas for c in l}, key=lambda s: (len(s), s))
    primeira, demais = colunas[0], colunas[1:]

    cabecalho = linhas[0]
    vencimentos = {}
    for linha in linhas[1:]:
        # a planilha vem com linhas de enchimento zeradas no fim; a data de
        # série 0 do Excel viraria um vencimento de 30/12/1899
        if not linha.get(primeira):
            continue
        vols = [linha[c] / 100 for c in demais if c in linha]
        if not any(v > 0 for v in vols):
            continue
        vencimentos[_data_excel(linha[primeira])] = vols

    if not vencimentos:
        raise SemDados("a planilha da superfície não trouxe vencimento algum")

    return {
        "referencia": _data_excel(cabecalho[primeira]),
        "deltas": [cabecalho[c] for c in demais],
        "vencimentos": vencimentos,
    }


def carregar(forcar: bool = False) -> dict:
    """A superfície, do cache quando ele está em dia, da B3 quando não está.

    `forcar` ignora o cache e vai à fonte — é o que a opção --atualizar do
    terminal usa.
    """
    agora = datetime.now()
    esperado = data_esperada(agora)

    tabela = _memoria.get("tabela")
    if tabela is None:
        guardadas = _guardadas()
        if guardadas:
            try:
                tabela = _ler(guardadas[-1].read_bytes())
                _memoria["tabela"] = tabela
            except (OSError, SemDados, zipfile.BadZipFile, ET.ParseError):
                tabela = None           # cache corrompido: baixa de novo

    if not forcar and tabela is not None:
        if tabela["referencia"] >= esperado:
            return tabela
        conferido = _conferido_em()
        if conferido is not None and agora - conferido < RECHECAGEM:
            return tabela               # B3 atrasada ou feriado; não insistir

    try:
        nova = _ler(baixar())
    except (OSError, SemDados, zipfile.BadZipFile, ET.ParseError):
        if tabela is not None:
            _marcar_conferencia(agora)
            return tabela               # a cópia velha serve melhor que nada
        raise

    _marcar_conferencia(agora)
    _memoria["tabela"] = nova
    return nova


def estado() -> dict:
    """O que o cache tem hoje, sem ir à rede — para o terminal contar."""
    guardadas = _guardadas()
    return {
        "esperado": data_esperada(),
        "guardado": guardadas[-1].name if guardadas else None,
        "conferido": _conferido_em(),
        "arquivos": len(guardadas),
    }


def smile_em_strike(deltas, vols, futuro: float, prazo: float) -> list:
    """Converte o smile por delta em [(strike, vol)], do menor strike ao maior.

    Manual da B3, seção 6.1. Delta é de opção de compra: delta alto é strike
    baixo, então a lista sai invertida em relação às colunas.
    """
    pares = []
    for delta, vol in zip(deltas, vols):
        if not 0 < delta < 100 or vol <= 0:
            continue
        desvio = vol * math.sqrt(prazo)
        strike = futuro * math.exp(
            -desvio * _NORMAL.inv_cdf(delta / 100) + desvio * desvio / 2
        )
        pares.append((strike, vol))
    pares.sort()
    return pares


def _tangentes(xs, ys) -> list:
    """Inclinações de Fritsch-Carlson — spline cúbico que não inventa curva.

    Passos da seção 6.2 do manual: média das secantes, zero quando elas
    trocam de sinal, e o corte no círculo de raio 3 que garante monotonia.
    """
    n = len(xs)
    secantes = [(ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]) for i in range(n - 1)]
    inclinacoes = [secantes[0]] + [
        (secantes[i - 1] + secantes[i]) / 2 for i in range(1, n - 1)
    ] + [secantes[-1]]

    for i, secante in enumerate(secantes):
        if secante == 0:
            inclinacoes[i] = inclinacoes[i + 1] = 0.0
            continue
        alfa, beta = inclinacoes[i] / secante, inclinacoes[i + 1] / secante
        if alfa < 0:
            inclinacoes[i] = 0.0
            alfa = 0.0
        if beta < 0:
            inclinacoes[i + 1] = 0.0
            beta = 0.0
        soma = alfa * alfa + beta * beta
        if soma > 9:
            corte = 3 / math.sqrt(soma)
            inclinacoes[i] = corte * alfa * secante
            inclinacoes[i + 1] = corte * beta * secante
    return inclinacoes


def interpolar(pares: list, strike: float) -> float:
    """Volatilidade no strike, por spline cúbico monótono.

    Fora da faixa coberta pelos deltas 1% e 99%, repete a volatilidade da
    ponta, como manda a seção 6.2 — não extrapola.
    """
    if not pares:
        raise SemDados("smile vazio")
    xs = [k for k, _ in pares]
    ys = [v for _, v in pares]
    if len(pares) == 1 or strike <= xs[0]:
        return ys[0]
    if strike >= xs[-1]:
        return ys[-1]

    inclinacoes = _tangentes(xs, ys)
    for i in range(len(xs) - 1):
        if xs[i] <= strike <= xs[i + 1]:
            largura = xs[i + 1] - xs[i]
            t = (strike - xs[i]) / largura
            t2, t3 = t * t, t * t * t
            return (
                (2 * t3 - 3 * t2 + 1) * ys[i]
                + (t3 - 2 * t2 + t) * largura * inclinacoes[i]
                + (-2 * t3 + 3 * t2) * ys[i + 1]
                + (t3 - t2) * largura * inclinacoes[i + 1]
            )
    return ys[-1]


def volatilidade(vencimento: date, futuro: float, prazo: float, strike: float,
                 pregao: date = None) -> dict:
    """Volatilidade da superfície para uma opção -> vol, smile e procedência.

    `pregao`, se vier, é conferido contra a data de referência da superfície:
    a B3 só publica o arquivo do dia, então precificar data passada com ela
    seria misturar o mercado de hoje com o preço de ontem.
    """
    tabela = carregar()
    referencia = tabela["referencia"]
    if pregao is not None and pregao != referencia:
        raise SemDados(
            f"a superfície publicada é de {referencia:%d/%m/%Y} e o pregão "
            f"pedido é {pregao:%d/%m/%Y} — a B3 só publica o arquivo do dia"
        )

    vols = tabela["vencimentos"].get(vencimento)
    if not vols:
        disponiveis = ", ".join(f"{d:%m/%Y}" for d in sorted(tabela["vencimentos"]))
        raise SemDados(
            f"a superfície não traz o vencimento {vencimento:%d/%m/%Y}. "
            f"Tem: {disponiveis}"
        )

    pares = smile_em_strike(tabela["deltas"], vols, futuro, prazo)
    if not pares:
        raise SemDados(f"smile de {vencimento:%d/%m/%Y} sem ponto utilizável")

    dentro = pares[0][0] <= strike <= pares[-1][0]
    return {
        "vol": interpolar(pares, strike),
        "referencia": referencia,
        "vencimento": vencimento,
        "smile": pares,
        "deltas": tabela["deltas"],
        "vols_por_delta": vols,
        "dentro_da_faixa": dentro,
        "faixa": (pares[0][0], pares[-1][0]),
    }
