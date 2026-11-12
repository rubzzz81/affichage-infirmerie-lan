# Dépannage

## La page ne s'ouvre pas (ERR_CONNECTION_REFUSED)

Le serveur ne tourne pas. Sur le Pi :

```bash
systemctl --user status cabinet-lan --no-pager -n 30
```

Une erreur Python s'affiche en bas. Vérifier `config.json` (une virgule en trop suffit à bloquer) :
`python3 -m json.tool ~/cabinet-lan/config.json`. Puis `systemctl --user restart cabinet-lan`.

Si des fichiers ont été copiés depuis Windows et que l'erreur parle de caractères bizarres :
`cd ~/cabinet-lan && sed -i 's/\r$//' *.py config.json deploy/*.sh static/*.html` (à taper **sur le Pi**,
pas à travers une commande `ssh "..."` dans PowerShell, qui peut abîmer le `\r`).

## « Accès réservé au réseau local » (403)

Le PC n'a pas une adresse privée (10.x, 172.16-31.x, 192.168.x) : il n'est pas sur le réseau du lycée.

## Le petit écran reste blanc ou noir

- `ls /dev/fb*` et `cat /sys/class/graphics/fb*/name` doivent montrer `fb_ili9340`.
- Sinon, vérifier `/boot/firmware/config.txt` (`dtparam=spi=on` et `dtoverlay=waveshare32b`)
  et la présence de `/boot/firmware/overlays/waveshare32b.dtbo`, puis redémarrer.

## Le petit écran est à l'envers ou couché

`"ecran_rotation": 180` (ou 90 / 270) dans `config.json`, redémarrer le service, puis refaire
« Calibrer » dans le menu tactile.

## Les boutons ne font rien

Vérifier dans `config.json` que les boutons sont sur **18, 23, 24** (et non 12, 16, 18).
Le journal (`systemctl --user status cabinet-lan`) doit afficher « Bouton GPIO18 -> suivant ».

## Le tactile ne répond pas

1. Test matériel : `grep ads7846 /proc/interrupts`. Le compteur doit augmenter quand on appuie.
2. S'il reste à **0** : le Pi ne reçoit aucun signal. Éteindre, vérifier que l'écran est bien
   enfoncé (broche physique 11 = GPIO17), vérifier la petite nappe souple de la dalle tactile.
   Si rien ne change, même sur un autre Pi : la dalle tactile de l'écran est défectueuse,
   remplacer l'écran. Les réglages restent possibles par la page web `/reglages`.
3. S'il augmente mais que les appuis tombent à côté : menu → **Calibrer**.

## Raspberry Pi Imager : « Error writing to storage device »

Essayer un autre port USB ou lecteur de carte, effacer la carte (`diskpart` → `list disk` →
`select disk N` → `clean`, en vérifiant bien le numéro du disque) ou avec SD Memory Card Formatter,
tester la carte avec H2testw ; en dernier recours, changer de carte.

## Code d'accès oublié

Sur le Pi : modifier `"code_admin"` dans `~/cabinet-lan/config.json`, puis
`systemctl --user restart cabinet-lan`.
