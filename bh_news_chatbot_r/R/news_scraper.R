# news_scraper.R
# Raspa o conteudo textual de URLs de noticias.
# Usa httr2 + rvest para extrair titulo, data e corpo do artigo.
# Salva cache local em JSON para evitar re-downloads.

CACHE_FILE         <- file.path(dirname(dirname(rlang::current_call()[[1]])),
                                "cache", "news_cache.json")
REQUEST_DELAY      <- 1.0   # segundos entre requisicoes
REQUEST_TIMEOUT    <- 20L
MAX_CONTENT_LENGTH <- 8000L  # chars por artigo

.scraper_headers <- c(
  "User-Agent" = paste0(
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ",
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
  ),
  "Accept-Language" = "pt-BR,pt;q=0.9"
)

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

.cache_path <- function() {
  p <- file.path(
    system.file(package = character(0)),  # vazio
    ".."                                  # nao usado
  )
  # Usa caminho relativo ao script
  cache_dir <- file.path(
    normalizePath(file.path(dirname(sys.frame(0)$ofile %||% "."), "..")),
    "cache"
  )
  if (!dir.exists(cache_dir)) dir.create(cache_dir, recursive = TRUE)
  file.path(cache_dir, "news_cache.json")
}

load_cache <- function(cache_file) {
  if (!file.exists(cache_file)) return(list())
  tryCatch(
    jsonlite::read_json(cache_file),
    error = function(e) list()
  )
}

save_cache <- function(cache, cache_file) {
  dir.create(dirname(cache_file), recursive = TRUE, showWarnings = FALSE)
  jsonlite::write_json(cache, cache_file, auto_unbox = TRUE, pretty = TRUE)
}

# ---------------------------------------------------------------------------
# HTTP + parsing
# ---------------------------------------------------------------------------

.fetch_html <- function(url) {
  tryCatch({
    resp <- httr2::request(url) |>
      httr2::req_headers(!!!.scraper_headers) |>
      httr2::req_timeout(REQUEST_TIMEOUT) |>
      httr2::req_error(is_error = \(r) FALSE) |>
      httr2::req_perform()

    status <- httr2::resp_status(resp)
    if (status != 200L) {
      message(sprintf("HTTP %d para %s", status, url))
      return(NULL)
    }

    ct <- httr2::resp_content_type(resp)
    if (!grepl("text/html|text/plain", ct, ignore.case = TRUE)) {
      return(NULL)
    }

    httr2::resp_body_string(resp)
  }, error = function(e) {
    message(sprintf("Erro ao acessar %s: %s", url, conditionMessage(e)))
    NULL
  })
}

.extract_article <- function(html, url) {
  doc <- tryCatch(rvest::read_html(html), error = function(e) NULL)
  if (is.null(doc)) return(list(url = url, title = "", date = "", body = ""))

  # Remove ruido
  rvest::html_nodes(doc, "script, style, nav, footer, header, aside, noscript") |>
    xml2::xml_remove()

  # Titulo
  title <- tryCatch({
    t <- rvest::html_text2(rvest::html_node(doc, "h1"))
    if (is.na(t) || !nzchar(t)) {
      t <- rvest::html_text2(rvest::html_node(doc, "title"))
    }
    trimws(t %||% "")
  }, error = function(e) "")

  # Data
  date <- tryCatch({
    el <- rvest::html_node(doc, paste(c(
      "time", "[class*='date']", "[class*='data']",
      "[class*='published']", "[class*='time']"
    ), collapse = ", "))
    trimws(rvest::html_text2(el) %||% "")
  }, error = function(e) "")

  # Corpo
  body <- ""
  selectors <- c(
    "article", "[class*='article-body']", "[class*='materia']",
    "[class*='content']", "[class*='texto']", "main", ".post-content"
  )
  for (sel in selectors) {
    el <- tryCatch(rvest::html_node(doc, sel), error = function(e) NULL)
    if (!is.null(el) && !is.na(el)) {
      candidate <- trimws(rvest::html_text2(el))
      if (nchar(candidate) > 200) {
        body <- candidate
        break
      }
    }
  }

  if (!nzchar(body)) {
    body <- tryCatch(
      trimws(rvest::html_text2(rvest::html_node(doc, "body"))),
      error = function(e) ""
    )
  }

  # Limpa espacos excessivos
  body <- gsub("\n{3,}", "\n\n", body)

  list(url = url, title = title %||% "", date = date %||% "", body = body %||% "")
}

# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------

scrape_article <- function(url, cache) {
  if (!is.null(cache[[url]])) return(cache[[url]])

  html <- .fetch_html(url)
  if (is.null(html)) {
    cache[[url]] <<- NULL
    return(NULL)
  }

  result <- .extract_article(html, url)

  # Trunca body
  if (nchar(result$body) > MAX_CONTENT_LENGTH) {
    result$body <- paste0(
      substr(result$body, 1, MAX_CONTENT_LENGTH),
      "\n[...conteudo truncado]"
    )
  }

  cache[[url]] <<- result
  result
}

scrape_all <- function(news_by_area,
                       max_per_area = 10L,
                       use_cache    = TRUE,
                       cache_file   = NULL) {
  if (is.null(cache_file)) {
    cache_dir  <- file.path(dirname(sys.frame(0)$ofile %||% "."), "..", "cache")
    cache_file <- file.path(normalizePath(cache_dir, mustWork = FALSE), "news_cache.json")
  }
  dir.create(dirname(cache_file), recursive = TRUE, showWarnings = FALSE)

  cache <- if (use_cache) load_cache(cache_file) else list()

  articles  <- list()
  areas     <- names(news_by_area)
  n_areas   <- length(areas)

  for (i in seq_along(areas)) {
    area <- areas[[i]]
    urls <- head(news_by_area[[area]], max_per_area)
    message(sprintf("[%d/%d] Raspando area '%s' (%d links)...",
                    i, n_areas, area, length(urls)))

    for (j in seq_along(urls)) {
      url <- urls[[j]]
      message(sprintf("  [%d/%d] %s", j, length(urls), substr(url, 1, 80)))

      article <- scrape_article(url, cache)
      if (!is.null(article)) {
        article$area <- area
        articles <- c(articles, list(article))
      }

      if (use_cache && j %% 5 == 0) save_cache(cache, cache_file)
      Sys.sleep(REQUEST_DELAY)
    }
  }

  if (use_cache) save_cache(cache, cache_file)
  message(sprintf("Total de artigos raspados: %d", length(articles)))
  articles
}

format_articles_for_context <- function(articles, max_total_chars = 80000L) {
  parts <- character(0)
  total <- 0L

  for (art in articles) {
    area       <- art$area  %||% "Geral"
    title      <- art$title %||% "(sem titulo)"
    date       <- art$date  %||% ""
    url        <- art$url   %||% ""
    body       <- art$body  %||% ""
    categories <- art$categories

    cats_str <- if (!is.null(categories) && length(categories) > 0)
      paste(categories, collapse = ", ") else ""

    section <- paste0(
      "--- NOTICIA ---\n",
      "Area: ",     area,  "\n",
      if (nzchar(cats_str)) paste0("Categorias: ", cats_str, "\n") else "",
      "Titulo: ",   title, "\n",
      if (nzchar(date)) paste0("Data: ", date, "\n") else "",
      "URL: ",      url,   "\n\n",
      body,          "\n\n"
    )

    if (total + nchar(section) > max_total_chars) break
    parts <- c(parts, section)
    total <- total + nchar(section)
  }

  paste(parts, collapse = "\n")
}
