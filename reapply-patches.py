#!/usr/bin/env python3
"""Reapply local Hermes patches that need to survive `hermes update`."""

import sys
from pathlib import Path

repo = Path.home() / ".hermes" / "hermes-agent"

# ---------------------------------------------------------------------------
# Telegram audio documents — classify audio document uploads as audio so the
# normal inbound audio path can preserve the attachment context for the agent.
# ---------------------------------------------------------------------------
telegram_path = repo / "plugins" / "platforms" / "telegram" / "adapter.py"
if not telegram_path.exists():
    telegram_path = repo / "gateway" / "platforms" / "telegram.py"
text = telegram_path.read_text()
orig = text

old = (
    '        if msg.audio:\n'
    '            return MessageType.AUDIO\n'
    '        if msg.voice:\n'
    '            return MessageType.VOICE\n'
    '        return MessageType.DOCUMENT\n'
)
new = (
    '        if msg.audio:\n'
    '            return MessageType.AUDIO\n'
    '        if msg.voice:\n'
    '            return MessageType.VOICE\n'
    '        if msg.document:\n'
    '            doc = msg.document\n'
    '            doc_mime = (getattr(doc, "mime_type", "") or "").lower()\n'
    '            filename = getattr(doc, "file_name", "") or ""\n'
    '            _, ext = os.path.splitext(filename)\n'
    '            ext = ext.lower()\n'
    '            if doc_mime.startswith("audio/") or SUPPORTED_DOCUMENT_TYPES.get(ext, "").startswith("audio/"):\n'
    '                return MessageType.AUDIO\n'
    '            _AUDIO_DOC_EXTS = {".aac", ".m4a", ".mp3", ".wav", ".flac", ".ogg", ".opus", ".wma"}\n'
    '            if ext in _AUDIO_DOC_EXTS:\n'
    '                return MessageType.AUDIO\n'
    '        return MessageType.DOCUMENT\n'
)
if '_AUDIO_DOC_EXTS' not in text:
    if old not in text:
        print("HERMES PATCH ERROR: Could not find Telegram media classifier marker", file=sys.stderr)
        sys.exit(2)
    text = text.replace(old, new, 1)

telegram_audio_documents_changed = text != orig
if telegram_audio_documents_changed:
    telegram_path.write_text(text)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
patched = []
if telegram_audio_documents_changed:
    patched.append("plugins/platforms/telegram/adapter.py (audio documents as audio)")

if not patched:
    print("All local Hermes patches already applied.")
else:
    for p in patched:
        print(f"Reapplied local Hermes patch: {p}")
