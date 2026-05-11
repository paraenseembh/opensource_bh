# Guia de Alterações — BH News Chatbot

Este documento descreve as funcionalidades adicionadas recentemente ao projeto, ensina como usá-las e responde às dúvidas mais comuns.

---

## O que foi adicionado

| Alteração | Arquivo | Descrição |
|---|---|---|
| Script de verificação de APIs | `test_api.py` | Testa conectividade, `complete()`, `stream()` e tratamento de erros de cada provedor |
| Testes de erros esperados | `test_api.py` | Verifica que o sistema rejeita corretamente chaves inválidas, modelos inexistentes e provedores desconhecidos |
| Integração Maritaca (Sabiá) | `llm_provider.py` | Terceiro provedor de LLM, focado em português brasileiro |
| Dependência `openai` | `requirements.txt` | Necessária para comunicar com a API compatível da Maritaca |
| Flag `--maritaca-key` | `main.py` | Permite passar a chave da Maritaca pela linha de comando |

---

## 1. Script de verificação de APIs (`test_api.py`)

### Para que serve

Antes de rodar o chatbot, use este script para confirmar que suas chaves de API estão corretas e que os provedores estão respondendo. Ele roda dois grupos de testes:

- **Testes funcionais**: chamam a API de verdade com uma mensagem simples. Precisam de chave válida.
- **Testes de erros esperados**: verificam que o sistema rejeita situações inválidas corretamente. **Não precisam de chave.**

### Como executar

```bash
# Testa todos os provedores configurados
python bh_news_chatbot/test_api.py

# Testa apenas um provedor
python bh_news_chatbot/test_api.py --provider anthropic
python bh_news_chatbot/test_api.py --provider gemini
python bh_news_chatbot/test_api.py --provider maritaca

# Roda apenas os testes de erros (não precisa de nenhuma chave)
python bh_news_chatbot/test_api.py --only-errors
```

### Como interpretar a saída

```
✓  verde   — teste passou
✗  vermelho — teste falhou (veja o motivo na mesma linha)
–  amarelo  — teste pulado (motivo entre parênteses)
```

**Exemplo de saída com chave configurada:**
```
Maritaca
─────────────────────────────────────────────────
  testes funcionais
  ✓ create_provider()   Maritaca (sabia-4)
  ✓ complete()          1.3s  "OK"
  ✓ stream()            1.1s  4 token(s)  "OK"

  erros esperados
  ✓ chave vazia → ValueError
  ✓ chave inválida → complete() falha
  ✓ chave inválida → stream() falha
  ✓ modelo inexistente → complete() falha
```

**Exemplo sem chave configurada:**
```
Maritaca
─────────────────────────────────────────────────
  testes funcionais
  –  todos os testes funcionais (MARITACA_KEY não configurada)

  erros esperados
  ✓ chave vazia → ValueError
  ✓ chave inválida → complete() falha   (ModuleNotFoundError — SDK não instalada)
  ✓ chave inválida → stream() falha
  –  modelo inexistente → complete() falha (requer chave válida)
```

> Os testes funcionais ficam com `–` se a chave não estiver configurada. Isso é normal — configure a chave e rode novamente.

### O que cada teste verifica

| Teste | O que valida |
|---|---|
| `create_provider()` | A fábrica cria o objeto do provedor sem erros |
| `complete()` | A API responde a uma mensagem simples |
| `stream()` | A API retorna tokens em streaming |
| `chave vazia → ValueError` | O sistema rejeita chave em branco antes de chamar a API |
| `chave inválida → complete() falha` | A API retorna erro de autenticação para chave falsa |
| `chave inválida → stream() falha` | Idem, no modo streaming |
| `modelo inexistente → complete() falha` | A API retorna erro para nome de modelo inválido |

---

## 2. Integração com Maritaca.ai (Sabiá)

### O que é a Maritaca

