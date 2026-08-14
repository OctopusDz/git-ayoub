"""Orchestration : parcours des pages de résultats puis des fiches de lot."""
from __future__ import annotations

import logging
from datetime import datetime

from . import config
from .fetch import Fetcher
from .normalize import normalize_lot
from .parse import build_listing_url, parse_detail, parse_listing, total_pages

log = logging.getLogger(__name__)


def collecter(categorie: str = "vehicules-de-tourisme",
              statuts: list[int] | None = None,
              max_pages: int = config.MAX_PAGES,
              max_lots: int | None = None,
              avec_detail: bool = True,
              fetcher: Fetcher | None = None) -> tuple[list[dict], dict]:
    """Collecte les lots d'une catégorie et retourne (faits, rapport)."""
    statuts = statuts or config.DEFAULT_LOT_STATUS
    chemin = config.CATEGORY_PATHS.get(categorie, categorie)
    selecteurs = config.load_selectors()
    fetcher = fetcher or Fetcher()

    rapport = {
        "categorie": categorie,
        "statuts": statuts,
        "pages_lues": 0,
        "lots_listes": 0,
        "fiches_lues": 0,
        "fiches_en_echec": 0,
        "demarre_le": datetime.now().isoformat(timespec="seconds"),
    }

    # --- 1. pagination -----------------------------------------------------
    entrees: dict[str, dict] = {}
    url = build_listing_url(chemin, statuts, 1)
    page_num = 1
    while url and page_num <= max_pages:
        html = fetcher.get(url)
        if not html:
            log.error("page %d inaccessible — arrêt de la pagination", page_num)
            break
        rapport["pages_lues"] += 1
        if page_num == 1:
            total = total_pages(html, selecteurs)
            if total:
                log.info("pagination annoncée : %s pages", total)
                rapport["pages_annoncees"] = total

        lots, suivant = parse_listing(html, url, selecteurs)
        nouveaux = 0
        for lot in lots:
            if lot["url"] not in entrees:
                entrees[lot["url"]] = lot
                nouveaux += 1
        log.info("page %d : %d lots (%d nouveaux, %d au total)",
                 page_num, len(lots), nouveaux, len(entrees))

        if nouveaux == 0:
            log.info("plus de nouveau lot — fin de la pagination")
            break
        if max_lots and len(entrees) >= max_lots:
            break

        page_num += 1
        url = suivant or build_listing_url(chemin, statuts, page_num)

    rapport["lots_listes"] = len(entrees)

    # --- 2. fiches détaillées ---------------------------------------------
    faits: list[dict] = []
    contexte = {"categorie": categorie,
                "date_collecte": datetime.now().isoformat(timespec="seconds")}

    liste = list(entrees.values())
    if max_lots:
        liste = liste[:max_lots]

    for index, entree in enumerate(liste, start=1):
        brut = dict(entree)
        if avec_detail:
            html = fetcher.get(entree["url"])
            if html:
                try:
                    brut.update({k: v for k, v in
                                 parse_detail(html, entree["url"], selecteurs).items()
                                 if v not in (None, "", [])})
                    rapport["fiches_lues"] += 1
                except Exception as exc:
                    rapport["fiches_en_echec"] += 1
                    log.warning("fiche illisible %s (%s)", entree["url"], exc)
            else:
                rapport["fiches_en_echec"] += 1
        faits.append(normalize_lot(brut, contexte))
        if index % 25 == 0:
            log.info("fiches traitées : %d / %d", index, len(liste))

    rapport["termine_le"] = datetime.now().isoformat(timespec="seconds")
    rapport["nb_faits"] = len(faits)
    rapport["completude_moyenne"] = (
        round(sum(f["completude_pct"] for f in faits) / len(faits)) if faits else 0
    )
    return faits, rapport
