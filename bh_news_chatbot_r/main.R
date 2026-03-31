#!/usr/bin/env Rscript
# main.R — Chatbot de Noticias de Belo Horizonte (versao R)
#
# Uso:
#   Rscript main.R [opcoes]
#
# Exemplos:
#   Rscript main.R
#   Rscript main.R --provider gemini --gemini-key AIza...
#   Rscript main.R --categorize
#   Rscript main.R --only-categorize
#   Rscript main.R --refresh
#
# Variaveis de ambiente:
#   ANTHROPIC_API_KEY  — chave Anthropic (obrigatorio se --provider anthropic)
#   GEMINI_API_KEY     — chave Google Gemini (obrigatorio se --provider gemini)

suppressPackageStartupMessages({
  library(optparse)
  library(httr2)
  library(rvest)
  library(jsonlite)
  library(readr)
  library(rlang)
})

# Carrega modulos do projeto
SCRIPT_DIR <- normalizePath(dirname(sys.frame(0)$ofile %||% "."))
for (f in list.files(file.path(SCRIPT_DIR, "R"), pattern = "\\.R$", full.names = TRUE)) {
  source(f)
}

CACHE_DIR  <- file.path(SCRIPT_DIR, "cache")
CACHE_FILE <- file.path(CACHE_DIR, "news_cache.json")

BANNER <- "
+----------------------------------------------------------+
|    Chatbot de Noticias de Belo Horizonte (R)             |
|    Alimentado por Claude / Gemini                        |
+----------------------------------------------------------+
"

HELP_TEXT <- "
Comandos especiais:
  /ajuda      — mostra esta mensagem
  /areas      — lista as areas tematicas da planilha
  /categorias — distribuicao de artigos por categoria
  /resumo     — artigos carregados por area
  /reiniciar  — reinicia o historico da conversa
  /sair       — encerra o chatbot

Exemplos de perguntas:
  'Quais sao as ultimas noticias de saude em BH?'
  'O que esta acontecendo no transporte publico?'
  'Resumo das noticias de educacao'
"

# ---------------------------------------------------------------------------
# CLI args
# ---------------------------------------------------------------------------

option_list <- list(
  make_option("--provider",        default = "anthropic",
              help = "Provedor de LLM: anthropic (padrao) ou gemini [%default]"),
  make_option("--api-key",         default = Sys.getenv("ANTHROPIC_API_KEY"),
              help = "Chave da API Anthropic (ou ANTHROPIC_API_KEY)"),
  make_option("--gemini-key",      default = Sys.getenv("GEMINI_API_KEY"),
              help = "Chave da API Google Gemini (ou GEMINI_API_KEY)"),
  make_option("--model",           default = NULL,
              help = "Modelo especifico (ex: gemini-1.5-pro, claude-sonnet-4-6)"),
  make_option("--sheet-id",        default = SPREADSHEET_ID,
              help = "ID da planilha do Google Sheets [%default]"),
  make_option("--max-per-area",    default = 10L, type = "integer",
              help = "Maximo de artigos por area [%default]"),
  make_option("--refresh",         action = "store_true", default = FALSE,
              help = "Forca re-download das noticias (ignora cache)"),
  make_option("--categorize",      action = "store_true", default = FALSE,
              help = "Categoriza artigos por conteudo antes do chat"),
  make_option("--only-categorize", action = "store_true", default = FALSE,
              help = "Apenas categoriza e exibe relatorio, sem abrir o chat")
)

opt <- parse_args(OptionParser(
  usage       = "Rscript %prog [opcoes]",
  option_list = option_list,
  description = "Chatbot de noticias de BH baseado em planilha do Google Sheets"
))

# ---------------------------------------------------------------------------
# Carrega artigos
# ---------------------------------------------------------------------------

