# Chatbot de Decretos Municipais de BH — Python

Chatbot interativo que responde perguntas sobre legislação e atos normativos do município de Belo Horizonte. Suporta duas fontes de dados e três provedores de IA.

---

## Instalação

```bash
pip install -r requirements.txt
```

---

## Fontes de dados

### CSV local (recomendado)

O repositório inclui `legislacao_2026_04.csv` com 5197 registros de decretos, portarias e leis municipais. Não requer internet para carregar os dados.

```bash
# Usa o CSV local padrão
python main.py --use-local-csv

# CSV em outro caminho
python main.py --csv /caminho/para/legislacao.csv
```

### Google Sheets (padrão original)

Lê links de uma planilha pública, raspa o conteúdo das páginas e usa o texto completo como contexto. Requer internet e a planilha deve ser pública.

```bash
python main.py --sheet-id SEU_ID_AQUI
```

> O ID da planilha está na URL: `https://docs.google.com/spreadsheets/d/**SEU_ID**/edit`
> A planilha deve estar configurada em **Arquivo → Compartilhar → "Qualquer pessoa com o link" → Leitor**.

---

## Configuração das chaves de API

Escolha o método adequado ao seu sistema operacional.

### Bash / Zsh (Linux e Mac)

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export GEMINI_API_KEY=AIza...
export MARITACA_KEY=...
```

Para persistir entre sessões, adicione as linhas ao `~/.bashrc` ou `~/.zshrc`.

### Windows — Prompt de Comando (CMD)

```cmd
set ANTHROPIC_API_KEY=sk-ant-...
set GEMINI_API_KEY=AIza...
set MARITACA_KEY=...
```

> Válido apenas na sessão atual. Para tornar permanente: **Painel de Controle → Sistema → Variáveis de Ambiente**.

### Windows — PowerShell

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
$env:GEMINI_API_KEY    = "AIza..."
$env:MARITACA_KEY      = "..."
```

Para persistir entre sessões:

```powershell
[System.Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "sk-ant-...", "User")
[System.Environment]::SetEnvironmentVariable("GEMINI_API_KEY",    "AIza...",    "User")
[System.Environment]::SetEnvironmentVariable("MARITACA_KEY",      "...",        "User")
```

### Fish shell

```fish
set -x ANTHROPIC_API_KEY sk-ant-...
set -x GEMINI_API_KEY AIza...
set -x MARITACA_KEY ...
```

Para persistir entre sessões:

```fish
set -Ux ANTHROPIC_API_KEY sk-ant-...
set -Ux GEMINI_API_KEY AIza...
set -Ux MARITACA_KEY ...
```

### Alternativa — argumento direto na linha de comando

```bash
python main.py --api-key sk-ant-...
python main.py --gemini-key AIza...
python main.py --maritaca-key ...
```

---

## Provedores de IA disponíveis

| Provedor | Flag | Env var | Modelo chat | Modelo rápido |
|---|---|---|---|---|
| Anthropic (Claude) | `--provider anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-4-6` | `claude-haiku-4-5` |
| Google Gemini | `--provider gemini` | `GEMINI_API_KEY` | `gemini-2.0-flash` | `gemini-2.0-flash` |
| Maritaca (Sabiá) | `--provider maritaca` | `MARITACA_KEY` | `sabia-4` | `sabiazinho-4` |

