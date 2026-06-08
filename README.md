# 💰 Sistema de Organização Financeira Pessoal

Sistema completo de controle financeiro pessoal que integra dados bancários reais diretamente no iPhone e no terminal. O projeto combina automação via N8N, armazenamento em Google Sheets, visualização nativa no iOS através de widgets Scriptable e um bot CLI em Python para controle de divisões financeiras entre pessoas.

---

## 🗂️ Estrutura do Repositório

```
├── N8N/
│   └── Get dados bancários.json          # Fluxo N8N exportado (importar direto na plataforma)
│
├── Scriptable/
│   ├── Saldo.js                          # Widget de saldo atual da conta
│   ├── Transações.js                     # Widget com últimas transações
│   └── Meta mensal.js                    # Widget de acompanhamento de meta mensal
│
├── bot pendencias/
│   ├── bot_pendencias.py                 # Bot CLI de controle de dívidas entre pessoas
│   ├── credentials.json                  # Credenciais da Service Account (não versionado)
│   └── pendencias.db                     # Banco de dados local SQLite (gerado automaticamente)
│
└── assets/
    ├── fluxo_N8N.png                     # Print do fluxo N8N
    └── Resultado_Widgets.jpeg            # Preview dos widgets no iPhone
```

---

## 🏗️ Arquitetura do Sistema

```
Banco (Pluggy API)
      │
      ▼
 Fluxo N8N  ──────────────────────────────────────┐
 (webhook + autenticação + coleta)                 │
      │                                            │
      ├──► HTTP call transactions                  │
      │         └──► Split Out                     │
      │               └──► Filtra info             │
      │                     └──► Insere transações ──► Google Sheets ◄──── Bot Pendências
      │                                            │       │                    │
      └──► HTTP call account info                  │       │            Lê PIX novos
                └──► Atualiza saldo ───────────────┘       │            Escreve Página2
                                                           ▼
                                                   Widgets Scriptable
                                                   (iOS / iPhone)
                                                     ├─ Saldo
                                                     ├─ Transações
                                                     └─ Meta Mensal
```

---

## ⚙️ Parte 1 — Fluxo N8N

O fluxo é responsável por buscar os dados bancários via API, tratá-los e gravá-los no Google Sheets automaticamente.

![Fluxo_N8N](assets/fluxo_N8N.png)

### Nós do fluxo (da esquerda para direita)

| Nó | Tipo | Descrição |
|---|---|---|
| **Webhook** | Trigger | Dispara o fluxo via requisição GET externa |
| **HTTP login pluggy** | HTTP Request (POST) | Autentica na API Pluggy e obtém token de acesso |
| **HTTP atualiza conta pluggy** | HTTP Request (PATCH) | Atualiza/sincroniza os dados da conta no Pluggy |
| **Wait** | Espera | Aguarda a sincronização ser concluída antes de prosseguir |
| **HTTP call transactions** | HTTP Request (GET) | Busca o histórico de transações da conta |
| **Split Out** | Transformação | Separa o array de transações em itens individuais |
| **Filtra info** | Code (manual) | Filtra e formata os campos relevantes de cada transação |
| **Insere transações** | Google Sheets | Insere ou atualiza as transações na aba correta (appendOrUpdate) |
| **HTTP call account info** | HTTP Request (GET) | Busca informações e saldo atual da conta |
| **Atualiza saldo** | Google Sheets | Atualiza a célula de saldo na planilha (update) |

### Como importar o fluxo

1. Acesse sua instância do N8N
2. Vá em **Workflows → Import from file**
3. Selecione o arquivo `N8N/Get dados bancários.json`
4. Configure as credenciais da Pluggy API e do Google Sheets nas etapas correspondentes
5. Ative o webhook e copie a URL gerada

### Pré-requisitos N8N

