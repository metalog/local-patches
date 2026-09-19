# Hermes local patch set

This repository is the source of truth for local Hermes changes. The live checkout under
`~/.hermes/hermes-agent` is disposable: `/home/ubuntu/bin/hermes-update-stable` stashes it,
checks out an exact stable tag, and runs `reapply-patches.py` before starting the gateway.

`reapply-patches.py` is deliberately fail-closed. If an upstream release changes the
surrounding code so a patch cannot be located, the update stops before the gateway is
restarted. Run it against a candidate tag first when the upstream layout has changed.

Active code patches:

- Telegram audio documents are classified as audio, preserving the normal audio inbound path.
- MCP stale output-schema errors trigger one `tools/list` refresh and one retry only for
  tools marked read-only or idempotent; write-capable tools are never replayed.

The files under `archive/` are reviewable snapshots, not automatically applied patches.
The MCP test snapshots are kept separately because the test module and MCP handler moved in
`v2026.9.14`; the `v2026.9.14` snapshot was run successfully (21 tests in that module).
