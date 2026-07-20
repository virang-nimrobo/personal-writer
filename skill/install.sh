#!/usr/bin/env bash
#
# install.sh — install/uninstall the `writer-model-edit` skill into Claude Code, Codex, and/or opencode.
#
# Usage:
#   ./install.sh install   [claude|codex|opencode|all]   # default target: all
#   ./install.sh uninstall [claude|codex|opencode|all]
#   ./install.sh status
#
# Options:
#   --copy     Copy the skill files instead of symlinking (standalone, no live updates).
#   --force    Overwrite/remove an existing install without prompting.
#
# By default the skill is SYMLINKED so edits to this repo propagate to both tools.
#

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
  local tool="$1"
  local target="${2:-}"
  if [[ -z "$target" ]]; then die "$tool: no target directory provided"; fi
  
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
  local tool="$1"
  local target="${2:-}"
  if [[ -z "$target" ]]; then die "$tool: no target directory provided"; fi

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
  local tool="$1"
  local target="${2:-}"
  if [[ -z "$target" ]]; then die "$tool: no target directory provided"; fi

  if [[ -L "$target" ]]; then
    printf '  %-7s %s -> %s\n' "$tool" "installed (symlink)" "$(readlink "$target")"
  elif [[ -d "$target" ]]; then
    printf '  %-7s %s (%s)\n' "$tool" "installed (copy)" "$target"
  else
    printf '  %-7s %s\n' "$tool" "not installed"
  fi
}

find_opencode_config() {
  local current_dir="$PWD"
  while [[ "$current_dir" != "/" ]]; do
    if [[ -f "$current_dir/opencode.json" ]]; then
      echo "$current_dir/opencode.json"
      return 0
    elif [[ -f "$current_dir/opencode.jsonc" ]]; then
      echo "$current_dir/opencode.jsonc"
      return 0
    elif [[ -d "$current_dir/.opencode" && -f "$current_dir/.opencode/opencode.json" ]]; then
      echo "$current_dir/.opencode/opencode.json"
      return 0
    fi
    current_dir="$(dirname "$current_dir")"
  done
  return 1
}

install_one_opencode() {
  local target_file
  target_file=$(find_opencode_config) || {
    c_dim "· opencode: no config found, creating $PWD/opencode.json"
    target_file="$PWD/opencode.json"
  }

  local abs_source_dir
  abs_source_dir=$(realpath "$SOURCE_DIR")

  if [[ -f "$target_file" ]]; then
    if jq -e ".skills.paths | contains([\"$abs_source_dir\"])" "$target_file" >/dev/null 2>&1; then
      c_green "✓ opencode: path already in $target_file"
      return 0
    fi

    jq --arg path "$abs_source_dir" '
      if .skills == null then .skills = {} else . end |
      if .skills.paths == null then .skills.paths = [] else .skills.paths end |
      if (.skills.paths | contains([$path]) | not) then .skills.paths += [$path] else . end
    ' "$target_file" > "$target_file.tmp" && mv "$target_file.tmp" "$target_file"
    c_green "✓ opencode: added $abs_source_dir to $target_file"
  else
    jq -n --arg path "$abs_source_dir" '{
      "$schema": "https://opencode.ai/config.json",
      "skills": {
        "paths": [$path]
      }
    }' > "$target_file"
    c_green "✓ opencode: created $target_file with $abs_source_dir"
  fi
}

uninstall_one_opencode() {
  local target_file
  target_file=$(find_opencode_config) || {
    c_dim "· opencode: no config found"
    return 0
  }

  local abs_source_dir
  abs_source_dir=$(realpath "$SOURCE_DIR")

  if [[ -f "$target_file" ]]; then
    if jq -e ".skills.paths | contains([\"$abs_source_dir\"])" "$target_file" >/dev/null 2>&1; then
      jq --arg path "$abs_source_dir" '
        if .skills.paths != null then
          .skills.paths |= map(select(. != $path)) |
          if (.skills.paths | length) == 0 then del(.skills) else . end
        else . end
      ' "$target_file" > "$target_file.tmp" && mv "$target_file.tmp" "$target_file"
      c_green "✓ opencode: removed $abs_source_dir from $target_file"
    else
      c_dim "· opencode: $abs_source_dir not found in $target_file"
    fi
  fi
}

status_one_opencode() {
  local target_file
  target_file=$(find_opencode_config)
  local abs_source_dir
  abs_source_dir=$(realpath "$SOURCE_DIR")

  if [[ -z "$target_file" ]]; then
    printf '  %-7s %s\n' "opencode" "no config found"
  elif [[ -f "$target_file" ]]; then
    if jq -e ".skills.paths | contains([\"$abs_source_dir\"])" "$target_file" >/dev/null 2>&1; then
      printf '  %-7s %s (%s)\n' "opencode" "installed" "$target_file"
    else
      printf '  %-7s %s\n' "opencode" "not installed"
    fi
  else
    printf '  %-7s %s\n' "opencode" "error"
  fi
}

# --- arg parsing -----------------------------------------------------------

ACTION="${1:-}"; [[ $# -gt 0 ]] && shift || true
TARGET="all"
for arg in "$@"; do
  case "$arg" in
    claude|codex|opencode|all) TARGET="$arg" ;;
    --copy)  MODE="copy" ;;
    --force) FORCE=1 ;;
    *) die "unknown argument: $arg" ;;
  esac
done

case "$ACTION" in
  install)
    c_blue "Installing '${SKILL_NAME}' (${MODE}) from ${SOURCE_DIR}"
    case "$TARGET" in
      claude)   install_one claude "$CLAUDE_DIR" ;;
      codex)    install_one codex "$CODEX_DIR" ;;
      opencode) install_one_opencode ;;
      all)
        install_one claude "$CLAUDE_DIR"
        install_one codex "$CODEX_DIR"
        install_one_opencode
        ;;
    esac
    ;;
  uninstall)
    c_blue "Uninstalling '${SKILL_NAME}'"
    case "$TARGET" in
      claude)   uninstall_one claude "$CLAUDE_DIR" ;;
      codex)    uninstall_one codex "$CODEX_DIR" ;;
      opencode) uninstall_one_opencode ;;
      all)
        uninstall_one claude "$CLAUDE_DIR"
        uninstall_one codex "$CODEX_DIR"
        uninstall_one_opencode
        ;;
    esac
    ;;
  status)
    c_blue "Status of '${SKILL_NAME}':"
    case "$TARGET" in
      claude)   status_one claude "$CLAUDE_DIR" ;;
      codex)    status_one codex "$CODEX_DIR" ;;
      opencode) status_one_opencode ;;
      all)
        status_one claude "$CLAUDE_DIR"
        status_one codex "$CODEX_DIR"
        status_one_opencode
        ;;
    esac
    ;;
  ""|-h|--help|help)
    cat <<'EOF'
install.sh — install/uninstall the `writer-model-edit` skill into Claude Code, Codex, and/or opencode.

Usage:
  ./install.sh install   [claude|codex|opencode|all]   # default target: all
  ./install.sh uninstall [claude|codex|opencode|all]
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
