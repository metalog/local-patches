#!/usr/bin/env python3
"""Reapply local Hermes patches that need to survive `hermes update`."""

import re
import subprocess
import sys
from pathlib import Path

repo = Path.home() / ".hermes" / "hermes-agent"
terminal_path = repo / "tools" / "terminal_tool.py"
gateway_path = repo / "gateway" / "run.py"

terminal_changed = False
gateway_changed = False

# ---------------------------------------------------------------------------
# Sudo fix #1 — insert _passwordless_sudo_available() function
# after _sudo_password_cache_lock
# ---------------------------------------------------------------------------
text = terminal_path.read_text()
orig = text

if "_passwordless_sudo_available" not in text:
    marker = (
        '_sudo_password_cache_lock = threading.Lock()\n'
        '\n'
        '# Optional UI callbacks for interactive prompts. When set, these are called\n'
        '# instead of the default /dev/tty or input() readers.'
    )
    replacement = """_sudo_password_cache_lock = threading.Lock()

# Cache whether passwordless sudo already works for the current user.
_sudo_nopass_available: bool | None = None


def _passwordless_sudo_available() -> bool:
    \"\"\"Return True when the current user can run sudo non-interactively.\"\"\"
    global _sudo_nopass_available
    if _sudo_nopass_available is not None:
        return _sudo_nopass_available
    try:
        result = subprocess.run(
            ["sudo", "-n", "true"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
        _sudo_nopass_available = (result.returncode == 0)
    except Exception:
        _sudo_nopass_available = False
    return _sudo_nopass_available


# Optional UI callbacks for interactive prompts. When set, these are called
# instead of the default /dev/tty or input() readers."""
    if marker not in text:
        print("HERMES PATCH ERROR: Could not find sudo cache lock marker", file=sys.stderr)
        sys.exit(2)
    text = text.replace(marker, replacement, 1)

if "_passwordless_sudo_available" not in text:
    print("HERMES PATCH ERROR: Inserting _passwordless_sudo_available failed", file=sys.stderr)
    sys.exit(2)

# ---------------------------------------------------------------------------
# Sudo fix #2 — early return in _transform_sudo_command for sudo -n / no-pass
# ---------------------------------------------------------------------------
old = (
    '    if command is None:\n'
    '        return None, None\n'
    '    transformed, has_real_sudo = _rewrite_real_sudo_invocations(command)'
)
new = (
    '    if command is None:\n'
    '        return None, None\n'
    '\n'
    '    # Respect explicit non-interactive sudo \u2014 don\'t rewrite to sudo -S.\n'
    "    if re.search(r'\\bsudo\\s+(?:--non-interactive\\b|-n\\b)', command):\n"
    '        return command, None\n'
    '\n'
    '    # Skip password handling when passwordless sudo is available.\n'
    '    if _passwordless_sudo_available():\n'
    '        return command, None\n'
    '\n'
    '    transformed, has_real_sudo = _rewrite_real_sudo_invocations(command)'
)
if old in text:
    text = text.replace(old, new, 1)
elif "if _passwordless_sudo_available():" not in text:
    print("HERMES PATCH ERROR: Could not find _transform_sudo_command insertion point", file=sys.stderr)
    sys.exit(2)

terminal_changed = text != orig
if terminal_changed:
    terminal_path.write_text(text)

# ---------------------------------------------------------------------------
# Gateway compression fix #1 — lower default threshold, fix comment
# ---------------------------------------------------------------------------
text = gateway_path.read_text()
orig = text

old = (
    '            # Read model + compression config from config.yaml.\n'
    '            # NOTE: hygiene threshold is intentionally HIGHER than the agent\'s\n'
    '            # own compressor (0.85 vs 0.50).  Hygiene is a safety net for\n'
    '            # sessions that grew too large between turns \u2014 it fires pre-agent\n'
    '            # to prevent API failures.  The agent\'s own compressor handles\n'
    '            # normal context management during its tool loop with accurate\n'
    '            # real token counts.  Having hygiene at 0.50 caused premature\n'
    '            # compression on every turn in long gateway sessions.\n'
    '            _hyg_model = "anthropic/claude-sonnet-4.6"\n'
    '            _hyg_threshold_pct = 0.85\n'
    '            _hyg_compression_enabled = True'
)
new = (
    '            # Read model + compression config from config.yaml.\n'
    '            # Hygiene should never fire later than the main agent compressor,\n'
    '            # so it follows compression.threshold from config instead of using\n'
    '            # a separate hardcoded percentage. The hard message limit remains\n'
    '            # as an earlier safety valve for runaway long-lived sessions.\n'
    '            _hyg_model = "anthropic/claude-sonnet-4.6"\n'
    '            _hyg_threshold_pct = 0.50\n'
    '            _hyg_compression_enabled = True'
)
if old in text:
    text = text.replace(old, new, 1)

