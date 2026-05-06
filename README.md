# open_bh
Coleção de dados públicos e amplamente disponibilizados na internet sobre o município de Belo Horizonte. 

Os datasets foram obtidos por meio da ferramenta <a href="https://docs.ckan.org/en/2.10/api/" target="_blank"> CKAN</a>, API utilizada no <a href="https://prefeitura.pbh.gov.br/transparencia" target="_blank"> Portal de Dados Abertos da Prefeitura de Belo Horizonte</a>. 

---

## Chatbot de Decretos Municipais de BH

Chatbot interativo que lê links de decretos e atos normativos do município de Belo Horizonte a partir de uma planilha do Google Sheets, raspa o conteúdo dos documentos e responde perguntas sobre a legislação municipal usando a API do Claude (Anthropic) ou Google Gemini.

Disponível em duas versões: **Python** e **R**.

---

### Pré-requisitos

**Planilha Google Sheets:** deve estar pública.
1. Abra a planilha → **Arquivo → Compartilhar → "Qualquer pessoa com o link" → Leitor**
   OU
2. **Arquivo → Publicar na web → CSV → Publicar**

**Chave de API** (escolha um provedor):
- Anthropic: [console.anthropic.com](https://console.anthropic.com)
- Google Gemini: [aistudio.google.com](https://aistudio.google.com)
- Maritaca AI: [plataforma.maritaca.ai](https://plataforma.maritaca.ai)

---

### Versão Python

#### Instalação

```bash
pip install -r bh_news_chatbot/requirements.txt
```

#### Configuração das chaves

**Bash / Zsh (Linux e Mac)**
```bash
export ANTHROPIC_API_KEY=sk-ant-...
export GEMINI_API_KEY=AIza...
export MARITACA_KEY=...
```
Para persistir entre sessões, adicione as linhas acima ao `~/.bashrc` ou `~/.zshrc`.

**Windows — Prompt de Comando (CMD)**
```cmd
set ANTHROPIC_API_KEY=sk-ant-...
set GEMINI_API_KEY=AIza...
set MARITACA_KEY=...
```
> Válido apenas na sessão atual. Para tornar permanente: **Painel de Controle → Sistema → Variáveis de Ambiente**.

**Windows — PowerShell**
```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
$env:GEMINI_API_KEY    = "AIza..."
$env:MARITACA_KEY      = "..."
```
Para persistir entre sessões no PowerShell:
```powershell
[System.Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "sk-ant-...", "User")
[System.Environment]::SetEnvironmentVariable("GEMINI_API_KEY",    "AIza...",    "User")
[System.Environment]::SetEnvironmentVariable("MARITACA_KEY",      "...",        "User")
```

**Fish shell**
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

**Alternativa universal — argumento na linha de comando**
```bash
python bh_news_chatbot/main.py --api-key sk-ant-...
python bh_news_chatbot/main.py --gemini-key AIza...
python bh_news_chatbot/main.py --maritaca-key ...
```

#### Uso

```bash
# Modo padrão (Anthropic + Google Sheets)
python bh_news_chatbot/main.py

# Usar o CSV local de legislação (sem acesso à internet para carregar dados)
python bh_news_chatbot/main.py --use-local-csv

# CSV local com outro provedor de LLM
python bh_news_chatbot/main.py --use-local-csv --provider gemini
python bh_news_chatbot/main.py --use-local-csv --provider maritaca

# CSV em outro caminho
python bh_news_chatbot/main.py --csv /caminho/para/legislacao.csv

# Com Google Gemini (fonte: Google Sheets)
python bh_news_chatbot/main.py --provider gemini

# Com Maritaca AI (Sabiá)
python bh_news_chatbot/main.py --provider maritaca

# Categorizar notícias por conteúdo antes do chat
python bh_news_chatbot/main.py --use-local-csv --categorize

# Apenas exibir relatório de categorias
python bh_news_chatbot/main.py --use-local-csv --only-categorize

# Forçar re-download (ignorar cache, apenas com Google Sheets)
python bh_news_chatbot/main.py --refresh

# Modelo específico
python bh_news_chatbot/main.py --provider gemini --model gemini-1.5-pro
python bh_news_chatbot/main.py --provider maritaca --model sabiazinho-4
```

#### Opções disponíveis

| Opção | Descrição | Padrão |
|---|---|---|
| `--provider` | Provedor de LLM: `anthropic`, `gemini` ou `maritaca` | `anthropic` |
| `--api-key` | Chave Anthropic | `ANTHROPIC_API_KEY` |
| `--gemini-key` | Chave Gemini | `GEMINI_API_KEY` |
| `--maritaca-key` | Chave Maritaca AI | `MARITACA_KEY` |
| `--model` | Modelo específico | padrão do provedor |
| `--use-local-csv` | Usa o CSV local `legislacao_2026_04.csv` como fonte | — |
| `--csv ARQUIVO` | Caminho para um CSV de legislação alternativo | — |
| `--max-per-area` | Máximo de artigos por área (apenas Google Sheets) | `10` |
| `--refresh` | Re-baixa todas as notícias (apenas Google Sheets) | — |
| `--categorize` | Categoriza artigos antes do chat | — |
| `--only-categorize` | Só categoriza, sem abrir o chat | — |
| `--sheet-id` | ID da planilha Google Sheets | ID padrão |

#### Modelos disponíveis por provedor

| Provedor | Modelo padrão | Modelo rápido |
|---|---|---|
| Anthropic | `claude-sonnet-4-6` | `claude-haiku-4-5` |
| Google Gemini | `gemini-2.0-flash` | `gemini-2.0-flash` |
| Maritaca AI | `sabia-4` | `sabiazinho-4` |

---

### Versão R

#### Instalação

```r
Rscript bh_news_chatbot_r/install_packages.R
```

Pacotes instalados: `httr2`, `rvest`, `jsonlite`, `readr`, `rlang`, `optparse`.

#### Configuração das chaves

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export GEMINI_API_KEY=AIza...
```

#### Uso

```bash
# Modo padrão (Anthropic)
Rscript bh_news_chatbot_r/main.R

# Com Google Gemini
Rscript bh_news_chatbot_r/main.R --provider gemini

# Categorizar notícias
Rscript bh_news_chatbot_r/main.R --categorize

# Apenas relatório de categorias
Rscript bh_news_chatbot_r/main.R --only-categorize

# Forçar re-download
Rscript bh_news_chatbot_r/main.R --refresh
```

As opções são idênticas à versão Python.

---

### Comandos dentro do chat (ambas as versões)

| Comando | Descrição |
|---|---|
| `/areas` | Lista as áreas temáticas da planilha |
| `/categorias` | Distribuição de artigos por categoria |
| `/resumo` | Quantidade de artigos carregados por área |
| `/reiniciar` | Limpa o histórico da conversa |
| `/ajuda` | Exibe todos os comandos |
| `/sair` | Encerra o chatbot |

---

### Categorias legislativas

O módulo de categorização classifica cada decreto em até 3 categorias:

`Urbanismo e Zoneamento` · `Obras e Infraestrutura Urbana` · `Saúde Pública` · `Educação` · `Meio Ambiente e Saneamento` · `Tributação e Finanças Públicas` · `Administração Pública` · `Segurança Pública e Defesa Civil` · `Transporte e Mobilidade Urbana` · `Habitação e Regularização Fundiária` · `Assistência Social` · `Cultura, Esporte e Lazer` · `Licitações e Contratos` · `Pessoal e Recursos Humanos` · `Outros`

---

### Testes de API

O projeto inclui scripts para verificar a conectividade e o comportamento dos provedores de LLM.

#### Teste geral (todos os provedores)

```bash
# Verifica todos os provedores configurados
python bh_news_chatbot/test_api.py

# Apenas um provedor específico
python bh_news_chatbot/test_api.py --provider maritaca

# Somente testes de erros (não precisa de chave válida)
python bh_news_chatbot/test_api.py --only-errors
```

#### Teste dedicado Maritaca AI

```bash
# Requer MARITACA_KEY definida para os testes funcionais
export MARITACA_KEY=sua-chave-aqui

# Roda todos os testes (configuração + erros + funcionais)
python bh_news_chatbot/test_maritaca.py

# Usa o modelo rápido (sabiazinho-4) nos testes funcionais
python bh_news_chatbot/test_maritaca.py --fast

# Somente erros e configuração (sem chave válida)
python bh_news_chatbot/test_maritaca.py --only-errors
```

O script `test_maritaca.py` executa quatro grupos de verificações:

| Grupo | O que verifica |
|---|---|
| Configuração | `MARITACA_BASE_URL`, nomes de modelos, alias `sabia` |
| Erros esperados | Chave vazia, chave inválida, modelo inexistente |
| Testes funcionais | `complete()`, `stream()`, conversa multi-turno |

---

### Cache

Os arquivos de cache ficam em `bh_news_chatbot/cache/` (Python) e `bh_news_chatbot_r/cache/` (R), ignorados pelo `.gitignore`:

- `news_cache.json` — conteúdo dos artigos raspados
- `categories_cache.json` — categorias já classificadas

O formato JSON é compatível entre as duas versões.
