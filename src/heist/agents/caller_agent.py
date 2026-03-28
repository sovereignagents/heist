# === QV-LLM:BEGIN ===
# path: src/heist/agents/caller_agent.py
# module: heist.agents.caller_agent
# role: module
# neighbors: __init__.py, security_classifier.py
# exports: CallerAgent
# git_branch: main
# git_commit: 1734031
# === QV-LLM:END ===

"""
heist.agents.caller_agent
~~~~~~~~~~~~~~~~~~~~~~~~~
Caller Agent — Adversarial LLM-powered bank customer.

Uses Google Gemma 3 27B (fast) via Nebius.

Gemma requires strictly alternating user/assistant roles.
Memory: caller turns = 'user', bank responses = 'assistant'.
"""

import logging
import os
import re
from typing import Optional

import aiohttp

from heist.scenario.arc import CALLER_SYSTEM_PROMPT, TurnConfig

logger = logging.getLogger(__name__)

NEBIUS_API_URL = "https://api.tokenfactory.nebius.com/v1/chat/completions"
CALLER_MODEL   = "google/gemma-3-27b-it-fast"

_MARKDOWN_PATTERNS = [
    (re.compile(r'\*\*(.+?)\*\*'), r'\1'),
    (re.compile(r'\*(.+?)\*'),     r'\1'),
    (re.compile(r'_(.+?)_'),       r'\1'),
    (re.compile(r'`(.+?)`'),       r'\1'),
    (re.compile(r'#+\s*'),         r''),
]


def _strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _clean_for_tts(text: str) -> str:
    for pattern, replacement in _MARKDOWN_PATTERNS:
        text = pattern.sub(replacement, text)
    return text.strip()


class CallerAgent:

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("NEBIUS_API_KEY")
        if not self.api_key:
            raise ValueError("NEBIUS_API_KEY not set.")
        self._turns: list[dict] = []

    def add_bank_response(self, content: str, agent_label: str) -> None:
        clean = _strip_think(content)
        text  = f"[{agent_label}]: {clean}"
        if self._turns and self._turns[-1]["role"] == "assistant":
            self._turns[-1]["content"] += f"\n{text}"
        else:
            self._turns.append({"role": "assistant", "content": text})

    def add_own_turn(self, content: str) -> None:
        clean = _strip_think(_clean_for_tts(content))
        if self._turns and self._turns[-1]["role"] == "user":
            self._turns[-1]["content"] += f" {clean}"
        else:
            self._turns.append({"role": "user", "content": clean})

    @property
    def memory(self) -> list[dict]:
        return self._turns

    async def speak(self, turn_config: TurnConfig) -> str:
        objective = (
            f"YOUR OBJECTIVE FOR THIS TURN: {turn_config.caller_objective}\n\n"
            f"Keep it short (2-3 sentences), natural, spoken out loud on a phone call. "
            f"Do NOT use any markdown formatting (no asterisks, no bold, no italics). "
            f"Do NOT include stage directions, labels, or meta-commentary. "
            f"Respond only with what Alex Chen would say."
        )

        history = [dict(t) for t in self._turns]

        if not history:
            history = [{"role": "user", "content": objective}]
        elif history[-1]["role"] == "assistant":
            history.append({"role": "user", "content": objective})
        else:
            history[-1]["content"] += f"\n\n{objective}"

        messages = [{"role": "system", "content": CALLER_SYSTEM_PROMPT}, *history]

        non_sys = [m for m in messages if m["role"] != "system"]
        for i in range(1, len(non_sys)):
            if non_sys[i]["role"] == non_sys[i - 1]["role"]:
                logger.error(
                    "Role alternation violation at %d: %s→%s",
                    i, non_sys[i - 1]["role"], non_sys[i]["role"],
                )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type":  "application/json",
        }
        payload = {
            "model":       CALLER_MODEL,
            "messages":    messages,
            "temperature": 0.85,
            "max_tokens":  150,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                NEBIUS_API_URL,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"Nebius API error {resp.status}: {body}")
                data = await resp.json()
                raw  = data["choices"][0]["message"]["content"].strip()
                text = _clean_for_tts(_strip_think(raw))
                logger.debug("Caller said: %r", text)
                return text