#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${SKILLS_DEST:-$HOME/.agents/skills}"

mkdir -p "$DEST"

installed=0
for skill_md in "$ROOT"/skills/*/SKILL.md; do
  [ -e "$skill_md" ] || continue
  dir="$(dirname "$skill_md")"
  name="$(basename "$dir")"
  rsync -a --delete --exclude '.DS_Store' "$dir/" "$DEST/$name/"
  echo "installed: $name -> $DEST/$name"
  installed=$((installed + 1))
done

if [ "$installed" -eq 0 ]; then
  echo "no skills found under $ROOT/skills" >&2
  exit 1
fi
echo "done: $installed skill(s) installed to $DEST"
