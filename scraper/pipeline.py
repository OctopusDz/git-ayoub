"""Orchestration de la collecte.

Le site protège son API par un contrôle anti-robot qui ne cède pas à tous les
coups : une page peut demander plusieurs tentatives, et un rythme trop soutenu
le fait se réarmer. La collecte est donc conçue pour être *patiente et
reprenable* plutôt que rapide :

* chaque page obtenue est écrite dans un cache disque ;
* relancer la collecte repart de ce cache — rien n'est redemandé deux fois ;
* les pages en échec sont mises de côté et reprises en fin de parcours ;
* la session est renouvelée régulièrement, ce qui remet le contrôle à zéro.
"""
from __future__ import annotations

import json
import logging
import random
import time
from datetime import datetime
from pathlib import Path

from . import config
from .api import DomaineClient
from .normalize import normalize_lot

log = logging.getLogger(__name__)


def _fichier_page(cache: Path, categorie_id: int, taille: int, page: int) -> Path:
    return cache / f"cat{categorie_id}_t{taille}_p{page:04d}.json"


def _lire_cache(chemin: Path) -> list | None:
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except Exception:
        return None


def collecter(categories: list[int] | None = None,
              statuts: list[str] | None = None,
              taille_page: int = config.PAGE_SIZE,
              max_pages: int = config.MAX_PAGES,
              max_lots: int | None = None,
              client: DomaineClient | None = None,
              cache: Path | None = None,
              pages_par_session: int = 15,
              pause_entre_pages: float = 0.0) -> tuple[list[dict], dict]:
    """Collecte les lots d'une ou plusieurs catégories.

    Retourne ``(faits, rapport)``. Les doublons entre catégories sont écartés
    sur l'identifiant de lot.
    """
    categories = categories or [config.DEFAULT_CATEGORIE]
    statuts = statuts or config.DEFAULT_LOT_STATUS
    client = client or DomaineClient()
    cache = Path(cache) if cache else config.DATA_DIR / "pages"
    cache.mkdir(parents=True, exist_ok=True)
    date_collecte = datetime.now().isoformat(timespec="seconds")

    rapport = {
        "demarre_le": date_collecte,
        "categories": {},
        "statuts": statuts,
        "taille_page": taille_page,
        "appels_api": 0,
        "pages_depuis_cache": 0,
        "pages_en_echec": [],
        "lots_en_erreur": 0,
    }

    faits: list[dict] = []
    vus: set = set()

    def enregistrer(items: list, categorie_id: int) -> int:
        ajoutes = 0
        for item in items:
            identifiant = item.get("id") or item.get("uid")
            if identifiant in vus:
                continue
            vus.add(identifiant)
            try:
                faits.append(normalize_lot(item, categorie_id, date_collecte))
                ajoutes += 1
            except Exception as exc:
                rapport["lots_en_erreur"] += 1
                log.warning("  lot %s illisible (%s)", identifiant, exc)
        return ajoutes

    for categorie_id in categories:
        libelle = config.CATEGORIES.get(categorie_id, str(categorie_id))
        log.info("catégorie %s (%s)", libelle, categorie_id)

        total_annonce = total_pages = None
        depuis_renouvellement = 0
        a_reprendre: list[int] = []
        page = 1

        while page <= max_pages:
            chemin = _fichier_page(cache, categorie_id, taille_page, page)
            items = _lire_cache(chemin) if chemin.exists() else None

            if items is not None:
                rapport["pages_depuis_cache"] += 1
            else:
                # Renouveler la session remet le contrôle anti-robot à zéro.
                if depuis_renouvellement >= pages_par_session:
                    log.info("  renouvellement de session")
                    client.reamorcer()
                    depuis_renouvellement = 0

                try:
                    produits = client.page_de_lots(categorie_id, statuts, page, taille_page)
                    rapport["appels_api"] += 1
                    depuis_renouvellement += 1
                    items = produits.get("items") or []
                    chemin.write_text(json.dumps(items, ensure_ascii=False),
                                      encoding="utf-8")
                    if total_annonce is None:
                        total_annonce = produits.get("total_count")
                        total_pages = (produits.get("page_info") or {}).get("total_pages")
                        log.info("  %s lots annoncés, %s pages de %d",
                                 total_annonce, total_pages, taille_page)
                except Exception as exc:
                    log.warning("  page %d en échec (%s) — reprise plus tard", page, exc)
                    rapport["pages_en_echec"].append(page)
                    a_reprendre.append(page)
                    client.reamorcer()
                    depuis_renouvellement = 0
                    page += 1
                    continue

            ajoutes = enregistrer(items, categorie_id)
            log.info("  page %d/%s — %d lots cumulés%s", page, total_pages or "?",
                     len(faits), "" if ajoutes else "  (aucun nouveau lot)")

            if not items:
                break
            if max_lots and len(faits) >= max_lots:
                log.info("  plafond de %d lots atteint", max_lots)
                break
            if total_pages and page >= total_pages:
                break

            page += 1
            if pause_entre_pages:
                time.sleep(pause_entre_pages + random.uniform(0, 0.6))

        # --- second passage sur les pages manquées ---
        if a_reprendre and not max_lots:
            log.info("  reprise de %d page(s) en échec", len(a_reprendre))
            restantes = []
            for numero in a_reprendre:
                client.reamorcer()
                try:
                    produits = client.page_de_lots(categorie_id, statuts,
                                                   numero, taille_page)
                    rapport["appels_api"] += 1
                    items = produits.get("items") or []
                    _fichier_page(cache, categorie_id, taille_page, numero).write_text(
                        json.dumps(items, ensure_ascii=False), encoding="utf-8")
                    enregistrer(items, categorie_id)
                    log.info("  page %d rattrapée — %d lots cumulés", numero, len(faits))
                except Exception as exc:
                    log.warning("  page %d toujours en échec (%s)", numero, exc)
                    restantes.append(numero)
                if pause_entre_pages:
                    time.sleep(pause_entre_pages)
            rapport["pages_en_echec"] = restantes

        rapport["categories"][libelle] = {
            "id": categorie_id,
            "total_annonce": total_annonce,
            "collectes": len(faits),
            "pages_lues": page,
        }
        if total_annonce and len(faits) < total_annonce and not max_lots:
            log.warning("  %s : %d lots sur %d annoncés — relancez la commande "
                        "pour compléter (le cache évite de tout refaire)",
                        libelle, len(faits), total_annonce)
        if max_lots and len(faits) >= max_lots:
            break

    if max_lots:
        faits = faits[:max_lots]

    rapport["termine_le"] = datetime.now().isoformat(timespec="seconds")
    rapport["nb_lots"] = len(faits)
    rapport["completude_moyenne"] = (
        round(sum(f["completude_pct"] for f in faits) / len(faits)) if faits else 0)
    return faits, rapport
