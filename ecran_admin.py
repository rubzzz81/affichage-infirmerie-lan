"""Menu de réglage tactile sur le petit écran Joy-it RB-TFT3.2-V2.

- Appui long (1,5 s) n'importe où sur l'écran : demande le code d'accès.
- Menu : nom du lycée, nom de l'infirmière, horaires, code d'accès, calibrage.
- Saisie avec un clavier AZERTY à l'écran (un stylet ou un ongle aide :
  l'écran est résistif).
- Retour automatique à l'affichage normal après 60 s sans toucher l'écran.

Le tactile (puce ADS7846) est lu directement dans /dev/input/eventN, sans
bibliothèque supplémentaire. Le calibrage est demandé la première fois et
enregistré dans config.json (gpio > tactile_calibration).
"""
import fcntl
import glob
import logging
import os
import select
import struct
import threading
import time

from gpio_panel import _police

log = logging.getLogger("cabinet.tactile")

# ---------------------------------------------------------------- tactile

EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
ABS_X, ABS_Y, ABS_PRESSURE = 0, 1, 24
BTN_TOUCH = 330
EVIOCGRAB = 0x40044590
FMT = "llHHi"
TAILLE = struct.calcsize(FMT)
APPUI_LONG = 1.5


def trouver_tactile():
    for dossier in sorted(glob.glob("/sys/class/input/event*")):
        try:
            with open(os.path.join(dossier, "device", "name")) as f:
                nom = f.read().strip()
        except OSError:
            continue
        if "ADS7846" in nom or "XPT2046" in nom or "touch" in nom.lower():
            return "/dev/input/" + os.path.basename(dossier)
    return None


