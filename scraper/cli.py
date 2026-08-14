"""Ligne de commande du scraper.

Exemples
--------
    # collecte complète des véhicules de tourisme, tous statuts de l'URL cible
    python -m scraper

    # test rapide : 2 pages, 20 lots
    python -m scraper --max-pages 2 --max-lots 20

    # autre catégorie, sans relecture du cache
    python -m scraper --category vehicules-utilitaires --no-cache
"""
from __future__ import annotations

import argparse
import logging
import sys

from . import config
from .export import to_csv, to_json, to_sqlite
from .fetch import Fetcher
from .pipeline import collecter


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scraper",
        description="Collecte les lots véhicules sur encheres-domaine.gouv.fr",
    )
    parser.add_argument("--category", default="vehicules-de-tourisme",
                        help="clé de catégorie ou chemin d'URL "
                             f"({', '.join(config.CATEGORY_PATHS)})")
    parser.add_argument("--statuts", default=",".join(map(str, config.DEFAULT_LOT_STATUS)),
                        help="codes lot_status séparés par des virgules")
    parser.add_argument("--max-pages", type=int, default=config.MAX_PAGES)
    parser.add_argument("--max-lots", type=int, default=None)
    parser.add_argument("--sans-detail", action="store_true",
                        help="ne lit pas les fiches détaillées (plus rapide, moins riche)")
    parser.add_argument("--no-cache", action="store_true", help="ignore le cache disque")
    parser.add_argument("--delai", type=float, default=config.REQUEST_DELAY,
                        help="délai minimum entre deux requêtes, en secondes")
    parser.add_argument("--ignorer-robots", action="store_true",
                        help="ne pas lire robots.txt (usage autorisé uniquement)")
    parser.add_argument("--sortie", default=str(config.DATA_DIR),
                        help="répertoire de sortie des fichiers produits")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    statuts = [int(s) for s in args.statuts.split(",") if s.strip()]
    fetcher = Fetcher(use_cache=not args.no_cache, delay=args.delai,
                      respect_robots=not args.ignorer_robots)

    faits, rapport = collecter(
        categorie=args.category,
        statuts=statuts,
        max_pages=args.max_pages,
        max_lots=args.max_lots,
        avec_detail=not args.sans_detail,
        fetcher=fetcher,
    )

    if not faits:
        logging.error("aucun lot collecté — vérifiez l'accès réseau au site "
                      "et les sélecteurs dans scraper/selectors.json")
        return 1

    from pathlib import Path
    sortie = Path(args.sortie)
    to_json(faits, sortie / "lots.json", meta=rapport)
    to_csv(faits, sortie / "lots.csv")
    to_sqlite(faits, sortie / "lots.sqlite")

    print("\n--- Rapport de collecte ---")
    for cle, valeur in rapport.items():
        print(f"  {cle:.<24} {valeur}")
    print(f"\nFichiers écrits dans {sortie.resolve()}")
    print("Étape suivante :  python -m etl.build_cube")
    return 0


if __name__ == "__main__":
    sys.exit(main())
