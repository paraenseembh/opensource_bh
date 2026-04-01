# llm_provider.R
# Abstração de provedores de LLM: Anthropic (Claude) e Google (Gemini).
# Cada provider é uma lista com $name e $complete(system, messages).

`%||%` <- function(a, b) if (!is.null(a) && nzchar(a)) a else b

# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------

.anthropic_complete <- function(api_key, model, max_tokens, system, messages) {
  resp <- httr2::request("https://api.anthropic.com/v1/messages") |>
    httr2::req_method("POST") |>
    httr2::req_headers(
      `x-api-key`          = api_key,
      `anthropic-version`  = "2023-06-01",
      `content-type`       = "application/json"
    ) |>
    httr2::req_body_json(list(
      model      = model,
      max_tokens = max_tokens,
      system     = system,
      messages   = messages
    )) |>
    httr2::req_error(is_error = \(r) FALSE) |>
    httr2::req_perform()

  if (httr2::resp_status(resp) != 200L) {
    stop(sprintf(
      "Anthropic API erro %d: %s",
      httr2::resp_status(resp),
      httr2::resp_body_string(resp)
    ))
  }

  httr2::resp_body_json(resp)$content[[1]]$text
}

anthropic_provider <- function(api_key = NULL,
                               model = "claude-sonnet-4-6",
                               max_tokens = 2048L) {
  key <- api_key %||% Sys.getenv("ANTHROPIC_API_KEY")
  if (!nzchar(key)) {
    stop("Chave Anthropic nao encontrada. Defina ANTHROPIC_API_KEY ou use --api-key.")
  }
  list(
    name     = paste0("Anthropic (", model, ")"),
    complete = function(system, messages) {
      .anthropic_complete(key, model, max_tokens, system, messages)
    }
  )
}

# ---------------------------------------------------------------------------
# Google Gemini
# ---------------------------------------------------------------------------

.to_gemini_messages <- function(messages) {
  lapply(messages, function(m) {
    list(
      role  = if (m$role == "assistant") "model" else "user",
      parts = list(list(text = m$content))
    )
  })
}

.gemini_complete <- function(api_key, model, max_tokens, system, messages) {
  url <- paste0(
    "https://generativelanguage.googleapis.com/v1beta/models/",
    model, ":generateContent?key=", api_key
  )

  body <- list(
    systemInstruction = list(parts = list(list(text = system))),
    contents          = .to_gemini_messages(messages),
    generationConfig  = list(maxOutputTokens = max_tokens)
  )

  resp <- httr2::request(url) |>
    httr2::req_method("POST") |>
    httr2::req_body_json(body) |>
    httr2::req_error(is_error = \(r) FALSE) |>
    httr2::req_perform()

  if (httr2::resp_status(resp) != 200L) {
    stop(sprintf(
      "Gemini API erro %d: %s",
      httr2::resp_status(resp),
      httr2::resp_body_string(resp)
    ))
  }

  data <- httr2::resp_body_json(resp)
  data$candidates[[1]]$content$parts[[1]]$text
}

gemini_provider <- function(api_key = NULL,
                            model = "gemini-2.0-flash",
                            max_tokens = 2048L) {
  key <- api_key %||% Sys.getenv("GEMINI_API_KEY")
  if (!nzchar(key)) {
    stop("Chave Gemini nao encontrada. Defina GEMINI_API_KEY ou use --gemini-key.")
  }
  list(
    name     = paste0("Google Gemini (", model, ")"),
    complete = function(system, messages) {
      .gemini_complete(key, model, max_tokens, system, messages)
    }
  )
}

# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

create_provider <- function(provider   = "anthropic",
                            api_key    = NULL,
                            model      = NULL,
                            fast       = FALSE,
                            max_tokens = 2048L) {
  p <- tolower(provider)

  if (p %in% c("anthropic", "claude")) {
    default_model <- if (fast) "claude-haiku-4-5-20251001" else "claude-sonnet-4-6"
    anthropic_provider(api_key    = api_key,
                       model      = model %||% default_model,
                       max_tokens = max_tokens)

  } else if (p %in% c("gemini", "google")) {
    default_model <- if (fast) "gemini-2.0-flash" else "gemini-2.0-flash"
    gemini_provider(api_key    = api_key,
                    model      = model %||% default_model,
                    max_tokens = max_tokens)

  } else {
    stop(sprintf(
      "Provedor desconhecido: '%s'. Use 'anthropic' ou 'gemini'.", provider
    ))
  }
}