class Tactile(threading.Thread):
    """Lit les appuis et appelle tap(x_brut, y_brut) ou long(x_brut, y_brut)."""

    def __init__(self, chemin, tap, long):
        super().__init__(daemon=True)
        self.chemin, self.tap, self.long = chemin, tap, long

    @staticmethod
    def _milieu(points):
        if len(points) > 4:
            points = points[2:-1]  # les premières/dernières mesures sont bruitées
        xs = sorted(p[0] for p in points)
        ys = sorted(p[1] for p in points)
        return xs[len(xs) // 2], ys[len(ys) // 2]

    def run(self):
        # Ne jamais s'arrêter : en cas d'erreur, on rouvre le périphérique
        while True:
            try:
                self._boucle()
            except Exception:
                log.exception("Lecture du tactile interrompue, reprise dans 2 s")
                time.sleep(2)
                self.chemin = trouver_tactile() or self.chemin

    def _boucle(self):
        fd = os.open(self.chemin, os.O_RDONLY)
        try:
            self._lire(fd)
        finally:
            os.close(fd)

    def _lire(self, fd):
        try:
            # Exclusif : le bureau (et donc la page du grand écran) ne reçoit pas ces appuis
            fcntl.ioctl(fd, EVIOCGRAB, 1)
        except OSError as exc:
            log.warning("Tactile non exclusif : %s", exc)
        x = y = None
        appuye, debut, points, long_fait = False, 0.0, [], False
        while True:
            pret, _, _ = select.select([fd], [], [], 0.1)
            if pret:
                data = os.read(fd, TAILLE * 64)
                if not data:
                    raise OSError("périphérique tactile fermé")
                for i in range(0, len(data) - TAILLE + 1, TAILLE):
                    _, _, type_, code, val = struct.unpack(FMT, data[i:i + TAILLE])
                    if type_ == EV_ABS and code == ABS_X:
                        x = val
                    elif type_ == EV_ABS and code == ABS_Y:
                        y = val
                    elif (type_ == EV_KEY and code == BTN_TOUCH) or \
                            (type_ == EV_ABS and code == ABS_PRESSURE and val == 0):
                        if val and not appuye:
                            appuye, debut, points, long_fait = True, time.monotonic(), [], False
                        elif not val and appuye:
                            appuye = False
                            if points and not long_fait:
                                self._appel(self.tap, self._milieu(points))
                    elif type_ == EV_SYN and appuye and x is not None and y is not None:
                        points.append((x, y))
            if appuye and not long_fait and points and time.monotonic() - debut >= APPUI_LONG:
                long_fait = True
                self._appel(self.long, self._milieu(points))

    @staticmethod
    def _appel(fn, xy):
        try:
            fn(*xy)
        except Exception:
            log.exception("Erreur dans le menu tactile")


# ---------------------------------------------------------------- dessin

NOIR = (32, 33, 36)
GRIS = (60, 64, 67)
GRIS_CLAIR = (95, 99, 104)
BLANC = (255, 255, 255)
VERT = (30, 142, 62)
ROUGE = (197, 34, 31)
BLEU = (26, 115, 232)

CLAVIERS = {
    "abc": [
        list("azertyuiop"),
        list("qsdfghjklm"),
        [("⇧", 1.5)] + list("wxcvbn") + ["'", ("⌫", 1.5)],
        [("123", 1.5), ("éà", 1.5), ("espace", 4), ("Annuler", 2), ("OK", 2)],
    ],
    "123": [
        list("1234567890"),
        list("h:/-()&,.+"),
        [("⇧", 1.5)] + list("_'\"!?@°") + [("⌫", 1.5)],
        [("abc", 1.5), ("éà", 1.5), ("espace", 4), ("Annuler", 2), ("OK", 2)],
    ],
    "éà": [
        list("éèêëàâäçùû"),
        list("ôöîïœæ«»–·"),
        [("⇧", 1.5)] + list("ÿñ€$%*=") + [("⌫", 1.5)],
        [("abc", 1.5), ("123", 1.5), ("espace", 4), ("Annuler", 2), ("OK", 2)],
    ],
}

JOURS_ORDRE = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


class Interface:
    def __init__(self, ecran, etat, config):
        self.ecran, self.etat, self.config = ecran, etat, config
        self.W, self.H = ecran.taille_logique()
        self.lock = threading.RLock()
        self.mode = "principal"
        self.zones = []          # [(x0, y0, x1, y1, action)]
        self.activite = time.monotonic()
        self.message = ""
        # clavier
        self.texte, self.titre, self.page, self.maj, self.valider = "", "", "abc", False, None
        self.code_saisi = ""
        self.calib_points = []
        self.apres_calib = None

    # ------------------------------------------------------------ démarrage

    def demarrer(self):
        self.etat.ecouteurs.append(self._etat_change)
        self.afficher()
        threading.Thread(target=self._minuteur, daemon=True).start()
        chemin = trouver_tactile()
        if chemin:
            Tactile(chemin, self._tap, self._long).start()
            log.info("Tactile prêt : %s (appui long pour le menu)", chemin)
        else:
            log.warning("Aucun écran tactile trouvé, menu de réglage indisponible")

    def _etat_change(self, _info):
        with self.lock:
            if self.mode == "principal":
                self.afficher()

    def _minuteur(self):
        derniere_minute = None
        while True:
            time.sleep(1)
            with self.lock:
                if self.mode != "principal" and time.monotonic() - self.activite > 60:
                    self.mode = "principal"
                    self.afficher()
                elif self.mode == "principal" and time.strftime("%H:%M") != derniere_minute:
                    derniere_minute = time.strftime("%H:%M")
                    try:
                        self.afficher()
                    except Exception as exc:
                        log.warning("Écran TFT : %s", exc)

    # ------------------------------------------------------------ calibrage

    def _calibrage(self):
        return self.config.get("gpio", {}).get("tactile_calibration")

    CIBLES = [(30, 30), (290, 30), (30, 210)]

    def _vers_ecran(self, rx, ry):
        c = self._calibrage()
        if not c:
            return None
        ax, ay = (ry, rx) if c["swap"] else (rx, ry)
        (cx0, cy0), (cx1, _), (_, cy2) = self._cibles()
        x = cx0 + (ax - c["x"][0]) * (cx1 - cx0) / ((c["x"][1] - c["x"][0]) or 1)
        y = cy0 + (ay - c["y"][0]) * (cy2 - cy0) / ((c["y"][1] - c["y"][0]) or 1)
        return max(0, min(self.W - 1, x)), max(0, min(self.H - 1, y))

    def _cibles(self):
        sx, sy = self.W / 320, self.H / 240
        return [(int(a * sx), int(b * sy)) for a, b in self.CIBLES]

    def _point_calib(self, rx, ry):
        self.calib_points.append((rx, ry))
        if len(self.calib_points) < 3:
            return self.afficher()
        (x1, y1), (x2, y2), (x3, y3) = self.calib_points
        swap = abs(y2 - y1) > abs(x2 - x1)
        if swap:
            cal = {"swap": True, "x": [y1, y2], "y": [x1, x3]}
        else:
            cal = {"swap": False, "x": [x1, x2], "y": [y1, y3]}
        if abs(cal["x"][1] - cal["x"][0]) < 150 or abs(cal["y"][1] - cal["y"][0]) < 150:
            self.calib_points = []
            self.message = "Recommencez, en visant les croix"
            return self.afficher()
        gpio = dict(self.config.get("gpio", {}), tactile_calibration=cal)
        self.etat.maj_config({"gpio": gpio}, "calibrage tactile")
        log.info("Calibrage tactile : %s", cal)
        self.message = ""
        suite, self.apres_calib = self.apres_calib, None
        self.mode = suite or "menu"
        self.afficher()

    # ------------------------------------------------------------ événements

    def _long(self, rx, ry):
        with self.lock:
            self.activite = time.monotonic()
            if self.mode == "calib":
                return self._point_calib(rx, ry)
            if self.mode != "principal":
                return
            self.code_saisi, self.message = "", ""
            if not self._calibrage():
                self.calib_points, self.apres_calib, self.mode = [], "code", "calib"
            else:
                self.mode = "code"
            self.afficher()

    def _tap(self, rx, ry):
        with self.lock:
            self.activite = time.monotonic()
            if self.mode == "calib":
                return self._point_calib(rx, ry)
            if self.mode == "principal":
                return
            xy = self._vers_ecran(rx, ry)
            if not xy:
                return
            for x0, y0, x1, y1, action in self.zones:
                if x0 <= xy[0] < x1 and y0 <= xy[1] < y1:
                    action()
                    break

    # ------------------------------------------------------------ affichage

    def afficher(self):
        from PIL import Image, ImageDraw
        with self.lock:
            self.zones = []
            if self.mode == "principal":
                img = self.ecran.image_principale(self.etat.info(), self.config)
            else:
                img = Image.new("RGB", (self.W, self.H), NOIR)
                d = ImageDraw.Draw(img)
                getattr(self, "_ecran_" + self.mode)(d)
            self.ecran.envoyer(img)
            return img

    def _bouton(self, d, rect, texte, action, fond=GRIS, taille=16):
        x0, y0, x1, y1 = rect
        d.rounded_rectangle((x0 + 2, y0 + 2, x1 - 2, y1 - 2), radius=5, fill=fond)
        police = _police(taille, gras=len(texte) > 1)
        while taille > 9:
            g, h, dr, b = d.textbbox((0, 0), texte, font=police)
            if dr - g <= x1 - x0 - 8:
                break
            taille -= 1
            police = _police(taille, gras=len(texte) > 1)
        g, h, dr, b = d.textbbox((0, 0), texte, font=police)
        d.text((x0 + (x1 - x0 - (dr - g)) // 2 - g, y0 + (y1 - y0 - (b - h)) // 2 - h),
               texte, font=police, fill=BLANC)
        self.zones.append((x0, y0, x1, y1, action))

    def _titre(self, d, texte, couleur=BLEU):
        d.rectangle((0, 0, self.W, 26), fill=couleur)
        p = _police(15)
        g, h, dr, b = d.textbbox((0, 0), texte, font=p)
        d.text(((self.W - (dr - g)) // 2, (26 - (b - h)) // 2 - h), texte, font=p, fill=BLANC)

    def _ecran_calib(self, d):
        n = len(self.calib_points)
        self._titre(d, "Calibrage du tactile (%d/3)" % (n + 1))
        p = _police(13, False)
        lignes = ["Appuyez au centre de la croix rouge", "avec un stylet ou un ongle."]
        if self.message:
            lignes.append(self.message)
        for i, l in enumerate(lignes):
            g, _, dr, _ = d.textbbox((0, 0), l, font=p)
            d.text(((self.W - (dr - g)) // 2, 95 + i * 20), l, font=p,
                   fill=(255, 200, 0) if i == 2 else BLANC)
        cx, cy = self._cibles()[n]
        d.line((cx - 12, cy, cx + 12, cy), fill=ROUGE, width=3)
        d.line((cx, cy - 12, cx, cy + 12), fill=ROUGE, width=3)
        d.ellipse((cx - 3, cy - 3, cx + 3, cy + 3), outline=BLANC)

    def _ecran_code(self, d):
        self._titre(d, "Code d'accès")
        p = _police(22)
        affiche = "● " * len(self.code_saisi) or "—"
        g, _, dr, _ = d.textbbox((0, 0), affiche, font=p)
        d.text((10, 32), self.message, font=_police(12, False), fill=(255, 200, 0))
        d.text((self.W - (dr - g) - 14, 30), affiche, font=p, fill=BLANC)
        touches = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "Annuler", "0", "⌫"]
        y0, h, w = 62, (self.H - 62) // 4, self.W // 3
        for i, t in enumerate(touches):
            r, c = divmod(i, 3)
            fond = GRIS_CLAIR if t in ("Annuler", "⌫") else GRIS
            self._bouton(d, (c * w, y0 + r * h, (c + 1) * w, y0 + (r + 1) * h), t,
                         lambda t=t: self._code_touche(t), fond, 20)

    def _code_touche(self, t):
        code = str(self.config.get("code_admin", "1234"))
        if t == "Annuler":
            self.mode = "principal"
        elif t == "⌫":
            self.code_saisi = self.code_saisi[:-1]
        else:
            self.code_saisi += t
            self.message = ""
            if len(self.code_saisi) >= len(code):
                if self.code_saisi == code:
                    self.mode, self.message = "menu", ""
                else:
                    self.message = "Code incorrect"
                self.code_saisi = ""
        self.afficher()

    def _ecran_menu(self, d):
        self._titre(d, self.message or "Réglages", VERT if self.message else BLEU)
        choix = [
            ("Nom du lycée", lambda: self._editer("Nom du lycée", self.config.get("lycee", ""),
                                                   lambda v: self._enregistrer("lycee", v))),
            ("Infirmière", lambda: self._editer("Nom de l'infirmière", self.config.get("infirmiere", ""),
                                                lambda v: self._enregistrer("infirmiere", v))),
            ("Horaires", lambda: self._aller("horaires")),
            ("Code d'accès", lambda: self._editer("Nouveau code (chiffres)", "",
                                                  self._nouveau_code, "123")),
            ("Calibrer", self._recalibrer),
            ("Quitter", lambda: self._aller("principal")),
        ]
        y0, h, w = 30, (self.H - 30) // 3, self.W // 2
        for i, (t, a) in enumerate(choix):
            r, c = divmod(i, 2)
            fond = GRIS_CLAIR if t == "Quitter" else GRIS
            self._bouton(d, (c * w, y0 + r * h, (c + 1) * w, y0 + (r + 1) * h), t, a, fond, 17)

    def _aller(self, mode):
        self.mode, self.message = mode, ""
        self.afficher()

    def _recalibrer(self):
        self.calib_points, self.apres_calib, self.mode, self.message = [], "menu", "calib", ""
        self.afficher()

    def _enregistrer(self, cle, valeur):
        self.etat.maj_config({cle: valeur.strip()}, "écran tactile")
        self.mode, self.message = "menu", "Enregistré ✓"
        self.afficher()

    def _nouveau_code(self, v):
        v = v.strip()
        if len(v) < 4 or not v.isdigit():
            self.mode, self.message = "menu", "Code : 4 chiffres minimum"
            # message d'erreur dans la même barre de titre
        else:
            self.etat.maj_config({"code_admin": v}, "écran tactile")
            self.mode, self.message = "menu", "Code changé ✓"
        self.afficher()

    def _ecran_horaires(self, d):
        self._titre(d, "Horaires (touchez un jour)")
        horaires = self.config.get("horaires", {})
        jours = list(horaires)
        bas = 36
        h = max(22, (self.H - 28 - bas) // max(1, len(jours)))
        pj, ph = _police(13), _police(13, False)
        for i, jour in enumerate(jours):
            y = 28 + i * h
            d.rounded_rectangle((2, y + 1, self.W - 2, y + h - 1), radius=4, fill=GRIS)
            d.text((8, y + (h - 15) // 2), jour.capitalize(), font=pj, fill=BLANC)
            val = horaires[jour]
            while val and d.textlength(val, font=ph) > self.W - 100:
                val = val[:-2] + "…"
            d.text((90, y + (h - 15) // 2), val, font=ph, fill=(220, 220, 220))
            self.zones.append((0, y, self.W, y + h, lambda j=jour: self._editer(
                "Horaires du " + j, horaires.get(j, ""),
                lambda v, j=j: self._enregistrer_jour(j, v), "123")))
        self._bouton(d, (0, self.H - bas, self.W, self.H), "Retour", lambda: self._aller("menu"),
                     GRIS_CLAIR, 15)

    def _enregistrer_jour(self, jour, valeur):
        horaires = dict(self.config.get("horaires", {}))
        horaires[jour] = valeur.strip()
        self.etat.maj_config({"horaires": horaires}, "écran tactile")
        self.mode, self.message = "horaires", ""
        self.afficher()

    # ------------------------------------------------------------ clavier

    def _editer(self, titre, texte, valider, page="abc"):
        self.titre, self.texte, self.valider, self.page, self.maj = titre, texte, valider, page, False
        self.retour_clavier = self.mode
        self.mode = "clavier"
        self.afficher()

    def _ecran_clavier(self, d):
        d.text((6, 3), self.titre, font=_police(12, False), fill=(190, 190, 190))
        d.rounded_rectangle((2, 19, self.W - 2, 47), radius=4, fill=BLANC)
        p = _police(16, False)
        vis = self.texte
        while vis and d.textlength(vis + "|", font=p) > self.W - 14:
            vis = vis[1:]
        d.text((8, 23), vis + "|", font=p, fill=(0, 0, 0))
        y0 = 50
        rangs = CLAVIERS[self.page]
        h = (self.H - y0) // len(rangs)
        for r, rang in enumerate(rangs):
            touches = [(t, 1) if isinstance(t, str) else t for t in rang]
            total = sum(w for _, w in touches)
            x = 0.0
            for t, w in touches:
                larg = self.W * w / total
                label = t.upper() if (self.maj and len(t) == 1) else t
                fond = {"OK": VERT, "Annuler": ROUGE, "⌫": GRIS_CLAIR, "⇧": BLEU if self.maj else GRIS_CLAIR,
                        "123": GRIS_CLAIR, "abc": GRIS_CLAIR, "éà": GRIS_CLAIR}.get(t, GRIS)
                self._bouton(d, (int(x), y0 + r * h, int(x + larg), y0 + (r + 1) * h),
                             label, lambda t=t: self._touche(t), fond, 15)
                x += larg

    def _touche(self, t):
        if t == "OK":
            valider, self.valider = self.valider, None
            return valider(self.texte)
        if t == "Annuler":
            self.mode = self.retour_clavier
        elif t == "⌫":
            self.texte = self.texte[:-1]
        elif t == "⇧":
            self.maj = not self.maj
        elif t in CLAVIERS:
            self.page = t
        elif t == "espace":
            self.texte += " "
        elif len(self.texte) < 70:
            self.texte += t.upper() if self.maj else t
            self.maj = False
        self.afficher()
