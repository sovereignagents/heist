# === QV-LLM:BEGIN ===
# path: src/heist/services/speechmatics_service.py
# module: heist.services.speechmatics_service
# role: module
# neighbors: __init__.py, demo_logger.py
# exports: SpeechmaticsTTSError, SpeechmaticsASRError, SpeechmaticsService
# git_branch: main
# git_commit: 1734031
# === QV-LLM:END ===

"""
heist.services.speechmatics_service
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unified Speechmatics TTS + ASR service.

Voice mapping:
    caller  → megan   US female  — Alex Chen, the bank customer
    bank    → theo    UK male    — the automated banking line
    manager → sarah   UK female  — Patricia Walsh, senior manager

TTS pipeline:
    POST https://preview.tts.speechmatics.com/generate/{voice}?output_format=wav_16000
    Returns streaming WAV audio (16 kHz, 16-bit signed, mono).
    Compatible with pydub — no changes needed in play_audio().

ASR pipeline (optional, controlled by ENABLE_SPEECHMATICS_ASR=true):
    Strips the WAV header from TTS output.
    Feeds raw PCM to Speechmatics RT ASR via WebSocket (BytesIO stream).
    Returns the final transcript string.
    This closes the realistic speech loop:
        LLM text → TTS → play → ASR → Bank Graph
"""

import asyncio
import io
import logging
import os

import aiohttp
import speechmatics
import speechmatics.client
import speechmatics.models

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TTS_BASE_URL = "https://preview.tts.speechmatics.com/generate/{voice}"
ASR_URL      = "wss://eu.rt.speechmatics.com/v2"

VOICE_MAP = {
    "caller":  "megan",   # US female  — Alex Chen, the bank customer
    "bank":    "theo",    # UK male    — automated banking line (formal)
    "manager": "sarah",   # UK female  — Patricia Walsh (warm, senior)
}

# Standard WAV header size for simple PCM WAV files (RIFF + fmt + data chunks)
WAV_HEADER_BYTES = 44

# TTS output sample rate — must match ASR config
SAMPLE_RATE = 16_000


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class SpeechmaticsTTSError(Exception):
    """Raised when the Speechmatics TTS request fails."""


