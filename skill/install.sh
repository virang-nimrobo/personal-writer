#!/usr/bin/env bash
#
# install.sh — install/uninstall the `writer-model-edit` skill into Claude Code and/or Codex.
#
# Usage:
#   ./install.sh install [claude|codex|all]   # default target: all
#   ./install.sh uninstall [claude|codex|all]
#   ./install.sh status
#
# Options:
#   --copy     Copy the skill files instead of symlinking (standalone, no live updates).
#   --force    Overwrite an existing install without prompting.
#
# By default the skill is SYMLINKED so edits to this repo propagate to both tools.

set -euo pipefail

SKILL_NAME="writer-model-edit"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CLAUDE_DIR="${HOME}/.claude/skills/${SKILL_NAME}"
CODEX_DIR="${HOME}/.codex/skills/${SKILL_NAME}"

MODE="symlink"   # or "copy"
FORCE=0

# --- helpers ---------------------------------------------------------------

c_blue()  { printf '\033[34m%s\033[0m\n' "$*"; }
c_green() { printf '\033[32m%s\033[0m\n' "$*"; }
c_red()   { printf '\033[31m%s\033[0m\n' "$*" >&2; }
c_dim()   { printf '\033[2m%s\033[0m\n' "$*"; }

die() { c_red "error: $*"; exit 1; }

# Is $1 a symlink that points into our source dir, or a copy we made? Used so
# uninstall never deletes something the user put there by hand.
owned_by_us() {
  local target="$1"
  if [[ -L "$target" ]]; then
    local dest; dest="$(readlink "$target")"
    [[ "$dest" == "$SOURCE_DIR" || "$dest" == "$SOURCE_DIR/" ]] && return 0
    return 1
  fi
  # A directory copy is "ours" if it contains our SKILL.md marker.
  [[ -f "$target/SKILL.md" ]] && grep -q "^name: ${SKILL_NAME}$" "$target/SKILL.md" 2>/dev/null
}

install_one() {
  local tool="$1" target="$2"
  local parent; parent="$(dirname "$target")"
  mkdir -p "$parent"

  if [[ -e "$target" || -L "$target" ]]; then
    if [[ "$FORCE" -eq 1 ]] || owned_by_us "$target"; then
      rm -rf "$target"
    else
      die "$tool: $target already exists and isn't ours. Re-run with --force to overwrite."
    fi
  fi

  if [[ "$MODE" == "copy" ]]; then
    cp -R "$SOURCE_DIR" "$target"
    # Don't drag the installer or VCS noise into the installed copy.
    rm -f "$target/install.sh"
    rm -rf "$target/.git"
    c_green "✓ $tool: copied → $target"
  else
    ln -s "$SOURCE_DIR" "$target"
    c_green "✓ $tool: symlinked → $target"
  fi
}

uninstall_one() {
  local tool="$1" target="$2"
  if [[ ! -e "$target" && ! -L "$target" ]]; then
    c_dim "· $tool: nothing installed at $target"
    return 0
  fi
  if owned_by_us "$target" || [[ "$FORCE" -eq 1 ]]; then
    rm -rf "$target"
    c_green "✓ $tool: removed $target"
  else
    die "$tool: $target exists but isn't ours. Re-run with --force to remove anyway."
  fi
}

status_one() {
  local tool="$1" target="$2"
  if [[ -L "$target" ]]; then
    printf '  %-7s %s -> %s\n' "$tool" "installed (symlink)" "$(readlink "$target")"
  elif [[ -d "$target" ]]; then
    printf '  %-7s %s (%s)\n' "$tool" "installed (copy)" "$target"
  else
    printf '  %-7s %s\n' "$tool" "not installed"
  fi
}

# --- arg parsing -----------------------------------------------------------

ACTION="${1:-}"; [[ $# -gt 0 ]] && shift || true
TARGET="all"
for arg in "$@"; do
  case "$arg" in
    claude|codex|all) TARGET="$arg" ;;
    --copy)  MODE="copy" ;;
    --force) FORCE=1 ;;
    *) die "unknown argument: $arg" ;;
  esac
done

run_for_targets() {
  local fn="$1"
  case "$TARGET" in
    claude) "$fn" claude "$CLAUDE_DIR" ;;
    codex)  "$fn" codex  "$CODEX_DIR" ;;
    all)    "$fn" claude "$CLAUDE_DIR"; "$fn" codex "$CODEX_DIR" ;;
  esac
}

case "$ACTION" in
  install)
    c_blue "Installing '${SKILL_NAME}' (${MODE}) from ${SOURCE_DIR}"
    run_for_targets install_one
    ;;
  uninstall)
    c_blue "Uninstalling '${SKILL_NAME}'"
    run_for_targets uninstall_one
    ;;
  status)
    c_blue "Status of '${SKILL_NAME}':"
    status_one claude "$CLAUDE_DIR"
    status_one codex  "$CODEX_DIR"
    ;;
  ""|-h|--help|help)
    cat <<'EOF'
install.sh — install/uninstall the `writer-model-edit` skill into Claude Code and/or Codex.

Usage:
  ./install.sh install   [claude|codex|all]   # default target: all
  ./install.sh uninstall [claude|codex|all]
  ./install.sh status

Options:
  --copy     Copy the skill files instead of symlinking (standalone, no live updates).
  --force    Overwrite/remove an existing install without prompting.

By default the skill is SYMLINKED so edits to this repo propagate to both tools.
EOF
    ;;
  *)
    die "unknown action '$ACTION' (use: install | uninstall | status)"
    ;;
esac
