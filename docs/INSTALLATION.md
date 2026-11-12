# Installation pas à pas

Durée : environ 45 minutes, dont 15 à 20 minutes d'attente (écriture de la carte, mises à jour).

Il faut : le matériel de [MATERIEL.md](MATERIEL.md), un PC Windows relié au même réseau que le Pi,
et une connexion Internet pour le Pi pendant l'installation (paquets et pilote de l'écran).

---

## Étape 1 – Préparer la carte microSD

1. Sur le PC, installer **Raspberry Pi Imager** (https://www.raspberrypi.com/software/).
2. Insérer la carte microSD dans le PC et lancer Raspberry Pi Imager.
3. Choisir :
   - **Appareil** : le modèle de Raspberry Pi (ex. Raspberry Pi 3).
   - **Système** : *Raspberry Pi OS (64-bit)* (la version avec bureau, pas « Lite »).
   - **Stockage** : la carte microSD.
4. Cliquer sur **Suivant**, puis **Modifier réglages** :
   - **Nom d'hôte** : par exemple `pi-infirmerie`.
   - **Nom d'utilisateur et mot de passe** : par exemple `pi` et un mot de passe à noter.
   - **Wi-Fi** : seulement si le Pi n'est pas branché en Ethernet.
   - **Paramètres locaux** : fuseau `Europe/Paris`, clavier `fr`.
   - Onglet **Services** : cocher **Activer SSH** (authentification par mot de passe).
5. Enregistrer, confirmer l'écriture et attendre la fin (vérification comprise).

> En cas d'erreur « Error writing to storage device », voir [DEPANNAGE.md](DEPANNAGE.md).

## Étape 2 – Premier démarrage

1. Insérer la carte dans le Pi, brancher l'écran HDMI, le réseau (câble Ethernet conseillé),
   puis l'alimentation. **Ne pas brancher le petit écran pour l'instant.**
2. Attendre que le bureau s'affiche (le premier démarrage peut prendre 2 à 3 minutes).
3. Trouver l'adresse IP du Pi : sur le Pi, ouvrir un terminal et taper `hostname -I`
   (ou survoler l'icône réseau en haut à droite). Exemple : `10.5.35.102`.

> Conseil : demander au service informatique une **réservation DHCP** pour ce Pi, pour que son
> adresse ne change pas.

## Étape 3 – Se connecter au Pi depuis le PC

Sur le PC, ouvrir **PowerShell** et taper (remplacer l'adresse) :

```powershell
ssh pi@10.5.35.102
```

Répondre `yes` à la première connexion, puis taper le mot de passe (il ne s'affiche pas, c'est normal).
L'invite devient `pi@pi-infirmerie:~ $` : les commandes suivantes sont tapées **sur le Pi**.

*(Facultatif, pour ne plus taper le mot de passe : sur le PC, `ssh-keygen -t ed25519` puis
`type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh pi@10.5.35.102 "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"`.)*

## Étape 4 – Mettre à jour le système

```bash
sudo apt update && sudo apt full-upgrade -y
```

## Étape 5 – Récupérer le programme

```bash
sudo apt install -y git
git clone https://github.com/rubzzz81/affichage-infirmerie-lan.git ~/cabinet-lan
```

Le dossier doit s'appeler exactement `~/cabinet-lan`.

*(Dépôt privé : GitHub demande un identifiant et un « personal access token » à la place du mot
de passe. Sinon, copier le dossier depuis le PC : `scp -r cabinet-lan pi@10.5.35.102:~/`.)*

## Étape 6 – Lancer l'installation

```bash
bash ~/cabinet-lan/deploy/install.sh
```

Le script (mot de passe demandé une fois pour `sudo`) :

1. installe les paquets Python nécessaires (gpiozero, Pillow, numpy) ;
2. télécharge le pilote du petit écran (`waveshare32b.dtbo`) et l'active dans `/boot/firmware/config.txt`
   (une copie de l'original est gardée dans `config.txt.avant-cabinet-lan`) ;
3. donne à l'utilisateur l'accès aux GPIO, au SPI, à l'écran et au tactile ;
4. installe et démarre le service `cabinet-lan` (serveur web sur le port 8080) ;
5. ajoute le lancement de Chromium en plein écran au démarrage du bureau.

Attendre le message **« Terminé »**. Puis, **toujours** :

```bash
sync
sudo poweroff
```

⚠️ Ne jamais couper le courant sans `sudo poweroff` : la carte SD peut perdre les derniers fichiers écrits.

## Étape 7 – Brancher le petit écran

1. Attendre que la LED verte du Pi ne clignote plus, puis débrancher l'alimentation.
2. Enficher le petit écran sur les 26 premières broches (voir [MATERIEL.md](MATERIEL.md)).
3. Rebrancher l'alimentation.

Au démarrage : le grand écran affiche la page en plein écran, le petit écran affiche l'état.

## Étape 8 – Vérifier

| Test | Résultat attendu |
|---|---|
| Appuyer sur KEY1 du petit écran | L'état change sur les deux écrans |
| Depuis le PC, ouvrir `http://10.5.35.102:8080/` | La même page que le grand écran |
| Ouvrir `http://10.5.35.102:8080/reglages`, code `1234` | Le formulaire de réglages s'affiche |
| Appui long (1,5 s) sur le petit écran | Calibrage (la 1re fois) puis demande du code |

Si le petit écran est à l'envers : dans `~/cabinet-lan/config.json`, mettre `"ecran_rotation": 180`
(ou 0, 90, 270), puis `systemctl --user restart cabinet-lan`.

## Étape 9 – Personnaliser

1. Ouvrir `http://<ip-du-pi>:8080/reglages` (ou le bouton ⚙ en bas à droite de la page).
2. Taper le code `1234`.
3. Renseigner le **nom du lycée**, le **nom de l'infirmière** et les **horaires**.
4. Mettre un **nouveau code** (4 à 8 chiffres) et **Enregistrer**.

Les états (textes, couleurs) se modifient dans `config.json` > `etats` (voir [UTILISATION.md](UTILISATION.md)).

## Mise à jour du programme plus tard

```bash
cd ~/cabinet-lan
git pull
systemctl --user restart cabinet-lan
```

`config.json` étant suivi par git, si `git pull` refuse à cause de modifications locales :
`cp config.json ~/config.sauve.json && git checkout config.json && git pull && cp ~/config.sauve.json config.json`.

## Commandes utiles

| Commande (sur le Pi) | Effet |
|---|---|
| `systemctl --user status cabinet-lan` | État du service et dernières lignes du journal |
| `systemctl --user restart cabinet-lan` | Redémarrer le programme (ex. après modification de `config.json`) |
| `curl -s localhost:8080/api/etat` | État actuel au format JSON |
| `sync && sudo poweroff` | Éteindre proprement |
