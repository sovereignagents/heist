"""
heist.agents.security_classifier
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Security Classifier — Real-time turn annotation using Gemma 3 27B fast.
"""

import logging
import os
import re
from enum import Enum
from typing import Optional

import aiohttp

from heist.scenario.arc import SECURITY_CLASSIFIER_PROMPT

logger = logging.getLogger(__name__)

NEBIUS_API_URL   = "https://api.tokenfactory.nebius.com/v1/chat/completions"
CLASSIFIER_MODEL = "google/gemma-3-27b-it-fast"


class SecurityLabel(Enum):
    SAFE         = "SAFE"
    PROBING      = "PROBING"
    SOCIAL       = "SOCIAL"
    OFF_TOPIC    = "OFF_TOPIC"
    HALLUCINATED = "HALLUCINATED"
    LEAKED       = "LEAKED"
    COMPROMISED  = "COMPROMISED"
    BLOCKED      = "BLOCKED"
    REFUSED      = "REFUSED"
    UNKNOWN      = "UNKNOWN"


LABEL_DISPLAY: dict[SecurityLabel, tuple[str, str, str]] = {
    SecurityLabel.SAFE:         ("✅",  "green",      "SAFE"),
    SecurityLabel.PROBING:      ("🔍",  "yellow",     "PROBING"),
    SecurityLabel.SOCIAL:       ("🤝",  "yellow",     "SOCIAL ENGINEERING"),
    SecurityLabel.OFF_TOPIC:    ("🎂",  "magenta",    "OFF-TOPIC"),
    SecurityLabel.HALLUCINATED: ("🧠",  "bold red",   "HALLUCINATED"),
    SecurityLabel.LEAKED:       ("⚠️ ", "red",        "DATA LEAKED"),
    SecurityLabel.COMPROMISED:  ("🚨",  "bold red",   "COMPROMISED"),
    SecurityLabel.BLOCKED:      ("🛡️ ", "cyan",       "BLOCKED BY GRAPH"),
    SecurityLabel.REFUSED:      ("🚫",  "dim red",    "LLM REFUSED (luck)"),
    SecurityLabel.UNKNOWN:      ("❓",  "white",      "UNKNOWN"),
}


class SecurityClassifier:

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("NEBIUS_API_KEY")
        if not self.api_key:
            raise ValueError("NEBIUS_API_KEY not set.")

    async def classify(
        self,
        caller_message: str,
        agent_response: str,
        active_agent: str,
    ) -> SecurityLabel:
        combined = (
            f"CALLER said: {caller_message}\n"
            f"{active_agent.upper()} AGENT responded: {agent_response}"
        )
        messages = [
            {"role": "user", "content": SECURITY_CLASSIFIER_PROMPT + combined}
        ]
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type":  "application/json",
        }
        payload = {
            "model":       CLASSIFIER_MODEL,
            "messages":    messages,
            "temperature": 0.1,
            "max_tokens":  20,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    NEBIUS_API_URL,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        return SecurityLabel.UNKNOWN
                    data = await resp.json()
                    raw  = data["choices"][0]["message"]["content"].strip()
                    raw  = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
                    first_word = (
                        raw.upper().replace(".", "").replace("'", "").split()[0]
                        if raw.split()
                        else ""
                    )
                    try:
                        return SecurityLabel(first_word)
                    except ValueError:
                        logger.debug("Unknown classifier label: %r", first_word)
                        return SecurityLabel.UNKNOWN
        except Exception as exc:
            logger.debug("Classifier error: %s", exc)
            return SecurityLabel.UNKNOWN