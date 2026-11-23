#!/bin/zsh
# Adds the `edge` command to zsh (macOS's default shell), so the agent starts from any folder.
#
#   ./scripts/install_shell.sh            # edge + Korean questions typed straight at the prompt
#   ./scripts/install_shell.sh --no-hook  # edge only
#   ./scripts/install_shell.sh --remove   # take it out again
#
# What it writes: one block between "# >>> local-edge-agent >>>" and "# <<< local-edge-agent <<<" in ~/.zshrc.
#   edge ...              runs main.py with the repo's .venv; `noglob` keeps a "?" in the question from being read
#                         as a file pattern ("zsh: no matches found").
#   Korean at the prompt  zsh calls command_not_found_handler when the first word is not a command; the handler
#                         passes the line to edge only when that word has non-ASCII letters (Korean), so a typo
#                         such as `gti status` still says "command not found". `setopt no_nomatch` lets a "?" at
#                         the end of such a line through as well.
set -e
REPO="$(cd "$(dirname "$0")/.." && pwd)"
RC="${ZDOTDIR:-$HOME}/.zshrc"
START="# >>> local-edge-agent >>>"
END="# <<< local-edge-agent <<<"

touch "$RC"
# Remove an earlier block (re-running the script updates it).
if grep -qF "$START" "$RC"; then
  sed -i '' "/$START/,/$END/d" "$RC"
fi
if [[ "$1" == "--remove" ]]; then
  echo "Removed from $RC. Open a new terminal tab."
  exit 0
fi
if [[ ! -x "$REPO/.venv/bin/python" ]]; then
  echo "No .venv in $REPO. Create it first (docs/manual.md, step 4)."
  exit 1
fi

{
  echo "$START"
  echo "edge_run() { ( cd \"$REPO\" && EDGE_CWD=\"\$OLDPWD\" .venv/bin/python main.py \"\$@\" ) }"
  echo "alias edge='noglob edge_run'"
  if [[ "$1" != "--no-hook" ]]; then
    cat <<'HOOK'
setopt no_nomatch
command_not_found_handler() {
  if [[ ${#1} -lt $(printf %s "$1" | LC_ALL=C wc -c) ]]; then
    edge_run "$@"
    return $?
  fi
  print -u2 "zsh: command not found: $1"
  return 127
}
HOOK
  fi
  echo "$END"
} >> "$RC"

echo "Added to $RC:"
sed -n "/$START/,/$END/p" "$RC"
echo
echo "Open a new terminal tab (or run: source $RC), then try:"
echo "  edge                  # menu"
echo "  edge 배터리 상태 어때?"
[[ "$1" != "--no-hook" ]] && echo "  배터리 상태 어때?       # Korean questions work without 'edge'"
