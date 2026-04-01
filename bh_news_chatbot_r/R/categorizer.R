# categorizer.R
# Categoriza decretos municipais de BH com base em seu conteudo usando um provedor de LLM.
# Processa documentos em lotes e persiste resultados em cache JSON.

CATEGORIES <- c(
  "Urbanismo e Zoneamento",
  "Obras e Infraestrutura Urbana",
  "Saude Publica",
  "Educacao",
  "Meio Ambiente e Saneamento",
  "Tributacao e Financas Publicas",
  "Administracao Publica",
  "Seguranca Publica e Defesa Civil",
  "Transporte e Mobilidade Urbana",
  "Habitacao e Regularizacao Fundiaria",
  "Assistencia Social",
  "Cultura, Esporte e Lazer",
  "Licitacoes e Contratos",
  "Pessoal e Recursos Humanos",
  "Outros"
)

BATCH_SIZE <- 15L

.CATEGORIZER_SYSTEM <- paste0(
  "Voce e um classificador de atos normativos municipais. Dada uma lista de decretos ou ",
  "documentos oficiais do municipio de Belo Horizonte (BH), atribua a cada um entre 1 e 3 ",
  "categorias do seguinte vocabulario controlado de legislacao municipal:\n\n",
  jsonlite::toJSON(CATEGORIES, auto_unbox = FALSE),
  "\n\nResponda SOMENTE com um objeto JSON no formato:\n",
  '{"<url>": ["Categoria1", "Categoria2"], "<url2>": ["Categoria1"]}',
  "\n\nRegras:\n",
  "- Use apenas categorias do vocabulario acima (exatamente como escritas).\n",
  "- Atribua no minimo 1 e no maximo 3 categorias por artigo.\n",
  "- Se nao se encaixar em nenhuma, use 'Outros'.\n",
  "- Nao inclua explicacoes fora do JSON."
)

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

.cat_cache_path <- function(cache_dir) {
  dir.create(cache_dir, recursive = TRUE, showWarnings = FALSE)
  file.path(cache_dir, "categories_cache.json")
}

.load_cat_cache <- function(cache_file) {
  if (!file.exists(cache_file)) return(list())
  tryCatch(jsonlite::read_json(cache_file), error = function(e) list())
}

.save_cat_cache <- function(cache, cache_file) {
  jsonlite::write_json(cache, cache_file, auto_unbox = TRUE, pretty = TRUE)
}

# ---------------------------------------------------------------------------
# Classificacao em lote
# ---------------------------------------------------------------------------

.build_batch_prompt <- function(batch) {
  parts <- lapply(batch, function(art) {
    snippet <- substr(art$body %||% "", 1, 600)
    paste0(
      "URL: ",    art$url   %||% "", "\n",
      "Titulo: ", art$title %||% "", "\n",
      "Trecho: ", snippet,           "\n"
    )
  })
  paste(parts, collapse = "\n---\n")
}

.classify_batch <- function(provider, batch) {
  prompt <- .build_batch_prompt(batch)
  raw    <- tryCatch(
    provider$complete(
      .CATEGORIZER_SYSTEM,
      list(list(role = "user", content = prompt))
    ),
    error = function(e) {
      message(sprintf("Erro na API de categorizacao: %s", conditionMessage(e)))
      NULL
    }
  )

  if (is.null(raw)) return(list())

  # Extrai JSON da resposta
  json_match <- regmatches(raw, regexpr("\\{[^\\{]*\\}", raw, perl = TRUE))
  if (length(json_match) == 0) {
    # Tenta match multiline
    json_match <- regmatches(raw, regexpr("\\{[\\s\\S]*\\}", raw, perl = TRUE))
  }
  if (length(json_match) == 0) {
    message(sprintf("Sem JSON valido na resposta: %s", substr(raw, 1, 200)))
    return(list())
  }

  result <- tryCatch(
    jsonlite::fromJSON(json_match, simplifyVector = FALSE),
    error = function(e) {
      message(sprintf("Erro ao parsear JSON de categorias: %s", conditionMessage(e)))
      list()
    }
  )

  # Sanitiza: garante que os valores sao vetores de strings do vocabulario
  valid <- CATEGORIES
  clean <- list()
  for (url in names(result)) {
    cats <- result[[url]]
    if (!is.list(cats) && !is.character(cats)) next
    cats <- as.character(unlist(cats))
    cats <- cats[cats %in% valid]
    if (length(cats) == 0) cats <- "Outros"
    clean[[url]] <- cats
  }

  clean
}

# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------

categorize_articles <- function(articles,
                                provider   = NULL,
                                use_cache  = TRUE,
                                batch_size = BATCH_SIZE,
                                cache_dir  = NULL) {
  if (is.null(provider)) {
    stop("Um provedor de LLM deve ser fornecido via provider=create_provider(...).")
  }

  if (is.null(cache_dir)) {
    cache_dir <- file.path(
      normalizePath(file.path(dirname(sys.frame(0)$ofile %||% "."), ".."), mustWork = FALSE),
      "cache"
    )
  }

  cache_file <- .cat_cache_path(cache_dir)
  cache      <- if (use_cache) .load_cat_cache(cache_file) else list()

  # Artigos ainda nao categorizados
  pending <- Filter(function(a) !is.null(a$url) && is.null(cache[[a$url]]), articles)

  if (length(pending) == 0) {
    message("Todos os artigos ja estao categorizados (cache).")
  } else {
    n_batches <- ceiling(length(pending) / batch_size)
    message(sprintf("Categorizando %d artigos em %d lotes...", length(pending), n_batches))

    for (i in seq(1, length(pending), by = batch_size)) {
      batch   <- pending[i:min(i + batch_size - 1L, length(pending))]
      batch_n <- ceiling(i / batch_size)
      message(sprintf("  Lote %d/%d (%d artigos)...", batch_n, n_batches, length(batch)))

      result <- .classify_batch(provider, batch)
      for (url in names(result)) cache[[url]] <- result[[url]]

      # Artigos sem retorno recebem "Outros"
      for (art in batch) {
        if (is.null(cache[[art$url]])) cache[[art$url]] <- "Outros"
      }

      if (use_cache) .save_cat_cache(cache, cache_file)
    }
  }

  # Aplica categorias nos artigos (modifica in-place via parent env)
  for (i in seq_along(articles)) {
    url <- articles[[i]]$url
    articles[[i]]$categories <- cache[[url]] %||% "Outros"
  }

  message("Categorizacao concluida.")
  articles
}

summarize_by_category <- function(articles) {
  result <- list()
  for (art in articles) {
    for (cat in (art$categories %||% "Outros")) {
      result[[cat]] <- c(result[[cat]], list(art))
    }
  }
  result
}

print_category_report <- function(articles) {
  by_cat <- summarize_by_category(articles)
  cat("\n\U0001F4CA Distribuicao por categoria:\n")
  cat(strrep("\u2500", 45), "\n")
  for (cat_name in CATEGORIES) {
    count <- length(by_cat[[cat_name]])
    if (count > 0) {
      bar <- strrep("\u2588", min(count, 30))
      cat(sprintf("  %-30s %s %d\n", cat_name, bar, count))
    }
  }
  cat(strrep("\u2500", 45), "\n")
  total      <- length(articles)
  categorized <- sum(sapply(articles, function(a) {
    cats <- a$categories %||% "Outros"
    !identical(as.character(cats), "Outros")
  }))
  cat(sprintf("  Total: %d artigos | Categorizados: %d\n\n", total, categorized))
}
