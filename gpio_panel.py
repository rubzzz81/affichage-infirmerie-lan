"""Petit écran Joy-it RB-TFT3.2-V2 (320x240, SPI) + ses 3 boutons.

L'écran est piloté par le noyau (overlay « waveshare32b », pilote fbtft) qui
crée un framebuffer (/dev/fb1 en général). On y dessine directement l'état
actuel avec Pillow : pas besoin de bureau ni de navigateur sur ce petit écran.

Boutons de l'écran (actifs à l'état bas) : broches physiques 12, 16, 18,
soit KEY1 = GPIO18, KEY2 = GPIO23, KEY3 = GPIO24 (numérotation BCM).
L'action de chacun se règle dans config.json > gpio > boutons :
"suivant", "precedent", "premier" ou l'id d'un état (ex. "absente").

Attention : GPIO17 est utilisé par le tactile de l'écran, ne pas y brancher
de bouton.
"""
import glob
import logging
import os
import threading
import time

log = logging.getLogger("cabinet.gpio")

_garder = []  # garde les objets en vie (sinon gpiozero libère les broches)

POLICES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]
POLICES_NORMALES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


def _police(taille, gras=True):
    from PIL import ImageFont
    for chemin in (POLICES if gras else POLICES_NORMALES):
        try:
            return ImageFont.truetype(chemin, taille)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=taille)
    except TypeError:  # Pillow ancien
        return ImageFont.load_default()


def _hex(couleur):
    couleur = (couleur or "#1e8e3e").lstrip("#")
    return tuple(int(couleur[i:i + 2], 16) for i in (0, 2, 4))


def trouver_framebuffer(reglage="auto"):
    """Renvoie /dev/fbN du petit écran SPI (pas celui de l'HDMI)."""
    if reglage and reglage != "auto":
        return reglage
    for dossier in sorted(glob.glob("/sys/class/graphics/fb*")):
        try:
            with open(os.path.join(dossier, "name")) as f:
                nom = f.read().strip().lower()
        except OSError:
            continue
        # fbtft nomme ses écrans « fb_ili9340 », « fb_ili9341 », etc.
        if nom.startswith("fb_") or "ili93" in nom or "ssd1289" in nom:
            return "/dev/" + os.path.basename(dossier)
    raise RuntimeError("aucun framebuffer d'écran SPI trouvé (overlay waveshare32b chargé ?)")


