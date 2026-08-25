# Como usar isso no celular

Três caminhos, do mais prático ao mais simples de montar.

---

## Opção 1 — App web numa URL fixa (recomendado)

Você abre um endereço no navegador do celular, digita o ativo e as datas.
Sem instalar nada, sem o notebook ligado, e dá para salvar como ícone na tela
inicial (fica parecendo um aplicativo). Hospedagem gratuita no Streamlit
Community Cloud.

Precisa de uma conta no GitHub (gratuita). São ~10 minutos, uma vez só.

### 1. Suba o projeto para o GitHub

No terminal, dentro desta pasta:

```bash
git init
git add .
git commit -m "App de retorno acumulado de ativos"
```

Crie um repositório vazio em <https://github.com/new> (pode ser **público** —
não há nada sigiloso aqui; repositório público é o que o plano gratuito do
Streamlit aceita sem configuração extra). Depois, ainda no terminal, rode as
duas linhas que o próprio GitHub mostra na tela, no estilo:

```bash
git remote add origin https://github.com/SEU-USUARIO/retorno-ativos.git
git branch -M main
git push -u origin main
```

O `.gitignore` já exclui a pasta `.venv`, então só o código vai para lá.

### 2. Publique no Streamlit Cloud

1. Entre em <https://share.streamlit.io> e faça login **com a conta do GitHub**.
2. Clique em **Create app** → **Deploy a public app from GitHub**.
3. Preencha:
   - Repository: `SEU-USUARIO/retorno-ativos`
   - Branch: `main`
   - Main file path: `app.py`
4. Clique em **Deploy**. A primeira construção leva 2–3 minutos (ele instala o
   que está no `requirements.txt`).

Pronto: você recebe uma URL fixa, tipo
`https://retorno-ativos.streamlit.app`.

### 3. Coloque na tela inicial do celular

- **iPhone (Safari):** abra a URL → botão de compartilhar → *Adicionar à Tela de Início*.
- **Android (Chrome):** abra a URL → menu ⋮ → *Adicionar à tela inicial*.

### Detalhes que vale saber

- O app "dorme" depois de alguns dias sem uso. Quando isso acontece, o primeiro
  acesso mostra um botão para acordar e leva ~30 segundos. Depois fica rápido.
- Para atualizar o app depois de mexer no código: `git add . && git commit -m "ajuste" && git push`.
  O Streamlit republica sozinho.
- App público significa que qualquer pessoa com o link consegue abrir. Como ele
  só consulta cotações públicas, não há problema. Se quiser fechar, dá para
  restringir por e-mail nas configurações do app (*Settings → Sharing*).

---

## Opção 2 — Google Colab

Já está pronto: o arquivo **`Retorno_Acumulado_Ativos_COLAB.ipynb`**.

1. Abra <https://drive.google.com> e envie o arquivo `.ipynb` para o seu Drive
   (ou vá em <https://colab.research.google.com> → *Upload* → escolha o arquivo).
2. No celular, abra o arquivo pelo app do Google Drive → *Abrir com Colaboratory*
   (ou acesse colab.research.google.com pelo navegador).
3. Toque em ▶️ na célula **1️⃣** e espere (~30 s, instala a biblioteca).
4. Preencha Ativo / datas na célula **2️⃣** e toque em ▶️.

**Prós:** roda na nuvem do Google, o notebook não precisa estar ligado, e é só
subir um arquivo.
**Contras:** a interface do Colab no celular é apertada; toda vez que abrir você
precisa rodar a célula 1 de novo (~30 s); e ele desconecta sozinho depois de um
tempo parado.

Por isso a Opção 1 é melhor para o dia a dia — mas o Colab funciona hoje, sem
criar conta em lugar nenhum.

---

## Opção 3 — Google Sheets (sem código, mais limitado)

Para consultas simples, o Google Sheets tem a função `GOOGLEFINANCE` e o app do
Sheets funciona bem no celular. Numa planilha:

```
=GOOGLEFINANCE("BVMF:PETR4"; "close"; DATA(2020;1;1))
```

**Prós:** zero manutenção, abre no app do Sheets.
**Contras:** não considera dividendos (o retorno sai só pela variação de preço),
a cobertura de FIIs e ETFs brasileiros é irregular, e montar o cálculo de
retorno acumulado dá mais trabalho do que parece.

Serve como plano B; para o que você pediu, as opções 1 e 2 entregam melhor.
