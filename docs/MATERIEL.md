# Matériel et branchements

## Liste du matériel

| Élément | Modèle utilisé / conseillé | Remarque |
|---|---|---|
| Ordinateur | Raspberry Pi 3 B / 3 B+ (testé), Pi 4 compatible | Pi 5 : non testé avec cet écran |
| Alimentation | Officielle Raspberry Pi 5 V 2,5 A (Pi 3) ou 5 V 3 A USB-C (Pi 4) | Une alimentation faible provoque des plantages |
| Carte microSD | 32 Go classe A1 (SanDisk, Samsung…) | |
| Petit écran | **Joy-it RB-TFT3.2-V2** (3,2", 320×240, SPI, tactile résistif, 3 boutons) | Clone du Waveshare 3,2" (B) |
| Grand écran | Écran ou TV avec entrée HDMI | Câble HDMI (micro-HDMI pour un Pi 4) |
| Boîtier | Boîtier compatible écran GPIO (ouvert sur le dessus) | Facultatif |

## Branchement du petit écran

**Pi éteint et débranché**, enficher l'écran sur les **26 premières broches** du connecteur GPIO,
côté carte SD : la broche 1 du Pi (coin, 3,3 V) sur la broche 1 de l'écran. L'écran recouvre
les broches 1 à 26 ; les broches 27 à 40 restent libres. Aucun fil à ajouter.

Vérifier qu'il n'est pas décalé d'une rangée et qu'il est enfoncé sur toute la longueur.

## Broches utilisées (numérotation BCM)

| Fonction | GPIO (BCM) | Broche physique |
|---|---|---|
| Écran : données SPI (MOSI, MISO, SCLK) | 10, 9, 11 | 19, 21, 23 |
| Écran : sélection affichage (CE0) | 8 | 24 |
| Tactile : sélection (CE1) | 7 | 26 |
| Écran : DC | 22 | 15 |
| Écran : RESET | 27 | 13 |
| Tactile : signal d'appui (PENIRQ) | **17** | 11 |
| Bouton KEY1 → état suivant | **18** | 12 |
| Bouton KEY2 → état précédent | **23** | 16 |
| Bouton KEY3 → retour « Entrez » | **24** | 18 |

⚠️ La documentation Joy-it indique « GPIO12, 16, 18 » pour les boutons : ce sont les numéros de
**broches physiques**, pas les numéros GPIO. Dans `config.json` il faut mettre 18, 23, 24.

Ne rien brancher d'autre sur GPIO17 : c'est le signal du tactile.

## Pilote

L'écran utilise l'overlay `waveshare32b` (pilote noyau `fbtft`, puce `ili9340`) et le contrôleur
tactile `ads7846`. Le script `install.sh` le télécharge et ajoute dans `/boot/firmware/config.txt` :

```
dtparam=spi=on
dtoverlay=waveshare32b
```

L'écran apparaît alors comme un framebuffer (`/dev/fb0` ou `/dev/fb1`), sur lequel le programme
dessine directement. Le bureau et Chromium restent sur l'écran HDMI.