- Conta na [Pluggy](https://pluggy.ai/) com uma conexão bancária ativa
- Google Sheets com as abas de transações e saldo configuradas
- Instância N8N (self-hosted ou cloud)

---

## 📱 Parte 2 — Widgets Scriptable (iOS)

Os widgets são scripts JavaScript executados pelo app [Scriptable](https://scriptable.app/) no iPhone. Eles leem os dados diretamente do Google Sheets e exibem as informações na tela inicial.

### Widgets disponíveis

#### `Saldo.js`
Exibe o saldo atual da conta bancária, entradas e saídas do dia, atualizado a cada execução do fluxo N8N.

#### `Transações.js`
Lista as últimas transações registradas, com descrição, data e valor (vermelho para débitos, verde para créditos).

#### `Meta mensal.js`
Acompanha o progresso em relação a uma meta de gastos definida para o mês, com barra de progresso e percentual utilizado.

### Como configurar os widgets

1. Instale o app **Scriptable** na App Store
2. Copie o conteúdo de cada arquivo `.js` para um novo script dentro do Scriptable
3. Em cada script, configure a URL da sua planilha Google Sheets publicada (planilha → Arquivo → Publicar na web → CSV)
4. Adicione o widget desejado na tela inicial do iPhone (pressione e segure → `+` → Scriptable)
5. Selecione o script correspondente ao widget

### Preview

![Widgets de organização financeira no iPhone](assets/Resultado_Widgets.jpeg)

---

## 🤖 Parte 3 — Bot de Pendências (Python CLI)

Bot de terminal em Python para controle de dívidas e divisões financeiras entre pessoas. Integra-se ao mesmo Google Sheets do sistema, lendo transações PIX automaticamente e sincronizando o resumo de pendências em uma aba dedicada.

### Funcionalidades

- Cadastro de pessoas e registro manual de gastos compartilhados com divisão automática
- Leitura de transações PIX do Google Sheets — detecta o nome da pessoa pela descrição e pergunta o que fazer com cada transação: abater dívida existente, registrar como novo gasto ou ignorar
- Cálculo de saldo líquido por pessoa (positivo e negativo se cancelam automaticamente)
- Sincronização automática do resumo de pendências na `Página2` do Google Sheets após qualquer alteração
- Revisão semanal automática ao abrir o bot no dia/hora configurados, com listagem detalhada de todas as dívidas e saldo final por pessoa
- Banco de dados local SQLite — sem dependências externas além do `gspread`

### Instalação

```bash
pip install gspread google-auth
python3 bot_pendencias.py
```

### Configurar acesso ao Google Sheets

O bot usa uma Service Account para ler e escrever na planilha. Para configurar:

1. Acesse [console.cloud.google.com](https://console.cloud.google.com) e crie um projeto
2. Ative **Google Sheets API** e **Google Drive API**
3. Vá em **Credenciais → Criar credenciais → Conta de serviço**
4. Na conta criada, gere uma chave **JSON** e salve como `credentials.json` na pasta `bot pendencias/`
5. Abra o `credentials.json`, copie o valor de `"client_email"` e compartilhe sua planilha com esse e-mail como **Editor**
6. No bot, acesse **Configurações** e cole o ID da planilha (trecho da URL entre `/d/` e `/edit`)

### Estrutura do Google Sheets esperada

| Aba | Conteúdo |
|---|---|
| `Página 1` | Transações do banco — colunas: Data, Descrição, Valor, Categoria, Tipo, ID |
| `Página2` | Gerada e mantida pelo bot — resumo de pendências por pessoa (uma linha por pessoa) |

### Agendamento semanal (cron)

Para o bot disparar a revisão automaticamente, agende a execução via cron:

```bash
crontab -e
# Exemplo: toda segunda-feira às 9h
0 9 * * 1 python3 "/caminho/completo/bot pendencias/bot_pendencias.py"
```

O dia e horário também podem ser alterados diretamente no menu **Configurações** do bot.

### Fluxo de uso típico

```
Abrir o bot
  └── Painel mostra saldo líquido por pessoa
  └── Aviso se houver PIX novos na planilha

Opção 3 — Processar PIX do Google Sheets
  └── Bot lista cada PIX não processado
  └── Detecta nome da pessoa pela descrição
  └── Pergunta: abater dívida / novo gasto / ignorar
  └── Atualiza Página2 automaticamente

Opção 2 — Ver detalhes / quitar
  └── Lista todas as transações abertas com IDs
  └── Permite quitar individualmente ou todas de uma vez
  └── Atualiza Página2 automaticamente
```

---

## 🔗 Tecnologias utilizadas

| Tecnologia | Função |
|---|---|
| [N8N](https://n8n.io/) | Orquestração e automação do fluxo de dados |
| [Pluggy API](https://pluggy.ai/) | Conexão open finance com o banco |
| [Google Sheets](https://sheets.google.com/) | Banco de dados intermediário e exibição de pendências |
| [Scriptable](https://scriptable.app/) | Renderização dos widgets no iOS |
| JavaScript | Lógica dos widgets |
| Python 3 + SQLite | Bot CLI de controle de pendências |

---

## 🔒 Segurança

- As credenciais da Pluggy API e do Google Sheets **não estão incluídas** neste repositório
- Configure-as diretamente nas credenciais do N8N e nas variáveis dos scripts Scriptable
- O arquivo `credentials.json` da Service Account deve estar no `.gitignore` — nunca versione esse arquivo
- Nunca exponha seu `clientId`, `clientSecret` ou tokens de acesso publicamente

---

## 👤 Autor

**Felipe Pipelmo**  
Estudante de Engenharia de Controle e Automação — focado em Automação de Processos, Engenharia de Dados e Integrações de APIs.

[GitHub](https://github.com/FelipePipelmo)
