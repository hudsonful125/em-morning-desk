#!/bin/bash
# schedule/install_website_mac.sh: keep the EM Morning Desk website running all the time,
# so you never need Terminal to open it. Just visit http://localhost:8501 in Safari.
#
# Run it once from the em-morning-desk folder:   bash schedule/install_website_mac.sh
# To turn it off:                                bash schedule/uninstall_website_mac.sh
#
# It uses launchd, the Mac's built-in service manager (free). The website starts when you
# log in and restarts by itself if it ever stops. It is only reachable from this Mac.

LABEL="com.emmorningdesk.website"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$(command -v python3)"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/em-morning-desk-website.log"

case "$PROJECT_DIR" in
  "$HOME/Downloads"*|"$HOME/Desktop"*|"$HOME/Documents"*)
    echo "This folder is inside Downloads, Desktop or Documents, which macOS blocks for background jobs."
    echo "Move it to your home folder first:  mv \"$PROJECT_DIR\" ~/em-morning-desk"
    exit 1;;
esac

if ! "$PYTHON" -c "import streamlit" 2>/dev/null; then
  echo "Streamlit isn't installed yet. Run:  python3 -m pip install streamlit"
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
cat > "$PLIST" <<PLIST_END
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$LABEL</string>
    <key>WorkingDirectory</key><string>$PROJECT_DIR</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON</string>
        <string>-m</string><string>streamlit</string><string>run</string>
        <string>$PROJECT_DIR/app.py</string>
        <string>--server.headless</string><string>true</string>
        <string>--server.address</string><string>localhost</string>
        <string>--server.port</string><string>8501</string>
        <string>--browser.gatherUsageStats</string><string>false</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>$LOG</string>
    <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
PLIST_END

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
launchctl bootstrap "gui/$(id -u)" "$PLIST"

echo "Starting the website..."
for i in $(seq 1 30); do
  sleep 1
  if curl -s -o /dev/null http://localhost:8501/_stcore/health; then
    echo "It's running. Opening http://localhost:8501 in your browser."
    open "http://localhost:8501"
    exit 0
  fi
done
echo "The website didn't start. Here's the log ($LOG):"
tail -20 "$LOG"
