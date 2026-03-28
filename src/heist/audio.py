"""
heist.audio
~~~~~~~~~~~
Async audio playback helpers.

play_audio()                 — fire-and-forget WAV bytes playback.
play_audio_with_typewriter() — plays audio while revealing the transcript
                               word-by-word in sync with the voice duration,
                               creating a live-captioning effect.
"""

import asyncio
import io
import logging

from pydub import AudioSegment
from pydub.playback import play
from rich.layout import Layout

from heist.ui.bubbles import conversation_bubble, render_conversation
from heist.ui.state import DemoState

logger = logging.getLogger(__name__)


async def play_audio(audio_bytes: bytes) -> None:
    """Play WAV bytes asynchronously without blocking the event loop."""
    try:
        segment = AudioSegment.from_file(io.BytesIO(audio_bytes), format="wav")
        await asyncio.get_event_loop().run_in_executor(None, play, segment)
    except Exception as exc:
        logger.warning("Audio playback error: %s", exc)


async def play_audio_with_typewriter(
    audio_bytes: bytes,
    text: str,
    agent_key: str,
    state: DemoState,
    layout: Layout,
) -> None:
    """
    Play audio while revealing the transcript word-by-word.

    The words are revealed at a rate proportional to the audio duration so
    the text caption stays roughly in sync with the voice.  A blinking cursor
    (▋) is appended to the in-progress bubble to signal ongoing speech.

    Falls back to instant display + plain playback if the audio cannot be
    decoded (e.g. during tests with stub bytes).
    """
    words = text.split()
    if not words:
        await play_audio(audio_bytes)
        return

    try:
        segment    = AudioSegment.from_file(io.BytesIO(audio_bytes), format="wav")
        duration_s = len(segment) / 1000.0
    except Exception:
        # Fallback: show all text immediately, then play
        state.conversation.append(conversation_bubble(text, agent_key))
        layout["conversation"].update(render_conversation(state))
        await play_audio(audio_bytes)
        return

    # Add a placeholder bubble with just the cursor
    state.conversation.append(conversation_bubble("▋", agent_key))
    layout["conversation"].update(render_conversation(state))

    delay_per_word = duration_s / max(len(words), 1)
    audio_task     = asyncio.get_event_loop().run_in_executor(None, play, segment)

    revealed: list[str] = []
    for word in words:
        revealed.append(word)
        state.conversation[-1] = conversation_bubble(
            " ".join(revealed) + " ▋", agent_key
        )
        layout["conversation"].update(render_conversation(state))
        await asyncio.sleep(delay_per_word)

    # Finalise: remove cursor
    state.conversation[-1] = conversation_bubble(text, agent_key)
    layout["conversation"].update(render_conversation(state))

    try:
        await audio_task
    except Exception as exc:
        logger.warning("Audio task error: %s", exc)