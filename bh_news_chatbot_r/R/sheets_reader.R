# sheets_reader.R
# Le links de noticias de uma planilha publica do Google Sheets.
#
# Pre-requisito: planilha deve estar publica.
#   Arquivo -> Compartilhar -> "Qualquer pessoa com o link" -> Leitor
#   OU Arquivo -> Publicar na web -> CSV -> Publicar

SPREADSHEET_ID <- "1GcHLEuIXtRFPy4md6o_EdSBcDp69p3Y3"
DEFAULT_GID    <- "0"

GVIZ_CSV_URL <- "https://docs.google.com/spreadsheets/d/%s/gviz/tq?tqx=out:csv&gid=%s"
EXPORT_CSV_URL <- "https://docs.google.com/spreadsheets/d/%s/export?format=csv&gid=%s"
HTML_VIEW_URL  <- "https://docs.google.com/spreadsheets/d/%s/htmlview"

.ua_headers <- c(
  "User-Agent"      = paste0(
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ",
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
  ),
  "Accept-Language" = "pt-BR,pt;q=0.9"
)

# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

.fetch_url <- function(url, timeout = 20L) {
  tryCatch({
    resp <- httr2::request(url) |>
      httr2::req_headers(!!!.ua_headers) |>
      httr2::req_timeout(timeout) |>
      httr2::req_error(is_error = \(r) FALSE) |>
      httr2::req_perform()

    if (httr2::resp_status(resp) != 200L) {
      message(sprintf("HTTP %d ao acessar %s", httr2::resp_status(resp), url))
      return(NULL)
    }
    httr2::resp_body_string(resp)
  }, error = function(e) {
    message(sprintf("Erro ao acessar %s: %s", url, conditionMessage(e)))
    NULL
  })
}

# ---------------------------------------------------------------------------
# Descoberta de abas via HTML
# ---------------------------------------------------------------------------

.parse_gids_from_html <- function(html) {
  sheets <- list()

  # Padrao 1: "sheetId":<gid>,"title":"<nome>" (JSON embutido)
  m <- gregexpr('"sheetId"\\s*:\\s*(\\d+).*?"title"\\s*:\\s*"([^"]+)"', html, perl = TRUE)
  matches <- regmatches(html, m)[[1]]
  if (length(matches) > 0) {
    for (match in matches) {
      gid   <- sub('.*"sheetId"\\s*:\\s*(\\d+).*', "\\1", match, perl = TRUE)
      title <- sub('.*"title"\\s*:\\s*"([^"]+)".*', "\\1", match, perl = TRUE)
      if (nzchar(gid) && nzchar(title)) {
        sheets <- c(sheets, list(list(title = title, gid = gid)))
      }
    }
    if (length(sheets) > 0) return(sheets)
  }

  # Padrao 2: data-sheet-id="<gid>"
  m2 <- gregexpr('data-sheet-id=["\']?(\\d+)["\']?', html, perl = TRUE)
  gids_found <- regmatches(html, m2)[[1]]
  if (length(gids_found) > 0) {
    for (i in seq_along(gids_found)) {
      gid <- sub('data-sheet-id=["\']?(\\d+)["\']?', "\\1", gids_found[[i]], perl = TRUE)
      sheets <- c(sheets, list(list(title = paste0("Aba", i), gid = gid)))
    }
    if (length(sheets) > 0) return(sheets)
  }

  list()
}

list_sheet_gids <- function(sheet_id = SPREADSHEET_ID) {
  url  <- sprintf(HTML_VIEW_URL, sheet_id)
  html <- .fetch_url(url)

  if (is.null(html)) {
    message(
      "Nao foi possivel acessar a planilha. ",
      "Verifique se ela e publica (compartilhada como 'Qualquer pessoa com o link')."
    )
    return(list(list(title = "Noticias", gid = DEFAULT_GID)))
  }

  sheets <- .parse_gids_from_html(html)

  if (length(sheets) == 0) {
    message("Nao foi possivel detectar abas no HTML — usando GID padrao.")
    return(list(list(title = "Noticias", gid = DEFAULT_GID)))
  }

  sheets
}

# ---------------------------------------------------------------------------
# Download de CSV
# ---------------------------------------------------------------------------

.fetch_csv_content <- function(sheet_id, gid) {
  urls <- c(
    sprintf(GVIZ_CSV_URL,   sheet_id, gid),
    sprintf(EXPORT_CSV_URL, sheet_id, gid)
  )

  for (url in urls) {
    message(sprintf("  Tentando: %s", url))
    content <- .fetch_url(url)
    if (!is.null(content) && !startsWith(trimws(content), "<!DOCTYPE")) {
      return(content)
    }
    if (!is.null(content)) {
      message("  Recebeu HTML em vez de CSV — planilha pode nao ser publica.")
    }
  }
  NULL
}

read_sheet_csv <- function(sheet_id, gid) {
  content <- .fetch_csv_content(sheet_id, gid)
  if (is.null(content)) return(data.frame())

  tryCatch(
    readr::read_csv(content, show_col_types = FALSE, name_repair = "minimal"),
    error = function(e) {
      message(sprintf("Erro ao parsear CSV (gid=%s): %s", gid, conditionMessage(e)))
      data.frame()
    }
  )
}

# ---------------------------------------------------------------------------
# Extracao de URLs
# ---------------------------------------------------------------------------

.extract_urls <- function(text) {
  m <- gregexpr("https?://[^\\s,;\"'>)\\]]+", text, perl = TRUE)
  unlist(regmatches(text, m))
}

# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------

load_all_news_links <- function(sheet_id  = SPREADSHEET_ID,
                                extra_gids = NULL) {
  sheets <- if (!is.null(extra_gids)) extra_gids else list_sheet_gids(sheet_id)
  message(sprintf("Abas encontradas: %s",
                  paste(sapply(sheets, `[[`, "title"), collapse = ", ")))

  news_by_area <- list()

  for (s in sheets) {
    area <- s$title
    gid  <- s$gid
    df   <- read_sheet_csv(sheet_id, gid)

    urls <- character(0)
    if (nrow(df) > 0) {
      for (col in as.list(df)) {
        vals <- as.character(col[!is.na(col)])
        urls <- c(urls, unlist(lapply(vals, .extract_urls)))
      }
    }

    urls <- unique(urls)

    if (length(urls) > 0) {
      news_by_area[[area]] <- urls
      message(sprintf("  %s: %d links encontrados", area, length(urls)))
    } else {
      message(sprintf("  %s: nenhum link encontrado", area))
    }

    Sys.sleep(0.3)
  }

  if (length(news_by_area) == 0) {
    message(paste(
      "Nenhum link encontrado. Verifique se a planilha esta publica:",
      "  1. Abra a planilha no Google Sheets",
      "  2. Arquivo -> Compartilhar -> 'Qualquer pessoa com o link' -> Leitor",
      "  OU",
      "  2. Arquivo -> Publicar na web -> CSV -> Publicar",
      sprintf("  ID da planilha: %s", sheet_id),
      sep = "\n"
    ))
  }

  news_by_area
}
