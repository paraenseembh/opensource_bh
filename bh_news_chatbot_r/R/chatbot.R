# chatbot.R
# Chatbot de noticias de BH usando um provedor de LLM.
# Mantem historico de conversa e responde perguntas com base nos artigos.

.SYSTEM_TEMPLATE <- "Voce e um assistente especializado em noticias de Belo Horizonte (BH), Minas Gerais.

Voce foi alimentado com as seguintes noticias recentes, organizadas por area tematica:

{news_context}

---

INSTRUCOES:
- Responda SEMPRE em portugues do Brasil.
- Baseie suas respostas nas noticias fornecidas acima.
- Se a informacao pedida nao estiver nas noticias, diga claramente que nao encontrou essa informacao.
- Ao citar uma noticia, mencione a area tematica, as categorias (se disponiveis) e o titulo.
- Seja objetivo, informativo e amigavel.
- Voce pode cruzar informacoes de diferentes areas quando fizer sentido.
- Se perguntado sobre um tema amplo, faca um resumo das noticias relevantes.
- Quando o usuario perguntar por uma categoria (ex: 'Saude', 'Meio Ambiente'), filtre pelo campo de categorias.
"

# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------

new_chatbot <- function(articles, provider) {
  news_context  <- format_articles_for_context(articles)
  system_prompt <- gsub("\\{news_context\\}", news_context, .SYSTEM_TEMPLATE, fixed = TRUE)

  env <- new.env(parent = emptyenv())
  env$provider      <- provider
  env$articles      <- articles
  env$system_prompt <- system_prompt
  env$history       <- list()

  class(env) <- "BHNewsChatbot"
  env
}

# ---------------------------------------------------------------------------
# Metodos
# ---------------------------------------------------------------------------

chatbot_chat <- function(bot, user_message) {
  bot$history <- c(bot$history, list(list(role = "user", content = user_message)))

  response <- tryCatch(
    bot$provider$complete(bot$system_prompt, bot$history),
    error = function(e) {
      stop(sprintf("Erro na API: %s", conditionMessage(e)))
    }
  )

  bot$history <- c(bot$history, list(list(role = "assistant", content = response)))
  response
}

chatbot_reset <- function(bot) {
  bot$history <- list()
  invisible(bot)
}

chatbot_get_areas <- function(bot) {
  sort(unique(sapply(bot$articles, function(a) a$area %||% "Geral")))
}

chatbot_summary <- function(bot) {
  by_area <- table(sapply(bot$articles, function(a) a$area %||% "Geral"))
  lines <- c(sprintf("Noticias carregadas (%s):", bot$provider$name))
  for (area in sort(names(by_area))) {
    lines <- c(lines, sprintf("  * %s: %d artigo(s)", area, by_area[[area]]))
  }
  lines <- c(lines, sprintf("  Total: %d artigos", length(bot$articles)))
  paste(lines, collapse = "\n")
}