class EcranTFT:
    def __init__(self, cfg):
        self.fb = trouver_framebuffer(cfg.get("ecran_framebuffer", "auto"))
        sysfs = "/sys/class/graphics/" + os.path.basename(self.fb)
        with open(sysfs + "/virtual_size") as f:
            self.W, self.H = (int(x) for x in f.read().strip().split(","))
        with open(sysfs + "/bits_per_pixel") as f:
            self.bpp = int(f.read().strip())
        try:
            with open(sysfs + "/stride") as f:
                self.stride = int(f.read().strip())
        except OSError:
            self.stride = self.W * self.bpp // 8
        self.rotation = int(cfg.get("ecran_rotation", 0)) % 360
        self.lock = threading.Lock()
        log.info("Écran TFT : %s %dx%d %d bits", self.fb, self.W, self.H, self.bpp)

    def _octets(self, img):
        """Convertit une image RGB Pillow au format du framebuffer."""
        if self.bpp == 32:
            r, g, b = img.split()
            from PIL import Image
            return Image.merge("RGBA", (b, g, r, Image.new("L", img.size, 255))).tobytes()
        try:
            import numpy as np
            a = np.asarray(img, dtype=np.uint16)
            v = ((a[:, :, 0] >> 3) << 11) | ((a[:, :, 1] >> 2) << 5) | (a[:, :, 2] >> 3)
            return v.astype("<u2").tobytes()
        except ImportError:
            out = bytearray()
            for r, g, b in img.getdata():
                v = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
                out += v.to_bytes(2, "little")
            return bytes(out)

    def _texte(self, draw, xy, texte, police, fill, centre=False, largeur=None):
        if centre:
            g, _, d, _ = draw.textbbox((0, 0), texte, font=police)
            xy = ((largeur - (d - g)) // 2, xy[1])
        draw.text(xy, texte, font=police, fill=fill)

    def _ajuster(self, draw, texte, largeur_max, taille_max, gras=True):
        taille = taille_max
        while taille > 12:
            police = _police(taille, gras)
            g, _, d, _ = draw.textbbox((0, 0), texte, font=police)
            if d - g <= largeur_max:
                return police
            taille -= 2
        return _police(12, gras)

    def taille_logique(self):
        """Taille de l'image à dessiner (avant rotation)."""
        return (self.H, self.W) if self.rotation in (90, 270) else (self.W, self.H)

    def image_principale(self, info, config):
        from PIL import Image, ImageDraw

        W, H = self.taille_logique()
        fond = _hex(info.get("couleur"))
        img = Image.new("RGB", (W, H), fond)
        d = ImageDraw.Draw(img)
        blanc = (255, 255, 255)

        # Bandeau du haut : lycée + heure
        d.rectangle((0, 0, W, 30), fill=(32, 33, 36))
        heure = time.strftime("%H:%M")
        ph = _police(18)
        g, _, dr, _ = d.textbbox((0, 0), heure, font=ph)
        lh = dr - g
        lycee = config.get("lycee", "")
        self._texte(d, (8, 5), lycee, self._ajuster(d, lycee, W - lh - 24, 16, False), blanc)
        self._texte(d, (W - lh - 8, 5), heure, ph, blanc)

        # État en gros au centre
        libelle = (info.get("court") or info.get("libelle", "")).upper()
        pl = self._ajuster(d, libelle, W - 16, 56)
        _, h0, _, h1 = d.textbbox((0, 0), libelle, font=pl)
        y = 30 + (H - 30 - 46 - (h1 - h0)) // 2 - h0
        self._texte(d, (0, y), libelle, pl, blanc, centre=True, largeur=W)

        detail = info.get("detail", "")
        if detail:
            pd = self._ajuster(d, detail, W - 16, 18, False)
            self._texte(d, (0, H - 44), detail, pd, blanc, centre=True, largeur=W)

        # Rappel des boutons en bas
        pb = _police(11, False)
        self._texte(d, (0, H - 16), "KEY1 suivant · KEY2 précédent · KEY3 « Entrez »",
                    pb, (235, 235, 235), centre=True, largeur=W)
        return img

    def dessiner(self, info, config):
        self.envoyer(self.image_principale(info, config))

    def envoyer(self, img):
        """Affiche une image (taille logique) sur l'écran."""
        if self.rotation:
            img = img.rotate(-self.rotation, expand=True)

        data = self._octets(img)
        ligne = self.W * self.bpp // 8
        with self.lock, open(self.fb, "r+b") as f:
            if self.stride == ligne:
                f.write(data)
            else:
                for i in range(self.H):
                    f.seek(i * self.stride)
                    f.write(data[i * ligne:(i + 1) * ligne])


ACTIONS = {"suivant", "precedent", "premier"}


def demarrer(etat, config):
    cfg = config.get("gpio", {})

    if cfg.get("ecran_actif", True):
        try:
            ecran = EcranTFT(cfg)
            _garder.append(ecran)
            try:
                import ecran_admin
                ui = ecran_admin.Interface(ecran, etat, config)
                ui.demarrer()
                _garder.append(ui)
            except Exception as exc:
                log.warning("Menu tactile non démarré : %s", exc)

                def afficher(info):
                    ecran.dessiner(info, config)

                afficher(etat.info())
                etat.ecouteurs.append(afficher)
        except Exception as exc:
            log.warning("Écran TFT indisponible : %s", exc)

    try:
        from gpiozero import Button
    except ImportError as exc:
        log.warning("gpiozero absent, boutons désactivés : %s", exc)
        return

    for broche, action in cfg.get("boutons", {}).items():
        broche = int(broche)
        if broche == 17:
            log.warning("GPIO17 est pris par le tactile de l'écran, bouton ignoré")
            continue
        if action not in ACTIONS and action not in etat.ids:
            log.warning("Action inconnue pour GPIO%d : %s", broche, action)
            continue

        def appui(action=action, broche=broche):
            src = "bouton GPIO%d" % broche
            if action == "suivant":
                etat.suivant(src)
            elif action == "precedent":
                etat.precedent(src)
            elif action == "premier":
                etat.premier(src)
            else:
                etat.definir(action, src)

        try:
            b = Button(broche, pull_up=True, bounce_time=0.08)
            b.when_pressed = appui
            _garder.append(b)
            log.info("Bouton GPIO%d -> %s", broche, action)
        except Exception as exc:
            log.warning("Bouton GPIO%d indisponible : %s", broche, exc)
