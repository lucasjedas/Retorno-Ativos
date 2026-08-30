"""Fontes oficiais para precificar opção de dólar.

Nada aqui depende do resto do projeto, e nada no resto do projeto depende
daqui — de propósito: o app publicado não pode quebrar por causa desta parte.

| Dado                          | Fonte                                        |
|-------------------------------|----------------------------------------------|
| Strike, vencimento, dias úteis| B3, `InstrumentsConsolidated`                |
| Preço de ajuste do futuro (F) | B3, `TradeInformationConsolidated`           |
| Juro até o vencimento         | B3, curva de DI1 (ajuste); CDI/SGS 4389 de reserva |
| Cupom cambial                 | B3, FRC (limpo) e DDI (sujo)                 |
| Dólar à vista (PTAX)          | Banco Central, Olinda                        |
| Volatilidade implícita        | B3, superfície de dólar (veja superficie.py) |

Os dois arquivos da B3 são o *open data* do site de arquivos: pede-se o nome
e a data, a API devolve um token, e o token baixa um CSV em latin-1 cuja
primeira linha é "Status do Arquivo: Final" (o cabeçalho vem na segunda).
São arquivos grandes — o de instrumentos passa de 30 MB —, por isso ficam em
cache no disco, em `.cache_b3/`, um por data. Data sem pregão não tem
arquivo: `ultimo_pregao()` anda para trás até achar.

O SGS do Banco Central responde 406 a pedido vindo de servidor em nuvem. Como
esta parte é de terminal, roda da máquina de casa e não esbarra nisso — mas
se um dia for para a web, o juro precisa de reserva.
"""

import csv
import json
import math
import tempfile
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

B3_PEDIDO = "https://arquivos.b3.com.br/api/download/requestname?fileName={nome}&date={data}"
B3_BAIXA = "https://arquivos.b3.com.br/api/{caminho}"
SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados"
OLINDA = (
    "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
    "CotacaoDolarPeriodo(dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
    "?@dataInicial='{inicio}'&@dataFinalCotacao='{fim}'&$format=json"
    "&$select=cotacaoVenda,dataHoraCotacao"
)

SERIE_CDI = 4389          # CDI anualizado, base 252 — reserva do DI1
ESPERA = 60               # segundos; o arquivo de instrumentos é grande
PREGOES_ATRAS = 10        # até onde andar para trás procurando pregão
def _pasta_cache() -> Path:
    """Onde guardar os arquivos da B3.

    Primeiro a pasta do projeto; se ela não for gravável — o que pode
    acontecer num servidor — cai para a pasta temporária do sistema. Sem esta
    saída, um disco somente-leitura derrubaria a página inteira em vez de
    apenas custar um download a mais.
    """
    preferida = Path(__file__).resolve().parent / ".cache_b3"
    try:
        preferida.mkdir(exist_ok=True)
        teste = preferida / ".escrita"
        teste.write_text("ok")
        teste.unlink()
        return preferida
    except OSError:
        alternativa = Path(tempfile.gettempdir()) / "cache_b3_retorno_ativos"
        alternativa.mkdir(exist_ok=True)
        return alternativa


CACHE = _pasta_cache()

CABECALHOS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}


class SemDados(Exception):
    """A fonte respondeu, mas não tem o dado pedido."""


def _abrir(url: str, espera: int = ESPERA) -> bytes:
    pedido = urllib.request.Request(url, headers=CABECALHOS)
    with urllib.request.urlopen(pedido, timeout=espera) as resposta:
        return resposta.read()


def _json(url: str, espera: int = ESPERA):
    return json.loads(_abrir(url, espera).decode("utf-8"))


def numero(texto: str):
    """'5528,359' -> 5528.359. None se vier vazio ou impróprio."""
    texto = (texto or "").strip()
    if not texto:
        return None
    try:
        return float(texto.replace(".", "").replace(",", "."))
    except ValueError:
        return None


# ---------------------------------------------------------------- B3

