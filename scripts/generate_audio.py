#!/usr/bin/env python3
# === QV-LLM:BEGIN ===
# path: scripts/generate_audio.py
# role: module
# neighbors: annotate_headers.py, flatten.py
# exports: main
# git_branch: main
# git_commit: 1734031
# === QV-LLM:END ===
"""
scripts/generate_audio.py — Pre-generate user voice audio files for the demo.

Uses Speechmatics TTS with the "megan" voice (US female — Alex Chen)
to pre-generate the five user utterances used in the demo.
This keeps demo playback deterministic and avoids live microphone
risk during presentations.

Usage:
    make generate-audio
    # or directly:
    uv run python scripts/generate_audio.py
"""

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

OUTPUT_DIR = Path("tests/audio")

UTTERANCES: dict[str, str] = {
    "user_input_1.wav": "I want to transfer money.",
    "user_input_2.wav": "Checking.",
    "user_input_3.wav": "Savings.",
    "user_input_4.wav": "Five hundred dollars.",
    "user_input_5.wav": "Yes, please.",
}


async def _main() -> None:
    from heist.services.speechmatics_service import SpeechmaticsService, SpeechmaticsTTSError

    try:
        tts = SpeechmaticsService()
    except ValueError as exc:
        print(f"✗ {exc}")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Generating user audio files via Speechmatics TTS")
    print("  Voice  : megan  (US female — Alex Chen)")
    print(f"  Output : {OUTPUT_DIR.resolve()}")
    print("=" * 60)

    for filename, text in UTTERANCES.items():
        print(f"  Generating {filename!r}  →  {text!r}")
        try:
            audio_bytes = await tts.synthesize(text, agent_role="caller")
            output_path = OUTPUT_DIR / filename
            output_path.write_bytes(audio_bytes)
            print(f"    ✓ Saved ({len(audio_bytes):,} bytes) → {output_path}")
        except SpeechmaticsTTSError as exc:
            print(f"    ✗ TTS error: {exc}")
            sys.exit(1)

    print()
    print("=" * 60)
    print(f"✓ {len(UTTERANCES)} audio files ready in {OUTPUT_DIR}/")
    print("=" * 60)
    print()
    print("Next steps:")
    print("  make demo-heist")


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()