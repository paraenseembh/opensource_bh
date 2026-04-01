# chatbot.R
# Chatbot de decretos municipais de BH usando um provedor de LLM.
# Mantem historico de conversa e responde perguntas com base nos documentos oficiais.

.SYSTEM_TEMPLATE <- "Voce e um assistente especializado em legislacao e atos normativos do municipio de Belo Horizonte (BH), Minas Gerais.

Voce foi alimentado com os seguintes decretos e documentos oficiais municipais, organizados por area:

{news_context}

---

INSTRUCOES:
- Responda SEMPRE em portugues do Brasil.
- Baseie suas respostas nos decretos e documentos fornecidos acima.
- Se a informacao pedida nao estiver nos documentos, diga claramente que nao encontrou essa informacao nas fontes disponiveis.
- Ao citar um decreto, mencione a categoria legislativa, o numero ou titulo do ato e a data (quando disponivel).
- Seja objetivo, preciso e claro — trata-se de legislacao municipal.
- Voce pode relacionar decretos de diferentes categorias quando fizer sentido.
- Se perguntado sobre um tema amplo, faca um resumo dos atos normativos relevantes.
- Quando o usuario perguntar por uma categoria (ex: 'Urbanismo', 'Licitacoes'), filtre os documentos pelo campo de categorias.
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
  lines <- c(sprintf("Decretos carregados (%s):", bot$provider$name))
  for (area in sort(names(by_area))) {
    lines <- c(lines, sprintf("  * %s: %d documento(s)", area, by_area[[area]]))
  }
  lines <- c(lines, sprintf("  Total: %d documentos", length(bot$articles)))
  paste(lines, collapse = "\n")
}
