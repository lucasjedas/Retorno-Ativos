# Retorno Acumulado de Ativos

Digite o ativo, a data de início e a data de fim — o programa devolve o retorno
acumulado do período, com dados do **Yahoo Finance**.

**No ar em: <https://retorno-ativos-7bct3huejyy3teaxs8tfec.streamlit.app>**

Vem em três formatos: terminal, app web (feito para o celular) e notebook do
Google Colab.

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
  placar de quanto o ativo rendeu a mais ou a menos. E download do histórico
  em CSV.

## De onde vêm os índices de comparação

| Índice | Fonte | Reserva |
|---|---|---|
| CDI | Banco Central — série 12 do SGS (diária) | IPEA Data `BM12_TJCDI12` (mensal) |
| IPCA | Banco Central — série 433 do SGS (mensal) | IPEA Data `PRECOS12_IPCAG12` |
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
| `indices.py` | Curvas de CDI, IPCA, Ibovespa e S&P 500 para comparação |
| `Retorno_Acumulado_Ativos_COLAB.ipynb` | Notebook do Google Colab |
| `GUIA-CELULAR.md` | Como publicar e usar no celular |
| `rodar.sh` / `web.sh` | Atalhos para rodar o terminal / o app web |
| `requirements.txt` | Dependências |
| `.venv/` | Ambiente Python local, já montado |
