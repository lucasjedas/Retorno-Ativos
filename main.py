"""Retorno acumulado de um ativo entre duas datas — versão de terminal.

Fonte dos dados: Yahoo Finance — cobre ações, ETFs, FIIs, BDRs, índices
(Brasil e EUA), câmbio, commodities e cripto.

Uso:
    python main.py                    # modo interativo
    python main.py PETR4 01/01/2020 31/12/2024
"""

import sys

try:
    from financeiro import (
        SIMBOLO_MOEDA,
        buscar_historico,
        calcular,
        data_br,
        dinheiro,
        ler_data,
        pct,
    )
except ImportError:
    sys.exit(
        "\nA biblioteca yfinance não está instalada.\n"
        "Rode:  pip install -r requirements.txt\n"
    )

from tickers import normalizar, sugerir


def perguntar_data(rotulo: str):
    while True:
        entrada = input(rotulo).strip()
        if entrada.lower() in ("sair", "q", "exit"):
            return None
        data = ler_data(entrada)
        if data:
            return data
        print("   Data inválida. Use o formato dd/mm/aaaa (ex: 05/01/2021).")


def exibir(entrada, simbolo, nome, moeda, m):
    cifra = SIMBOLO_MOEDA.get(moeda, moeda)
    largura = 62

    print()
    print("=" * largura)
    titulo = nome if nome and nome != simbolo else normalizar(entrada)
    print(f"  {titulo}")
    print(f"  {simbolo}  ·  {data_br(m['data_ini'])} → {data_br(m['data_fim'])}"
          f"  ·  {m['pregoes']} {m['cadencia']}")
    print("=" * largura)
    print()
    print(f"  Preço inicial ......... {dinheiro(m['preco_ini'], cifra)}")
    print(f"  Preço final ........... {dinheiro(m['preco_fim'], cifra)}")
    print()
    print(f"  RETORNO ACUMULADO ..... {pct(m['retorno_total'])}")
    if m["tem_proventos"]:
        print(f"     · só variação de preço ....... {pct(m['retorno_preco'])}")
        print(f"     · com proventos reinvestidos . {pct(m['retorno_total'])}")
    if m["mensal"] is not None:
        print(f"  Retorno médio mensal .. {pct(m['mensal'])} a.m.")
    if m["anualizado"] is not None:
        print(f"  Retorno médio anual ... {pct(m['anualizado'])} a.a.")
    if m["mensal"] is not None or m["anualizado"] is not None:
        print("     · taxas equivalentes: compostas ao longo do período,")
        print("       chegam ao mesmo retorno acumulado acima.")
    print()
    valor_final = 1000 * (1 + m["retorno_total"])
    print(f"  {dinheiro(1000, cifra)} investidos virariam {dinheiro(valor_final, cifra)}")
    print()
    print(f"  Máxima no período ..... {dinheiro(m['maxima'], cifra)}")
    print(f"  Mínima no período ..... {dinheiro(m['minima'], cifra)}")
    print(f"  Queda máxima .......... {pct(m['drawdown'])}")
    if m["volatilidade"] is not None:
        print(f"  Volatilidade anual .... {pct(m['volatilidade'], sinal=False)}")
    if m["melhor_dia"]:
        print(f"  Melhor dia ............ {pct(m['melhor_dia'][1])} em {data_br(m['melhor_dia'][0])}")
    if m["pior_dia"]:
        print(f"  Pior dia .............. {pct(m['pior_dia'][1])} em {data_br(m['pior_dia'][0])}")
    print()
    print("  Fonte: Yahoo Finance")
    print("=" * largura)
    print()


def consultar(entrada, inicio, fim):
    if inicio >= fim:
        print("\n  A data de início precisa ser anterior à data de fim.\n")
        return

    print(f"\n  Buscando {normalizar(entrada)}...")
    simbolo, df, moeda, nome = buscar_historico(entrada, inicio, fim)

    if df is None:
        print(f"\n  Não encontrei dados para '{normalizar(entrada)}' nesse período.")
        dica = sugerir(entrada)
        if dica:
            print(f"  Você quis dizer: {dica}?")
        print("  Verifique o código ou tente outro intervalo de datas.")
        print("  Exemplos: PETR4, BOVA11, IBOV, AAPL, SPY, SP500, HGLG11, BTC\n")
        return

    exibir(entrada, simbolo, nome, moeda, calcular(df))


def interativo():
    print()
    print("  RETORNO ACUMULADO DE ATIVOS")
    print("  Ações, ETFs, FIIs, BDRs, índices (BR/EUA), câmbio, cripto.")
    print("  Digite 'sair' a qualquer momento para encerrar.")
    print()

    while True:
        ativo = input("  Ativo (ex: PETR4, BOVA11, IBOV, AAPL): ").strip()
        if not ativo:
            continue
        if ativo.lower() in ("sair", "q", "exit"):
            break

        inicio = perguntar_data("  Data de início (dd/mm/aaaa): ")
        if inicio is None:
            break
        fim = perguntar_data("  Data de fim (dd/mm/aaaa): ")
        if fim is None:
            break

        consultar(ativo, inicio, fim)

    print("  Até mais.\n")


def main():
    if len(sys.argv) == 4:
        inicio, fim = ler_data(sys.argv[2]), ler_data(sys.argv[3])
        if not inicio or not fim:
            sys.exit("Datas inválidas. Use dd/mm/aaaa.")
        consultar(sys.argv[1], inicio, fim)
    else:
        interativo()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Encerrado.\n")
