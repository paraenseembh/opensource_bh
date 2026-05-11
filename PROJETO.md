# Opensource BH — Documentação do Projeto

## O que é este projeto?

Este repositório reúne ferramentas abertas para consultar e explorar a legislação municipal de **Belo Horizonte**. O foco é democratizar o acesso a decretos, portarias e leis municipais, tornando esses documentos pesquisáveis e compreensíveis por qualquer pessoa — não apenas por advogados ou servidores públicos.

O projeto nasce de uma ideia simples: os atos normativos da prefeitura estão publicados na internet, mas dispersos, difíceis de buscar e escritos em linguagem técnica. Com um chatbot e um motor de busca, qualquer cidadão pode perguntar em linguagem natural — "quais decretos tratam de transporte público em 2026?" — e obter uma resposta compreensível.

---

## Módulos do repositório

| Pasta | O que faz |
|---|---|
| `bh_news_chatbot/` | Chatbot em Python que responde perguntas sobre a legislação municipal usando IA |
| `bh_news_chatbot_r/` | A mesma ferramenta, reescrita em R para quem prefere essa linguagem |
| `corpus_dom/` | Pipeline de mineração: baixa e estrutura documentos do Diário Oficial do Município (DOM-BH) |
| `busca_dom/` | Motor de busca com interface web para pesquisar no corpus do DOM-BH |
| `legislacao_2026_04.csv` | Base de dados com 5.197 registros de decretos, portarias e leis (abril de 2026) |

---

## Principais marcos do desenvolvimento

A tabela abaixo registra os commits mais relevantes, em ordem cronológica — do mais antigo ao mais recente.

| Commit | O que foi feito |
|---|---|
| `1bb853f` | Criação do chatbot inicial, lendo links de legislação a partir de uma planilha Google Sheets |
| `0917368` | Adição de categorização automática de decretos por tema (urbanismo, saúde, educação etc.) via IA |
| `f90c78f` | Suporte ao Google Gemini como provedor de IA, além do Claude (Anthropic) |
| `6d82c97` | Versão do chatbot reescrita em linguagem R |
| `1b661a1` | Correção do acesso ao Google Sheets (API descontinuada substituída) |
| `601478b` | Adição do pipeline `corpus_dom`: extração e estruturação dos PDFs e páginas do DOM-BH |
| `48811ea` | Suporte a PDF e DOCX no scraper; exportação para JSONL e CSV |
| `22c45ab` | Motor de busca `busca_dom` com TF-IDF e interface Streamlit |
| `c0b7bca` | Upload do CSV de legislação com mais de 5.000 registros |
| `041ec3f` | Adaptação do projeto para foco nos decretos municipais de BH |
| `8107507` | Adição da Maritaca AI (modelo Sabiá, IA brasileira) como terceiro provedor |
| `a5a671d` | Script de verificação das APIs dos três provedores |
| `5647369` | Testes dedicados para a Maritaca AI com cobertura de erros |
| `b120473` | Atualização da documentação principal do README |

---

## Dependências

### Python — Chatbot (`bh_news_chatbot/`)

```
anthropic>=0.40.0       # API do Claude (Anthropic)
google-genai>=1.0.0     # API do Google Gemini
openai>=1.0.0           # Compatibilidade com APIs no padrão OpenAI (usada pela Maritaca)
beautifulsoup4>=4.12.0  # Raspagem de páginas web
lxml>=5.0.0             # Parser HTML/XML
requests>=2.32.0        # Requisições HTTP
```

### Python — Corpus DOM (`corpus_dom/`)

```
pandas>=2.0.0                   # Manipulação de dados tabulares
requests>=2.31.0                # Requisições HTTP
beautifulsoup4>=4.12.0          # Raspagem de HTML
lxml>=4.9.0                     # Parser HTML/XML
mysql-connector-python>=8.3.0   # Conexão com banco de dados MySQL
python-dotenv>=1.0.0            # Leitura de variáveis de ambiente (.env)
pdfplumber>=0.10.0              # Extração de texto de PDFs
python-docx>=1.0.0              # Leitura de arquivos DOCX
```

### Python — Busca DOM (`busca_dom/`)

```
pandas>=2.0.0           # Manipulação de dados
scikit-learn>=1.4.0     # Algoritmo de busca TF-IDF
streamlit>=1.35.0       # Interface web interativa
python-dotenv>=1.0.0    # Leitura de variáveis de ambiente
```

### R — Chatbot (`bh_news_chatbot_r/`)

```
httr2       # Requisições HTTP
rvest       # Raspagem de páginas web
jsonlite    # Leitura e escrita de JSON
readr       # Leitura de CSV
rlang       # Utilitários de programação em R
optparse    # Argumentos de linha de comando
```

---

## Para quem não tem experiência com programação

Esta seção é uma introdução gentil para quem quer rodar o projeto, mas nunca usou Git ou Python antes. Não se preocupe — você não precisa entender tudo de uma vez. Cada passo é simples quando feito um de cada vez.

---

### O que é código aberto (opensource)?

Um projeto **opensource** é aquele cujo código-fonte está disponível publicamente para qualquer pessoa ler, usar, modificar e distribuir. Pense como uma receita de bolo publicada na internet: qualquer um pode copiar, adaptar e melhorar.

Este projeto segue essa filosofia. Ele está disponível gratuitamente, aceita contribuições de qualquer pessoa e foi construído colaborativamente, usando ferramentas que também são abertas.

