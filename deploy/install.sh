#!/bin/bash
# Installation de la version LAN simplifiée + écran Joy-it RB-TFT3.2-V2.
# À lancer en tant qu'utilisateur normal (pi / infirmerie), PAS avec sudo :
#   bash ~/cabinet-lan/deploy/install.sh
set -e
APP="$HOME/cabinet-lan"
[ "$(id -u)" = 0 ] && { echo "Lance ce script sans sudo."; exit 1; }
[ -f "$APP/server.py" ] || { echo "Copie d'abord le dossier cabinet-lan dans $HOME"; exit 1; }

echo "== 1/5 Paquets"
sudo apt-get update
sudo apt-get install -y python3-gpiozero python3-lgpio python3-pil python3-numpy fonts-dejavu-core curl unzip

echo "== 2/5 Pilote de l'écran 3,2\" (overlay waveshare32b, compatible RB-TFT3.2-V2)"
BOOT=/boot/firmware; [ -d "$BOOT/overlays" ] || BOOT=/boot
if [ ! -f "$BOOT/overlays/waveshare32b.dtbo" ]; then
  TMP=$(mktemp -d)
  if [ -f "$APP/deploy/waveshare32b.dtbo" ]; then
    cp "$APP/deploy/waveshare32b.dtbo" "$TMP/"
  else
    curl -fL -o "$TMP/w.zip" https://files.waveshare.com/upload/c/c3/Waveshare32b.zip
    unzip -o "$TMP/w.zip" -d "$TMP" >/dev/null
  fi
  sudo cp "$(find "$TMP" -name 'waveshare32b.dtbo' | head -1)" "$BOOT/overlays/"
  rm -rf "$TMP"
fi
CFG="$BOOT/config.txt"
sudo cp -n "$CFG" "$CFG.avant-cabinet-lan"
grep -q '^dtparam=spi=on' "$CFG" || echo 'dtparam=spi=on' | sudo tee -a "$CFG" >/dev/null
grep -q '^dtoverlay=waveshare32b' "$CFG" || echo 'dtoverlay=waveshare32b' | sudo tee -a "$CFG" >/dev/null

echo "== 3/5 Droits (GPIO, écran)"
sudo usermod -aG gpio,video,spi,input "$USER"

echo "== 4/5 Service"
chmod +x "$APP/deploy/kiosk.sh"
mkdir -p "$HOME/.config/systemd/user"
cp "$APP/deploy/cabinet-lan.service" "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
# L'ancienne version (avec admin et stats) est arrêtée mais ses fichiers restent dans ~/cabinet
systemctl --user disable --now cabinet.service 2>/dev/null || true
systemctl --user enable --now cabinet-lan.service
sudo loginctl enable-linger "$USER"

echo "== 5/5 Kiosque au démarrage"
AUTO="$HOME/.config/labwc/autostart"
mkdir -p "$(dirname "$AUTO")"
[ -f "$AUTO" ] && cp -n "$AUTO" "$AUTO.avant-cabinet-lan"
touch "$AUTO"
sed -i '/cabinet\/deploy\/kiosk.sh/d; /cabinet-lan\/deploy\/kiosk.sh/d' "$AUTO"
echo "$APP/deploy/kiosk.sh &" >> "$AUTO"

IP=$(hostname -I | awk '{print $1}')
echo
echo "Terminé. Redémarre le Pi : sudo reboot"
echo "Page d'affichage : http://$IP:8080/  (boutons de commande : http://$IP:8080/?commande)"