A [Maritaca AI](https://maritaca.ai) é uma empresa brasileira que desenvolve modelos de linguagem otimizados para o português. Os modelos da família **Sabiá** têm desempenho superior em textos em português em relação a modelos genéricos do mesmo tamanho.

### Modelos disponíveis

| Modelo | Uso recomendado | Custo |
|---|---|---|
| `sabia-4` | Chat principal, respostas de maior qualidade | Mais alto |
| `sabiazinho-4` | Categorização, tarefas rápidas, menor latência | Mais baixo |

### Como obter a chave

1. Acesse [plataforma.maritaca.ai/chaves-de-api](https://plataforma.maritaca.ai/chaves-de-api)
2. Crie uma conta (novos usuários recebem R$ 20 de crédito)
3. Gere uma nova chave de API

### Como configurar

```bash
# Variável de ambiente (recomendado)
export MARITACA_KEY=sua-chave-aqui

# Ou passe direto na linha de comando
python bh_news_chatbot/main.py --provider maritaca --maritaca-key sua-chave-aqui
```

### Como usar no chatbot

```bash
# Uso básico com Sabiá-4
python bh_news_chatbot/main.py --provider maritaca

# Com modelo rápido (menor custo)
python bh_news_chatbot/main.py --provider maritaca --model sabiazinho-4

# Com categorização e 5 artigos por área
python bh_news_chatbot/main.py --provider maritaca --max-per-area 5 --categorize

# Apenas categorizar sem abrir o chat
python bh_news_chatbot/main.py --provider maritaca --only-categorize
```

### Verificar se a chave está funcionando

```bash
export MARITACA_KEY=sua-chave-aqui
python bh_news_chatbot/test_api.py --provider maritaca
```

---

## 3. Comparativo de provedores

| Provedor | Env var | Modelo chat | Modelo rápido | Foco |
|---|---|---|---|---|
| Anthropic (Claude) | `ANTHROPIC_API_KEY` | `claude-sonnet-4-6` | `claude-haiku-4-5` | Geral, inglês/português |
| Google Gemini | `GEMINI_API_KEY` | `gemini-2.0-flash` | `gemini-2.0-flash` | Geral, multimodal |
| Maritaca (Sabiá) | `MARITACA_KEY` | `sabia-4` | `sabiazinho-4` | Português brasileiro |

> Para projetos de legislação municipal em português como este, a Maritaca tende a produzir respostas mais naturais e precisas no idioma.

---

## 4. Instalação após as alterações

Se você já tinha o projeto instalado, atualize as dependências para incluir o SDK `openai` (necessário para a Maritaca):

```bash
pip install -r bh_news_chatbot/requirements.txt
```

Ou instale apenas o novo pacote:

```bash
pip install "openai>=1.0.0"
```

---

## 5. Perguntas frequentes

### Os testes de erros passam mesmo sem chave instalada. Isso está certo?

Sim. Testes como "chave inválida → complete() falha" verificam apenas que *alguma exceção é lançada*. Sem o SDK instalado, o Python lança `ModuleNotFoundError` antes mesmo de chamar a API — o teste ainda passa porque o comportamento esperado (falha) ocorreu. Com o SDK instalado e chave inválida, seria lançado um `AuthenticationError` da API.

### Por que os testes funcionais ficam como `–` (pulado)?

Porque a chave de API não está configurada. Configure a variável de ambiente e rode novamente:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python bh_news_chatbot/test_api.py --provider anthropic
```

### Posso usar mais de um provedor ao mesmo tempo?

Não simultaneamente — você escolhe um por execução com `--provider`. Mas pode ter as três chaves configuradas e alternar conforme precisar.

### Como saber qual provedor está sendo usado no chat?

O banner inicial mostra:
```
Decretos carregados (Maritaca (sabia-4)):
  • Área X: 10 documento(s)
  ...
```

### O teste "modelo inexistente" fica como `–` mesmo com chave válida. Por quê?

Verifique se a chave está realmente configurada como variável de ambiente (não apenas passada por `--api-key`). O teste usa `os.environ.get()` internamente:

```bash
# Certifique-se de usar export, não apenas assignment
export ANTHROPIC_API_KEY=sk-ant-...   # correto
ANTHROPIC_API_KEY=sk-ant-...          # errado — não fica no ambiente do subprocesso
```

### O que fazer se `complete()` falhar com erro de autenticação?

1. Verifique se a chave está correta e sem espaços extras
2. Verifique se a chave não expirou ou foi revogada
3. Para Anthropic: confirme que tem créditos disponíveis em [console.anthropic.com](https://console.anthropic.com)
4. Para Maritaca: confirme o saldo em [plataforma.maritaca.ai](https://plataforma.maritaca.ai)
5. Para Gemini: confirme que a API está habilitada no [Google AI Studio](https://aistudio.google.com)

### Como usar o modelo rápido/barato para reduzir custos?

O modelo rápido é usado automaticamente para a categorização interna. Para o chat, passe `--model` explicitamente:

```bash
# Anthropic — modelo barato
python bh_news_chatbot/main.py --provider anthropic --model claude-haiku-4-5-20251001

# Maritaca — modelo barato
python bh_news_chatbot/main.py --provider maritaca --model sabiazinho-4

# Gemini — mesmos modelos (flash já é o padrão)
python bh_news_chatbot/main.py --provider gemini --model gemini-2.0-flash
```

### O token do GitHub é necessário para usar o chatbot?

Não. O token do GitHub só foi usado para consultar a URL pública do repositório. O chatbot precisa apenas das chaves de LLM (`ANTHROPIC_API_KEY`, `GEMINI_API_KEY` ou `MARITACA_KEY`).

> **Importante:** nunca compartilhe tokens ou chaves de API em conversas, issues ou commits. Se isso acontecer, revogue imediatamente o token no painel do serviço correspondente.

---

## 6. Referência rápida de comandos

```bash
# Verificar APIs antes de usar
python bh_news_chatbot/test_api.py

# Inspecionar o cache de artigos
python bh_news_chatbot/debug.py

# Iniciar o chatbot (Anthropic)
python bh_news_chatbot/main.py

# Iniciar o chatbot (Gemini)
python bh_news_chatbot/main.py --provider gemini

# Iniciar o chatbot (Maritaca)
python bh_news_chatbot/main.py --provider maritaca

# Forçar re-download dos artigos
python bh_news_chatbot/main.py --refresh

# Categorizar artigos e ver relatório
python bh_news_chatbot/main.py --only-categorize

# Limpar cache manualmente
rm bh_news_chatbot/cache/news_cache.json
rm bh_news_chatbot/cache/categories_cache.json
```
