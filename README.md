# Retorno Acumulado de Ativos

Digite o ativo, a data de início e a data de fim — o programa devolve o retorno
acumulado do período, com dados do **Yahoo Finance**.

**No ar em: <https://retorno-ativos-7bct3huejyy3teaxs8tfec.streamlit.app>**

Vem em três formatos: terminal, app web (feito para o celular) e notebook do
Google Colab.

O app tem **duas telas**: o retorno acumulado, que é a inicial, e as **opções
de dólar da B3**, no botão 🎯 Opções logo abaixo do título — precificação pelo
modelo Black-76 com dados oficiais da B3. Veja [Opções de dólar](#opções-de-dólar-b3).

## No computador

**Terminal:**

```bash
./rodar.sh                                  # modo interativo
./rodar.sh PETR4 01/01/2020 31/12/2024      # direto pela linha de comando
```

**App web (mesma interface do celular, rodando na sua máquina):**

```bash
./web.sh
```

**Opções de dólar (terminal):**

```bash
./opcao.sh                              # modo interativo
./opcao.sh DOLN27P005200 28/08/2026     # direto pela linha de comando
```

Ele abre o navegador em `http://localhost:8501`. Para parar, `Ctrl+C` no terminal.

## No celular

Abra <https://retorno-ativos-7bct3huejyy3teaxs8tfec.streamlit.app> e adicione à tela inicial
(iPhone/Safari: compartilhar → *Adicionar à Tela de Início*; Android/Chrome:
menu ⋮ → *Adicionar à tela inicial*). Fica com cara de aplicativo.

O **[GUIA-CELULAR.md](GUIA-CELULAR.md)** guarda o passo a passo da publicação
e a alternativa pelo Google Colab.

## O que ele aceita

| Tipo | Exemplos |
|---|---|
| Ações Brasil | `PETR4`, `VALE3`, `ITUB4`, `WEGE3` |
| ETFs Brasil | `BOVA11`, `IVVB11`, `SMAL11`, `NASD11` |
| FIIs | `HGLG11`, `MXRF11`, `KNRI11` |
| BDRs | `AAPL34`, `MSFT34`, `GOGL34` |
| Ações EUA | `AAPL`, `MSFT`, `NVDA`, `TSLA` |
| ETFs EUA | `SPY`, `VOO`, `QQQ`, `IVV` |
| Índices | `IBOV`, `SP500`, `NASDAQ`, `DOW`, `VIX`, `DAX`, `NIKKEI` |
| Câmbio | `DOLAR`, `EURBRL`, `EURUSD` |
| Commodities | `OURO`, `PETROLEO` |
| Cripto | `BTC`, `ETH` |
| Indicadores | `CDI`, `IPCA`, `CPI` (inflação dos EUA) |

`CDI`, `IPCA` e `CPI` não são ativos negociados e não existem no Yahoo — vêm
das fontes oficiais e são tratados como número índice, então rendem as mesmas
medidas dos demais (retorno acumulado, taxas médias, gráfico). Aceitam também
`DI`, `inflação` e `inflacaoEUA`.

Não precisa saber o sufixo do Yahoo: digitando `PETR4` ele testa `PETR4.SA`,
digitando `IBOV` ele usa `^BVSP`. Se quiser, pode digitar o código exato do
Yahoo também (`PETR4.SA`, `^GSPC`, `BRL=X`).

**Datas:** `dd/mm/aaaa` (ex: `05/01/2021`). Também aceita `dd/mm/aa` e `aaaa-mm-dd`.

## O que aparece no resultado

- **Retorno acumulado** — considerando dividendos/proventos reinvestidos
  (usa o preço ajustado). Quando o ativo pagou proventos, o programa mostra
  também o retorno só de variação de preço, para comparar.
- **Retorno médio mensal (a.m.) e anual (a.a.)** — taxas equivalentes por
  juros compostos: são a taxa que, aplicada mês a mês (ou ano a ano) ao longo
  do período, chega exatamente ao retorno acumulado. Não é o acumulado
  dividido pelo número de meses, que ignoraria os juros sobre juros.
  A mensal aparece a partir de 7 dias de janela; a anual, a partir de ~1 mês.
- Quanto R$ 1.000 investidos no início teriam virado no fim.
- Máxima, mínima, queda máxima (drawdown), volatilidade anual, melhor e pior dia.
- No app web: gráfico de linhas da curva de retorno, com caixas logo acima
  dele para marcar **CDI, IPCA, Ibovespa e S&P 500** — o que estiver marcado
  entra no gráfico no mesmo período, partindo de zero na data inicial, com o
  placar de quanto o ativo rendeu a mais ou a menos. Passando o mouse pelo
  gráfico, uma régua acompanha o cursor e mostra a data e o retorno de todas
  as linhas naquele dia. E download do histórico em CSV.

## De onde vêm os índices de comparação

| Série | Fonte | Reserva |
|---|---|---|
| CDI | Banco Central — série 12 do SGS (diária) | IPEA Data `BM12_TJCDI12` (mensal) |
| IPCA | Banco Central — série 433 do SGS (mensal) | IPEA Data `PRECOS12_IPCAG12` |
| CPI | BLS — `CUUR0000SA0`, número índice mensal | — |
| Ibovespa | Yahoo Finance (`^BVSP`) | — |
| S&P 500 | Yahoo Finance (`^GSPC`) | — |

O WAF do Banco Central responde **HTTP 406** a pedidos vindos de servidores em
nuvem: da sua máquina a API abre normalmente, do Streamlit Cloud não. Por isso
o CDI e o IPCA caem para o IPEA Data quando o BCB recusa — a curva fica em
degraus mensais e o app avisa na tela que a reserva entrou.

O IPCA é mensal e sai com cerca de dez dias de defasagem, então a curva dele
termina antes do fim do período — o app avisa na tela até que data ela vai.
Comparar um ativo em real com o S&P 500 ignora a variação do câmbio; nesse
caso o app também avisa.

## Opções de dólar (B3)

A segunda tela do app — botão **🎯 Opções** — e o `./opcao.sh` no terminal.
Você dá o código da opção e a data, e sai o prêmio teórico pelo modelo
**Black-76**, com cada insumo vindo de fonte oficial.

```bash
./opcao.sh DOLN27P005200 28/08/2026                # o básico
./opcao.sh DOLN27P005200 28/08/2026 --smile        # mostra o sorriso todo
./opcao.sh DOLN27P005200 28/08/2026 --vol 12       # sua volatilidade
./opcao.sh DOLN27P005200 28/08/2026 --premio 118   # devolve a implícita
./opcao.sh DOLN27P005200 28/08/2026 --paridade     # termo por cupom cambial
./opcao.sh DOLN27P005200 28/08/2026 --atualizar    # rebaixa a superfície
```

### O código da opção

`DOL` (ou `WDO`, as mini) + mês + ano + `C`/`P` + **strike de 6 dígitos com
zeros à esquerda**, em pontos — reais por US$ 1.000.

| Código | O que é |
|---|---|
| `DOLN27P005200` | Put de julho/2027, strike 5200 pontos = R$ 5,20 por dólar |
| `DOLN27C006000` | Call de julho/2027, strike R$ 6,00 |
| `WDOF27C005250` | Mini call de janeiro/2027, strike R$ 5,25 |

As letras dos meses são as do mercado futuro: `F G H J K M N Q U V X Z`, de
janeiro a dezembro. Se você escrever o strike com os centavos à mostra
(`DOLN27P520000`), o programa entende e responde com o código da B3. Strike que
não existe devolve os strikes vizinhos daquele vencimento.

### Os cinco insumos

| | O que é | De onde vem |
|---|---|---|
| **F** | Preço a termo | Preço de ajuste do futuro de **mesmo vencimento** (`DOLN27`), da B3 |
| **K** | Strike | Cadastro da B3, lido pelo código |
| **T** | Prazo | Dias corridos até o vencimento ÷ 365, do cadastro da B3 |
| **r** | Juro | Curva de **DI1** da B3, no vértice do vencimento |
| **σ** | Volatilidade | **Superfície de volatilidade de dólar** da B3, no strike da opção |

Três coisas que o programa faz e que costumam sair erradas quando se faz na mão:

- **F é o futuro do vencimento, não o dólar de hoje.** Os dois estavam 6,3%
  distantes em 28/08/2026 — o futuro embute o cupom cambial. Trocar um pelo
  outro daria +96% numa put e −44,6% na call equivalente.
- **A volatilidade é lida no strike da opção, não no dinheiro.** A superfície
  vem por delta; o programa converte os onze deltas em strikes e interpola no
  strike da opção, como manda o manual da B3. Usar só a volatilidade ATM
  subestimaria a put mais fora do dinheiro da `DOLN27` em 20,3%.
- **O prazo é em dias corridos.** É a base em que a B3 calibra a volatilidade
  que publica. Medir em dias úteis com essa volatilidade subestima o prêmio em
  cerca de 2%. O desconto continua saindo da curva de DI em base 252.

O resultado ainda traz as gregas e uma **conferência de paridade**: o preço a
termo refeito com dólar à vista e cupom cambial, ao lado do ajuste do futuro.
Se os dois se afastarem muito num dia, alguma ponta está estranha.

### Limites

- A B3 publica a superfície **uma vez por dia**, depois da coleta das 18h, e
  sobrescreve o arquivo — não há histórico. Só dá para precificar o pregão mais
  recente; para uma data passada é preciso informar a volatilidade à mão.
- Fora da faixa dos deltas 1%–99%, a regra da B3 é repetir a volatilidade da
  ponta. Como o sorriso sobe nas asas, isso subestima o prêmio em strikes muito
  distantes — o programa avisa quando acontece.
- É **preço teórico**, não executável. Vencimentos longos têm pouca liquidez em
  tela, e a negociação real acontece com a mesa, conversando em volatilidade.
  Custos e imposto ficam de fora.

### De onde vêm os dados das opções

| Dado | Fonte |
|---|---|
| Cadastro (strike, vencimento, dias úteis, estilo, multiplicador) | B3 — `InstrumentsConsolidated` |
| Preço de ajuste do futuro e curvas DI1, FRC e DDI | B3 — `TradeInformationConsolidated` |
| Volatilidade implícita | B3 — Superfície de volatilidade de dólar |
| Dólar à vista, só na conferência de paridade | Banco Central — PTAX |

Os arquivos da B3 são grandes e ficam em cache no disco, em `.cache_b3/`. A
superfície só é rebaixada quando fica velha — a primeira consulta depois das
18h atualiza, as demais leem do disco.

## Observações

- Se a data de início cair em fim de semana ou feriado, o cálculo começa no
  primeiro pregão seguinte (o mesmo vale para a data final, para trás). A data
  efetivamente usada aparece no cabeçalho do resultado.
- Preços de ativos brasileiros vêm em reais; os de fora, na moeda de origem —
  o retorno de um ativo em dólar **não** inclui a variação cambial.
- Dados do Yahoo Finance são gratuitos e podem ter falhas pontuais em ativos
  pouco líquidos. Para decisões de investimento, confira em uma segunda fonte.

## Arquivos

| Arquivo | Para que serve |
|---|---|
| `main.py` | Programa de terminal |
| `app.py` | App web (Streamlit) |
| `financeiro.py` | Busca das cotações e cálculo — compartilhado pelos dois |
| `tickers.py` | Traduz o que você digita para o código do Yahoo Finance |
| `macro.py` | Séries de CDI, IPCA e CPI (Banco Central, IPEA, BLS) |
| `indices.py` | Põe os índices na mesma régua do ativo, para o gráfico |
| `opcao.py` | Opções de dólar no terminal |
| `pagina_opcoes.py` | Opções de dólar na segunda tela do app web |
| `opcoes.py` | Lê o código da opção e junta os insumos |
| `black76.py` | O modelo Black-76: prêmio, gregas e volatilidade implícita |
| `superficie.py` | Superfície de volatilidade de dólar da B3 |
| `fontes.py` | Arquivos da B3 (cadastro, ajustes, curvas) e Banco Central |
| `Retorno_Acumulado_Ativos_COLAB.ipynb` | Notebook do Google Colab |
| `GUIA-CELULAR.md` | Como publicar e usar no celular |
| `rodar.sh` / `web.sh` / `opcao.sh` | Atalhos para o terminal, o app web e as opções |
| `requirements.txt` | Dependências |
| `.venv/` | Ambiente Python local, já montado |
