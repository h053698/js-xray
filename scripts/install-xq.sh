#!/bin/sh
# Put xq on the PATH by symlinking it, so a query reads "xq summary" instead of
# "python3 /long/path/skill/scripts/xq.py /long/path/name.xrayjs summary". The
# point of the tool is to spend fewer tokens per answer, and a path that long is
# a tax on every one of them.
#
# A symlink rather than a copy: the link keeps pointing at the checkout, so a
# pull updates the installed command with no reinstall step, and there is never a
# stale second copy to answer differently from the tests.
#
#   sh scripts/install-xq.sh [--dry-run] [--bin-dir DIR]
#
# Idempotent. Re-running refreshes our own link and changes nothing else. It
# never writes to a system directory and never asks for sudo: an install that
# needs a password to undo is not one to run unattended.
set -eu

DRY_RUN=0
BIN_DIR=""

usage() {
    cat <<'EOF'
usage: sh scripts/install-xq.sh [--dry-run] [--bin-dir DIR]

  --dry-run      report what would happen; write nothing
  --bin-dir DIR  install into DIR instead of searching the PATH
                 (created if absent; how the test suite stays out of ~)
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) DRY_RUN=1 ;;
        --bin-dir)
            [ $# -ge 2 ] || { echo "install-xq: --bin-dir needs a directory" >&2; exit 2; }
            BIN_DIR="$2"; shift ;;
        --bin-dir=*) BIN_DIR=$(printf %s "$1" | sed "s/^--bin-dir=//") ;;
        -h|--help) usage; exit 0 ;;
        *) echo "install-xq: unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

say() { echo "install-xq: $*"; }
would() { if [ "$DRY_RUN" -eq 1 ]; then say "would $*"; else say "$*"; fi; }

# Resolve the repo from this script's own location, so it works from any cwd and
# the link records an absolute path.
script_dir=$(cd "$(dirname "$0")" && pwd)
repo_root=$(cd "$script_dir/.." && pwd)
SOURCE="$repo_root/skill/scripts/xq.py"

[ -f "$SOURCE" ] || { echo "install-xq: not found: $SOURCE" >&2; exit 1; }

# ---------------------------------------------------------------- executable bit
# The link is invoked as a bare command, so the shebang has to be reachable.
if [ -x "$SOURCE" ]; then
    say "already executable: skill/scripts/xq.py"
else
    would "chmod +x skill/scripts/xq.py"
    [ "$DRY_RUN" -eq 1 ] || chmod +x "$SOURCE"
fi

# ------------------------------------------------------------------ target dir
# Preference order. ~/.local/bin first because it is the conventional per-user
# bin directory and is already on the PATH here; ~/bin second, for setups that
# predate that convention. Anything else must be both on the PATH and writable,
# and system prefixes are excluded even when writable -- a directory shared with
# a package manager is not ours to add commands to.
in_path() {
    case ":$PATH:" in *":$1:"*) return 0 ;; esac
    return 1
}

is_system_dir() {
    case "$1" in
        /usr/*|/bin|/sbin|/opt/*|/Library/*|/System/*|/nix/*|/var/*) return 0 ;;
    esac
    return 1
}

chosen=""
reason=""
if [ -n "$BIN_DIR" ]; then
    chosen="$BIN_DIR"
    reason="given with --bin-dir"
else
    for candidate in "$HOME/.local/bin" "$HOME/bin"; do
        if [ -d "$candidate" ] && [ -w "$candidate" ]; then
            chosen="$candidate"; reason="conventional user bin directory"
            in_path "$candidate" && reason="$reason, already on PATH"
            break
        fi
    done
    if [ -z "$chosen" ]; then
        # Nothing conventional exists yet: take a writable non-system PATH entry if
        # the shell already has one, so the command resolves without touching any
        # shell configuration.
        saved_ifs=$IFS
        IFS=:
        for candidate in $PATH; do
            [ -n "$candidate" ] || continue
            is_system_dir "$candidate" && continue
            if [ -d "$candidate" ] && [ -w "$candidate" ]; then
                chosen="$candidate"; reason="writable non-system PATH entry"; break
            fi
        done
        IFS=$saved_ifs
    fi
    if [ -z "$chosen" ]; then
        # Create the conventional directory rather than reaching for /usr/local/bin.
        chosen="$HOME/.local/bin"; reason="created; no writable PATH entry existed"
    fi
fi

if [ ! -d "$chosen" ]; then
    would "mkdir -p $chosen"
    [ "$DRY_RUN" -eq 1 ] || mkdir -p "$chosen"
elif [ ! -w "$chosen" ]; then
    echo "install-xq: not writable: $chosen" >&2
    if is_system_dir "$chosen"; then
        echo "install-xq: that is a system directory; this script will not use sudo." >&2
        echo "install-xq: to install there yourself:" >&2
        echo "  sudo ln -s '$SOURCE' '$chosen/xq'" >&2
    fi
    exit 1
fi

LINK="$chosen/xq"
say "target $LINK ($reason)"

# ------------------------------------------------------------------- the link
# An existing xq belonging to something else is left alone. Silently shadowing
# another tool is the kind of breakage that surfaces days later, in an unrelated
# script, with nothing pointing back here.
if [ -L "$LINK" ]; then
    current=$(readlink "$LINK" 2>/dev/null || echo "")
    if [ "$current" = "$SOURCE" ]; then
        say "already installed and current; nothing to do"
    else
        case "$current" in
            */skill/scripts/xq.py)
                would "repoint $LINK: $current -> $SOURCE"
                [ "$DRY_RUN" -eq 1 ] || ln -sfn "$SOURCE" "$LINK" ;;
            *)
                echo "install-xq: $LINK already exists and points at $current," >&2
                echo "install-xq: which is not a js-xray checkout. Refusing to replace it." >&2
                echo "install-xq: remove it yourself, or use --bin-dir to install elsewhere." >&2
                exit 1 ;;
        esac
    fi
elif [ -e "$LINK" ]; then
    echo "install-xq: $LINK already exists and is not a symlink. Refusing to replace it." >&2
    echo "install-xq: remove it yourself, or use --bin-dir to install elsewhere." >&2
    exit 1
else
    would "link $LINK -> $SOURCE"
    [ "$DRY_RUN" -eq 1 ] || ln -s "$SOURCE" "$LINK"
fi

# ---------------------------------------------------------------------- PATH
if in_path "$chosen"; then
    say "$chosen is on your PATH; run: xq summary"
else
    say "WARNING: $chosen is not on your PATH, so xq will not be found yet."
    shell_name=${SHELL:-}
    case "$shell_name" in
        */zsh)  rc="~/.zshrc" ;;
        */bash) rc="~/.bashrc" ;;
        */fish) rc="~/.config/fish/config.fish" ;;
        *)      rc="your shell startup file" ;;
    esac
    if [ "$rc" = "~/.config/fish/config.fish" ]; then
        say "add to $rc:  fish_add_path $chosen"
    else
        say "add to $rc:  export PATH=\"$chosen:\$PATH\""
    fi
    say "then restart the shell, or export it in this one to use xq right away"
fi

if [ "$DRY_RUN" -eq 1 ]; then
    say "dry run: nothing was written"
fi
