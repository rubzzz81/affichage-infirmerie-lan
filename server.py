#!/usr/bin/env python3
"""Affichage cabinet infirmerie - version LAN simplifiée.

- Sert une page plein écran (état, horaires, lycée, infirmière).
- Répond uniquement aux adresses du réseau local (LAN).
- Pilote le petit écran Joy-it RB-TFT3.2-V2 et ses 3 boutons via les GPIO (gpio_panel.py).

Aucune dépendance obligatoire hors Python 3 : le module GPIO est facultatif.
"""
import ipaddress
import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE, "config.json")
ETAT_FILE = os.path.join(BASE, "etat.json")
STATIC = os.path.join(BASE, "static")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("cabinet")


def charger_config():
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)


class Etat:
    """État courant, partagé entre la page web et le bouton GPIO."""

    def __init__(self, config):
        self.config = config
        self.ids = [e["id"] for e in config["etats"]]
        self.lock = threading.Lock()
        self.version = 0
        try:  # change à chaque modification, même après un redémarrage
            self.config_version = int(os.path.getmtime(CONFIG_FILE))
        except OSError:
            self.config_version = 0
        self.ecouteurs = []
        self.courant = self.ids[0]
        try:
            with open(ETAT_FILE, encoding="utf-8") as f:
                sauve = json.load(f).get("etat")
            if sauve in self.ids:
                self.courant = sauve
        except (OSError, ValueError):
            pass

    def info(self):
        e = next(x for x in self.config["etats"] if x["id"] == self.courant)
        return dict(e, version=self.version, config_version=self.config_version)

    def maj_config(self, modifs, source="?"):
        """Modifie lycée / infirmière / horaires et enregistre config.json."""
        with self.lock:
            for cle in ("lycee", "infirmiere", "horaires"):
                if cle in modifs:
                    self.config[cle] = modifs[cle]
            for cle, val in modifs.items():
                if cle not in ("lycee", "infirmiere", "horaires"):
                    self.config[cle] = val
            tmp = CONFIG_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, CONFIG_FILE)
            self.config_version += 1
        log.info("Configuration modifiée (via %s) : %s", source, ", ".join(modifs))

    def definir(self, nouvel_id, source="?"):
        if nouvel_id not in self.ids:
            return False
        with self.lock:
            if nouvel_id == self.courant:
                return True
            self.courant = nouvel_id
            self.version += 1
            try:
                tmp = ETAT_FILE + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump({"etat": nouvel_id}, f)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, ETAT_FILE)
            except OSError as exc:
                log.warning("Impossible d'enregistrer l'état : %s", exc)
        log.info("Nouvel état : %s (via %s)", nouvel_id, source)
        for fn in list(self.ecouteurs):
            try:
                fn(self.info())
            except Exception:  # un écran en panne ne doit pas bloquer le reste
                log.exception("Erreur d'un écouteur d'état")
        return True

    def suivant(self, source="?"):
        i = self.ids.index(self.courant)
        return self.definir(self.ids[(i + 1) % len(self.ids)], source)

    def precedent(self, source="?"):
        i = self.ids.index(self.courant)
        return self.definir(self.ids[(i - 1) % len(self.ids)], source)

    def premier(self, source="?"):
        return self.definir(self.ids[0], source)


TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}


def est_lan(adresse):
    try:
        ip = ipaddress.ip_address(adresse)
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_private or ip.is_loopback or ip.is_link_local


