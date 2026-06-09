#!/usr/bin/env bash
#
# LanPaste installer for macOS.
#
# Installs LanPaste and registers it as an always-on launchd service that
# starts at login and restarts itself if it ever crashes.
#
# One-line install:
#   curl -fsSL https://raw.githubusercontent.com/asispan/lanpaste/main/install.sh | bash
#
# Or from a checkout:
#   git clone https://github.com/asispan/lanpaste.git && cd lanpaste && ./install.sh
#
# Configurable via environment variables:
#   PORT            Port to listen on            (default: 8080)
#   LANPASTE_HOME   Install directory            (default: ~/.lanpaste)
#   LANPASTE_LABEL  launchd service label        (default: com.asispan.lanpaste)
#   LANPASTE_REPO   Git URL to clone from        (default: the public GitHub repo)
#
set -euo pipefail

REPO_URL="${LANPASTE_REPO:-https://github.com/asispan/lanpaste.git}"
LANPASTE_HOME="${LANPASTE_HOME:-$HOME/.lanpaste}"
PORT="${PORT:-8080}"
LABEL="${LANPASTE_LABEL:-com.asispan.lanpaste}"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mwarning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31merror:\033[0m %s\n'   "$*" >&2; exit 1; }

# --- Preflight ----------------------------------------------------------------
[ "$(uname -s)" = "Darwin" ] || die "This installer is for macOS. See the README for manual/Linux setup."
command -v python3 >/dev/null 2>&1 || die "python3 not found. Run 'xcode-select --install' (or install Homebrew Python), then retry."

# --- Locate or fetch the source ----------------------------------------------
# If this script lives next to app.py we install in place; otherwise we clone.
SRC=""
self="${BASH_SOURCE[0]:-}"
if [ -n "$self" ]; then
  here="$(cd "$(dirname "$self")" 2>/dev/null && pwd || true)"
  [ -n "$here" ] && [ -f "$here/app.py" ] && SRC="$here"
fi

if [ -z "$SRC" ]; then
  command -v git >/dev/null 2>&1 || die "git not found. Run 'xcode-select --install', then retry."
  if [ -d "$LANPASTE_HOME/.git" ]; then
    info "Updating existing install at $LANPASTE_HOME"
    git -C "$LANPASTE_HOME" pull --ff-only --quiet
  else
    info "Cloning LanPaste into $LANPASTE_HOME"
    git clone --depth 1 --quiet "$REPO_URL" "$LANPASTE_HOME"
  fi
  SRC="$LANPASTE_HOME"
else
  info "Installing in place from $SRC"
fi

# --- Python environment -------------------------------------------------------
info "Setting up the Python environment"
[ -d "$SRC/.venv" ] || python3 -m venv "$SRC/.venv"
"$SRC/.venv/bin/python" -m pip install --quiet --upgrade pip
"$SRC/.venv/bin/python" -m pip install --quiet -r "$SRC/requirements.txt"
mkdir -p "$SRC/logs"

# --- launchd service ----------------------------------------------------------
info "Writing LaunchAgent → $PLIST"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$SRC/.venv/bin/python</string>
        <string>$SRC/app.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$SRC</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PORT</key>
        <string>$PORT</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>5</integer>
    <key>StandardOutPath</key>
    <string>$SRC/logs/out.log</string>
    <key>StandardErrorPath</key>
    <string>$SRC/logs/err.log</string>
</dict>
</plist>
PLIST

info "(Re)loading the service"
launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$PLIST"
launchctl kickstart -k "$DOMAIN/$LABEL" 2>/dev/null || true

# --- Verify & report ----------------------------------------------------------
sleep 2
ip="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
echo
if lsof -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  info "LanPaste is running 🎉"
else
  warn "Service installed but nothing is listening on port $PORT yet."
  warn "Check the logs: tail -f \"$SRC/logs/err.log\""
  warn "If the port is busy: lsof -iTCP:$PORT -sTCP:LISTEN  (or re-run with PORT=9000)"
fi
echo
echo "  Local:   http://localhost:$PORT"
[ -n "$ip" ] && echo "  Network: http://$ip:$PORT   (open this on any device on your LAN)"
echo
echo "  Logs:    $SRC/logs/"
echo "  Manage:  launchctl kickstart -k $DOMAIN/$LABEL   # restart"
echo "  Remove:  curl -fsSL https://raw.githubusercontent.com/asispan/lanpaste/main/uninstall.sh | bash"
echo