> A Maritaca é uma IA brasileira focada em português. Obtenha sua chave em [plataforma.maritaca.ai](https://plataforma.maritaca.ai/chaves-de-api).

---

## Limite de contexto por provedor

Cada provedor tem uma janela de contexto diferente, o que determina quantos documentos do CSV cabem com texto completo. O chatbot aplica automaticamente o limite correto para cada provedor.

| Provedor | Janela de contexto | Docs do CSV com texto completo |
|---|---|---|
| Google Gemini | 1M tokens (~3,5M chars) | **todos os 2.755** |
| Anthropic Claude | 200K tokens (~680K chars) | ~1.343 |
| Maritaca Sabiá-4 | 128K tokens (~430K chars) | ~853 |

Independente do limite de texto completo, o chatbot sempre inclui no contexto um **índice compacto** (título + área + data) de todos os documentos, e o comando `/documentos` lista todos via memória sem custo de tokens.

### Ajuste manual com `--context-size`

```bash
# Define o limite manualmente em caracteres
python main.py --use-local-csv --context-size 500000

# Sem limite (use com cautela — pode ultrapassar a janela do modelo)
python main.py --use-local-csv --context-size 0
```

---

## Todos os parâmetros de linha de comando

| Parâmetro | Descrição | Padrão |
|---|---|---|
| `--provider` | Provedor: `anthropic`, `gemini` ou `maritaca` | `anthropic` |
| `--api-key KEY` | Chave da API Anthropic | `ANTHROPIC_API_KEY` |
| `--gemini-key KEY` | Chave da API Google Gemini | `GEMINI_API_KEY` |
| `--maritaca-key KEY` | Chave da API Maritaca | `MARITACA_KEY` |
| `--model NOME` | Modelo específico (ex: `sabiazinho-4`) | padrão do provedor |
| `--use-local-csv` | Usa o CSV local `legislacao_2026_04.csv` | — |
| `--csv ARQUIVO` | Caminho para um CSV de legislação alternativo | — |
| `--context-size N` | Limite de chars para o contexto (0 = sem limite) | automático por provedor |
| `--sheet-id ID` | ID da planilha do Google Sheets | ID padrão |
| `--max-per-area N` | Máximo de artigos por área (apenas Google Sheets) | `10` |
| `--refresh` | Ignora o cache e re-baixa todos os artigos (Google Sheets) | — |
| `--categorize` | Categoriza artigos por conteúdo antes do chat | — |
| `--only-categorize` | Apenas categoriza e exibe o relatório, sem abrir o chat | — |
| `--log-level` | Nível de detalhe dos logs: `DEBUG` `INFO` `WARNING` `ERROR` | `INFO` |

### Exemplos

```bash
# CSV local com Gemini (todos os 2755 documentos no contexto)
python main.py --use-local-csv --provider gemini

# CSV local com Maritaca (Sabiá)
python main.py --use-local-csv --provider maritaca

# CSV local com Anthropic e modelo rápido
python main.py --use-local-csv --provider anthropic --model claude-haiku-4-5-20251001

# Google Sheets com Gemini, 5 artigos por área e categorização
python main.py --provider gemini --max-per-area 5 --categorize

# Apenas ver o relatório de categorias
python main.py --use-local-csv --only-categorize

# Logs detalhados para depuração
python main.py --use-local-csv --log-level DEBUG
```

---

## Comandos disponíveis dentro do chat

| Comando | Descrição |
|---|---|
| `/documentos` | Lista todos os documentos carregados (lê da memória, não do LLM) |
| `/documentos <área>` | Filtra documentos por área (ex: `/documentos Orçamento`) |
| `/areas` | Lista as áreas temáticas disponíveis |
| `/categorias` | Exibe quantos artigos há em cada categoria de conteúdo |
| `/resumo` | Mostra quantos artigos foram carregados por área |
| `/reiniciar` | Limpa o histórico da conversa e começa do zero |
| `/ajuda` | Exibe todos os comandos disponíveis |
| `/sair` | Encerra o chatbot |

> `/documentos` sempre lista todos os registros da memória (até 2.755), independente do número de documentos no contexto do LLM.

---

## Categorias legislativas

Quando `--categorize` é usado, cada decreto recebe até 3 categorias automaticamente:

- Urbanismo e Zoneamento
- Obras e Infraestrutura Urbana
- Saúde Pública
- Educação
- Meio Ambiente e Saneamento
- Tributação e Finanças Públicas
- Administração Pública
- Segurança Pública e Defesa Civil
- Transporte e Mobilidade Urbana
- Habitação e Regularização Fundiária
- Assistência Social
- Cultura, Esporte e Lazer
- Licitações e Contratos
- Pessoal e Recursos Humanos
- Outros

---

## Cache

Os downloads são salvos em `cache/` para evitar re-requisições desnecessárias (apenas no modo Google Sheets):

| Arquivo | Conteúdo |
|---|---|
| `cache/news_cache.json` | Conteúdo dos artigos raspados |
| `cache/categories_cache.json` | Categorias já classificadas |

Para limpar o cache e baixar tudo novamente:

```bash
python main.py --refresh
```

---

## Verificação e testes das APIs

### Teste geral — todos os provedores

```bash
# Testa todos os provedores configurados
python test_api.py

# Testa apenas um provedor
python test_api.py --provider anthropic
python test_api.py --provider gemini
python test_api.py --provider maritaca

# Apenas os testes de erros (não precisa de chave válida)
python test_api.py --only-errors
```

### Teste dedicado — Maritaca AI

```bash
# Roda todos os testes (configuração + erros + funcionais)
python test_maritaca.py

# Usa o modelo rápido (sabiazinho-4) nos testes funcionais
python test_maritaca.py --fast

# Somente erros e configuração (sem chave válida)
python test_maritaca.py --only-errors
```

O script `test_maritaca.py` executa três grupos de verificações:

| Grupo | O que verifica |
|---|---|
| Configuração | `MARITACA_BASE_URL`, nomes de modelos, alias `sabia` |
| Erros esperados | Chave vazia, chave inválida, modelo inexistente |
| Testes funcionais | `complete()`, `stream()`, conversa multi-turno |

### Casos de erro testados (ambos os scripts)

| Caso | Comportamento esperado |
|---|---|
| `create_provider("openai", ...)` | `ValueError`: provider desconhecido |
| `create_provider("anthropic", api_key="")` | `ValueError`: chave não configurada |
| `complete()` com chave inválida | Exceção de autenticação da API |
| `stream()` com chave inválida | Exceção de autenticação da API |
| `complete()` com modelo inexistente | Exceção de modelo não encontrado |

---

## Depuração do cache

O script `debug.py` inspeciona os arquivos de cache sem precisar executar o chatbot completo:

```bash
# Resumo: total de artigos, distribuição por área, falhas
python debug.py

# Conteúdo completo de cada artigo
python debug.py --verbose

# Inspecionar uma URL específica
python debug.py --url https://...

# Listar apenas URLs que falharam ou ficaram sem conteúdo
python debug.py --failures

# Exportar todos os artigos para um arquivo JSON
python debug.py --export artigos.json
```
