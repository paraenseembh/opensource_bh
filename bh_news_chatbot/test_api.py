#!/usr/bin/env python3
"""
test_api.py — Verifica conectividade e tratamento de erros das APIs de IA.

Executa dois grupos de testes por provedor:

  Funcionais  — requerem chave válida; verificam complete() e stream().
  Erros       — verificam que erros esperados são lançados corretamente:
                  chave vazia, chave inválida, modelo inexistente, provider
                  desconhecido.

Uso:
    python bh_news_chatbot/test_api.py
    python bh_news_chatbot/test_api.py --provider anthropic
    python bh_news_chatbot/test_api.py --provider gemini
    python bh_news_chatbot/test_api.py --only-errors
"""

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

SYSTEM_PROMPT    = "Você é um assistente de teste. Responda de forma muito breve."
TEST_MESSAGE     = [{"role": "user", "content": "Diga apenas: OK"}]
INVALID_KEY      = "chave-invalida-para-teste-xyz-000"
INVALID_MODEL    = "modelo-inexistente-xyz-9999"

GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"

SEP  = "─" * 55
SEP2 = "┄" * 55


def _ok(label: str, detail: str = ""):
    suffix = f"  {DIM}{detail}{RESET}" if detail else ""
    print(f"  {GREEN}✓{RESET} {label}{suffix}")


def _fail(label: str, err: str = ""):
    msg = f": {err}" if err else ""
    print(f"  {RED}✗{RESET} {label}{RED}{msg}{RESET}")


def _skip(label: str, reason: str = ""):
    msg = f" ({reason})" if reason else ""
    print(f"  {YELLOW}–{RESET} {label}{YELLOW}{msg}{RESET}")


def _section(title: str):
    print(f"\n  {CYAN}{DIM}{title}{RESET}")
    print(f"  {SEP2}")


# ---------------------------------------------------------------------------
# Testes funcionais
# ---------------------------------------------------------------------------

def test_factory(provider_name: str, api_key: str):
    """Testa create_provider() e retorna instância ou None."""
    from llm_provider import create_provider
    try:
        p = create_provider(provider_name, api_key=api_key)
        _ok("create_provider()", p.name)
        return p
    except Exception as e:
        _fail("create_provider()", str(e))
        return None


def test_complete(provider) -> bool:
    try:
        t0 = time.perf_counter()
        response = provider.complete(SYSTEM_PROMPT, TEST_MESSAGE)
        elapsed = time.perf_counter() - t0
        preview = response.strip()[:60].replace("\n", " ")
        _ok("complete()", f'{elapsed:.1f}s  "{preview}"')
        return True
    except Exception as e:
        _fail("complete()", str(e))
        return False


def test_stream(provider) -> bool:
    try:
        t0 = time.perf_counter()
        tokens = list(provider.stream(SYSTEM_PROMPT, TEST_MESSAGE))
        elapsed = time.perf_counter() - t0
        full = "".join(tokens).strip()[:60].replace("\n", " ")
        _ok("stream()", f'{elapsed:.1f}s  {len(tokens)} token(s)  "{full}"')
        return True
    except Exception as e:
        _fail("stream()", str(e))
        return False


# ---------------------------------------------------------------------------
# Testes de erros esperados
# ---------------------------------------------------------------------------

def _expect_error(label: str, fn, expected_types: tuple = (Exception,)) -> bool:
    """Executa fn() e passa se lançar uma das exceções esperadas."""
    try:
        fn()
        _fail(label, "nenhuma exceção lançada (deveria ter falhado)")
        return False
    except expected_types as e:
        _ok(label, f"{type(e).__name__} lançado corretamente")
        return True
    except Exception as e:
        _fail(label, f"exceção inesperada — {type(e).__name__}: {e}")
        return False


def run_error_tests(provider_name: str, valid_key: str) -> tuple[int, int]:
    """
    Roda todos os testes de erro para um provedor.
    Retorna (passed, total).
    """
    from llm_provider import create_provider

    _section("erros esperados")
    passed = 0
    total  = 0

    # 1. Chave vazia → ValueError antes de chamar a API
    total += 1
    passed += _expect_error(
        "chave vazia → ValueError",
        lambda: create_provider(provider_name, api_key=""),
        (ValueError,),
    )

    # 2. Chave inválida → erro de autenticação em complete()
    total += 1
    passed += _expect_error(
        "chave inválida → complete() falha",
        lambda: create_provider(provider_name, api_key=INVALID_KEY)
                    .complete(SYSTEM_PROMPT, TEST_MESSAGE),
    )

    # 3. Chave inválida → erro de autenticação em stream()
    total += 1
    passed += _expect_error(
        "chave inválida → stream() falha",
        lambda: list(
            create_provider(provider_name, api_key=INVALID_KEY)
                .stream(SYSTEM_PROMPT, TEST_MESSAGE)
        ),
    )

    # 4. Modelo inexistente → erro de API (requer chave válida)
    if valid_key:
        total += 1
        passed += _expect_error(
            "modelo inexistente → complete() falha",
            lambda: create_provider(provider_name, api_key=valid_key, model=INVALID_MODEL)
                        .complete(SYSTEM_PROMPT, TEST_MESSAGE),
        )
    else:
        _skip("modelo inexistente → complete() falha", "requer chave válida")

    return passed, total


