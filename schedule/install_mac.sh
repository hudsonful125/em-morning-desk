#!/bin/bash
# schedule/install_mac.sh: run the morning brief automatically every weekday at 7:30 am.
#
# Run it once from the em-morning-desk folder:   bash schedule/install_mac.sh
# To change the time, edit HOUR and MINUTE below and run it again.
# To turn the schedule off:                      bash schedule/uninstall_mac.sh
#
# It uses launchd, the Mac's built-in scheduler (free, nothing to install).
# If your Mac is asleep at 7:30, the job runs as soon as it wakes up.
# If the Mac is shut down, that morning is skipped.

HOUR=7
MINUTE=30

LABEL="com.emmorningdesk.brief"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$(command -v python3)"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/em-morning-desk.log"

if [ -z "$PYTHON" ]; then
  echo "Couldn't find python3. Is Python installed?"
  exit 1
fi

# One <dict> per weekday (1 = Monday ... 5 = Friday)
DAYS=""
for DAY in 1 2 3 4 5; do
  DAYS="$DAYS
      <dict><key>Weekday</key><integer>$DAY</integer><key>Hour</key><integer>$HOUR</integer><key>Minute</key><integer>$MINUTE</integer></dict>"
done

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
cat > "$PLIST" <<PLIST_END
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON</string>
        <string>$PROJECT_DIR/morning_job.py</string>
    </array>
    <key>StartCalendarInterval</key>
    <array>$DAYS
    </array>
    <key>StandardOutPath</key><string>$LOG</string>
    <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
PLIST_END

# (Re)load the schedule
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
launchctl bootstrap "gui/$(id -u)" "$PLIST"

echo "Scheduled: every weekday at $HOUR:$(printf %02d $MINUTE)."
echo "Running it once now as a test (the first run of the day can take about a minute)..."
: > "$LOG"
launchctl kickstart "gui/$(id -u)/$LABEL"

# Wait for the test run to finish (up to 3 minutes), then show what happened
for i in $(seq 1 90); do
  sleep 2
  if grep -qE "Brief emailed|Brief saved|ready in the briefs|Error|Traceback|Operation not permitted" "$LOG" 2>/dev/null; then
    sleep 3
    break
  fi
done
echo
echo "----- test run log ($LOG) -----"
cat "$LOG"
echo "-------------------------------"
if grep -q "Operation not permitted" "$LOG"; then
  echo
  echo "macOS blocked the scheduled job from reading this folder. Send a photo of this screen to Claude."
fi
