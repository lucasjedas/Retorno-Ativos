"""Resolução de códigos de ativos para o padrão do Yahoo Finance.

O usuário digita "IBOV", "PETR4", "SPX", "BOVA11"...  Aqui isso vira
"^BVSP", "PETR4.SA", "^GSPC", "BOVA11.SA".
"""

import re

# Índices e apelidos comuns -> símbolo oficial no Yahoo Finance
ALIASES = {
    # --- Índices Brasil ---
    "IBOV": "^BVSP",
    "IBOVESPA": "^BVSP",
    "BVSP": "^BVSP",
    "IBRX": "^IBX50",
    "IBXL": "^IBX50",
    "IFIX": "IFIX.SA",
    # --- Índices EUA ---
    "SP500": "^GSPC",
    "S&P500": "^GSPC",
    "SPX": "^GSPC",
    "GSPC": "^GSPC",
    "NASDAQ": "^IXIC",
    "IXIC": "^IXIC",
    "NDX": "^NDX",
    "NASDAQ100": "^NDX",
    "DOW": "^DJI",
    "DOWJONES": "^DJI",
    "DJI": "^DJI",
    "RUSSELL2000": "^RUT",
    "RUT": "^RUT",
    "VIX": "^VIX",
    # --- Outros mercados ---
    "FTSE": "^FTSE",
    "DAX": "^GDAXI",
    "NIKKEI": "^N225",
    # --- Câmbio / commodities / cripto ---
    "DOLAR": "BRL=X",
    "USDBRL": "BRL=X",
    "DOLAR/REAL": "BRL=X",
    "EURBRL": "EURBRL=X",
    "EURUSD": "EURUSD=X",
    "OURO": "GC=F",
    "GOLD": "GC=F",
    "PETROLEO": "CL=F",
    "OIL": "CL=F",
    "BITCOIN": "BTC-USD",
    "BTC": "BTC-USD",
    "ETHEREUM": "ETH-USD",
    "ETH": "ETH-USD",
}

# Ação/unit/BDR/ETF/FII brasileiro: 4 letras + 1 ou 2 dígitos (PETR4, BOVA11, HGLG11, AAPL34)
PADRAO_B3 = re.compile(r"^[A-Z]{4}\d{1,2}$")


"""Códigos que as pessoas costumam confundir -> o que provavelmente quiseram."""
CONFUSOES = {
    "IBOV": "IBOV (o índice) ou BOVA11 (o ETF que replica o Ibovespa)",
    "SP500": "SP500 (o índice) ou IVVB11 / SPY / VOO (ETFs que o replicam)",
    "NASDAQ": "NASDAQ (o índice) ou QQQ (ETF) ou NASD11 (ETF na B3)",
    "IFIX": "IFIX (o índice de fundos imobiliários)",
    "DOW": "DOW (o índice Dow Jones) ou DIA (ETF)",
    "BTC": "BTC (bitcoin em dólar) ou BITH11 (ETF de cripto na B3)",
}


def sugerir(entrada: str):
    """Dica quando o código digitado não existe (ex: 'IBOV11')."""
    codigo = normalizar(entrada)
    raiz = codigo.rstrip("0123456789")
    for chave in (codigo, raiz):
        if chave in CONFUSOES:
            return CONFUSOES[chave]
    return None


def normalizar(entrada: str) -> str:
    """Limpa o que o usuário digitou."""
    return entrada.strip().upper().replace(" ", "")


def candidatos(entrada: str):
    """Devolve os símbolos a tentar, em ordem de prioridade.

    Tentar mais de um evita que o usuário precise saber se o código leva
    ".SA" ou "^" na frente.
    """
    codigo = normalizar(entrada)
    if not codigo:
        return []

    lista = []

    def add(simbolo):
        if simbolo and simbolo not in lista:
            lista.append(simbolo)

    # 1) Apelido conhecido
    if codigo in ALIASES:
        add(ALIASES[codigo])

    # 2) Já veio pronto (".SA", "^GSPC", "BRL=X", "BTC-USD")
    if codigo.startswith("^") or "." in codigo or "=" in codigo or "-" in codigo:
        add(codigo)

    # 3) Padrão B3 -> acrescenta .SA
    if PADRAO_B3.match(codigo):
        add(f"{codigo}.SA")

    # 4) Como digitado (ticker dos EUA: AAPL, SPY, VOO, QQQ...)
    add(codigo)

    # 5) Último recurso: tenta a versão brasileira mesmo fora do padrão
    add(f"{codigo}.SA")

    return lista
