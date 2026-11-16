#!/bin/bash
# schedule/uninstall_website_mac.sh: stop the always-on website.
LABEL="com.emmorningdesk.website"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "The always-on website is off. (Run schedule/install_website_mac.sh to turn it back on.)"
