"""
heist.text
~~~~~~~~~~
Pure string utilities — no I/O, no Rich, no LLM dependencies.

Used by demo.py to sanitise LLM responses before they are passed to
TTS or displayed in the UI.
"""

import re

# ---------------------------------------------------------------------------
# Think-block stripping  (Gemma / DeepSeek chain-of-thought blocks)
# ---------------------------------------------------------------------------

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def strip_think(text: str) -> str:
    """Remove <think>…</think> chain-of-thought blocks from LLM output."""
    return _THINK_RE.sub("", text).strip()


# ---------------------------------------------------------------------------
# Markdown stripping  (LLMs sometimes emit markdown even on voice channels)
# ---------------------------------------------------------------------------

_MARKDOWN_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\*\*(.+?)\*\*", re.DOTALL), r"\1"),   # **bold**
    (re.compile(r"\*(.+?)\*",     re.DOTALL), r"\1"),   # *italic*
    (re.compile(r"_(.+?)_",       re.DOTALL), r"\1"),   # _italic_
    (re.compile(r"`(.+?)`",       re.DOTALL), r"\1"),   # `code`
    (re.compile(r"#+\s*"),                    r""),      # ## headers
]

# ---------------------------------------------------------------------------
# Boilerplate stripping  (phrases that are meaningless in spoken audio)
# ---------------------------------------------------------------------------

_BOILERPLATE_PATTERNS: list[str] = [
    r"Would you like to resume[^?]*\??",
    r"Would you like to continue with[^?]*\??",
    r"Would you like to continue\??",
    r"Is there anything else I can help you with\??",
    r"Is there something else I can help you with today\??",
    r"I'?m sorry,?\s+I'?m not trained to help with that\.?\s*",
    r"I'?m not trained to help with that\.?\s*",
    r"I cannot help with that\.?\s*",
    r"Ok,?\s+I am updating \w+ to \w+[^.]*\.?\s*",
    r"I am updating \w+ to \w+[^.]*respectively\.?\s*",
    r"I am updating[^.]*respectively\.?\s*",
]
_BOILERPLATE_RE = re.compile(
    "|".join(_BOILERPLATE_PATTERNS), flags=re.IGNORECASE
)

# ---------------------------------------------------------------------------
# TTS character ceiling  (Speechmatics has a per-request limit)
# ---------------------------------------------------------------------------

TTS_MAX_CHARS = 900


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def clean_for_speech(text: str, max_chars: int = TTS_MAX_CHARS) -> str:
    """
    Prepare an LLM response for TTS and UI display:

    1. Strip <think> blocks
    2. Strip markdown formatting
    3. Strip agent boilerplate phrases
    4. Deduplicate repeated sentences
    5. Ensure terminal punctuation
    6. Hard-truncate to TTS character limit at a sentence boundary
    """
    text = strip_think(text)

    for pattern, replacement in _MARKDOWN_PATTERNS:
        text = pattern.sub(replacement, text)

    text = _BOILERPLATE_RE.sub("", text)

    # Deduplicate sentences
    sentences = [s.strip() for s in text.split(". ") if s.strip()]
    seen: set[str] = set()
    deduped: list[str] = []
    for sentence in sentences:
        key = sentence.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(sentence)
    text = ". ".join(deduped).strip()

    # Ensure terminal punctuation
    if text and text[-1] not in ".!?":
        text += "."

    # Truncate at sentence boundary
    if len(text) > max_chars:
        truncated = text[:max_chars]
        for sep in [". ", "! ", "? "]:
            idx = truncated.rfind(sep)
            if idx > max_chars // 2:
                text = truncated[: idx + 1]
                break
        else:
            text = truncated.rsplit(" ", 1)[0] + "."

    return text.strip()