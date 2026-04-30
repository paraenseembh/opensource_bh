# Chatbot de Decretos Municipais de BH — Python

Chatbot interativo que lê links de decretos e atos normativos do município de Belo Horizonte a partir de uma planilha do Google Sheets, raspa o conteúdo dos documentos e responde perguntas sobre a legislação municipal usando Claude (Anthropic) ou Google Gemini.

---

## Instalação

```bash
pip install -r requirements.txt
```

---

## Configuração de chaves de API

Defina a variável de ambiente do provedor que for usar:

```bash
# Anthropic (Claude)
export ANTHROPIC_API_KEY=sk-ant-...

# Google Gemini
export GEMINI_API_KEY=AIza...

# Maritaca (Sabiá — modelos em português)
export MARITACA_KEY=...
```

Alternativamente, passe a chave diretamente na linha de comando com `--api-key`, `--gemini-key` ou `--maritaca-key`.

### Provedores disponíveis

| Provedor | Flag | Env var | Modelo chat | Modelo rápido |
|---|---|---|---|---|
| Anthropic (Claude) | `--provider anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-4-6` | `claude-haiku-4-5` |
| Google Gemini | `--provider gemini` | `GEMINI_API_KEY` | `gemini-2.0-flash` | `gemini-2.0-flash` |
| Maritaca (Sabiá) | `--provider maritaca` | `MARITACA_KEY` | `sabia-4` | `sabiazinho-4` |

