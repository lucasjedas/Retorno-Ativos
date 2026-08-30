"""Preço de opção de dólar da B3 pelo Black-76 — versão de terminal.

Fontes: B3 (cadastro do instrumento, preço de ajuste do futuro e superfície
de volatilidade) e Banco Central (CDI). Nada aqui toca o app web.

A volatilidade sai da superfície da B3, que existe só para o pregão mais
recente — para precificar data passada é preciso passar --vol.

A superfície fica em cache no disco e só é rebaixada quando fica velha: a B3
publica uma vez por dia, depois da coleta das 18h, então a primeira chamada
depois desse horário atualiza e as demais leem do disco.

Uso:
    python opcao.py                                  # modo interativo
    python opcao.py DOLN27P005200 28/08/2026
    python opcao.py DOLN27P005200 28/08/2026 --vol 12
    python opcao.py DOLN27P005200 28/08/2026 --premio 57,1
    python opcao.py DOLN27P005200 28/08/2026 --smile    # mostra o sorriso todo
    python opcao.py DOLN27P005200 28/08/2026 --atualizar  # rebaixa a superfície
    python opcao.py DOLN27P005200 28/08/2026 --paridade   # termo por cupom cambial
"""

import sys
from datetime import date, datetime

import fontes
import opcoes
import superficie

FORMATOS_DATA = ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y")
LARGURA = 66


def ler_data(texto: str):
    """'28/08/2026' (ou variantes) -> date. None se inválida."""
    texto = (texto or "").strip()
    for formato in FORMATOS_DATA:
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


def ler_numero(texto: str):
    """Aceita vírgula decimal, como todo mundo escreve aqui. None se inválido."""
    try:
        return float((texto or "").strip().replace(",", "."))
    except ValueError:
        return None


def data_br(d) -> str:
    return f"{d:%d/%m/%Y}"


def pct(x, casas=2) -> str:
    return f"{x * 100:.{casas}f}%".replace(".", ",")


def num(x, casas=2, sinal=False) -> str:
    """Número no padrão daqui: ponto no milhar, vírgula no decimal."""
    formato = f"{x:+,.{casas}f}" if sinal else f"{x:,.{casas}f}"
    return formato.replace(",", "@").replace(".", ",").replace("@", ".")


