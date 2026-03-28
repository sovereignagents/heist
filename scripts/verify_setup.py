#!/usr/bin/env python3
# === QV-LLM:BEGIN ===
# path: scripts/verify_setup.py
# role: module
# neighbors: annotate_headers.py, flatten.py, generate_audio.py
# exports: main
# git_branch: main
# git_commit: 1734031
# === QV-LLM:END ===

"""
scripts/verify_setup.py — Pre-flight diagnostics for the heist demo.

Checks everything required before running the demo:
  - Python version
  - Environment variables (API keys)
  - Python dependencies
  - Package structure (src/heist modules)
  - Generated audio files
  - External service connectivity (Speechmatics, Nebius)

No external servers need to be running — the LangGraph setup is fully
in-process. No action server or MCP proxy required.

Usage:
    make verify
    # or directly:
    uv run python scripts/verify_setup.py
"""

import asyncio
import importlib.util
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

GREEN   = "\033[92m"
YELLOW  = "\033[93m"
RED     = "\033[91m"
BLUE    = "\033[94m"
MAGENTA = "\033[95m"
BOLD    = "\033[1m"
RESET   = "\033[0m"
DIM     = "\033[2m"


def ok(msg: str)     -> None: print(f"{GREEN}  ✓  {msg}{RESET}")
def warn(msg: str)   -> None: print(f"{YELLOW}  ⚠  {msg}{RESET}")
def fail(msg: str)   -> None: print(f"{RED}  ✗  {msg}{RESET}")
def hint(msg: str)   -> None: print(f"{DIM}       → {msg}{RESET}")
def info(msg: str)   -> None: print(f"{BLUE}  ℹ  {msg}{RESET}")

def section(title: str) -> None:
    print(f"\n{BLUE}{BOLD}{'─' * 58}{RESET}")
    print(f"{BLUE}{BOLD}  {title}{RESET}")
    print(f"{BLUE}{BOLD}{'─' * 58}{RESET}")


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_python_version() -> bool:
    v = sys.version_info
    if v.major == 3 and v.minor in (10, 11):
        ok(f"Python {v.major}.{v.minor}.{v.micro}")
        return True
    fail(f"Python {v.major}.{v.minor} detected — requires 3.10 or 3.11")
    hint("Use pyenv: pyenv install 3.11 && pyenv local 3.11")
    return False


def check_env_var(name: str, label: str, required: bool = True) -> bool:
    value = os.getenv(name, "").strip()
    placeholder = f"your-{name.lower().replace('_', '-')}"
    if value and placeholder not in value.lower():
        masked = f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "***"
        ok(f"{label}  {DIM}({name}={masked}){RESET}")
        return True
    if required:
        fail(f"{label} not set  ({name})")
        hint(f"Add {name}=your-key to your .env file")
    else:
        warn(f"{label} not set  ({name})  — optional")
    return False


def check_module(module: str, label: str) -> bool:
    if importlib.util.find_spec(module) is not None:
        ok(label)
        return True
    fail(f"{label}  ({module}) not installed")
    hint("Run: make install")
    return False


def check_heist_package() -> bool:
    """Verify the installed src/heist package structure is complete."""
    all_ok = True
    modules = [
        ("heist",                           "heist  (package root)"),
        ("heist.demo",                      "heist.demo"),
        ("heist.text",                      "heist.text"),
        ("heist.audio",                     "heist.audio"),
        ("heist.graphs.bank_graph",         "heist.graphs.bank_graph"),
        ("heist.graphs.manager_graph",      "heist.graphs.manager_graph"),
        ("heist.graphs.state",              "heist.graphs.state"),
        ("heist.graphs.tools",              "heist.graphs.tools"),
        ("heist.agents.caller_agent",       "heist.agents.caller_agent"),
        ("heist.agents.security_classifier","heist.agents.security_classifier"),
        ("heist.services.speechmatics_service", "heist.services.speechmatics_service"),
        ("heist.services.demo_logger",      "heist.services.demo_logger"),
        ("heist.scenario.arc",              "heist.scenario.arc"),
        ("heist.ui.state",                  "heist.ui.state"),
        ("heist.ui.bubbles",                "heist.ui.bubbles"),
        ("heist.ui.layout",                 "heist.ui.layout"),
    ]
    for module, label in modules:
        if importlib.util.find_spec(module) is not None:
            ok(label)
        else:
            fail(f"{label}  — not importable")
            hint("Run: make install  (editable install needed)")
            all_ok = False
    return all_ok


def check_audio_files() -> bool:
    audio_dir = Path("tests/audio")
    expected  = [f"user_input_{i}.wav" for i in range(1, 6)]
    missing   = [f for f in expected if not (audio_dir / f).exists()]
    if not missing:
        ok(f"Audio files present  {DIM}({audio_dir}/){RESET}")
        return True
    fail(f"Missing audio files: {', '.join(missing)}")
    hint("Run: make generate-audio")
    return False


