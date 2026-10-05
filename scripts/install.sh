#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PLUGIN_NAME="${PLUGIN_NAME:-smooth}"
PLUGIN_VERSION="${PLUGIN_VERSION:-}"
PLUGIN_HOME="${AGENT_PLUGINS_HOME:-$HOME/.agents/plugins}"
OPENCODE_CONFIG="${OPENCODE_CONFIG_FILE:-}"
CODEX_MARKETPLACE="${CODEX_MARKETPLACE_FILE:-}"
UNINSTALL=0

for argument in "$@"; do
  case "$argument" in
    --uninstall)
      UNINSTALL=1
      ;;
    --help|-h)
      echo "usage: bash scripts/install.sh [--uninstall]"
      exit 0
      ;;
    *)
      echo "unknown argument: $argument" >&2
      exit 2
      ;;
  esac
done

args=(
  "$ROOT/scripts/plugin_installer.py"
  --source-root "$ROOT"
  --home "$HOME"
  --plugin-store "$PLUGIN_HOME"
  --name "$PLUGIN_NAME"
)

if [ "$UNINSTALL" -eq 1 ]; then
  args+=(--uninstall)
fi

if [ -n "$PLUGIN_VERSION" ]; then
  args+=(--version "$PLUGIN_VERSION")
fi
if [ -n "$OPENCODE_CONFIG" ]; then
  args+=(--opencode-config "$OPENCODE_CONFIG")
fi
if [ -n "$CODEX_MARKETPLACE" ]; then
  args+=(--codex-marketplace "$CODEX_MARKETPLACE")
fi

if [ "${INSTALL_OPENCODE:-1}" != "1" ]; then
  args+=(--skip-opencode)
fi
if [ "${INSTALL_CODEX:-1}" != "1" ]; then
  args+=(--skip-codex)
fi
if [ "${INSTALL_KIMI_WORK:-1}" != "1" ]; then
  args+=(--skip-kimi)
fi
if [ "${INSTALL_GEMINI:-1}" != "1" ]; then
  args+=(--skip-gemini)
fi
if [ "${INSTALL_KIMI_WORK:-1}" = "1" ]; then
  KIMI_SHARE="${KIMI_SHARE_DIR:-$HOME/Library/Application Support/kimi-desktop/daimon-share}"
  if [ "$UNINSTALL" -eq 1 ] || [ -n "${KIMI_SHARE_DIR:-}" ] || [ -d "$KIMI_SHARE" ]; then
    args+=(--kimi-share-dir "$KIMI_SHARE")
  fi
  if [ "$UNINSTALL" -eq 0 ]; then
    KIMI_BUILDER="${KIMI_PLUGIN_BUILDER:-/Applications/Kimi.app/Contents/Resources/resources/daimon-bundle/app/daimon/assets/builtin-skills/plugin-builder}"
    KIMI_REGISTER="${KIMI_REGISTER_SCRIPT:-$KIMI_BUILDER/scripts/register_personal.py}"
    if [ -f "$KIMI_REGISTER" ]; then
      args+=(--kimi-register "$KIMI_REGISTER")
      KIMI_DAIMON="${KIMI_DAIMON_BIN:-/Applications/Kimi.app/Contents/Resources/resources/daimon-bundle/bin/kimi-daimon}"
      KIMI_NODE_BIN="${KIMI_NODE_BIN:-/Applications/Kimi.app/Contents/Resources/resources/runtime/node}"
      [ -x "$KIMI_DAIMON" ] && args+=(--kimi-daimon-bin "$KIMI_DAIMON")
      [ -x "$KIMI_NODE_BIN" ] && args+=(--kimi-node "$KIMI_NODE_BIN")
    else
      echo "kimi-work: skipped (Kimi plugin-builder not found at $KIMI_REGISTER)" >&2
    fi
  fi
fi

if [ -n "${SKILLS_DEST:-}" ] || [ -n "${KIMI_SKILLS_DEST:-}" ]; then
  echo "warning: SKILLS_DEST/KIMI_SKILLS_DEST are deprecated; skills are installed only as a plugin" >&2
fi

exec "$PYTHON_BIN" "${args[@]}"
