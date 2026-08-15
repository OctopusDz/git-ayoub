"""Assemble une version autonome de l'application, données embarquées.

L'application déployée va chercher ses données auprès du serveur. Pour un
aperçu — ou une consultation hors ligne — il faut au contraire un fichier
unique qui ne dépende de rien : les données sont alors injectées dans la page,
et tout ce qui suppose un hébergement (manifeste, service worker, icônes) est
retiré.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SOURCE = RACINE / "app" / "index.html"
DONNEES = RACINE / "app" / "data" / "hybrides.json"
SORTIE = RACINE / "dist" / "hybrides-autonome.html"

# Balises qui n'ont de sens qu'une fois la page hébergée.
A_RETIRER = (
    r'\s*<link rel="manifest"[^>]*>',
    r'\s*<link rel="apple-touch-icon"[^>]*>',
    r'\s*<link rel="icon"[^>]*>',
)


def construire(destination: Path | None = None) -> Path:
    destination = Path(destination) if destination else SORTIE
    page = SOURCE.read_text(encoding="utf-8")
    donnees = DONNEES.read_text(encoding="utf-8")

    for motif in A_RETIRER:
        page = re.sub(motif, "", page)

    # Le service worker mettrait en cache une page qui n'a pas d'origine
    # stable : on le débranche.
    page = page.replace('if ("serviceWorker" in navigator) {',
                        'if (false) {')

    # `</script>` à l'intérieur d'une chaîne JSON fermerait la balise hôte.
    charge = donnees.replace("</", "<\\/")
    balise = (f'<script id="donnees-embarquees" type="application/json">'
              f'{charge}</script>\n')
    if "<script>" not in page:
        raise SystemExit("structure de page inattendue : aucun bloc <script>")
    page = page.replace('<script>\n"use strict";', balise + '<script>\n"use strict";', 1)

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(page, encoding="utf-8")

    meta = json.loads(donnees)["meta"]
    taille = destination.stat().st_size / 1_048_576
    print(f"Page autonome : {destination} ({meta['nb_hybrides']} hybrides, "
          f"{taille:.1f} Mo)")
    return destination


if __name__ == "__main__":
    sys.exit(0 if construire() else 1)
