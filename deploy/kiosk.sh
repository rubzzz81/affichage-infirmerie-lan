#!/bin/bash
# Lance la page d'affichage en plein écran sur l'écran HDMI.
PORT=$(python3 -c "import json;print(json.load(open('$HOME/cabinet-lan/config.json')).get('port',8080))" 2>/dev/null || echo 8080)
URL="http://localhost:$PORT/"

# Attendre que le serveur réponde (60 s max)
for i in $(seq 1 60); do
  curl -s -o /dev/null "$URL" && break
  sleep 1
done

NAV=$(command -v chromium || command -v chromium-browser)
exec "$NAV" --kiosk --noerrdialogs --disable-infobars --no-first-run \
  --disable-session-crashed-bubble --disable-features=Translate \
  --password-store=basic --check-for-update-interval=31536000 "$URL"
