#!/usr/bin/env bash
set -euo pipefail

source_dir="${1:?usage: rebuild-frontend.sh /path/to/computer-source}"
patch_dir="$(cd "$(dirname "$0")" && pwd)"
frontend_dir="$source_dir/cptr/frontend"
installed_build="/home/ae/.local/lib/cptr/venv/lib/python3.12/site-packages/cptr/frontend/build"
backup_build="${installed_build}.before-local-patch-$(date +%Y%m%d-%H%M%S)"

git -C "$source_dir" apply --check "$patch_dir/patches/android-terminal-input.patch"
git -C "$source_dir" apply "$patch_dir/patches/android-terminal-input.patch"

npm --prefix "$frontend_dir" ci --cache /tmp/cptr-npm-cache
npm --prefix "$frontend_dir" run build -- --logLevel error

mv "$installed_build" "$backup_build"
cp -a "$frontend_dir/build" "$installed_build"
systemctl --user restart cptr.service

echo "Patched frontend installed. Backup: $backup_build"
