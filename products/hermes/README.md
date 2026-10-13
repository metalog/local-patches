# Hermes local patch set

This repository is the source of truth for local Hermes changes. The live checkout under
`~/.hermes/hermes-agent` is disposable: `/home/ubuntu/bin/hermes-update-stable` is a launcher
for `products/hermes/hermes-update-stable` in this repository; it stashes the checkout,
checks out an exact stable tag, and runs `reapply-patches.py` before starting the gateway.

`reapply-patches.py` is deliberately fail-closed. If an upstream release changes the
surrounding code so a patch cannot be located, the update stops before the gateway is
restarted. Run it against a candidate tag first when the upstream layout has changed.

## Native update entrypoints

`~/.local/bin/hermes` runs external `products/hermes/update-policy.py`;
`cmd_update` (including Python-module and Telegram entrypoints) calls the same
policy. The guard itself is reapplied atomically with the patch chain. A missing
guard makes the external launcher refuse updates, not fall through to native.
Default `hermes update`, `--yes`, `--gateway`, and `--channel stable` select the
latest stable tag, keep old source changes stashed, and validate patches BEFORE
restart. Native help, read-only flags and channel metadata operations remain
native. Unsupported mutation flags and non-default profiles are refused.

Telegram uses a separate transient systemd unit (passwordless sudo required),
not just setsid: setsid remains in the gateway's `KillMode=mixed` cgroup. The
unit owns output/exit-code IPC even after the requesting gateway stops. Neither
a missing policy nor a patch conflict permits a native updater fallback.

Active code patches:

- Telegram audio documents are classified as audio, preserving the normal audio inbound path.
- Durable final-response retries preserve the original metadata and reply anchor; retry notices do not claim a reconnect.
- MCP stale output-schema errors trigger one `tools/list` refresh and one retry only for
  tools marked read-only or idempotent; write-capable tools are never replayed.

The files under `archive/` are reviewable snapshots, not automatically applied patches.
The MCP test snapshots are kept separately because the test module and MCP handler moved in
`v2026.9.14`; the `v2026.9.14` snapshot was run successfully (21 tests in that module).

Stable updates accept SemVer tags (`v0.21.6`) and prefer them over historical calendar tags.
PM releases provision their required tools and dependency generation through Hermes PM, migrate
config non-interactively, and rebuild dashboard assets when the dashboard service is active.
The gateway and dashboard are restarted under their existing systemd user identity.

Delivery routing regression: both boot and runtime retries lost Telegram private-topic metadata
and the reply anchor on unpatched v0.21.6. The patch and regression snapshots are stored here;
the snapshots in `archive/` are not applied to the live checkout. Older rows without the new
nullable delivery context retain their previous recovery behavior.
