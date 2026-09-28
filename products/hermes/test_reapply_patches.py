#!/usr/bin/env python3
"""Regression tests for release-aware local patch application."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PATCH_SCRIPT = Path(__file__).with_name("reapply-patches.py")

TELEGRAM_MARKER = '''        for attr, mtype in (\n            ("sticker", MessageType.STICKER), ("photo", MessageType.PHOTO), ("video", MessageType.VIDEO),\n            ("audio", MessageType.AUDIO), ("voice", MessageType.VOICE)):\n            if getattr(msg, attr):\n                return mtype\n        return MessageType.DOCUMENT\n'''

MODERN_MCP_MARKER = '''        async def _call():\n            async with server._rpc_lock, _track_inflight_rpc(server, server_name, op, retry_safe=read_only):\n                server._pending_call_context = contextvars.copy_context()  # for the elicitation callback\n                try:\n                    result = await _call_tool_racing_stdio_death(server, server_name, tool_name, args)\n                finally:\n                    server._pending_call_context = None\n            if getattr(server, "_mark_session_proven", None) is not None:  # round-trip done: transport healthy\n                server._mark_session_proven()\n            return _render_call_tool_result(result, server_name)\n'''


class ReapplyPatchesTests(unittest.TestCase):
    def run_reapply(self, root: Path) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["HERMES_REPO"] = str(root)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [sys.executable, str(PATCH_SCRIPT)],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_applies_to_current_split_mcp_handler_layout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            telegram = root / "plugins" / "platforms" / "telegram"
            mcp = root / "tools"
            telegram.mkdir(parents=True)
            mcp.mkdir()
            (telegram / "adapter.py").write_text(TELEGRAM_MARKER)
            (mcp / "mcp_tool_handlers.py").write_text(
                "def _make_tool_handler(server_name, tool_name, tool_timeout):\n"
                "    read_only = _tool_is_read_only(server_name, tool_name)\n"
                + MODERN_MCP_MARKER
                + "        def _on_failure(exc):\n"
                + "            pass\n"
            )

            result = self.run_reapply(root)

            self.assertEqual(result.returncode, 0, result.stderr)
            patched = (mcp / "mcp_tool_handlers.py").read_text()
            self.assertIn("refreshing tools/list; a read-only or idempotent call will be retried once", patched)
            self.assertIn("async def _invoke_tool_call():", patched)
            self.assertIn("retry_safe = bool(", patched)
            self.assertIn("retry_safe=read_only", patched)

            second = self.run_reapply(root)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("All local Hermes patches already applied.", second.stdout)


if __name__ == "__main__":
    unittest.main()