def _baixar_b3(nome: str, dia: date) -> bytes:
    """CSV cru do open data da B3. SemDados se não houver arquivo no dia."""
    try:
        pedido = _json(B3_PEDIDO.format(nome=nome, data=dia.isoformat()), espera=30)
    except urllib.error.HTTPError as erro:
        if erro.code == 400:
            raise SemDados(f"B3 não tem {nome} em {dia:%d/%m/%Y}") from erro
        raise
    caminho = pedido.get("redirectUrl", "").lstrip("~/")
    if not caminho:
        raise SemDados(f"B3 não devolveu arquivo de {nome} em {dia:%d/%m/%Y}")
    return _abrir(B3_BAIXA.format(caminho=caminho))


def arquivo_b3(nome: str, dia: date) -> Path:
    """Baixa (ou reaproveita do cache) um arquivo do open data da B3."""
    CACHE.mkdir(exist_ok=True)
    destino = CACHE / f"{nome}_{dia.isoformat()}.csv"
    if destino.exists() and destino.stat().st_size > 0:
        return destino
    dados = _baixar_b3(nome, dia)
    provisorio = destino.with_suffix(".parcial")
    provisorio.write_bytes(dados)
    provisorio.replace(destino)      # só vira cache quando terminou de baixar
    return destino


def _linhas(caminho: Path):
    with open(caminho, encoding="latin-1", newline="") as arquivo:
        next(arquivo)                # "Status do Arquivo: Final"
        yield from csv.DictReader(arquivo, delimiter=";")


def tem_pregao(dia: date) -> bool:
    try:
        arquivo_b3("TradeInformationConsolidated", dia)
        return True
    except SemDados:
        return False


def ultimo_pregao(dia: date) -> date:
    """O próprio dia, ou o pregão anterior mais próximo."""
    for atras in range(PREGOES_ATRAS + 1):
        candidato = dia - timedelta(days=atras)
        if tem_pregao(candidato):
            return candidato
    raise SemDados(
        f"nenhum pregão da B3 nos {PREGOES_ATRAS} dias até {dia:%d/%m/%Y} "
        "(data no futuro, ou o open data ainda não publicou)"
    )


def instrumentos(dia: date, ativo: str = "DOL") -> dict:
    """Instrumentos do ativo negociados no dia -> {ticker: registro}."""
    caminho = arquivo_b3("InstrumentsConsolidated", dia)
    achados = {x["TckrSymb"]: x for x in _linhas(caminho) if x["Asst"] == ativo}
    if not achados:
        raise SemDados(f"B3 não lista instrumentos de {ativo} em {dia:%d/%m/%Y}")
    return achados


def ajustes(dia: date, prefixo: str = "DOL") -> dict:
    """Preço de ajuste do dia -> {ticker: preço}. Só quem tem ajuste entra."""
    caminho = arquivo_b3("TradeInformationConsolidated", dia)
    achados = {}
    for linha in _linhas(caminho):
        ticker = linha["TckrSymb"]
        if not ticker.startswith(prefixo):
            continue
        preco = numero(linha["AdjstdQt"])
        if preco is not None:
            achados[ticker] = preco
    return achados


def curva_di(dia: date) -> list:
    """Curva de juro pré do DI1 no dia -> [(vencimento, taxa, dias úteis)].

    O preço de ajuste do DI1 vem com a taxa já calculada no campo
    `AdjstdQtTax`, e o cadastro dá vencimento e dias úteis de cada vértice.
    É a fonte certa para descontar a opção: o CDI à vista é a taxa de um dia,
    e o que se quer é a taxa até o vencimento.
    """
    cadastro = instrumentos(dia, ativo="DI1")
    caminho = arquivo_b3("TradeInformationConsolidated", dia)
    vertices = []
    for linha in _linhas(caminho):
        ticker = linha["TckrSymb"]
        if not ticker.startswith("DI1"):
            continue
        taxa = numero(linha["AdjstdQtTax"])
        registro = cadastro.get(ticker)
        if taxa is None or registro is None or not registro["XprtnDt"]:
            continue
        vertices.append((
            date.fromisoformat(registro["XprtnDt"]),
            taxa / 100,
            int(registro["WrkgDays"]),
        ))
    vertices.sort()
    if not vertices:
        raise SemDados(f"sem curva de DI1 em {dia:%d/%m/%Y}")
    return vertices