load_articles <- function(opt) {
  use_cache <- !opt$refresh

  if (use_cache && file.exists(CACHE_FILE)) {
    message(sprintf("Cache encontrado em %s", CACHE_FILE))
    cached <- tryCatch(jsonlite::read_json(CACHE_FILE), error = function(e) list())
    articles <- Filter(function(v) {
      !is.null(v) && is.list(v) && nzchar(v$body %||% "")
    }, cached)
    if (length(articles) > 0) {
      message(sprintf("Artigos carregados do cache: %d", length(articles)))
      return(articles)
    }
    message("Cache vazio ou invalido, buscando novamente...")
  }

  message(sprintf("Lendo planilha (ID: %s)...", opt$`sheet-id`))
  news_by_area <- load_all_news_links(sheet_id = opt$`sheet-id`)

  if (length(news_by_area) == 0) {
    cat("Nenhum link encontrado na planilha.\n")
    quit(status = 1)
  }

  message(sprintf("Raspando artigos (max %d por area)...", opt$`max-per-area`))
  articles <- scrape_all(
    news_by_area,
    max_per_area = opt$`max-per-area`,
    use_cache    = use_cache,
    cache_file   = CACHE_FILE
  )

  if (length(articles) == 0) {
    cat("Nenhum artigo foi raspado com sucesso.\n")
    quit(status = 1)
  }

  articles
}

# ---------------------------------------------------------------------------
# Loop interativo
# ---------------------------------------------------------------------------

run_interactive <- function(bot) {
  cat(BANNER)
  cat(chatbot_summary(bot), "\n")
  cat(HELP_TEXT)
  cat(strrep("-", 60), "\n")

  repeat {
    user_input <- tryCatch(
      readline(prompt = "\nVoce: "),
      error = function(e) "/sair"
    )

    user_input <- trimws(user_input)
    if (!nzchar(user_input)) next

    cmd <- tolower(user_input)

    if (cmd %in% c("/sair", "/exit", "/quit")) {
      cat("Ate logo!\n")
      break

    } else if (cmd %in% c("/ajuda", "/help")) {
      cat(HELP_TEXT)

    } else if (cmd == "/areas") {
      areas <- chatbot_get_areas(bot)
      cat("\nAreas disponiveis (da planilha):\n")
      for (a in areas) cat(sprintf("  * %s\n", a))

    } else if (cmd == "/categorias") {
      if (any(sapply(bot$articles, function(a) !is.null(a$categories)))) {
        print_category_report(bot$articles)
      } else {
        cat("\nArtigos ainda nao categorizados. Use --categorize ao iniciar.\n")
      }

    } else if (cmd == "/resumo") {
      cat("\n", chatbot_summary(bot), "\n")

    } else if (cmd %in% c("/reiniciar", "/reset")) {
      chatbot_reset(bot)
      cat("Historico reiniciado.\n")

    } else {
      cat("\nAssistente: ")
      response <- tryCatch(
        chatbot_chat(bot, user_input),
        error = function(e) {
          sprintf("[Erro na API: %s]", conditionMessage(e))
        }
      )
      cat(response, "\n")
    }
  }
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

# Determina a chave correta pelo provedor
api_key <- if (opt$provider == "gemini") opt$`gemini-key` else opt$`api-key`

# Cria provedor de chat
chat_provider <- tryCatch(
  create_provider(opt$provider, api_key = api_key, model = opt$model),
  error = function(e) {
    cat(sprintf("Erro ao criar provedor: %s\n", conditionMessage(e)))
    quit(status = 1)
  }
)

# Provedor rapido para categorizacao
fast_provider <- tryCatch(
  create_provider(opt$provider, api_key = api_key, model = NULL, fast = TRUE),
  error = function(e) chat_provider
)

message(sprintf("Provedor: %s", chat_provider$name))

# Carrega artigos
articles <- load_articles(opt)

# Categoriza se solicitado
if (opt$categorize || opt$`only-categorize`) {
  message("Categorizando artigos por conteudo...")
  articles <- categorize_articles(articles,
                                  provider  = fast_provider,
                                  cache_dir = CACHE_DIR)
  print_category_report(articles)
  if (opt$`only-categorize`) quit(status = 0)
}

# Inicia chatbot
message(sprintf("Inicializando chatbot com %d artigos...", length(articles)))
bot <- new_chatbot(articles, chat_provider)

# Loop interativo
run_interactive(bot)
