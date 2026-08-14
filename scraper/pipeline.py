"""Orchestration de la collecte : pagination de l'API, normalisation, rapport."""
from __future__ import annotations

import logging
from datetime import datetime

from . import config
from .api import DomaineClient
from .normalize import normalize_lot

log = logging.getLogger(__name__)


def collecter(categories: list[int] | None = None,
              statuts: list[str] | None = None,
              taille_page: int = config.PAGE_SIZE,
              max_pages: int = config.MAX_PAGES,
              max_lots: int | None = None,
              client: DomaineClient | None = None) -> tuple[list[dict], dict]:
    """Collecte les lots d'une ou plusieurs catégories.

    Retourne ``(faits, rapport)``. Les doublons entre catégories sont écartés
    sur l'identifiant de lot.
    """
    categories = categories or [config.DEFAULT_CATEGORIE]
    statuts = statuts or config.DEFAULT_LOT_STATUS
    client = client or DomaineClient()
    date_collecte = datetime.now().isoformat(timespec="seconds")

    rapport = {
        "demarre_le": date_collecte,
        "categories": {},
        "statuts": statuts,
        "taille_page": taille_page,
        "appels_api": 0,
        "lots_en_erreur": 0,
    }

    faits: list[dict] = []
    vus: set = set()

    for categorie_id in categories:
        libelle = config.CATEGORIES.get(categorie_id, str(categorie_id))
        log.info("catégorie %s (%s)", libelle, categorie_id)
        page, total_pages, total_annonce, collectes = 1, None, None, 0

        taille = taille_page
        while page <= max_pages:
            try:
                produits = client.page_de_lots(categorie_id, statuts, page, taille)
            except Exception as exc:
                # Certaines instances Magento plafonnent la taille de page :
                # on réduit progressivement plutôt que d'abandonner la collecte.
                if taille > 8:
                    taille = max(8, taille // 2)
                    log.warning("  appel refusé (%s) — nouvelle tentative avec "
                                "%d lots par page", exc, taille)
                    continue
                raise
            rapport["appels_api"] += 1

            items = produits.get("items") or []
            if total_annonce is None:
                total_annonce = produits.get("total_count")
                total_pages = (produits.get("page_info") or {}).get("total_pages")
                log.info("  %s lots annoncés, %s pages de %d",
                         total_annonce, total_pages, taille)

            if not items:
                break

            for item in items:
                identifiant = item.get("id") or item.get("uid")
                if identifiant in vus:
                    continue
                vus.add(identifiant)
                try:
                    faits.append(normalize_lot(item, categorie_id, date_collecte))
                    collectes += 1
                except Exception as exc:
                    rapport["lots_en_erreur"] += 1
                    log.warning("  lot %s illisible (%s)", identifiant, exc)

            log.info("  page %d/%s — %d lots cumulés (%d %%)", page, total_pages or "?",
                     len(faits),
                     round(100 * len(faits) / total_annonce) if total_annonce else 0)

            if max_lots and len(faits) >= max_lots:
                log.info("  plafond de %d lots atteint", max_lots)
                break
            if total_pages and page >= total_pages:
                break
            page += 1

        rapport["categories"][libelle] = {
            "id": categorie_id,
            "total_annonce": total_annonce,
            "collectes": collectes,
            "pages_lues": page,
            "taille_page_retenue": taille,
        }
        if total_annonce and collectes < total_annonce and not max_lots:
            log.warning("  %s : %d lots collectés sur %d annoncés",
                        libelle, collectes, total_annonce)
        if max_lots and len(faits) >= max_lots:
            break

    if max_lots:
        faits = faits[:max_lots]

    rapport["termine_le"] = datetime.now().isoformat(timespec="seconds")
    rapport["nb_lots"] = len(faits)
    rapport["completude_moyenne"] = (
        round(sum(f["completude_pct"] for f in faits) / len(faits)) if faits else 0)
    return faits, rapport
