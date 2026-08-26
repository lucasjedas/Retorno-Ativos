"""Busca de cotações e cálculo de retorno.

Módulo compartilhado pelo programa de terminal (main.py) e pelo app web
(app.py). Fonte dos dados: Yahoo Finance.
"""

import contextlib
import io
import logging
import time
import warnings
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

import yfinance as yf  # noqa: E402  (depois do filtro de warnings, de propósito)

import pandas as pd

import macro as series_macro
from tickers import candidatos, macro_de

FORMATOS_DATA = ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y")
SIMBOLO_MOEDA = {"BRL": "R$", "USD": "US$", "EUR": "€", "GBP": "£", "JPY": "¥"}


@contextlib.contextmanager
def sem_ruido():
    """Engole o que a biblioteca imprime ao testar códigos que não existem."""
    lixo = io.StringIO()
    with contextlib.redirect_stderr(lixo), contextlib.redirect_stdout(lixo):
        yield


def ler_data(texto: str):
    """Converte '31/12/2024' (ou variantes) em datetime. None se inválida."""
    texto = (texto or "").strip()
    for formato in FORMATOS_DATA:
        try:
            return datetime.strptime(texto, formato)
        except ValueError:
            continue
    return None


TENTATIVAS = 3          # o Yahoo recusa pedidos em rajada; vale insistir
ESPERA_ENTRE = 1.5      # segundos, dobrando a cada nova tentativa


def buscar_historico(entrada: str, inicio: datetime, fim: datetime, diagnostico=None):
    """Tenta cada símbolo candidato até achar dados no período.

    Retorna (simbolo, DataFrame, moeda, nome) ou (None, None, None, None).

    'diagnostico', se for uma lista, recebe uma linha por tentativa frustrada.
    Sem isso a falha fica muda: o Yahoo costuma recusar pedidos vindos de
    servidores em nuvem, e sem o motivo registrado não dá para distinguir
    isso de um código de ativo inexistente.
    """
    # O Yahoo trata 'end' como exclusivo: soma 1 dia para incluir a data final.
    fim_exclusivo = fim + timedelta(days=1)

    def anotar(texto):
        if diagnostico is not None:
            diagnostico.append(texto)

    # CDI, IPCA e CPI não são ativos negociados: vêm de fonte própria, como
    # número índice. Daqui para baixo tudo trata a série igual a um preço.
    nome_macro = macro_de(entrada)
    if nome_macro:
        try:
            serie, origem = series_macro.nivel(nome_macro, inicio, fim)
        except Exception as erro:
            anotar(f"{nome_macro}: {type(erro).__name__}: {erro}")
            return None, None, None, None
        if serie is None or len(serie) < 2:
            anotar(f"{nome_macro}: menos de duas leituras no período")
            return None, None, None, None
        df = pd.DataFrame({"Close": serie, "Adj Close": serie})
        descricao = series_macro.SERIES[nome_macro]["nome"]
        return nome_macro, df, "", f"{descricao} · fonte: {origem}"

    for simbolo in candidatos(entrada):
        df = None
        for tentativa in range(1, TENTATIVAS + 1):
            try:
                with sem_ruido():
                    papel = yf.Ticker(simbolo)
                    df = papel.history(
                        start=inicio.strftime("%Y-%m-%d"),
                        end=fim_exclusivo.strftime("%Y-%m-%d"),
                        auto_adjust=False,
                        actions=False,
                    )
            except Exception as erro:
                anotar(f"{simbolo} (tentativa {tentativa}): {type(erro).__name__}: {erro}")
                df = None
            else:
                if df is not None and not df.empty:
                    break
                anotar(f"{simbolo} (tentativa {tentativa}): resposta vazia")
                df = None

            if tentativa < TENTATIVAS:
                time.sleep(ESPERA_ENTRE * tentativa)

        if df is None or df.empty or "Close" not in df.columns:
            continue

        df = df.dropna(subset=["Close"])
        if len(df) < 2:
            anotar(f"{simbolo}: só {len(df)} pregão(ões) no período")
            continue

        moeda, nome = "", simbolo
        with sem_ruido():
            try:
                info = papel.fast_info
                moeda = (info.get("currency") or "") if hasattr(info, "get") else ""
            except Exception:
                pass
            try:
                dados = papel.info
                nome = dados.get("longName") or dados.get("shortName") or simbolo
            except Exception:
                pass

        return simbolo, df, moeda, nome

    return None, None, None, None