def juro_ate(dia: date, vencimento: date) -> tuple:
    """Taxa pré até o vencimento -> (taxa, de onde veio).

    Vértice exato quando existe — e existe quase sempre, porque opção de dólar
    e DI1 vencem os dois no 1º dia útil do mês. Fora isso, interpolação
    exponencial: o que se interpola é o logaritmo do fator de capitalização
    contra dias úteis, que é a convenção da curva.
    """
    vertices = curva_di(dia)
    for venc, taxa, _ in vertices:
        if venc == vencimento:
            ticker_mes = f"{venc:%m/%Y}"
            return taxa, f"DI1 {ticker_mes}, vértice exato"

    antes = [v for v in vertices if v[0] < vencimento]
    depois = [v for v in vertices if v[0] > vencimento]
    if not antes or not depois:
        raise SemDados(
            f"o vencimento {vencimento:%d/%m/%Y} está fora da curva de DI1 "
            f"({vertices[0][0]:%m/%Y} a {vertices[-1][0]:%m/%Y})"
        )

    (venc_a, taxa_a, du_a), (venc_b, taxa_b, du_b) = antes[-1], depois[0]
    # dias úteis do vencimento, estimados na proporção dos dias corridos
    # entre os dois vértices — não há calendário de feriados aqui
    vao = (venc_b - venc_a).days
    fracao = (vencimento - venc_a).days / vao if vao else 0.0
    du = du_a + (du_b - du_a) * fracao
    if du <= 0 or du_a <= 0 or du_b <= du_a:
        raise SemDados("curva de DI1 sem prazo utilizável")

    ln_a = du_a * math.log1p(taxa_a)
    ln_b = du_b * math.log1p(taxa_b)
    ln = ln_a + (ln_b - ln_a) * (du - du_a) / (du_b - du_a)
    taxa = math.expm1(ln / du)
    return taxa, (f"DI1 interpolado entre {venc_a:%m/%Y} e {venc_b:%m/%Y}")


CUPOM = {
    "FRC": "limpo",     # FRA de Cupom Cambial de DI1 — à vista até o vencimento
    "DDI": "sujo",      # Cupom Cambial de DI1 — casado com a PTAX de D-1
}
BASE_CUPOM = 360        # o cupom é linear, base 360 dias corridos


def curva_cupom(dia: date, familia: str = "FRC") -> list:
    """Curva de cupom cambial -> [(vencimento, taxa, dias corridos)].

    `familia` é "FRC" (cupom limpo, que é o que o manual da B3 pede em §2.1)
    ou "DDI" (cupom sujo, casado com a PTAX do dia anterior). A taxa vem
    pronta no campo `AdjstdQtTax` do ajuste; o DDI ainda traz o PU, que
    obedece a `100000 / (1 + i * dc/360)` — linear, base 360 dias corridos,
    não 252 como o DI.
    """
    if familia not in CUPOM:
        raise ValueError(f"família de cupom precisa ser {' ou '.join(CUPOM)}")
    cadastro = instrumentos(dia, ativo=familia)
    caminho = arquivo_b3("TradeInformationConsolidated", dia)
    vertices = []
    for linha in _linhas(caminho):
        ticker = linha["TckrSymb"]
        if not ticker.startswith(familia):
            continue
        taxa = numero(linha["AdjstdQtTax"])
        registro = cadastro.get(ticker)
        if taxa is None or registro is None or not registro["XprtnDt"]:
            continue
        vencimento = date.fromisoformat(registro["XprtnDt"])
        vertices.append((vencimento, taxa / 100, (vencimento - dia).days))
    vertices.sort()
    if not vertices:
        raise SemDados(f"sem curva de {familia} em {dia:%d/%m/%Y}")
    return vertices


