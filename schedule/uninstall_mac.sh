#!/bin/bash
# schedule/uninstall_mac.sh: turn off the weekday-morning schedule.
LABEL="com.emmorningdesk.brief"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "The morning schedule is off. (Run schedule/install_mac.sh to turn it back on.)"
