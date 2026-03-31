# install_packages.R
# Instala os pacotes necessarios para o chatbot de noticias de BH (versao R).
# Execute uma vez antes de rodar main.R:
#   Rscript install_packages.R

required <- c("httr2", "rvest", "jsonlite", "readr", "stringr", "rlang", "optparse")

to_install <- setdiff(required, rownames(installed.packages()))

if (length(to_install) == 0) {
  cat("Todos os pacotes ja estao instalados.\n")
} else {
  cat(sprintf("Instalando: %s\n", paste(to_install, collapse = ", ")))
  install.packages(to_install, repos = "https://cloud.r-project.org")
  cat("Instalacao concluida.\n")
}