def cupom_ate(dia: date, vencimento: date, familia: str = "FRC") -> tuple:
    """Cupom cambial até o vencimento -> (taxa, de onde veio).

    Interpolação exponencial no logaritmo do fator `1 + i*dc/360`, contra dias
    corridos. Como o cupom vence no mesmo dia que a opção e que o DI, o
    vértice exato é a regra e a interpolação a exceção.
    """
    vertices = curva_cupom(dia, familia)
    for venc, taxa, _ in vertices:
        if venc == vencimento:
            return taxa, f"{familia} {venc:%m/%Y}, vértice exato"

    antes = [v for v in vertices if v[0] < vencimento]
    depois = [v for v in vertices if v[0] > vencimento]
    if not antes or not depois:
        raise SemDados(
            f"{vencimento:%d/%m/%Y} está fora da curva de {familia} "
            f"({vertices[0][0]:%m/%Y} a {vertices[-1][0]:%m/%Y})"
        )
    (venc_a, taxa_a, dc_a), (venc_b, taxa_b, dc_b) = antes[-1], depois[0]
    dc = (vencimento - dia).days
    if dc <= 0 or dc_b <= dc_a:
        raise SemDados(f"curva de {familia} sem prazo utilizável")
    ln_a = math.log1p(taxa_a * dc_a / BASE_CUPOM)
    ln_b = math.log1p(taxa_b * dc_b / BASE_CUPOM)
    ln = ln_a + (ln_b - ln_a) * (dc - dc_a) / (dc_b - dc_a)
    taxa = math.expm1(ln) * BASE_CUPOM / dc
    return taxa, f"{familia} interpolado entre {venc_a:%m/%Y} e {venc_b:%m/%Y}"


def ptax(dia: date, atras: int = 10) -> tuple:
    """Dólar de venda da PTAX até a data -> (cotação, data de fato).

    É o melhor à vista disponível de graça, mas não é o que a B3 usa: o
    manual pede o "dólar cupom limpo", que é o fechamento das 18h, e a PTAX
    é a média apurada por volta das 13h. A diferença aparece na conferência
    de paridade.
    """
    url = OLINDA.format(inicio=f"{dia - timedelta(days=atras):%m-%d-%Y}",
                        fim=f"{dia:%m-%d-%Y}")
    dados = _json(url, espera=30).get("value") or []
    cotacoes = sorted(
        (date.fromisoformat(x["dataHoraCotacao"][:10]), float(x["cotacaoVenda"]))
        for x in dados if x.get("cotacaoVenda")
    )
    if not cotacoes:
        raise SemDados(f"PTAX sem cotação até {dia:%d/%m/%Y}")
    return cotacoes[-1][1], cotacoes[-1][0]


def ptax_anterior(dia: date) -> tuple:
    """A PTAX do dia útil anterior — o à vista que casa com o cupom sujo."""
    return ptax(dia - timedelta(days=1))


# ---------------------------------------------------------------- Banco Central

def cdi_ao_ano(dia: date, atras: int = 15) -> tuple:
    """CDI anualizado base 252 na data -> (taxa decimal, data de fato).

    Devolve o último valor publicado até a data pedida: o SGS não publica em
    fim de semana e sai com um dia de defasagem.
    """
    url = SGS.format(serie=SERIE_CDI) + (
        f"?formato=json&dataInicial={dia - timedelta(days=atras):%d/%m/%Y}"
        f"&dataFinal={dia:%d/%m/%Y}"
    )
    dados = _json(url, espera=30)
    if not dados:
        raise SemDados(f"SGS {SERIE_CDI} sem CDI publicado até {dia:%d/%m/%Y}")
    ultimo = dados[-1]
    data = date(*reversed([int(p) for p in ultimo["data"].split("/")]))
    return float(ultimo["valor"]) / 100, data

