#!/usr/bin/env bash
#
# LanPaste uninstaller for macOS.
#
#   curl -fsSL https://raw.githubusercontent.com/asispan/lanpaste/main/uninstall.sh | bash
#
# By default this stops the service and removes the LaunchAgent but KEEPS your
# installed copy and data. Pass --purge to also delete the install directory.
#
#   ... | bash -s -- --purge
#
set -euo pipefail

LANPASTE_HOME="${LANPASTE_HOME:-$HOME/.lanpaste}"
LABEL="${LANPASTE_LABEL:-com.asispan.lanpaste}"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"
PURGE=0
[ "${1:-}" = "--purge" ] && PURGE=1

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }

info "Stopping the service"
launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true

info "Removing LaunchAgent"
rm -f "$PLIST"

if [ "$PURGE" -eq 1 ]; then
  info "Purging install directory $LANPASTE_HOME (including pastes and uploads)"
  rm -rf "$LANPASTE_HOME"
else
  echo
  info "Done. Your install and data remain at: $LANPASTE_HOME"
  echo "    To remove them too:  rm -rf \"$LANPASTE_HOME\""
  echo "    Or re-run with:      curl -fsSL https://raw.githubusercontent.com/asispan/lanpaste/main/uninstall.sh | bash -s -- --purge"
fi
