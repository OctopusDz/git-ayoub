"""Relit les descriptifs de l'historique avec la classification courante.

Les descriptifs sont conservés dans le référentiel : quand la façon de lire
l'état d'un véhicule change, il n'y a donc rien à recollecter — il suffit de
relire. Sans cela, les ventes passées resteraient jugées à l'ancienne règle et
les comparaisons seraient faussées.

Seuls les champs d'état sont réécrits ; le reste — prix, dates, kilométrage —
n'est pas touché.

    python3 tools/reclasser.py            # aperçu, n'écrit rien
    python3 tools/reclasser.py --ecrire   # applique
"""
from __future__ import annotations

import collections
import gzip
import json
import sys
from datetime import datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from scraper.description import analyser  # noqa: E402

HISTORIQUE = RACINE / "data" / "historique.json.gz"

# Champs réécrits : uniquement la lecture de l'état.
CHAMPS_ETAT = (
    "defauts", "nb_defauts", "nb_defauts_majeurs", "mentions_fourriere",
    "cout_mentions", "sans_cle", "sans_carte_grise", "non_roulant",
    "etat_non_constate", "usure_ordinaire", "gravite",
)


def reclasser(chemin: Path = None, ecrire: bool = False) -> dict:
    chemin = Path(chemin) if chemin else HISTORIQUE
    with gzip.open(chemin, "rt", encoding="utf-8") as fh:
        charge = json.load(fh)
    lots = charge["lots"]

    avant = collections.Counter(l.get("gravite") for l in lots)
    changes = 0

    for lot in lots:
        description = lot.get("description")
        if not description:
            continue
        relu = analyser(description)
        nouveau = {c: relu.get(c) for c in CHAMPS_ETAT if c in relu}
        if any(lot.get(c) != v for c, v in nouveau.items()):
            changes += 1
        lot.update(nouveau)

    apres = collections.Counter(l.get("gravite") for l in lots)

    print(f"{len(lots)} lots relus, {changes} modifiés\n")
    print(f"{'état signalé':24s} {'avant':>7s} {'après':>7s}")
    for etat in sorted(set(avant) | set(apres), key=lambda e: -apres.get(e, 0)):
        print(f"  {str(etat):22s} {avant.get(etat, 0):7d} {apres.get(etat, 0):7d}")

    if not ecrire:
        print("\n(aperçu — relancer avec --ecrire pour appliquer)")
        return {"lots": len(lots), "modifies": changes, "ecrit": False}

    charge["lots"] = lots
    charge["reclasse_le"] = datetime.now().isoformat(timespec="seconds")
    with gzip.open(chemin, "wt", encoding="utf-8") as fh:
        json.dump(charge, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"\nécrit {chemin} ({chemin.stat().st_size // 1024} Ko)")
    return {"lots": len(lots), "modifies": changes, "ecrit": True}


if __name__ == "__main__":
    reclasser(ecrire="--ecrire" in sys.argv)
