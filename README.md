# Local patches and overlays

This repository is the source of truth for local changes that must survive
upstream upgrades of third-party products.

## Products

- [`products/hermes`](products/hermes/README.md) — release-aware Hermes patches
  and the stable update launcher.
- [`products/cptr`](products/cptr/README.md) — Open WebUI Computer mobile
  terminal input patch and frontend rebuild helper.

Each product directory owns its patches, apply/update tooling, validation, and
rollback notes. Product-specific deployment repositories such as
`metalog/openhands-local` remain separate when they contain a complete runtime
overlay rather than a small upstream patch set.

The Hermes symlinks at the repository root are temporary compatibility entry
points for older installations.