Plataformas como o **GitHub** hospedam projetos opensource e permitem que pessoas do mundo inteiro colaborem. O endereço deste projeto é `github.com/paraenseembh/opensource_bh`.

---

### O que é Git e por que usamos?

**Git** é um sistema que registra todas as mudanças feitas no código ao longo do tempo. É como um histórico de versões, mas muito mais poderoso: você pode ver quem mudou o quê, quando, e por quê. Se algo der errado, dá para voltar a uma versão anterior.

Quando você "clona" um repositório, está baixando uma cópia completa do projeto, incluindo todo esse histórico.

#### Instalando o Git

- **Linux (Ubuntu/Debian):** `sudo apt install git`
- **Mac:** `brew install git` (ou baixar em git-scm.com)
- **Windows:** baixar o instalador em git-scm.com/downloads

#### Clonando o repositório (baixando o projeto)

Abra o terminal (no Windows, use o "Git Bash" instalado com o Git) e digite:

```bash
git clone https://github.com/paraenseembh/opensource_bh.git
```

Isso vai criar uma pasta chamada `opensource_bh` no seu computador com todos os arquivos do projeto.

Entre na pasta:

```bash
cd opensource_bh
```

#### Atualizando o projeto

Se o projeto receber melhorias depois que você clonou, basta rodar:

```bash
git pull
```

Isso baixa as novidades sem precisar clonar tudo de novo.

#### Comandos Git úteis para o dia a dia

| Comando | O que faz |
|---|---|
| `git status` | Mostra o que mudou desde o último registro |
| `git log --oneline` | Mostra o histórico de commits em formato compacto |
| `git pull` | Baixa as últimas atualizações do projeto |
| `git checkout nome-da-branch` | Muda para uma versão específica do projeto |

---

### O que é Python e por que precisamos dele?

**Python** é uma linguagem de programação muito usada em ciência de dados, automação e inteligência artificial. O chatbot e os scripts de mineração de dados deste projeto são escritos em Python.

#### Instalando o Python

Baixe a versão 3.10 ou mais recente em **python.org/downloads**.

Durante a instalação no Windows, marque a opção **"Add Python to PATH"** — isso é importante para que os comandos funcionem no terminal.

Verifique se a instalação funcionou:

```bash
python --version
```

Deve aparecer algo como `Python 3.12.3`.

#### O que são dependências e como instalar?

Um programa raramente faz tudo sozinho — ele usa bibliotecas feitas por outras pessoas para não reinventar a roda. Essas bibliotecas são chamadas de **dependências**.

No Python, as dependências ficam listadas em um arquivo chamado `requirements.txt`. Para instalar tudo de uma vez:

```bash
pip install -r bh_news_chatbot/requirements.txt
```

O `pip` é o gerenciador de pacotes do Python — ele baixa e instala cada biblioteca automaticamente.

#### Ambientes virtuais (boa prática)

Antes de instalar as dependências, é recomendado criar um **ambiente virtual** — uma pasta isolada que contém o Python e as bibliotecas só deste projeto, sem bagunçar o resto do sistema.

```bash
# Cria o ambiente virtual (só precisa fazer uma vez)
python -m venv .venv

# Ativa o ambiente (Linux/Mac)
source .venv/bin/activate

# Ativa o ambiente (Windows)
.venv\Scripts\activate

# Agora instale as dependências dentro do ambiente
pip install -r bh_news_chatbot/requirements.txt
```

Quando terminar de usar o projeto, desative o ambiente com:

```bash
deactivate
```

---

### Rodando o chatbot

Com as dependências instaladas e uma chave de API configurada, o chatbot é iniciado com:

```bash
# Usando a base de dados local (sem precisar de internet para carregar os dados)
python bh_news_chatbot/main.py --use-local-csv
```

Se você não tem uma chave de API ainda, crie uma conta gratuita em um dos provedores suportados:

- **Anthropic (Claude):** console.anthropic.com
- **Google Gemini:** aistudio.google.com
- **Maritaca AI (Sabiá — IA brasileira):** plataforma.maritaca.ai

Depois de obter a chave, configure-a no terminal antes de rodar o chatbot:

```bash
# Linux/Mac
export ANTHROPIC_API_KEY=sua-chave-aqui

# Windows (CMD)
set ANTHROPIC_API_KEY=sua-chave-aqui
```

Ou passe a chave diretamente na linha de comando:

```bash
python bh_news_chatbot/main.py --use-local-csv --api-key sua-chave-aqui
```

Dentro do chat, você pode perguntar em linguagem natural:

```
> Quais decretos tratam de transporte público em 2024?
> O que diz o decreto 18.012?
> Existem atos sobre habitação de interesse social?
```

Use `/ajuda` para ver todos os comandos disponíveis e `/sair` para encerrar.

---

### Como contribuir com o projeto

Opensource é sobre colaboração. Se você encontrou um bug, quer sugerir uma melhoria ou quer adicionar uma funcionalidade:

1. **Abra uma issue** no GitHub descrevendo o problema ou a ideia
2. **Fork** o repositório (cria uma cópia sua no GitHub)
3. Faça as mudanças na sua cópia
4. **Abra um Pull Request** — uma proposta de mudança que os mantenedores podem revisar e aceitar

Não precisa ser programador para contribuir: melhorar a documentação, reportar bugs ou sugerir novas fontes de dados já são contribuições valiosas.

---

*Última atualização: maio de 2026*
