"""Ligne de commande du collecteur.

Exemples
--------
    # véhicules de tourisme, tous les statuts de l'URL cible (~9 800 lots)
    python -m scraper

    # essai rapide
    python -m scraper --max-lots 200

    # toutes les catégories véhicules
    python -m scraper --categories toutes

    # utilitaires + camions, statuts « en cours » uniquement
    python -m scraper --categories 6,9 --statuts 13,14,15
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import config
from .api import DomaineClient
from .export import to_csv, to_json, to_sqlite
from .pipeline import collecter


def _categories(valeur: str) -> list[int]:
    if valeur.strip().lower() in ("toutes", "all"):
        return sorted(config.CATEGORIES)
    return [int(v) for v in valeur.split(",") if v.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scraper",
        description="Collecte les lots véhicules via l'API GraphQL "
                    "d'encheres-domaine.gouv.fr",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Catégories disponibles :\n" + "\n".join(
            f"  {identifiant:>2} — {libelle}"
            for identifiant, libelle in sorted(config.CATEGORIES.items())),
    )
    parser.add_argument("--categories", default=str(config.DEFAULT_CATEGORIE),
                        help="identifiants séparés par des virgules, ou « toutes »")
    parser.add_argument("--statuts", default=",".join(config.DEFAULT_LOT_STATUS),
                        help="codes lot_status séparés par des virgules")
    parser.add_argument("--taille-page", type=int, default=config.PAGE_SIZE,
                        help="lots par appel API (défaut : %(default)s)")
    parser.add_argument("--max-pages", type=int, default=config.MAX_PAGES)
    parser.add_argument("--max-lots", type=int, default=None,
                        help="plafond de lots collectés (essais rapides)")
    parser.add_argument("--delai", type=float, default=config.REQUEST_DELAY,
                        help="délai minimum entre deux appels, en secondes")
    parser.add_argument("--sortie", default=str(config.DATA_DIR),
                        help="répertoire de sortie")
    parser.add_argument("--har", default=None,
                        help="fichier HAR récent : reprend les cookies d'une "
                             "session de navigation pour passer le contrôle anti-robot")
    parser.add_argument("--sans-cube", action="store_true",
                        help="ne pas construire le cube du portail")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    client = DomaineClient(delay=args.delai)
    if args.har:
        from .session_har import appliquer
        try:
            session = appliquer(client, args.har)
            logging.info("session reprise depuis %s (hôte %s)", args.har, session["hote"])
        except Exception as exc:
            logging.error("HAR inexploitable : %s", exc)
            return 1
    try:
        faits, rapport = collecter(
            categories=_categories(args.categories),
            statuts=[s.strip() for s in args.statuts.split(",") if s.strip()],
            taille_page=args.taille_page,
            max_pages=args.max_pages,
            max_lots=args.max_lots,
            client=client,
        )
    except Exception as exc:
        logging.error("collecte interrompue : %s", exc)
        return 1

    if not faits:
        logging.error("aucun lot collecté — vérifiez l'accès réseau au site")
        return 1

    sortie = Path(args.sortie)
    to_json(faits, sortie / "lots.json", meta=rapport)
    to_csv(faits, sortie / "lots.csv")
    to_sqlite(faits, sortie / "lots.sqlite")

    print("\n--- Rapport de collecte ---")
    for categorie, detail in rapport["categories"].items():
        print(f"  {categorie:.<34} {detail['collectes']} lots "
              f"(sur {detail['total_annonce']} annoncés)")
    print(f"  {'total':.<34} {rapport['nb_lots']} lots")
    print(f"  {'appels API':.<34} {rapport['appels_api']}")
    print(f"  {'complétude moyenne':.<34} {rapport['completude_moyenne']} %")
    print(f"  {'lots en erreur':.<34} {rapport['lots_en_erreur']}")
    print(f"\nFichiers écrits dans {sortie.resolve()}")

    if not args.sans_cube:
        from etl.build_cube import construire
        construire(sortie / "lots.json", config.PORTAL_DATA_DIR / "dataset.json")
        print("Cube du portail mis à jour : portal/data/dataset.json")
        print("Ouvrez le portail :  python -m http.server -d portal 8000")
    return 0


if __name__ == "__main__":
    sys.exit(main())