def exibir(r: dict):
    tipo = "CALL" if r["tipo"] == "call" else "PUT"
    g = r["gregas"]

    print()
    print("=" * LARGURA)
    print(f"  {r['ticker']}  ·  {tipo} de dólar  ·  strike {num(r['strike'], 0)} pontos")
    print(f"  Vencimento {data_br(r['vencimento'])}  ·  {r['estilo']}  ·  "
          f"{r['dias_uteis']} dias úteis ({r['dias_corridos']} corridos)")
    print("=" * LARGURA)
    if r["digitado"] != r["ticker"]:
        print(f"\n  Você digitou {r['digitado']} — o código da B3 é {r['ticker']}.")
    if r["recuou"]:
        print(f"\n  Sem pregão na data pedida; usando {data_br(r['pregao'])}.")

    print()
    print("  INSUMOS DO MODELO")
    print(f"    F  preço a termo ................ {num(r['futuro'], 3)} pontos")
    print(f"       origem: {r['origem_futuro']}")
    print(f"    K  strike ....................... {num(r['strike'], 0)} pontos")
    print(f"    T  prazo ........................ {r['dias_corridos']}/365 = "
          f"{num(r['prazo_anos'], 6)} ano")
    print(f"       (o desconto usa {r['dias_uteis']} dias úteis, base 252 da curva)")
    print(f"    r  juro até o vencimento ......... {pct(r['taxa'])} a.a. (base 252)")
    print(f"       origem: {r['origem_juro']}")
    print(f"    σ  volatilidade ................. {pct(r['vol'])} a.a.")
    print(f"       origem: {r['origem_vol']}")

    print()
    print(f"  PRÊMIO TEÓRICO ........ {num(r['premio'], 3)} pontos")
    print(f"                          R$ {num(r['premio_reais'])} por contrato "
          f"(× {num(r['multiplicador'], 0)})")

    if r["premio_mercado"] is not None:
        print()
        print(f"  Prêmio de mercado ..... {num(r['premio_mercado'], 3)} pontos")
        diferenca = r["premio"] - r["premio_mercado"]
        print(f"    modelo − mercado .... {num(diferenca, 3, sinal=True)} pontos")
        if r["vol_implicita"] is None:
            print("    volatilidade implícita: fora do alcance do modelo")
            print("      (prêmio abaixo do valor intrínseco ou acima de 500% de vol)")
        else:
            print(f"    volatilidade implícita {pct(r['vol_implicita'])} a.a.")

    print()
    print("  GREGAS")
    print(f"    Delta ... {num(g['delta'], 4, sinal=True)}   por 1 ponto do futuro")
    print(f"    Gama .... {num(g['gama'], 6, sinal=True)}   variação do delta por 1 ponto")
    print(f"    Vega .... {num(g['vega'], 4, sinal=True)}   por 1 ponto percentual de vol")
    print(f"    Theta ... {num(g['theta'], 4, sinal=True)}   por dia corrido que passa")
    print(f"    Rho ..... {num(g['rho'], 4, sinal=True)}   por 1 ponto percentual de juro")

    par = r["paridade"]
    print()
    print("  CONFERÊNCIA DE PARIDADE (forma de câmbio do manual, §2.1)")
    if par["erro"]:
        print(f"    não deu para conferir: {par['erro']}")
    else:
        print(f"    dólar à vista (PTAX {data_br(par['data_spot'])}) . {num(par['spot'], 1)} pontos")
        print(f"    cupom cambial limpo ............. {pct(par['cupom'])} a.a. (base 360)")
        print(f"       {par['origem_cupom']}")
        print(f"    termo por paridade .............. {num(par['futuro'], 3)} pontos")
        print(f"    ajuste do futuro {r['futuro_ticker']} ......... {num(r['futuro_ajuste'], 3)} pontos")
        print(f"    diferença ....................... {num(par['diferenca'] * 100, 3, sinal=True)}%")
        print("       o resíduo é o horário do à vista: a B3 usa o fechamento")
        print("       das 18h e a PTAX é a média apurada por volta das 13h")

    print()
    dentro = (r["moneyness"] > 1) if r["tipo"] == "call" else (r["moneyness"] < 1)
    print(f"  Moneyness (F/K) ....... {num(r['moneyness'], 4)}"
          f"  ({'dentro' if dentro else 'fora'} do dinheiro para esta {tipo.lower()})")
    print()
    fonte_vol = ("superfície da B3" if r["smile"] else "informada por você")
    print(f"  Fontes: B3 (cadastro, ajuste, curvas DI1 e FRC) · "
          f"Banco Central (PTAX) · vol: {fonte_vol}")
    print("  Modelo: Black-76, europeia sobre futuro, prazo em dias corridos/365")
    print("=" * LARGURA)
    print()


def exibir_smile(r: dict):
    """O sorriso de volatilidade daquele vencimento, do jeito que a B3 publica."""
    smile = r["smile"]
    if not smile:
        print("\n  Sem superfície para este caso — nada de sorriso para mostrar.\n")
        return
    print()
    print(f"  SORRISO DE VOLATILIDADE — {smile['vencimento']:%d/%m/%Y}"
          f"  (superfície de {smile['referencia']:%d/%m/%Y})")
    print("    delta      strike        vol")
    ordenados = sorted(zip(smile["deltas"], smile["vols_por_delta"]),
                       key=lambda par: -par[0])
    strikes = [k for k, _ in smile["smile"]]
    # os dois vértices que cercam o strike da opção
    vizinhos = {
        i for i in range(len(strikes) - 1)
        if strikes[i] <= r["strike"] <= strikes[i + 1]
    }
    vizinhos |= {i + 1 for i in vizinhos}
    for i, ((delta, vol), strike) in enumerate(zip(ordenados, strikes)):
        marca = "  <-" if i in vizinhos else ""
        print(f"    {delta:>4.0f}%   {num(strike, 1):>9}   {pct(vol)}{marca}")
    print(f"\n    strike {num(r['strike'], 0)} interpolado por spline monótono"
          f" -> {pct(r['vol'])}")
    print()


def consultar(codigo, data_referencia, vol=None, premio=None,
              mostrar_smile=False, atualizar=False, forward="futuro"):
    print(f"\n  Buscando {codigo.upper()} em {data_br(data_referencia)}...")
    if atualizar:
        try:
            tabela = superficie.carregar(forcar=True)
            print(f"  Superfície rebaixada: {data_br(tabela['referencia'])}.")
        except (fontes.SemDados, OSError) as erro:
            print(f"  Não consegui rebaixar a superfície: {erro}")
    try:
        resultado = opcoes.precificar(
            codigo, data_referencia, vol=vol, premio_mercado=premio,
            forward=forward,
        )
    except opcoes.CodigoInvalido as erro:
        print(f"\n  {erro}\n")
        return
    except fontes.SemDados as erro:
        print(f"\n  {erro}\n")
        return
    except OSError as erro:
        print(f"\n  Não consegui falar com a fonte: {erro}\n")
        return
    exibir(resultado)
    if mostrar_smile:
        exibir_smile(resultado)