class SpeechmaticsASRError(Exception):
    """Raised when the Speechmatics ASR request fails."""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class SpeechmaticsService:
    """
    Unified TTS + ASR via Speechmatics.

    Usage:
        svc = SpeechmaticsService()

        # TTS only (always active)
        audio_bytes = await svc.synthesize("Hello world", agent_role="caller")

        # TTS + ASR (active when ENABLE_SPEECHMATICS_ASR=true)
        audio_bytes, transcript = await svc.synthesize_and_transcribe(
            "Hello world", agent_role="caller"
        )
        # transcript is what you send to the Bank Graph

    Required env vars:
        SPEECHMATICS_API_KEY    — your Speechmatics API key
        ENABLE_SPEECHMATICS_ASR — set to "true" to enable the TTS→ASR round-trip
                                  (optional, default false)
    """

    def __init__(self) -> None:
        self.api_key = os.environ.get("SPEECHMATICS_API_KEY", "").strip()
        if not self.api_key:
            raise ValueError(
                "SPEECHMATICS_API_KEY is not set. "
                "Add it to your .env file or environment."
            )
        self.asr_enabled = (
            os.environ.get("ENABLE_SPEECHMATICS_ASR", "false").lower() == "true"
        )
        logger.info(
            "SpeechmaticsService ready — ASR loop %s",
            "ENABLED" if self.asr_enabled
            else "disabled (set ENABLE_SPEECHMATICS_ASR=true to enable)",
        )

    # ------------------------------------------------------------------ TTS

    async def synthesize(self, text: str, agent_role: str) -> bytes:
        """
        Convert text to WAV audio bytes using Speechmatics TTS.

        Args:
            text:       The text to synthesise.
            agent_role: One of "caller", "bank", "manager".
                        Determines the voice used.

        Returns:
            WAV audio bytes (16 kHz, 16-bit, mono, with WAV header).
            Directly compatible with pydub.AudioSegment.from_file(BytesIO(...)).

        Raises:
            SpeechmaticsTTSError on HTTP or connection failure.
        """
        voice = VOICE_MAP.get(agent_role, "megan")
        url   = TTS_BASE_URL.format(voice=voice)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type":  "application/json",
        }
        payload = {"text": text}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    headers=headers,
                    params={"output_format": "wav_16000"},
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        raise SpeechmaticsTTSError(
                            f"Speechmatics TTS HTTP {resp.status} for voice={voice}: "
                            f"{body[:300]}"
                        )
                    chunks: list[bytes] = []
                    async for chunk in resp.content.iter_chunked(4096):
                        chunks.append(chunk)
                    audio_bytes = b"".join(chunks)

        except aiohttp.ClientError as exc:
            raise SpeechmaticsTTSError(f"TTS network error: {exc}") from exc

        if len(audio_bytes) < WAV_HEADER_BYTES:
            raise SpeechmaticsTTSError(
                f"TTS response too short ({len(audio_bytes)} bytes) — "
                "expected at least a WAV header"
            )

        logger.debug(
            "TTS OK  voice=%-6s  role=%-8s  bytes=%d  text=%r",
            voice, agent_role, len(audio_bytes), text[:60],
        )
        return audio_bytes

    # ------------------------------------------------------------------ ASR

    async def transcribe(self, wav_bytes: bytes) -> str:
        """
        Transcribe WAV audio bytes to text using Speechmatics RT ASR.

        Strips the WAV header, feeds raw PCM (pcm_s16le, 16 kHz) to the
        Speechmatics WebSocket ASR, and returns the concatenated final
        transcript.

        This is intentionally run AFTER playback, not concurrently, to keep
        the implementation simple and avoid buffering complexity.

        Returns:
            Transcript string, or empty string if ASR fails (non-fatal).
        """
        pcm_data = wav_bytes[WAV_HEADER_BYTES:]
        if not pcm_data:
            logger.warning("transcribe() called with empty PCM after header strip")
            return ""

        transcript_parts: list[str] = []

        ws = speechmatics.client.WebsocketClient(
            speechmatics.models.ConnectionSettings(
                url=ASR_URL,
                auth_token=self.api_key,
            )
        )

        def on_transcript(msg: dict) -> None:
            text = msg.get("metadata", {}).get("transcript", "").strip()
            if text:
                transcript_parts.append(text)

        ws.add_event_handler(
            event_name=speechmatics.models.ServerMessageType.AddTranscript,
            event_handler=on_transcript,
        )

        audio_settings              = speechmatics.models.AudioSettings()
        audio_settings.encoding     = "pcm_s16le"
        audio_settings.sample_rate  = SAMPLE_RATE
        audio_settings.chunk_size   = 1024

        conf = speechmatics.models.TranscriptionConfig(
            language="en",
            operating_point="enhanced",
            max_delay=1.0,
            enable_partials=False,
        )

        audio_stream = io.BytesIO(pcm_data)

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: ws.run_synchronously(audio_stream, conf, audio_settings),
            )
        except Exception as exc:
            logger.warning(
                "Speechmatics ASR failed (using LLM text fallback): %s", exc
            )
            return ""

        transcript = " ".join(transcript_parts).strip()
        logger.debug("ASR transcript: %r", transcript)
        return transcript

    # ------------------------------------------------------------------ combined

    async def synthesize_and_transcribe(
        self,
        text: str,
        agent_role: str,
    ) -> tuple[bytes, str]:
        """
        TTS the text, then (if ASR is enabled) transcribe the audio.

        Returns:
            (wav_bytes, transcript)

            transcript is:
              - the ASR transcript  if ENABLE_SPEECHMATICS_ASR=true and ASR succeeded
              - the original text   otherwise (ASR disabled or failed)

        Usage in demo.py:
            1. Pass wav_bytes to play_audio / play_audio_with_typewriter
            2. Pass transcript to the Bank Graph (instead of the raw LLM text)
        """
        wav_bytes = await self.synthesize(text, agent_role)

        if not self.asr_enabled:
            return wav_bytes, text

        transcript = await self.transcribe(wav_bytes)
        if not transcript:
            logger.warning(
                "ASR returned empty transcript for role=%s — falling back to LLM text",
                agent_role,
            )
            return wav_bytes, text

        return wav_bytes, transcript