class Handler(BaseHTTPRequestHandler):
    etat = None
    config = None

    def log_message(self, fmt, *args):  # journal plus discret
        pass

    def _envoyer(self, code, corps, type_="application/json; charset=utf-8"):
        if isinstance(corps, (dict, list)):
            corps = json.dumps(corps, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", type_)
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corps)

    def _lan_seulement(self):
        if est_lan(self.client_address[0]):
            return True
        self._envoyer(403, {"erreur": "Accès réservé au réseau local"})
        return False

    def do_GET(self):
        if not self._lan_seulement():
            return
        chemin = self.path.split("?", 1)[0]
        if chemin == "/api/etat":
            return self._envoyer(200, self.etat.info())
        if chemin == "/api/config":
            c = self.config
            return self._envoyer(200, {
                "lycee": c["lycee"],
                "infirmiere": c["infirmiere"],
                "horaires": c["horaires"],
                "etats": c["etats"],
                "modification_web": c.get("modification_web", True),
            })
        if chemin == "/":
            chemin = "/index.html"
        if chemin == "/reglages":
            chemin = "/reglages.html"
        fichier = os.path.normpath(os.path.join(STATIC, chemin.lstrip("/")))
        if not fichier.startswith(STATIC + os.sep) or not os.path.isfile(fichier):
            return self._envoyer(404, {"erreur": "introuvable"})
        with open(fichier, "rb") as f:
            data = f.read()
        ext = os.path.splitext(fichier)[1].lower()
        self._envoyer(200, data, TYPES.get(ext, "application/octet-stream"))

    def _lire_json(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        return json.loads(self.rfile.read(min(n, 16384)) or b"{}")

    def _reglages(self):
        """Modifie lycée / infirmière / horaires / code, protégé par le code d'accès."""
        try:
            d = self._lire_json()
        except ValueError:
            return self._envoyer(400, {"erreur": "JSON invalide"})
        code = str(self.config.get("code_admin", "1234"))
        if str(d.get("code", "")) != code:
            time.sleep(1.5)  # freine les essais au hasard
            log.warning("Réglages web : code incorrect depuis %s", self.client_address[0])
            return self._envoyer(403, {"erreur": "Code incorrect"})
        if d.get("verifier"):
            return self._envoyer(200, {"ok": True})
        modifs = {}
        for cle in ("lycee", "infirmiere"):
            if isinstance(d.get(cle), str) and d[cle].strip():
                modifs[cle] = d[cle].strip()[:120]
        h = d.get("horaires")
        if isinstance(h, dict):
            modifs["horaires"] = {str(j).strip().lower()[:20]: str(v).strip()[:80]
                                  for j, v in h.items() if str(j).strip()}
        nouveau = str(d.get("nouveau_code", "")).strip()
        if nouveau:
            if not (nouveau.isdigit() and 4 <= len(nouveau) <= 8):
                return self._envoyer(400, {"erreur": "Le code doit faire 4 à 8 chiffres"})
            modifs["code_admin"] = nouveau
        if not modifs:
            return self._envoyer(400, {"erreur": "Rien à enregistrer"})
        self.etat.maj_config(modifs, "page réglages " + self.client_address[0])
        return self._envoyer(200, {"ok": True})

    def do_POST(self):
        if not self._lan_seulement():
            return
        if self.path.split("?", 1)[0] == "/api/reglages":
            return self._reglages()
        if not self.config.get("modification_web", True):
            return self._envoyer(403, {"erreur": "Modification depuis le web désactivée"})
        chemin = self.path.split("?", 1)[0]
        if chemin == "/api/suivant":
            self.etat.suivant("web " + self.client_address[0])
            return self._envoyer(200, self.etat.info())
        if chemin == "/api/etat":
            try:
                n = int(self.headers.get("Content-Length", 0))
                demande = json.loads(self.rfile.read(min(n, 4096)) or b"{}")
            except ValueError:
                return self._envoyer(400, {"erreur": "JSON invalide"})
            if self.etat.definir(demande.get("etat"), "web " + self.client_address[0]):
                return self._envoyer(200, self.etat.info())
            return self._envoyer(400, {"erreur": "état inconnu"})
        self._envoyer(404, {"erreur": "introuvable"})


def main():
    config = charger_config()
    etat = Etat(config)
    Handler.etat = etat
    Handler.config = config

    if config.get("gpio", {}).get("actif", False):
        try:
            import gpio_panel
            gpio_panel.demarrer(etat, config)
        except Exception as exc:
            log.warning("GPIO non démarré (le site web continue) : %s", exc)

    port = int(config.get("port", 8080))
    serveur = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    log.info("Affichage disponible sur http://<ip-du-pi>:%d (réseau local uniquement)", port)
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