# ---------------------------------------------------------------------------
# Gateway compression fix #2 — read compression.threshold from config
# ---------------------------------------------------------------------------
old = (
    '                    # Read compression settings \u2014 only use enabled flag.\n'
    '                    # The threshold is intentionally separate from the agent\'s\n'
    '                    # compression.threshold (hygiene runs higher).\n'
    '                    _comp_cfg = _hyg_data.get("compression", {})\n'
    '                    if isinstance(_comp_cfg, dict):\n'
    '                        _hyg_compression_enabled = str(\n'
    '                            _comp_cfg.get("enabled", True)\n'
    '                        ).lower() in ("true", "1", "yes")'
)
new = (
    '                    # Read compression settings. Hygiene follows the same\n'
    '                    # threshold as the main agent compressor so gateway\n'
    '                    # sessions never compress later than normal agent turns.\n'
    '                    _comp_cfg = _hyg_data.get("compression", {})\n'
    '                    if isinstance(_comp_cfg, dict):\n'
    '                        _hyg_compression_enabled = str(\n'
    '                            _comp_cfg.get("enabled", True)\n'
    '                        ).lower() in ("true", "1", "yes")\n'
    '                        try:\n'
    '                            _hyg_threshold_pct = float(\n'
    '                                _comp_cfg.get("threshold", _hyg_threshold_pct)\n'
    '                            )\n'
    '                        except (TypeError, ValueError):\n'
    '                            pass'
)
if old in text:
    text = text.replace(old, new, 1)

gateway_changed = text != orig
if gateway_changed:
    gateway_path.write_text(text)

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
cli_gateway_changed = text != orig
if cli_gateway_changed:
    cli_gateway_path.write_text(text)

# ---------------------------------------------------------------------------
# Sudo fix #4 — scope_cmd for system in hermes_cli/main.py
# Makes `hermes update` restart gateway via sudo -n instead of polkit
# ---------------------------------------------------------------------------
cli_main_path = repo / "hermes_cli" / "main.py"
text = cli_main_path.read_text()
orig = text

old = (
    "                    (\"system\", [\"systemctl\"]),\n"
)
new = (
    '                    ("system", ["sudo", "-n", "systemctl"]),\n'
)
if old in text:
    text = text.replace(old, new, 1)

cli_main_changed = text != orig
if cli_main_changed:
    cli_main_path.write_text(text)





# ---------------------------------------------------------------------------
# Telegram audio documents — classify .aac/.m4a/... document uploads as audio
# so the agent receives an audio attachment note instead of an empty document turn.
# ---------------------------------------------------------------------------
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
    '        return MessageType.DOCUMENT\n'
)
if 'SUPPORTED_DOCUMENT_TYPES.get(ext, "").startswith("audio/")' not in text:
    if old not in text:
        print("HERMES PATCH ERROR: Could not find Telegram media classifier marker", file=sys.stderr)
        sys.exit(2)
    text = text.replace(old, new, 1)

telegram_audio_documents_changed = text != orig
if telegram_audio_documents_changed:
    telegram_path.write_text(text)
telegram_audio_documents_test_changed = False

telegram_post_send_typing_changed = False
text = telegram_path.read_text()
orig = text

rich_post_send_typing = (
    '                    if rich_result.success:\n'
    '                        # Re-trigger typing like the legacy success path does.\n'
    '                        try:\n'
    '                            await self.send_typing(chat_id, metadata=metadata)\n'
    '                        except Exception:\n'
    '                            pass  # Typing failures are non-fatal\n'
    '                    return rich_result\n'
)
if rich_post_send_typing in text:
    text = text.replace(rich_post_send_typing, '                    return rich_result\n', 1)

legacy_post_send_typing = (
    '            # Re-trigger typing indicator after sending a message.\n'
    '            # Telegram clears the typing state when a new message is delivered,\n'
    '            # so without this the "...typing" bubble disappears mid-response\n'
    '            # (especially noticeable when the agent sends intermediate progress\n'
    '            # messages like "Checking:" before running tools).\n'
    '            try:\n'
    '                await self.send_typing(chat_id, metadata=metadata)\n'
    '            except Exception:\n'
    '                pass  # Typing failures are non-fatal\n'
    '\n'
    '            return SendResult(\n'
)
if legacy_post_send_typing in text:
    text = text.replace(legacy_post_send_typing, '            return SendResult(\n', 1)

telegram_post_send_typing_changed = text != orig
if telegram_post_send_typing_changed:
    telegram_path.write_text(text)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
patched = []
if terminal_changed:
    patched.append("tools/terminal_tool.py (sudo fix)")
if gateway_changed:
    patched.append("gateway/run.py (compression fix)")
if cli_gateway_changed:
    patched.append("hermes_cli/gateway.py (systemctl sudo)")
if cli_main_changed:
    patched.append("hermes_cli/main.py (update systemctl sudo)")
if telegram_audio_documents_changed:
    patched.append("gateway/platforms/telegram.py (audio documents as audio)")
if telegram_audio_documents_test_changed:
    patched.append("tests/gateway/test_telegram_audio_vs_voice.py (audio document regression)")
if telegram_post_send_typing_changed:
    patched.append("gateway/platforms/telegram.py (no post-send typing tail)")

if not patched:
    print("All local Hermes patches already applied.")
else:
    for p in patched:
        print(f"Reapplied local Hermes patch: {p}")
