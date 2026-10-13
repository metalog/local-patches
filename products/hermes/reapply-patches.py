#!/usr/bin/env python3
"""Reapply local Hermes patches that need to survive `hermes update`."""

import os
import shutil
import tempfile
import subprocess
import sys
from pathlib import Path

repo = Path(os.environ.get("HERMES_REPO", Path.home() / ".hermes" / "hermes-agent")).expanduser()

# Validate the complete patch chain on a source-only copy before touching any
# target. A late conflict must not leave audio/MCP/delivery half patched.
if os.environ.get("HERMES_PATCH_PREFLIGHT") != "1":
    with tempfile.TemporaryDirectory(prefix="hermes-patch-preflight-", dir=os.environ.get("TMPDIR")) as directory:
        candidate = Path(directory)
        for relative in ("plugins/platforms/telegram/adapter.py", "gateway/platforms/telegram.py",
                         "tools/mcp_tool.py", "tools/mcp_tool_handlers.py",
                         "gateway/delivery_ledger.py", "gateway/platforms/base.py",
                         "gateway/run_startup.py", "gateway/run_topics.py", "gateway/run_inbound.py", "gateway/session.py",
                         "hermes_cli/main.py"):
            source = repo / relative
            if source.exists():
                target = candidate / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        check = subprocess.run([sys.executable, str(Path(__file__).resolve())],
            env={**os.environ, "HERMES_REPO": str(candidate), "HERMES_PATCH_PREFLIGHT": "1"},
            capture_output=True, text=True)
        if check.returncode:
            print("HERMES PATCH ERROR: preflight failed; target checkout unchanged", file=sys.stderr)
            print(check.stderr, file=sys.stderr)
            sys.exit(check.returncode)

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
telegram_loop_old = (
    '        for attr, mtype in (\n'
    '            ("sticker", MessageType.STICKER), ("photo", MessageType.PHOTO), ("video", MessageType.VIDEO),\n'
    '            ("audio", MessageType.AUDIO), ("voice", MessageType.VOICE)):\n'
    '            if getattr(msg, attr):\n'
    '                return mtype\n'
    '        return MessageType.DOCUMENT\n'
)
telegram_loop_new = (
    '        for attr, mtype in (\n'
    '            ("sticker", MessageType.STICKER), ("photo", MessageType.PHOTO), ("video", MessageType.VIDEO),\n'
    '            ("audio", MessageType.AUDIO), ("voice", MessageType.VOICE)):\n'
    '            if getattr(msg, attr):\n'
    '                return mtype\n'
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
    if old in text:
        text = text.replace(old, new, 1)
    elif telegram_loop_old in text:
        text = text.replace(telegram_loop_old, telegram_loop_new, 1)
    else:
        print("HERMES PATCH ERROR: Could not find Telegram media classifier marker", file=sys.stderr)
        sys.exit(2)

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
mcp_handler_layout = "legacy"
if (repo / "tools" / "mcp_tool_handlers.py").exists():
    mcp_tool_path = repo / "tools" / "mcp_tool_handlers.py"
    mcp_handler_layout = "split"
if not mcp_tool_path.exists():
    print(f"HERMES PATCH ERROR: MCP tool handler module not found: {mcp_tool_path}", file=sys.stderr)
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
mcp_split_old = '''        async def _call():
            async with server._rpc_lock, _track_inflight_rpc(server, server_name, op):
                server._pending_call_context = contextvars.copy_context()  # for the elicitation callback
                try:
                    result = await _call_tool_racing_stdio_death(server, server_name, tool_name, args)
                finally:
                    server._pending_call_context = None
            if getattr(server, "_mark_session_proven", None) is not None:  # round-trip done: transport healthy
                server._mark_session_proven()
            return _render_call_tool_result(result, server_name)
'''
mcp_split_new = '''        async def _invoke_tool_call():
            async with server._rpc_lock, _track_inflight_rpc(server, server_name, op):
                server._pending_call_context = contextvars.copy_context()  # for the elicitation callback
                try:
                    return await _call_tool_racing_stdio_death(server, server_name, tool_name, args)
                finally:
                    server._pending_call_context = None

        async def _call():
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
            if getattr(server, "_mark_session_proven", None) is not None:  # round-trip done: transport healthy
                server._mark_session_proven()
            return _render_call_tool_result(result, server_name)
'''
mcp_modern_old = '''        async def _call():
            async with server._rpc_lock, _track_inflight_rpc(server, server_name, op, retry_safe=read_only):
                server._pending_call_context = contextvars.copy_context()  # for the elicitation callback
                try:
                    result = await _call_tool_racing_stdio_death(server, server_name, tool_name, args)
                finally:
                    server._pending_call_context = None
            if getattr(server, "_mark_session_proven", None) is not None:  # round-trip done: transport healthy
                server._mark_session_proven()
            return _render_call_tool_result(result, server_name)
'''
mcp_modern_new = mcp_split_new.replace(
    "async with server._rpc_lock, _track_inflight_rpc(server, server_name, op):",
    "async with server._rpc_lock, _track_inflight_rpc(server, server_name, op, retry_safe=read_only):",
)
# v0.21.6 adds native image delivery; retain its per-attempt image cache reset.
mcp_native_old = mcp_modern_old.replace(
    "            return _render_call_tool_result(result, server_name)\n",
    "            image_paths.clear()\n            return _render_call_tool_result(result, server_name, image_paths)\n",
)
mcp_native_new = mcp_modern_new.replace(
    "            return _render_call_tool_result(result, server_name)\n",
    "            image_paths.clear()\n            return _render_call_tool_result(result, server_name, image_paths)\n",
)
if mcp_sentinel not in mcp_text:
    candidates = (
        ((mcp_native_old, mcp_native_new), (mcp_modern_old, mcp_modern_new), (mcp_split_old, mcp_split_new))
        if mcp_handler_layout == "split"
        else ((mcp_old, mcp_new),)
    )
    selected_old = selected_new = None
    for candidate_old, candidate_new in candidates:
        if candidate_old in mcp_text:
            selected_old, selected_new = candidate_old, candidate_new
            break
    if selected_old is None:
        print(
            "HERMES PATCH ERROR: Could not find MCP tool-call marker; "
            "review upstream schema-refresh behavior before updating",
            file=sys.stderr,
        )
        sys.exit(2)
    assert selected_new is not None
    mcp_text = mcp_text.replace(selected_old, selected_new, 1)

mcp_schema_refresh_changed = mcp_text != mcp_orig
if mcp_schema_refresh_changed:
    mcp_tool_path.write_text(mcp_text)

# Keep delivery routing across durable retries (normal finals and restart recovery).
delivery_routing_changed = False
delivery_patch = Path(__file__).with_name("delivery-routing.patch")
if delivery_patch.exists() and (repo / "gateway" / "delivery_ledger.py").exists():
    command = ["git", "-C", str(repo), "apply"]
    applied = subprocess.run(command + ["--reverse", "--check", str(delivery_patch)], capture_output=True)
    if applied.returncode != 0:
        check = subprocess.run(command + ["--check", str(delivery_patch)], capture_output=True, text=True)
        if check.returncode != 0:
            print("HERMES PATCH ERROR: Delivery routing patch needs review against this release", file=sys.stderr)
            print(check.stderr, file=sys.stderr)
            sys.exit(2)
        subprocess.run(command + [str(delivery_patch)], check=True)
        delivery_routing_changed = True

# Telegram request routing is mandatory for this gateway layout. Exact forward
# or reverse checks only: upstream changes require human review, never fuzz.
telegram_routing_changed = False
if (repo / "gateway" / "run_topics.py").exists():
    routing_patch = Path(__file__).with_name("telegram-request-routing.patch")
    if not routing_patch.is_file():
        print("HERMES PATCH ERROR: Telegram routing patch missing", file=sys.stderr)
        sys.exit(2)
    command = ["git", "-C", str(repo), "apply"]
    applied = subprocess.run(command + ["--reverse", "--check", str(routing_patch)], capture_output=True)
    if applied.returncode:
        check = subprocess.run(command + ["--check", str(routing_patch)], capture_output=True, text=True)
        if check.returncode:
            print("HERMES PATCH ERROR: Telegram routing conflicts with target release", file=sys.stderr)
            print(check.stderr, file=sys.stderr)
            sys.exit(2)
        subprocess.run(command + [str(routing_patch)], check=True)
        telegram_routing_changed = True

# Install the CLI/module update guard as part of the same atomic preflight.
main_path = repo / "hermes_cli/main.py"
if main_path.exists():
    main_text = main_path.read_text()
    if "# HERMES_LOCAL_UPDATE_POLICY" not in main_text:
        marker = '    """Update Hermes Agent: hangup protection + update lock around ``_cmd_update_impl``."""\n'
        guard = '    # HERMES_LOCAL_UPDATE_POLICY: external policy survives checkout replacement.\n    import runpy\n    policy = Path.home() / ".hermes/local-patches/products/hermes/update-policy.py"\n    if not policy.is_file():\n        raise SystemExit("Local update policy missing; refusing update")\n    if runpy.run_path(str(policy))["route"](args, PROJECT_ROOT):\n        return\n'
        if main_text.count(marker) != 1:
            print("HERMES PATCH ERROR: Native update entry changed; refusing update", file=sys.stderr)
            sys.exit(2)
        main_path.write_text(main_text.replace(marker, marker + guard, 1))

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
patched = []
if telegram_routing_changed:
    patched.append("Telegram requests (new root topic/session; no last-topic recovery)")
if delivery_routing_changed:
    patched.append("gateway delivery ledger (preserve routing and accurate retry marker)")
if telegram_audio_documents_changed:
    patched.append("plugins/platforms/telegram/adapter.py (audio documents as audio)")
if mcp_schema_refresh_changed:
    patched.append(f"{mcp_tool_path.relative_to(repo)} (refresh stale output schema and retry safe calls)")

if not patched:
    print("All local Hermes patches already applied.")
else:
    for p in patched:
        print(f"Reapplied local Hermes patch: {p}")
