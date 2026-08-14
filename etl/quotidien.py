"""Mise à jour quotidienne des ventes ouvertes.

Recollecter chaque matin les 9 000 ventes closes n'aurait pas de sens : elles
ne bougent plus. L'historique est donc figé une fois pour toutes dans le dépôt,
compressé, et seules les ventes ouvertes — quelques centaines de lots, quatre
appels — sont rafraîchies.

Deux commandes :

    python3 -m etl.quotidien figer     # après une collecte complète
    python3 -m etl.quotidien           # mise à jour du jour
"""
from __future__ import annotations

import gzip
import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
LOTS = RACINE / "data" / "lots.json"
HISTORIQUE = RACINE / "data" / "historique.json.gz"
JOURNAL = RACINE / "data" / "suivi.json"

# Tous les champs sont conservés : compressé, l'historique complet ne pèse que
# quelques centaines de kilo-octets, et le portail garde ainsi toute sa
# richesse d'analyse sur les ventes passées.

log = logging.getLogger(__name__)


def figer(source: Path = LOTS, destination: Path = HISTORIQUE) -> Path:
    """Fige les ventes closes en référence compressée et durable."""
    lots = json.loads(Path(source).read_text(encoding="utf-8"))["lots"]
    # Les invendus font partie de l'historique : ils disent ce qui ne trouve
    # pas preneur, information aussi utile que les prix atteints.
    closes = [l for l in lots if l.get("statut") != "Vente à venir"]
    charge = {
        "fige_le": datetime.now().isoformat(timespec="seconds"),
        "nb_ventes_closes": len(closes),
        "dont_adjugees": sum(1 for l in closes if l.get("prix")),
        "lots": closes,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(destination, "wt", encoding="utf-8") as fh:
        json.dump(charge, fh, ensure_ascii=False, separators=(",", ":"))
    taille = destination.stat().st_size / 1_048_576
    print(f"Historique figé : {destination} ({len(closes)} ventes closes, {taille:.1f} Mo)")
    return destination


def charger_historique(chemin: Path = HISTORIQUE) -> list[dict]:
    if not Path(chemin).exists():
        raise FileNotFoundError(
            f"{chemin} est introuvable. Lancez d'abord : python3 -m etl.quotidien figer")
    with gzip.open(chemin, "rt", encoding="utf-8") as fh:
        return json.load(fh)["lots"]


def _lire_journal() -> dict:
    if JOURNAL.exists():
        try:
            return json.loads(JOURNAL.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"lots_connus": [], "historique_des_jours": []}


def mettre_a_jour(statuts: list[str] | None = None, fils: int = 8) -> dict:
    """Collecte les ventes ouvertes, les estime, reconstruit portail et page.

    Retourne le compte rendu du jour : nouveautés, occasions à retenir.
    """
    from scraper import config
    from scraper.parallele import collecter_parallele
    from etl.estimation import estimer
    from etl.build_cube import construire as construire_cube
    from etl.build_artifact import construire as construire_page
    from scraper.export import to_csv, to_json

    statuts = statuts or ["13", "14", "15"]
    historique = charger_historique()

    faits, rapport = collecter_parallele(
        categories=[config.DEFAULT_CATEGORIE], statuts=statuts,
        taille_page=100, fils=fils, max_pages=20)
    if not faits:
        raise RuntimeError("aucune vente ouverte collectée")

    for lot in faits:
        lot.update({k: v for k, v in estimer(lot, historique).items()
                    if k in ("estimation", "fourchette_basse", "fourchette_haute",
                             "prix_max_conseille", "verdict", "confiance",
                             "marge_pct", "nb_comparables")})

    journal = _lire_journal()
    connus = set(journal.get("lots_connus") or [])
    nouveaux = [l for l in faits if l["id_lot"] not in connus]

    def interessant(lot):
        # L'outre-mer est écarté : l'acheminement vers la métropole coûte
        # davantage que la marge attendue sur ces montants.
        return (lot.get("verdict") in ("Très intéressant", "Intéressant")
                and (lot.get("carburant") or "").startswith("Hybride essence")
                and lot.get("metropole") is not False
                and not lot.get("non_roulant"))

    a_retenir = sorted([l for l in faits if interessant(l)],
                       key=lambda l: -(l.get("marge_pct") or 0))

    # Le cube réunit historique et ventes ouvertes ; le portail montre les deux.
    ensemble = historique + faits
    to_json(ensemble, LOTS, meta={**rapport, "mode": "mise à jour quotidienne"})
    to_csv(ensemble, RACINE / "data" / "lots.csv")
    construire_cube(LOTS, RACINE / "portal" / "data" / "dataset.json")
    construire_page()

    journal["lots_connus"] = sorted({l["id_lot"] for l in faits} | connus)
    journal["historique_des_jours"] = (journal.get("historique_des_jours") or [])[-59:] + [{
        "jour": date.today().isoformat(),
        "ventes_ouvertes": len(faits),
        "nouveaux_lots": len(nouveaux),
        "a_retenir": len(a_retenir),
    }]
    JOURNAL.write_text(json.dumps(journal, ensure_ascii=False, indent=1), encoding="utf-8")

    return {"ventes_ouvertes": len(faits), "nouveaux": nouveaux,
            "a_retenir": a_retenir, "rapport": rapport}


def resumer(bilan: dict) -> str:
    """Compte rendu lisible du jour."""
    lignes = [f"{bilan['ventes_ouvertes']} ventes ouvertes, "
              f"{len(bilan['nouveaux'])} nouvelles depuis hier."]
    retenus = bilan["a_retenir"]
    if not retenus:
        lignes.append("Aucun hybride essence intéressant aujourd'hui.")
        return "\n".join(lignes)

    lignes.append(f"\n{len(retenus)} hybride(s) essence à regarder :")
    for lot in retenus[:10]:
        km = f"{lot['kilometrage']:,.0f} km".replace(",", " ") if lot.get("kilometrage") \
            else "km inconnu"
        lignes.append(
            f"  • {lot['intitule']} — {lot.get('annee') or '?'}, {km}, "
            f"{lot.get('departement') or 'lieu inconnu'}\n"
            f"    mise à prix {lot['mise_a_prix']:.0f} € · "
            f"attendu {lot.get('estimation')} € · "
            f"ne pas dépasser {lot.get('prix_max_conseille')} € "
            f"({lot.get('verdict')}, clôture {(lot.get('date_fin') or '')[:10]})\n"
            f"    {lot.get('url')}")
    return "\n".join(lignes)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if argv and argv[0] == "figer":
        figer()
        return 0
    try:
        print(resumer(mettre_a_jour()))
    except Exception as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
