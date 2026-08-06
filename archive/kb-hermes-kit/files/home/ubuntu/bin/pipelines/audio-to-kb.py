#!/usr/bin/env python3
"""Audio file -> STT -> kb/fleeting commit via voice-to-kb.py."""

import argparse
import os
import subprocess
import sys

HERMES_AGENT = "/home/ubuntu/.hermes/hermes-agent"
VOICE_TO_KB = "/home/ubuntu/bin/pipelines/voice-to-kb.py"

sys.path.insert(0, HERMES_AGENT)

from tools.transcription_tools import transcribe_audio  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Transcribe an audio file and save it to kb/fleeting.")
    parser.add_argument("audio_path", help="Path to cached audio file")
    parser.add_argument("--dry-run", action="store_true", help="Transcribe only; do not write kb")
    args = parser.parse_args()

    audio_path = os.path.abspath(os.path.expanduser(args.audio_path))
    if not os.path.exists(audio_path):
        print(f"ERROR: audio file not found: {audio_path}", file=sys.stderr)
        return 1

    result = transcribe_audio(audio_path)
    if not result.get("success"):
        print(f"ERROR: STT failed: {result.get('error', 'unknown')}", file=sys.stderr)
        return 1

    transcript = (result.get("transcript") or "").strip()
    if not transcript:
        print("ERROR: STT returned empty transcript", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"DRY_RUN: transcript_chars={len(transcript)}")
        return 0

    proc = subprocess.run(
        [sys.executable, VOICE_TO_KB],
        input=transcript,
        text=True,
        capture_output=True,
    )
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.returncode != 0:
        if proc.stderr.strip():
            print(proc.stderr.strip(), file=sys.stderr)
        return proc.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
