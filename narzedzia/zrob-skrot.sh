#!/bin/zsh
# Zakłada skrót „Finanse DigitalH” w ~/Applications (Launchpad, Spotlight). Uruchomić raz na Macu.
# Klik: gdy apka już działa, otwiera ją w przeglądarce; gdy nie, uruchamia ją w tle (log w ~/Library/Logs).
set -e
REPO="${0:A:h:h}"
APP="$HOME/Applications/Finanse DigitalH.app"
LOG="$HOME/Library/Logs/DigitalH-Finanse.log"
mkdir -p "$HOME/Applications"
rm -rf "$APP"
osacompile -o "$APP" -e "do shell script \"if /usr/bin/nc -z 127.0.0.1 8765 2>/dev/null; then open http://127.0.0.1:8765/; else nohup '$REPO/start.command' > '$LOG' 2>&1 & fi\""
echo "Gotowe: $APP"