def run_error_tests_generic() -> tuple[int, int]:
    """Testes de erro independentes de provedor."""
    from llm_provider import create_provider

    _section("erros gerais (independente de provedor)")
    passed = 0
    total  = 0

    # Provider desconhecido
    total += 1
    passed += _expect_error(
        "provider desconhecido → ValueError",
        lambda: create_provider("openai", api_key="qualquer"),
        (ValueError,),
    )

    # Mensagens vazias passadas para complete (chave inválida, erro antes da API)
    total += 1
    passed += _expect_error(
        "chave vazia anthropic → ValueError",
        lambda: create_provider("anthropic", api_key=""),
        (ValueError,),
    )

    total += 1
    passed += _expect_error(
        "chave vazia gemini → ValueError",
        lambda: create_provider("gemini", api_key=""),
        (ValueError,),
    )

    total += 1
    passed += _expect_error(
        "chave vazia maritaca → ValueError",
        lambda: create_provider("maritaca", api_key=""),
        (ValueError,),
    )

    return passed, total


# ---------------------------------------------------------------------------
# Suite completa por provedor
# ---------------------------------------------------------------------------

def run_suite(provider_name: str, api_key: str, only_errors: bool) -> tuple[int, int]:
    label = provider_name.capitalize()
    print(f"\n{BOLD}{label}{RESET}")
    print(SEP)

    passed = 0
    total  = 0

    # ── Testes funcionais ───────────────────────────────────────────────────
    if not only_errors:
        _section("testes funcionais")
        if not api_key:
            env_var = {
                "anthropic": "ANTHROPIC_API_KEY",
                "gemini":    "GEMINI_API_KEY",
                "maritaca":  "MARITACA_KEY",
            }.get(provider_name, f"{provider_name.upper()}_KEY")
            _skip("todos os testes funcionais", f"{env_var} não configurada")
        else:
            provider = test_factory(provider_name, api_key)
            total += 1
            if provider:
                passed += 1
                total  += 1; passed += test_complete(provider)
                total  += 1; passed += test_stream(provider)
            else:
                _skip("complete()", "factory falhou")
                _skip("stream()",   "factory falhou")
                total += 2

    # ── Testes de erros esperados ───────────────────────────────────────────
    ep, et = run_error_tests(provider_name, api_key)
    passed += ep
    total  += et

    return passed, total


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Verifica APIs de IA: testes funcionais e de erros esperados"
    )
    parser.add_argument(
        "--provider",
        choices=["anthropic", "gemini", "maritaca", "all"],
        default="all",
        help="Provedor a testar (padrão: all)",
    )
    parser.add_argument(
        "--only-errors",
        action="store_true",
        help="Executa apenas os testes de erros (não precisa de chave válida)",
    )
    args = parser.parse_args()

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    gemini_key    = os.environ.get("GEMINI_API_KEY", "")
    maritaca_key  = os.environ.get("MARITACA_KEY", "")

    print(f"\n{BOLD}Verificação de APIs — BH News Chatbot{RESET}")
    print(SEP)
    status_a = "configurada" if anthropic_key else f"{YELLOW}não configurada{RESET}"
    status_g = "configurada" if gemini_key    else f"{YELLOW}não configurada{RESET}"
    status_m = "configurada" if maritaca_key  else f"{YELLOW}não configurada{RESET}"
    print(f"  ANTHROPIC_API_KEY : {status_a}")
    print(f"  GEMINI_API_KEY    : {status_g}")
    print(f"  MARITACA_KEY      : {status_m}")

    total_passed = 0
    total_tests  = 0

    providers_to_run = (
        ["anthropic", "gemini", "maritaca"] if args.provider == "all" else [args.provider]
    )
    key_map = {"anthropic": anthropic_key, "gemini": gemini_key, "maritaca": maritaca_key}

    # Testes gerais independentes de provedor
    print(f"\n{BOLD}Geral{RESET}")
    print(SEP)
    gp, gt = run_error_tests_generic()
    total_passed += gp
    total_tests  += gt

    # Suites por provedor
    for pname in providers_to_run:
        p, t = run_suite(pname, key_map[pname], args.only_errors)
        total_passed += p
        total_tests  += t

    # Sumário final
    print(f"\n{SEP}")
    if total_tests == 0:
        print(f"  {YELLOW}Nenhum teste executado.{RESET}")
        sys.exit(2)

    skipped_functional = (
        sum(1 for pname in providers_to_run if not key_map[pname])
        if not args.only_errors else 0
    )

    color  = GREEN if total_passed == total_tests else RED
    status = "PASSOU" if total_passed == total_tests else "FALHOU"
    note   = f"  ({skipped_functional} provedor(es) sem chave: testes funcionais pulados)" if skipped_functional else ""
    print(
        f"  {color}{BOLD}{status}{RESET}  "
        f"{total_passed}/{total_tests} teste(s){note}"
    )
    print()
    sys.exit(0 if total_passed == total_tests else 1)


if __name__ == "__main__":
    main()
