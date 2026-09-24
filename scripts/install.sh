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

KIMI_DEST="${KIMI_SKILLS_DEST:-$HOME/Library/Application Support/kimi-desktop/daimon-share/daimon/skills}"
if [ -d "$KIMI_DEST" ]; then
  linked=0
  for skill_md in "$ROOT"/skills/*/SKILL.md; do
    [ -e "$skill_md" ] || continue
    name="$(basename "$(dirname "$skill_md")")"
    target="$KIMI_DEST/$name"
    if [ -e "$target" ] && [ ! -L "$target" ]; then
      backup="${target}.bak"
      if [ -e "$backup" ]; then
        backup="${target}.bak.$(date +%Y%m%d%H%M%S)"
      fi
      echo "backing up existing directory: $target -> $backup"
      mv "$target" "$backup"
    fi
    ln -sfn "$DEST/$name" "$target"
    echo "linked: $DEST/$name -> $target"
    linked=$((linked + 1))
  done
  echo "done: $linked skill(s) linked to $KIMI_DEST"
fi

