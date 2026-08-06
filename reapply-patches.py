#!/usr/bin/env python3
"""Reapply local Hermes patches that need to survive `hermes update`."""

import re
import subprocess
import sys
from pathlib import Path

repo = Path.home() / ".hermes" / "hermes-agent"
gateway_path = repo / "gateway" / "run.py"

# ---------------------------------------------------------------------------
# Sudo fix #3 — _systemctl_cmd in hermes_cli/gateway.py
# Makes `hermes gateway restart/status/stop` use sudo -n instead of polkit
# ---------------------------------------------------------------------------
cli_gateway_path = repo / "hermes_cli" / "gateway.py"
text = cli_gateway_path.read_text()
orig = text

old = (
    'def _systemctl_cmd(system: bool = False) -> list[str]:\n'
    '    if not system:\n'
    '        _ensure_user_systemd_env()\n'
    '    return ["systemctl"] if system else ["systemctl", "--user"]\n'
    '\n'
    '\n'
    'def _journalctl_cmd(system: bool = False) -> list[str]:'
)
new = (
    'def _systemctl_cmd(system: bool = False) -> list[str]:\n'
    '    if not system:\n'
    '        _ensure_user_systemd_env()\n'
    '        return ["systemctl", "--user"]\n'
    '    # System-scope runs via sudo -n (passwordless) to avoid polkit auth prompt\n'
    '    return ["sudo", "-n", "systemctl"]\n'
    '\n'
    '\n'
    'def _journalctl_cmd(system: bool = False) -> list[str]:'
)
# Idempotent — nothing to do if already present
if old in text:
    text = text.replace(old, new, 1)
cli_gateway_changed = text != orig
if cli_gateway_changed:
    cli_gateway_path.write_text(text)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Telegram audio documents — classify .aac/.m4a/... document uploads as audio
# so the agent receives an audio attachment note with a marker.
# WITHOUT this: .aac → DOCUMENT → run.py skips both AUDIO and VOICE paths
# (line 9346: MessageType.AUDIO check fails; line 9348: DOCUMENT excluded) →
# no marker → msg='' → agent sees empty turn → no pipeline.
# WITH this: .aac → AUDIO → audio_file_paths → marker added → skill triggers.
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

# Post-send typing — upstream has the notify-gated fix built in (see #48678).
telegram_post_send_typing_changed = False
telegram_post_send_typing_changed = False

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
patched = []
if cli_gateway_changed:
    patched.append("hermes_cli/gateway.py (systemctl sudo)")
if telegram_audio_documents_changed:
    patched.append("plugins/platforms/telegram/adapter.py (audio documents as audio)")

if not patched:
    print("All local Hermes patches already applied.")
else:
    for p in patched:
        print(f"Reapplied local Hermes patch: {p}")