def mostrar_volatilidades(_=None):
    """A superfície publicada, no dinheiro, vencimento a vencimento."""
    try:
        tabela = superficie.carregar()
    except (fontes.SemDados, OSError) as erro:
        print(f"\n  Superfície da B3 indisponível: {erro}\n")
        return
    situacao = superficie.estado()
    print(f"\n  Superfície de volatilidade da B3 — {data_br(tabela['referencia'])}")
    atraso = "em dia" if tabela["referencia"] >= situacao["esperado"] else (
        f"ATRASADA — o esperado é {data_br(situacao['esperado'])}")
    conferido = situacao["conferido"]
    print(f"  Cache: {atraso}"
          + (f" · última ida à fonte {conferido:%d/%m %H:%M}" if conferido else ""))
    print("  Volatilidade no dinheiro (delta 50) por vencimento:")
    deltas = tabela["deltas"]
    meio = deltas.index(50.0) if 50.0 in deltas else len(deltas) // 2
    for venc in sorted(tabela["vencimentos"]):
        vols = tabela["vencimentos"][venc]
        if meio < len(vols):
            print(f"    {data_br(venc)} ... {pct(vols[meio])}")
    print()


def perguntar_data(rotulo: str):
    while True:
        entrada = input(rotulo).strip()
        if entrada.lower() in ("sair", "q", "exit"):
            return None
        if not entrada:
            return date.today()
        data = ler_data(entrada)
        if data:
            return data
        print("   Data inválida. Use o formato dd/mm/aaaa (ex: 28/08/2026).")


def interativo():
    print()
    print("  OPÇÃO DE DÓLAR — MODELO BLACK-76")
    print("  Código da B3: DOL + mês + ano + C/P + strike.")
    print("  Ex: DOLN27P005200 = put de julho/2027, strike 5200 (R$ 5,20).")
    print("  Enter na data usa hoje. 'vol' mostra a superfície. 'sair' encerra.")
    print()

    while True:
        codigo = input("  Opção (ex: DOLN27P005200): ").strip()
        if not codigo:
            continue
        if codigo.lower() in ("sair", "q", "exit"):
            break
        if codigo.lower() == "vol":
            mostrar_volatilidades()
            continue

        quando = perguntar_data("  Data de início (dd/mm/aaaa, Enter = hoje): ")
        if quando is None:
            break

        digitada = input("  Volatilidade % a.a. (Enter = superfície da B3): ").strip()
        vol = None
        if digitada:
            lida = ler_numero(digitada)
            if lida is None or lida <= 0:
                print("   Volatilidade inválida; usando a superfície da B3.")
            else:
                vol = lida / 100

        consultar(codigo, quando, vol=vol)

    print("  Até mais.\n")


def _opcao_numerica(args, nome):
    """Tira '--nome valor' da lista e devolve o valor lido."""
    if nome not in args:
        return None
    lugar = args.index(nome)
    if lugar + 1 >= len(args):
        sys.exit(f"Falta o valor de {nome}.")
    valor = ler_numero(args[lugar + 1])
    if valor is None:
        sys.exit(f"Valor inválido em {nome}: {args[lugar + 1]!r}")
    del args[lugar:lugar + 2]
    return valor


def main():
    args = sys.argv[1:]
    if not args:
        interativo()
        return

    mostrar_smile = "--smile" in args
    if mostrar_smile:
        args.remove("--smile")
    atualizar = "--atualizar" in args
    if atualizar:
        args.remove("--atualizar")
    forward = "futuro"
    if "--paridade" in args:
        args.remove("--paridade")
        forward = "paridade"
    vol = _opcao_numerica(args, "--vol")
    premio = _opcao_numerica(args, "--premio")

    if len(args) != 2:
        sys.exit(__doc__.split("Uso:")[1].strip())

    quando = ler_data(args[1])
    if not quando:
        sys.exit("Data inválida. Use dd/mm/aaaa.")

    consultar(
        args[0], quando,
        vol=(vol / 100 if vol else None),
        premio=premio, mostrar_smile=mostrar_smile, atualizar=atualizar,
        forward=forward,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  Cancelado.\n")
