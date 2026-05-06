#!/usr/bin/env python3
"""
test_maritaca.py — Testes dedicados ao provedor Maritaca AI (Sabiá).

Testa complete(), stream() e tratamento de erros usando os modelos
sabia-4 (chat) e sabiazinho-4 (fast) via API compatível com OpenAI.

Uso:
    python bh_news_chatbot/test_maritaca.py
    python bh_news_chatbot/test_maritaca.py --only-errors
    python bh_news_chatbot/test_maritaca.py --fast
"""

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from llm_provider import (
    MARITACA_BASE_URL,
    MARITACA_CHAT_MODEL,
    MARITACA_FAST_MODEL,
    MariticaProvider,
    create_provider,
)

SYSTEM_PROMPT = "Você é um assistente de teste. Responda de forma muito breve."
TEST_MESSAGE  = [{"role": "user", "content": "Diga apenas: OK"}]
INVALID_KEY   = "chave-invalida-para-teste-xyz-000"
INVALID_MODEL = "modelo-inexistente-xyz-9999"

GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
SEP    = "─" * 55
SEP2   = "┄" * 55


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


def _expect_error(label: str, fn, expected_types: tuple = (Exception,)) -> bool:
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


# ---------------------------------------------------------------------------
# Testes funcionais
# ---------------------------------------------------------------------------

def test_factory(api_key: str, model: str) -> MariticaProvider | None:
    try:
        p = create_provider("maritaca", api_key=api_key, model=model)
        _ok("create_provider('maritaca')", p.name)
        return p
    except Exception as e:
        _fail("create_provider('maritaca')", str(e))
        return None


def test_complete(provider: MariticaProvider) -> bool:
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


def test_stream(provider: MariticaProvider) -> bool:
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


def test_multi_turn(provider: MariticaProvider) -> bool:
    """Verifica que o provedor mantém contexto em conversas multi-turno."""
    messages = [
        {"role": "user",      "content": "Meu nome é Claude."},
        {"role": "assistant", "content": "Olá, Claude!"},
        {"role": "user",      "content": "Qual é o meu nome? Responda em uma palavra."},
    ]
    try:
        t0 = time.perf_counter()
        response = provider.complete(SYSTEM_PROMPT, messages)
        elapsed = time.perf_counter() - t0
        preview = response.strip()[:60].replace("\n", " ")
        _ok("complete() multi-turno", f'{elapsed:.1f}s  "{preview}"')
        return True
    except Exception as e:
        _fail("complete() multi-turno", str(e))
        return False


def run_functional_tests(api_key: str, model: str) -> tuple[int, int]:
    _section(f"testes funcionais — {model}")
    passed = 0
    total  = 0

    provider = test_factory(api_key, model)
    total += 1
    if provider is None:
        _skip("complete()",        "factory falhou")
        _skip("stream()",          "factory falhou")
        _skip("complete() multi-turno", "factory falhou")
        total += 3
        return passed, total

    passed += 1

    total += 1; passed += test_complete(provider)
    total += 1; passed += test_stream(provider)
    total += 1; passed += test_multi_turn(provider)

    return passed, total


# ---------------------------------------------------------------------------
# Testes de erros esperados
# ---------------------------------------------------------------------------

def run_error_tests(api_key: str) -> tuple[int, int]:
    _section("erros esperados")
    passed = 0
    total  = 0

    # Chave vazia → ValueError antes de chamar a API
    total += 1
    passed += _expect_error(
        "chave vazia → ValueError",
        lambda: create_provider("maritaca", api_key=""),
        (ValueError,),
    )

    # Chave inválida → erro de autenticação em complete()
    total += 1
    passed += _expect_error(
        "chave inválida → complete() falha",
        lambda: create_provider("maritaca", api_key=INVALID_KEY)
                    .complete(SYSTEM_PROMPT, TEST_MESSAGE),
    )

    # Chave inválida → erro de autenticação em stream()
    total += 1
    passed += _expect_error(
        "chave inválida → stream() falha",
        lambda: list(
            create_provider("maritaca", api_key=INVALID_KEY)
                .stream(SYSTEM_PROMPT, TEST_MESSAGE)
        ),
    )

    # Modelo inexistente requer chave válida para chegar na API
    if api_key:
        total += 1
        passed += _expect_error(
            "modelo inexistente → complete() falha",
            lambda: create_provider("maritaca", api_key=api_key, model=INVALID_MODEL)
                        .complete(SYSTEM_PROMPT, TEST_MESSAGE),
        )
    else:
        _skip("modelo inexistente → complete() falha", "requer MARITACA_KEY válida")

    return passed, total