async def check_speechmatics(api_key: str) -> bool:
    if not api_key:
        fail("Speechmatics: skipped  (SPEECHMATICS_API_KEY not set)")
        return False
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://preview.tts.speechmatics.com/generate/theo",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type":  "application/json",
                },
                json={"text": "Test."},
                params={"output_format": "wav_16000"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    ok("Speechmatics TTS reachable  (key is valid)")
                    return True
                fail(f"Speechmatics TTS returned HTTP {resp.status}")
                hint("Check your SPEECHMATICS_API_KEY")
                return False
    except Exception as exc:
        fail(f"Speechmatics unreachable: {exc}")
        hint("Check your internet connection")
        return False


async def check_nebius(api_key: str) -> bool:
    if not api_key:
        fail("Nebius: skipped  (NEBIUS_API_KEY not set)")
        return False
    try:
        import aiohttp
        # Minimal chat completion — cheapest valid request to test auth
        payload = {
            "model":      "google/gemma-3-27b-it-fast",
            "messages":   [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.tokenfactory.nebius.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type":  "application/json",
                },
                json=payload,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status == 200:
                    ok("Nebius API reachable  (key is valid, Gemma endpoint)")
                    return True
                body = await resp.text()
                fail(f"Nebius returned HTTP {resp.status}")
                hint(f"Response: {body[:120]}")
                return False
    except Exception as exc:
        fail(f"Nebius unreachable: {exc}")
        hint("Check your internet connection and NEBIUS_API_KEY")
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run_checks() -> int:
    print(f"\n{BOLD}{BLUE}{'=' * 58}{RESET}")
    print(f"{BOLD}{BLUE}  🏦  The Heist — Pre-flight Diagnostics{RESET}")
    print(f"{BOLD}{BLUE}{'=' * 58}{RESET}")
    info("No external servers required — LangGraph runs in-process.")

    errors   = 0
    warnings = 0

    # ── Python ───────────────────────────────────────────────────────────
    section("Python Environment")
    if not check_python_version():
        errors += 1

    # ── API Keys ─────────────────────────────────────────────────────────
    section("API Keys  (.env)")
    nebius_key       = os.getenv("NEBIUS_API_KEY", "").strip()
    speechmatics_key = os.getenv("SPEECHMATICS_API_KEY", "").strip()

    if not check_env_var("NEBIUS_API_KEY",       "Nebius API Key      (Gemma + MiniMax LLMs)"):
        errors += 1
    if not check_env_var("SPEECHMATICS_API_KEY", "Speechmatics API Key (TTS + optional ASR)"):
        errors += 1

    # Optional — ASR round-trip
    asr_enabled = os.getenv("ENABLE_SPEECHMATICS_ASR", "false").lower() == "true"
    if asr_enabled:
        ok("ENABLE_SPEECHMATICS_ASR=true  (realistic speech loop active)")
    else:
        info("ENABLE_SPEECHMATICS_ASR=false  (LLM text sent directly — set true for full loop)")

    # ── Python deps ───────────────────────────────────────────────────────
    section("Python Dependencies")
    deps = [
        ("langgraph",        "langgraph"),
        ("langchain",        "langchain"),
        ("langchain_openai", "langchain-openai"),
        ("aiohttp",          "aiohttp"),
        ("speechmatics",     "speechmatics-python"),
        ("pydub",            "pydub"),
        ("rich",             "rich"),
        ("dotenv",           "python-dotenv"),
    ]
    for module, label in deps:
        if not check_module(module, label):
            errors += 1

    # ── Package structure ─────────────────────────────────────────────────
    section("Heist Package  (src/heist)")
    if not check_heist_package():
        errors += 1

    # ── Audio files ───────────────────────────────────────────────────────
    section("Demo Audio Files")
    if not check_audio_files():
        warnings += 1   # not fatal — demo still runs without pre-generated audio

    # ── External services ─────────────────────────────────────────────────
    section("External Service Connectivity")
    if not await check_speechmatics(speechmatics_key):
        errors += 1
    if not await check_nebius(nebius_key):
        errors += 1

    # ── Summary ───────────────────────────────────────────────────────────
    print(f"\n{BOLD}{'=' * 58}{RESET}")

    if errors == 0 and warnings == 0:
        print(f"{GREEN}{BOLD}✓  All checks passed — ready to run the demo!{RESET}")
        print()
        print(f"  {MAGENTA}Run the demo:{RESET}")
        print(f"    {GREEN}make demo-heist{RESET}")
        print()
        print(f"  {BLUE}Generate audio first (if not already done):{RESET}")
        print(f"    {GREEN}make generate-audio{RESET}")

    elif errors == 0:
        print(f"{YELLOW}{BOLD}⚠  Ready with {warnings} warning(s) — see above.{RESET}")
        print()
        print(f"  {MAGENTA}Run the demo:{RESET}")
        print(f"    {GREEN}make demo-heist{RESET}")

    else:
        print(f"{RED}{BOLD}✗  {errors} error(s) found — fix them before running the demo.{RESET}")
        if warnings:
            print(f"{YELLOW}  Also {warnings} warning(s) noted above.{RESET}")
        print()
        print(f"  {BLUE}Common fixes:{RESET}")
        print(f"    {GREEN}make install{RESET}         install / reinstall dependencies")
        print(f"    {GREEN}cp .env.example .env{RESET} then fill in your API keys")

    print()
    return 0 if errors == 0 else 1


def main() -> None:
    sys.exit(asyncio.run(run_checks()))


if __name__ == "__main__":
    main()