def calcular(df):
    """Métricas do período a partir do histórico."""
    # 'Adj Close' já embute proventos e desdobramentos (retorno total).
    coluna_total = "Adj Close" if "Adj Close" in df.columns else "Close"
    serie_total = df[coluna_total].dropna()
    serie_preco = df["Close"].dropna()

    inicio_total, fim_total = float(serie_total.iloc[0]), float(serie_total.iloc[-1])
    inicio_preco, fim_preco = float(serie_preco.iloc[0]), float(serie_preco.iloc[-1])

    retorno_total = fim_total / inicio_total - 1
    retorno_preco = fim_preco / inicio_preco - 1

    data_ini = serie_total.index[0].to_pydatetime()
    data_fim = serie_total.index[-1].to_pydatetime()
    dias = max((data_fim - data_ini).days, 1)
    anos = dias / 365.25

    # Taxas equivalentes por juros compostos: a taxa que, repetida a cada
    # mês (ou ano) do período, chega exatamente ao mesmo retorno acumulado.
    # Não é o retorno acumulado dividido pelo número de meses — isso ignoraria
    # o efeito dos juros sobre juros.
    meses = anos * 12
    perda_total = retorno_total <= -1  # (1+r)^x não existe para r <= -1

    # Anualizar só faz sentido a partir de ~1 mês de janela; abaixo disso a
    # extrapolação (36x ou mais) diria mais sobre o ruído do que sobre o ativo.
    anualizado = (
        (1 + retorno_total) ** (1 / anos) - 1
        if anos >= 0.08 and not perda_total else None
    )
    # A taxa mensal extrapola bem menos, então aceita janelas mais curtas.
    mensal = (
        (1 + retorno_total) ** (1 / meses) - 1
        if dias >= 7 and not perda_total else None
    )

    drawdown = float((serie_total / serie_total.cummax() - 1).min())

    variacao_diaria = serie_total.pct_change().dropna()
    volatilidade = (
        float(variacao_diaria.std() * (252 ** 0.5)) if len(variacao_diaria) > 1 else None
    )

    melhor_dia = pior_dia = None
    if not variacao_diaria.empty:
        melhor_dia = (variacao_diaria.idxmax().to_pydatetime(), float(variacao_diaria.max()))
        pior_dia = (variacao_diaria.idxmin().to_pydatetime(), float(variacao_diaria.min()))

    # IPCA e CPI têm uma leitura por mês; chamar isso de "pregão" seria dizer
    # que três anos de IPCA tiveram 37 dias de negociação.
    intervalo = serie_total.index.to_series().diff().dt.days.median()
    cadencia = "leituras mensais" if intervalo and intervalo > 20 else "pregões"

    return {
        "cadencia": cadencia,
        "data_ini": data_ini,
        "data_fim": data_fim,
        "preco_ini": inicio_preco,
        "preco_fim": fim_preco,
        "retorno_total": retorno_total,
        "retorno_preco": retorno_preco,
        "tem_proventos": coluna_total == "Adj Close" and abs(retorno_total - retorno_preco) > 1e-6,
        "anualizado": anualizado,   # taxa média anual (equivalente composta)
        "mensal": mensal,           # taxa média mensal (equivalente composta)
        "meses": meses,
        "anos": anos,
        "drawdown": drawdown,
        "volatilidade": volatilidade,
        "pregoes": len(serie_total),
        "maxima": float(serie_preco.max()),
        "minima": float(serie_preco.min()),
        "melhor_dia": melhor_dia,
        "pior_dia": pior_dia,
        "serie": serie_total,
    }


# --------------------------------------------------------------------------
# Formatação no padrão brasileiro
# --------------------------------------------------------------------------
def pct(valor, sinal=True):
    modelo = f"{valor * 100:+,.2f}%" if sinal else f"{valor * 100:,.2f}%"
    return modelo.replace(",", "@").replace(".", ",").replace("@", ".")


def dinheiro(valor, simbolo):
    texto = f"{valor:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
    return f"{simbolo} {texto}" if simbolo else texto


def data_br(data):
    return data.strftime("%d/%m/%Y")
