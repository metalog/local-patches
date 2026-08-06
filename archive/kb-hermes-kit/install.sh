#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FILES="${ROOT}/files/home/ubuntu"

if [[ ! -d "${FILES}" ]]; then
  echo "Missing payload directory: ${FILES}" >&2
  exit 1
fi

mkdir -p \
  "${HOME}/.hermes/local-patches" \
  "${HOME}/.hermes/skills/productivity/voice-notes/references" \
  "${HOME}/bin/pipelines"

cp -a "${FILES}/.hermes/local-patches/." "${HOME}/.hermes/local-patches/"
cp -a "${FILES}/.hermes/skills/productivity/voice-notes/." "${HOME}/.hermes/skills/productivity/voice-notes/"
cp -a "${FILES}/bin/." "${HOME}/bin/"

chmod +x \
  "${HOME}/.hermes/local-patches/reapply-patches.py" \
  "${HOME}/bin/hermes-update-local" \
  "${HOME}/bin/reapply-hermes-local-patches" \
  "${HOME}/bin/pipelines/audio-to-kb.py"

echo "Installed Hermes local kit."
echo "Next:"
echo "  ${HOME}/bin/reapply-hermes-local-patches"
echo "  sudo -n systemctl restart hermes-gateway"
