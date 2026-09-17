#!/usr/bin/env python3
"""Reapply local Hermes patches that need to survive `hermes update`."""

import os
import sys
from pathlib import Path

repo = Path(os.environ.get("HERMES_REPO", Path.home() / ".hermes" / "hermes-agent")).expanduser()

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
# MCP stale output schema recovery — a server deployment can change a tool's
# outputSchema without the replaced process being able to notify an existing
# long-lived client. Refresh tools/list after the precise SDK validation error
# and retry once, but only for tools declared read-only or idempotent.
# ---------------------------------------------------------------------------
mcp_tool_path = repo / "tools" / "mcp_tool.py"
if not mcp_tool_path.exists():
    print(f"HERMES PATCH ERROR: MCP tool module not found: {mcp_tool_path}", file=sys.stderr)
    sys.exit(2)
mcp_text = mcp_tool_path.read_text()
mcp_orig = mcp_text

mcp_sentinel = (
    "refreshing tools/list; a read-only or idempotent call will be retried once"
)
mcp_old = '''        async def _call():
            _mark_server_call_started(server)
            async with server._rpc_lock:
                # Snapshot the agent's context so an elicitation callback
                # triggered during this call (fired on the MCP recv loop
                # task, which doesn't inherit our contextvars) can replay
                # it and detect the gateway platform / session for routing.
                server._pending_call_context = contextvars.copy_context()
                try:
                    result = await server.session.call_tool(tool_name, arguments=args)
                finally:
                    server._pending_call_context = None
'''
mcp_new = '''        async def _invoke_tool_call():
            async with server._rpc_lock:
                # Snapshot the agent's context so an elicitation callback
                # triggered during this call (fired on the MCP recv loop
                # task, which doesn't inherit our contextvars) can replay
                # it and detect the gateway platform / session for routing.
                server._pending_call_context = contextvars.copy_context()
                try:
                    return await server.session.call_tool(tool_name, arguments=args)
                finally:
                    server._pending_call_context = None

        async def _call():
            _mark_server_call_started(server)
            try:
                result = await _invoke_tool_call()
            except RuntimeError as exc:
                message = str(exc)
                stale_output_schema = (
                    message.startswith("Invalid structured content returned by tool ")
                    or " has an output schema but did not return structured content" in message
                )
                if not stale_output_schema:
                    raise
                logger.warning(
                    "MCP tool %s/%s result did not match the cached output schema; "
                    "refreshing tools/list; a read-only or idempotent call will be retried once",
                    server_name,
                    tool_name,
                )
                # A server deployment can change outputSchema without the old
                # process being able to deliver tools/list_changed to this
                # long-lived client. Refresh both the SDK validation cache and
                # Hermes' registered schemas, then repeat the read once. A
                # genuinely invalid server response fails the second call and
                # follows the normal error/circuit-breaker path below.
                await server._refresh_tools()
                refreshed_tool = next(
                    (tool for tool in server._tools if tool.name == tool_name),
                    None,
                )
                annotations = getattr(refreshed_tool, "annotations", None)
                retry_safe = bool(
                    mcp_field(annotations, "read_only_hint", "readOnlyHint", False)
                    or mcp_field(annotations, "idempotent_hint", "idempotentHint", False)
                )
                if not retry_safe:
                    logger.warning(
                        "MCP tool %s/%s schema refreshed, but the call will not be "
                        "repeated because the tool is not declared read-only or idempotent",
                        server_name,
                        tool_name,
                    )
                    raise
                result = await _invoke_tool_call()
'''
if mcp_sentinel not in mcp_text:
    if mcp_old not in mcp_text:
        print(
            "HERMES PATCH ERROR: Could not find MCP tool-call marker; "
            "review upstream schema-refresh behavior before updating",
            file=sys.stderr,
        )
        sys.exit(2)
    mcp_text = mcp_text.replace(mcp_old, mcp_new, 1)

mcp_schema_refresh_changed = mcp_text != mcp_orig
if mcp_schema_refresh_changed:
    mcp_tool_path.write_text(mcp_text)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
patched = []
if telegram_audio_documents_changed:
    patched.append("plugins/platforms/telegram/adapter.py (audio documents as audio)")
if mcp_schema_refresh_changed:
    patched.append("tools/mcp_tool.py (refresh stale output schema and retry safe calls)")

if not patched:
    print("All local Hermes patches already applied.")
else:
    for p in patched:
        print(f"Reapplied local Hermes patch: {p}")
