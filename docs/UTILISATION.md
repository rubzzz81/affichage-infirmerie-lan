# Utilisation au quotidien

## Changer l'état

- **Bouton KEY1** (petit écran) : état suivant (Entrez → Patientez → Absente → Fermé → Entrez…).
- **Bouton KEY2** : état précédent.
- **Bouton KEY3** : retour direct à « Entrez ».
- Depuis un PC du réseau : `http://<ip-du-pi>:8080/?commande` affiche des boutons d'état
  (désactivable avec `"modification_web": false` dans `config.json`).

L'état est conservé après un redémarrage.

## Modifier le lycée, l'infirmière, les horaires

**Depuis un PC** : bouton ⚙ en bas à droite de la page, ou `http://<ip-du-pi>:8080/reglages`.
Taper le code, modifier, **Enregistrer**. L'affichage se met à jour en quelques secondes.
Un jour laissé vide n'est pas affiché.

**Depuis le petit écran** : appui long (1,5 s) → code → menu. Saisie au clavier AZERTY à l'écran
(`123` : chiffres, `éà` : accents, `⇧` : majuscule). Le menu se ferme seul après 60 s sans appui.
L'écran est résistif : utiliser un stylet ou l'ongle.

## Modifier les états

Dans `config.json`, la liste `etats` : chaque état a

| Clé | Rôle |
|---|---|
| `id` | identifiant (sans espace) |
| `libelle` | grand texte sur la page |
| `detail` | phrase sous le texte |
| `couleur` | couleur de fond (ex. `#1e8e3e`) |
| `court` | texte du petit écran (court !) |
| `image` | facultatif : image dans `static/` (ex. `"/logo.png"`) |

Puis `systemctl --user restart cabinet-lan`.

## Changer l'action des boutons

`config.json` > `gpio` > `boutons` : `"18": "suivant"`. Actions possibles : `suivant`,
`precedent`, `premier`, ou l'`id` d'un état (ex. `"24": "absente"`).