# ---------------------------------------------------------------------------
# Verificações de configuração
# ---------------------------------------------------------------------------

def run_config_checks() -> tuple[int, int]:
    _section("verificações de configuração")
    passed = 0
    total  = 0

    # Base URL correta
    total += 1
    expected = "https://chat.maritaca.ai/api"
    if MARITACA_BASE_URL == expected:
        _ok("MARITACA_BASE_URL", MARITACA_BASE_URL)
        passed += 1
    else:
        _fail("MARITACA_BASE_URL", f"esperado '{expected}', obtido '{MARITACA_BASE_URL}'")

    # Modelos padrão existem (não são vazios)
    total += 1
    if MARITACA_CHAT_MODEL:
        _ok("MARITACA_CHAT_MODEL", MARITACA_CHAT_MODEL)
        passed += 1
    else:
        _fail("MARITACA_CHAT_MODEL", "vazio")

    total += 1
    if MARITACA_FAST_MODEL:
        _ok("MARITACA_FAST_MODEL", MARITACA_FAST_MODEL)
        passed += 1
    else:
        _fail("MARITACA_FAST_MODEL", "vazio")

    # Alias "sabia" funciona na factory
    total += 1
    passed += _expect_error(
        "alias 'sabia' com chave vazia → ValueError (factory reconhece alias)",
        lambda: create_provider("sabia", api_key=""),
        (ValueError,),
    )

    return passed, total


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Testes dedicados ao provedor Maritaca AI (Sabiá)"
    )
    parser.add_argument(
        "--only-errors",
        action="store_true",
        help="Executa apenas testes de erros e configuração (sem chave válida)",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help=f"Usa o modelo rápido ({MARITACA_FAST_MODEL}) nos testes funcionais",
    )
    args = parser.parse_args()

    api_key = os.environ.get("MARITACA_KEY", "")
    model   = MARITACA_FAST_MODEL if args.fast else MARITACA_CHAT_MODEL

    print(f"\n{BOLD}Testes Maritaca AI (Sabiá){RESET}")
    print(SEP)
    status = "configurada" if api_key else f"{YELLOW}não configurada{RESET}"
    print(f"  MARITACA_KEY : {status}")
    print(f"  Modelo chat  : {MARITACA_CHAT_MODEL}")
    print(f"  Modelo fast  : {MARITACA_FAST_MODEL}")
    print(f"  Base URL     : {MARITACA_BASE_URL}")

    total_passed = 0
    total_tests  = 0

    # Verificações de configuração (sempre rodam)
    cp, ct = run_config_checks()
    total_passed += cp
    total_tests  += ct

    # Testes de erros (sempre rodam)
    ep, et = run_error_tests(api_key)
    total_passed += ep
    total_tests  += et

    # Testes funcionais (requerem chave válida)
    if not args.only_errors:
        if not api_key:
            print(f"\n  {YELLOW}Testes funcionais ignorados — defina MARITACA_KEY para executá-los.{RESET}")
        else:
            fp, ft = run_functional_tests(api_key, model)
            total_passed += fp
            total_tests  += ft

    # Sumário
    print(f"\n{SEP}")
    color  = GREEN if total_passed == total_tests else RED
    status = "PASSOU" if total_passed == total_tests else "FALHOU"
    print(f"  {color}{BOLD}{status}{RESET}  {total_passed}/{total_tests} teste(s)")
    print()
    sys.exit(0 if total_passed == total_tests else 1)


if __name__ == "__main__":
    main()