> A Maritaca é uma IA brasileira focada em português. Obtenha sua chave em [plataforma.maritaca.ai](https://plataforma.maritaca.ai/chaves-de-api).

---

## Como controlar a quantidade de artigos lidos

O parâmetro `--max-per-area` define o número máximo de artigos baixados **por área temática** da planilha. O padrão é `10`.

```bash
# Ler até 5 artigos por área (mais rápido, menos contexto)
python main.py --max-per-area 5

# Ler até 20 artigos por área (mais contexto, mais lento)
python main.py --max-per-area 20
```

> **Dica:** valores altos aumentam o tempo de download e o custo da API (mais tokens). Para testes, use `--max-per-area 3`.

---

## Todos os parâmetros de linha de comando

| Parâmetro | Descrição | Padrão |
|---|---|---|
| `--max-per-area N` | Máximo de artigos por área temática | `10` |
| `--provider` | Provedor: `anthropic`, `gemini` ou `maritaca` | `anthropic` |
| `--api-key KEY` | Chave da API Anthropic | `ANTHROPIC_API_KEY` |
| `--gemini-key KEY` | Chave da API Google Gemini | `GEMINI_API_KEY` |
| `--maritaca-key KEY` | Chave da API Maritaca | `MARITACA_KEY` |
| `--model NOME` | Modelo específico (ex: `sabiazinho-4`) | padrão do provedor |
| `--sheet-id ID` | ID da planilha do Google Sheets | ID padrão |
| `--refresh` | Ignora o cache e re-baixa todos os artigos | — |
| `--categorize` | Categoriza artigos por conteúdo antes do chat | — |
| `--only-categorize` | Apenas categoriza e exibe o relatório, sem abrir o chat | — |
| `--log-level` | Nível de detalhe dos logs: `DEBUG` `INFO` `WARNING` `ERROR` | `INFO` |

### Exemplos

```bash
# Uso básico com Anthropic
python main.py

# Com Gemini, 5 artigos por área e categorização
python main.py --provider gemini --max-per-area 5 --categorize

# Forçar re-download e usar modelo específico
python main.py --refresh --model claude-haiku-4-5-20251001

# Apenas ver o relatório de categorias sem abrir o chat
python main.py --only-categorize --provider gemini

# Usar Maritaca (Sabiá) como provedor
python main.py --provider maritaca

# Maritaca com modelo rápido explícito
python main.py --provider maritaca --model sabiazinho-4

# Logs detalhados para depuração
python main.py --log-level DEBUG
```

---

## Comandos disponíveis dentro do chat

| Comando | Descrição |
|---|---|
| `/areas` | Lista as áreas temáticas da planilha (ex: Saúde, Educação) |
| `/categorias` | Exibe quantos artigos há em cada categoria de conteúdo |
| `/resumo` | Mostra quantos artigos foram carregados por área |
| `/reiniciar` | Limpa o histórico da conversa e começa do zero |
| `/ajuda` | Exibe todos os comandos disponíveis |
| `/sair` | Encerra o chatbot |

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

Os downloads são salvos em `cache/` para evitar re-requisições desnecessárias:

| Arquivo | Conteúdo |
|---|---|
| `cache/news_cache.json` | Conteúdo dos artigos raspados |
| `cache/categories_cache.json` | Categorias já classificadas |

Para limpar o cache e baixar tudo novamente:

```bash
python main.py --refresh
```

Ou apague os arquivos manualmente:

```bash
rm cache/news_cache.json cache/categories_cache.json
```

---

## Verificação e testes das APIs

O script `test_api.py` verifica se as APIs de IA estão acessíveis e se o tratamento de erros funciona corretamente. Ele roda dois grupos de testes:

| Grupo | O que testa | Precisa de chave válida? |
|---|---|---|
| **Funcionais** | `create_provider()`, `complete()`, `stream()` | Sim |
| **Erros esperados** | chave vazia, chave inválida, modelo inexistente, provider desconhecido | Não (exceto modelo inexistente) |

### Como executar

```bash
# Testa ambos os provedores (funcionais + erros)
python bh_news_chatbot/test_api.py

# Testa apenas um provedor
python bh_news_chatbot/test_api.py --provider anthropic
python bh_news_chatbot/test_api.py --provider gemini

# Apenas os testes de erros esperados (não precisa de chave)
python bh_news_chatbot/test_api.py --only-errors
```

### Saída esperada (com chave configurada)

```
Verificação de APIs — BH News Chatbot
───────────────────────────────────────────────────────
  ANTHROPIC_API_KEY : configurada
  GEMINI_API_KEY    : configurada

Geral
───────────────────────────────────────────────────────
  erros gerais (independente de provedor)
  ✓ provider desconhecido → ValueError
  ✓ chave vazia anthropic → ValueError
  ✓ chave vazia gemini → ValueError

Anthropic
───────────────────────────────────────────────────────
  testes funcionais
  ✓ create_provider()
  ✓ complete()
  ✓ stream()

  erros esperados
  ✓ chave vazia → ValueError
  ✓ chave inválida → complete() falha
  ✓ chave inválida → stream() falha
  ✓ modelo inexistente → complete() falha
...
  PASSOU  N/N teste(s)
```

### Casos de erro testados

| Caso | Comportamento esperado |
|---|---|
| `create_provider("openai", ...)` | `ValueError`: provider desconhecido |
| `create_provider("anthropic", api_key="")` | `ValueError`: chave não configurada |
| `complete()` com chave inválida | Exceção de autenticação da API |
| `stream()` com chave inválida | Exceção de autenticação da API |
| `complete()` com modelo inexistente | Exceção de modelo não encontrado |

> Os testes de erro **passam quando a exceção esperada é lançada**. Se nenhuma exceção for lançada, o teste falha.

---

## Depuração do cache

O script `debug.py` inspeciona os arquivos de cache sem precisar executar o chatbot completo:

```bash
# Resumo: total de artigos, distribuição por área, falhas
python bh_news_chatbot/debug.py

# Conteúdo completo de cada artigo
python bh_news_chatbot/debug.py --verbose

# Inspecionar uma URL específica
python bh_news_chatbot/debug.py --url https://...

# Listar apenas URLs que falharam ou ficaram sem conteúdo
python bh_news_chatbot/debug.py --failures

# Exportar todos os artigos para um arquivo JSON
python bh_news_chatbot/debug.py --export artigos.json
```

---

## Planilha Google Sheets

A planilha deve estar pública para que o scraper consiga acessá-la:

1. Abra a planilha no Google Sheets
2. **Arquivo → Compartilhar → "Qualquer pessoa com o link" → Leitor**

Para usar uma planilha diferente da padrão:

```bash
python main.py --sheet-id SEU_ID_AQUI
```

O ID está na URL da planilha:
```
https://docs.google.com/spreadsheets/d/SEU_ID_AQUI/edit
```
