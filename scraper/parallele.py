"""Collecte parallèle.

Le coût dominant n'est pas le débit mais le contrôle anti-robot, qui se
franchit session par session. Plutôt que d'insister sur une seule session, on
en ouvre plusieurs de front : chaque fil a son propre bocal à cookies et
travaille sur ses propres pages. Une session qui se fait refouler ne bloque
plus les autres, et le temps total s'effondre.

Comme pour la collecte séquentielle, chaque page obtenue est écrite dans le
cache : relancer ne redemande que ce qui manque.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from . import config
from . import transport as transport_http
from .api import QUERY_LOTS
from .normalize import normalize_lot
from .pipeline import _fichier_page, _lire_cache

log = logging.getLogger(__name__)

_local = threading.local()


def _entetes() -> dict:
    return {
        "User-Agent": config.USER_AGENT,
        "Accept": "*/*",
        "Accept-Language": "fr-FR,fr;q=0.9",
        "Content-Type": "application/json",
        "store": config.STORE,
        "x-magento-cache-id": config.MAGENTO_CACHE_ID,
        "Referer": config.PAGE_CATEGORIE,
    }


def _session(renouveler: bool = False):
    """Session propre au fil courant, amorcée à la première utilisation."""
    transport = getattr(_local, "transport", None)
    if transport is not None and not renouveler:
        return transport
    if transport is not None:
        transport.fermer()
    transport = transport_http.creer(_entetes())
    transport_http.amorcer_session(transport)
    _local.transport = transport
    return transport


def _url(categorie_id: int, statuts: list[str], page: int, taille: int) -> str:
    variables = {
        "currentPage": page,
        "pageSize": taille,
        "sort": {"start_auction_lot_at": "ASC"},
        "filter": {
            "category_uid": {"eq": config.category_uid(categorie_id)},
            "lot_status": {"in": list(statuts)},
        },
    }
    return config.GRAPHQL_URL + "?" + urllib.parse.urlencode({
        "query": QUERY_LOTS,
        "operationName": "getCategoryLots",
        "variables": json.dumps(variables, separators=(",", ":"), ensure_ascii=False),
    })


def _recuperer_page(categorie_id: int, statuts: list[str], page: int,
                    taille: int, cache: Path, essais: int,
                    forcer: bool = False) -> tuple[int, list | None, dict]:
    """Récupère une page. Retourne (numéro, items, page_info).

    ``forcer`` court-circuite le cache : utile pour la sonde de démarrage, qui
    a besoin du nombre total de pages — une information que le cache ne
    conserve pas.
    """
    chemin = _fichier_page(cache, categorie_id, taille, page)
    if chemin.exists() and not forcer:
        items = _lire_cache(chemin)
        if items is not None:
            return page, items, {}

    for essai in range(essais):
        transport = _session(renouveler=essai > 0)
        try:
            corps = transport_http.resoudre_challenge(
                transport, _url(categorie_id, statuts, page, taille))
            charge = json.loads(corps.decode("utf-8"))
            produits = (charge.get("data") or {}).get("products") or {}
            items = produits.get("items")
            if items is None:
                raise ValueError("réponse sans lots")
            chemin.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
            return page, items, {
                "total_count": produits.get("total_count"),
                "total_pages": (produits.get("page_info") or {}).get("total_pages"),
            }
        except Exception:
            if essai < essais - 1:
                time.sleep(0.5 * (essai + 1))
    return page, None, {}


def collecter_parallele(categories: list[int] | None = None,
                        statuts: list[str] | None = None,
                        taille_page: int = 8,
                        fils: int = 12,
                        essais: int = 3,
                        max_pages: int | None = None,
                        cache: Path | None = None) -> tuple[list[dict], dict]:
    """Collecte plusieurs pages de front. Retourne ``(faits, rapport)``."""
    categories = categories or [config.DEFAULT_CATEGORIE]
    statuts = statuts or config.DEFAULT_LOT_STATUS
    cache = Path(cache) if cache else config.DATA_DIR / "pages"
    cache.mkdir(parents=True, exist_ok=True)
    date_collecte = datetime.now().isoformat(timespec="seconds")

    rapport = {
        "demarre_le": date_collecte,
        "mode": f"parallèle ({fils} fils)",
        "taille_page": taille_page,
        "categories": {},
        "appels_api": 0,
        "pages_depuis_cache": 0,
        "pages_en_echec": [],
        "lots_en_erreur": 0,
    }

    faits: list[dict] = []
    vus: set = set()

    for categorie_id in categories:
        libelle = config.CATEGORIES.get(categorie_id, str(categorie_id))

        # Le nombre de pages vient du serveur : on interroge des pages
        # successives jusqu'à en obtenir une fraîche, le contrôle anti-robot
        # pouvant refuser les premières et le cache ne portant pas ce total.
        total_pages = total_annonce = None
        for sonde in range(1, 9):
            _, _, info = _recuperer_page(categorie_id, statuts, sonde,
                                         taille_page, cache, essais,
                                         forcer=True)
            if info.get("total_pages"):
                total_pages = info["total_pages"]
                total_annonce = info.get("total_count")
                break

        if not total_pages:
            if not max_pages:
                log.error("%s : impossible de connaître le nombre de pages — "
                          "précisez --max-pages pour lancer quand même", libelle)
                continue
            total_pages = max_pages
            log.warning("%s : nombre de pages inconnu, on s'en tient à %d",
                        libelle, total_pages)
        if max_pages:
            total_pages = min(total_pages, max_pages)

        log.info("%s : %s lots, %d pages de %d, %d fils",
                 libelle, total_annonce, total_pages, taille_page, fils)

        pages = list(range(1, total_pages + 1))
        resultats: dict[int, list] = {}
        echecs: list[int] = []
        debut = time.time()

        with ThreadPoolExecutor(max_workers=fils) as pool:
            travaux = {
                pool.submit(_recuperer_page, categorie_id, statuts, page,
                            taille_page, cache, essais): page
                for page in pages
            }
            faits_recus = 0
            for termine in as_completed(travaux):
                page, items, _ = termine.result()
                rapport["appels_api"] += 1
                if items is None:
                    echecs.append(page)
                    continue
                resultats[page] = items
                faits_recus += 1
                if faits_recus % 25 == 0:
                    ecoule = time.time() - debut
                    log.info("  %d/%d pages en %.0f s (%.1f pages/s)",
                             faits_recus, total_pages, ecoule, faits_recus / max(ecoule, 1))

        duree = time.time() - debut
        log.info("  %d pages obtenues, %d en échec, en %.0f s",
                 len(resultats), len(echecs), duree)

        avant = len(faits)
        for page in sorted(resultats):
            for item in resultats[page]:
                identifiant = item.get("id") or item.get("uid")
                if identifiant in vus:
                    continue
                vus.add(identifiant)
                try:
                    faits.append(normalize_lot(item, categorie_id, date_collecte))
                except Exception as exc:
                    rapport["lots_en_erreur"] += 1
                    log.warning("  lot %s illisible (%s)", identifiant, exc)

        rapport["categories"][libelle] = {
            "id": categorie_id,
            "total_annonce": total_annonce,
            "collectes": len(faits) - avant,
            "pages_lues": len(resultats),
            "duree_secondes": round(duree),
        }
        rapport["pages_en_echec"].extend(echecs)

    rapport["termine_le"] = datetime.now().isoformat(timespec="seconds")
    rapport["nb_lots"] = len(faits)
    rapport["completude_moyenne"] = (
        round(sum(f["completude_pct"] for f in faits) / len(faits)) if faits else 0)
    return faits, rapport
