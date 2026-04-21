#!/usr/bin/env python3
"""
test_api.py — Verifica conectividade com as APIs de IA (Anthropic e Gemini).

Uso:
    python bh_news_chatbot/test_api.py
    python bh_news_chatbot/test_api.py --provider anthropic
    python bh_news_chatbot/test_api.py --provider gemini
"""

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

SYSTEM_PROMPT = "Você é um assistente de teste. Responda de forma muito breve."
TEST_MESSAGE  = [{"role": "user", "content": "Diga apenas: OK"}]

GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

SEP = "─" * 55


def _ok(label: str, detail: str = ""):
    suffix = f"  {detail}" if detail else ""
    print(f"  {GREEN}✓{RESET} {label}{suffix}")


def _fail(label: str, err: str = ""):
    msg = f": {err}" if err else ""
    print(f"  {RED}✗{RESET} {label}{msg}")


def _skip(label: str, reason: str = ""):
    msg = f" ({reason})" if reason else ""
    print(f"  {YELLOW}–{RESET} {label}{msg}")


# ---------------------------------------------------------------------------
# Testes individuais
# ---------------------------------------------------------------------------

def test_factory(provider_name: str, api_key: str) -> object | None:
    """Testa create_provider() e retorna a instância ou None se falhar."""
    from llm_provider import create_provider
    try:
        p = create_provider(provider_name, api_key=api_key)
        _ok("create_provider()", p.name)
        return p
    except Exception as e:
        _fail("create_provider()", str(e))
        return None


def test_complete(provider) -> bool:
    """Testa complete() — resposta única."""
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
    """Testa stream() — coleta tokens e verifica que há saída."""
    try:
        t0 = time.perf_counter()
        tokens = list(provider.stream(SYSTEM_PROMPT, TEST_MESSAGE))
        elapsed = time.perf_counter() - t0
        full = "".join(tokens).strip()[:60].replace("\n", " ")
        n = len(tokens)
        _ok("stream()", f'{elapsed:.1f}s  {n} token(s)  "{full}"')
        return True
    except Exception as e:
        _fail("stream()", str(e))
        return False


# ---------------------------------------------------------------------------
# Suite por provedor
# ---------------------------------------------------------------------------

def run_suite(provider_name: str, api_key: str) -> tuple[int, int]:
    """Executa os testes para um provedor. Retorna (passed, total)."""
    label = provider_name.capitalize()
    print(f"\n{BOLD}{label}{RESET}")
    print(SEP)

    if not api_key:
        env_var = "ANTHROPIC_API_KEY" if provider_name == "anthropic" else "GEMINI_API_KEY"
        _skip("todos os testes", f"{env_var} não configurada")
        return 0, 0

    passed = 0
    total  = 0

    provider = test_factory(provider_name, api_key)
    total += 1
    if provider:
        passed += 1

        total  += 1
        passed += test_complete(provider)

        total  += 1
        passed += test_stream(provider)
    else:
        _skip("complete()", "factory falhou")
        _skip("stream()",   "factory falhou")
        total += 2

    return passed, total


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Verifica conectividade com as APIs de IA (Anthropic e Gemini)"
    )
    parser.add_argument(
        "--provider",
        choices=["anthropic", "gemini", "all"],
        default="all",
        help="Provedor a testar (padrão: all)",
    )
    args = parser.parse_args()

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    gemini_key    = os.environ.get("GEMINI_API_KEY", "")

    print(f"\n{BOLD}Verificação de APIs — BH News Chatbot{RESET}")
    print(SEP)
    print(f"  ANTHROPIC_API_KEY : {'configurada' if anthropic_key else f'{YELLOW}não configurada{RESET}'}")
    print(f"  GEMINI_API_KEY    : {'configurada' if gemini_key    else f'{YELLOW}não configurada{RESET}'}")

    total_passed = 0
    total_tests  = 0

    providers_to_run = (
        ["anthropic", "gemini"] if args.provider == "all" else [args.provider]
    )

    key_map = {"anthropic": anthropic_key, "gemini": gemini_key}

    for pname in providers_to_run:
        p, t = run_suite(pname, key_map[pname])
        total_passed += p
        total_tests  += t

    # Sumário final
    print(f"\n{SEP}")
    skipped = sum(
        1 for pname in providers_to_run if not key_map[pname]
    )
    if total_tests == 0:
        print(f"  {YELLOW}Nenhum teste executado — configure pelo menos uma chave de API.{RESET}")
        print(f"  Veja: export ANTHROPIC_API_KEY=... ou export GEMINI_API_KEY=...")
        sys.exit(2)

    color  = GREEN if total_passed == total_tests else RED
    status = "PASSOU" if total_passed == total_tests else "FALHOU"
    print(
        f"  {color}{BOLD}{status}{RESET}  "
        f"{total_passed}/{total_tests} teste(s)"
        + (f"  ({skipped} provedor(es) sem chave)" if skipped else "")
    )
    print()
    sys.exit(0 if total_passed == total_tests else 1)


if __name__ == "__main__":
    main()
