"""Client de l'API GraphQL du site Enchères du Domaine.

Le site expose ses données via Magento GraphQL. On rejoue exactement la requête
``getCategoryLots`` du site : même document, mêmes champs — c'est la façon la
plus stable d'interroger l'API, puisque toute évolution du schéma casserait
d'abord leur propre front.

Aucune dépendance externe : la bibliothèque standard suffit, le collecteur se
lance donc sans rien installer.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse

from . import config
from . import transport as transport_http

log = logging.getLogger(__name__)

# Requête du site, reprise à l'identique (relevé réseau du 14/08).
QUERY_LOTS = (
    "query getCategoryLots($currentPage:Int$filter:ProductAttributeFilterInput!"
    "$pageSize:Int$sort:ProductAttributeSortInput){products(currentPage:$currentPage "
    "filter:$filter pageSize:$pageSize sort:$sort){...ProductsFragment __typename}}"
    "fragment ProductsFragment on Products{items{__typename auction auction_auto_status "
    "auction_type bid_winner_amount description{html __typename}dropoff_location_id "
    "dropoff_location{city postcode __typename}end_auction_lot_at end_date has_lost "
    "has_won id last_bid lot_number location lot_status lot_status_label luxury "
    "luxury_label name offers_submission_deadline price_auction professional_only "
    "reserve_price sku sales_inspector_data{cav_name __typename}short_description{html "
    "__typename}small_image{url __typename}start_auction_lot_at start_date uid url_key}"
    "page_info{total_pages __typename}total_count __typename}"
)

QUERY_CATEGORIES = (
    'query getCategories{categoryList(filters:{ids:{in:["4"]}}){uid name url_path '
    "children{uid name url_path __typename}__typename}}"
)

QUERY_CAV = "query getCavList{getCavList{dnid_cav_id cav_name cav_status __typename}}"


class ApiError(RuntimeError):
    """Erreur renvoyée par l'API GraphQL (message métier, pas réseau)."""


class DomaineClient:
    """Client HTTP de l'API, poli et tolérant aux pannes passagères."""

    def __init__(self, delay: float = config.REQUEST_DELAY,
                 transport: str = "auto"):
        self.delay = delay
        self._last_call = 0.0
        self.entetes = {
            "User-Agent": config.USER_AGENT,
            "Accept": "*/*",
            "Accept-Language": "fr-FR,fr;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Content-Type": "application/json",
            "store": config.STORE,
            "x-magento-cache-id": config.MAGENTO_CACHE_ID,
            "Referer": config.PAGE_CATEGORIE,
        }
        self.transport = transport_http.creer(self.entetes, transport)
        self._amorce_faite = False

    # -- session ------------------------------------------------------------
    def amorcer(self) -> None:
        """Visite la page d'accueil pour obtenir PHPSESSID et le cookie
        anti-robot, sans lesquels l'API répond parfois en erreur."""
        if self._amorce_faite:
            return
        self._amorce_faite = True
        try:
            self.transport.get(config.BASE_URL)
        except Exception as exc:
            log.warning("amorçage de session impossible (%s) — on tente sans", exc)

    # -- appel générique ----------------------------------------------------
    def graphql(self, query: str, variables: dict | None = None,
                operation: str | None = None) -> dict:
        """Exécute une requête GraphQL en GET (comme le site) et renvoie ``data``."""
        self.amorcer()
        parametres = {
            "query": query,
            "variables": json.dumps(variables or {}, separators=(",", ":"),
                                    ensure_ascii=False),
        }
        if operation:
            parametres["operationName"] = operation
        url = f"{config.GRAPHQL_URL}?{urllib.parse.urlencode(parametres)}"

        delai = 2.0
        for tentative in range(1, config.MAX_RETRIES + 1):
            ecoule = time.time() - self._last_call
            if ecoule < self.delay:
                time.sleep(self.delay - ecoule)
            try:
                brut = transport_http.resoudre_challenge(self.transport, url)
                self._last_call = time.time()
                charge = json.loads(brut.decode("utf-8"))
                if charge.get("errors"):
                    raise ApiError("; ".join(e.get("message", "?")
                                             for e in charge["errors"]))
                return charge.get("data") or {}
            except ApiError:
                raise                       # erreur de schéma : inutile d'insister
            except urllib.error.HTTPError as exc:
                self._last_call = time.time()
                if exc.code in (403, 407):
                    raise RuntimeError(
                        f"accès refusé ({exc.code}) — le domaine "
                        f"{urllib.parse.urlparse(config.BASE_URL).netloc} est bloqué "
                        "par la politique réseau de cet environnement") from exc
                if exc.code < 500 and exc.code != 429:
                    raise
                if tentative == config.MAX_RETRIES:
                    raise
                log.warning("HTTP %s — nouvelle tentative dans %.0f s", exc.code, delai)
                time.sleep(delai)
                delai *= 2
            except json.JSONDecodeError:
                # Contrôle anti-robot non franchi : on repart d'une session
                # neuve, ce qui suffit dans la grande majorité des cas.
                self._last_call = time.time()
                if tentative == config.MAX_RETRIES:
                    raise RuntimeError(
                        "le contrôle anti-robot du site n'a pas pu être franchi")
                log.warning("contrôle anti-robot non franchi — nouvelle session "
                            "dans %.0f s", delai)
                time.sleep(delai)
                self.reamorcer()
                delai *= 2
            except Exception as exc:
                self._last_call = time.time()
                if tentative == config.MAX_RETRIES:
                    raise
                log.warning("appel en échec (%s) — nouvelle tentative dans %.0f s",
                            exc, delai)
                time.sleep(delai)
                delai *= 2
        return {}

    def reamorcer(self) -> None:
        """Repart d'une session vierge (nouveaux cookies)."""
        self.transport.fermer()
        self.transport = transport_http.creer(self.entetes)
        self._amorce_faite = False
        self.amorcer()

    # -- requêtes métier ----------------------------------------------------
    def page_de_lots(self, categorie_id: int, statuts: list[str],
                     page: int, taille: int) -> dict:
        variables = {
            "currentPage": page,
            "pageSize": taille,
            "sort": {"start_auction_lot_at": "ASC"},
            "filter": {
                "category_uid": {"eq": config.category_uid(categorie_id)},
                "lot_status": {"in": list(statuts)},
            },
        }
        data = self.graphql(QUERY_LOTS, variables, "getCategoryLots")
        return data.get("products") or {}

    def categories_vehicules(self) -> dict[int, str]:
        """Arbre des sous-catégories véhicules, tel que publié par le site."""
        import base64
        data = self.graphql(QUERY_CATEGORIES, {}, "getCategories")
        resultat: dict[int, str] = {}
        for racine in data.get("categoryList") or []:
            for enfant in racine.get("children") or []:
                try:
                    identifiant = int(base64.b64decode(enfant["uid"]).decode())
                except Exception:
                    continue
                resultat[identifiant] = enfant.get("name")
        return resultat

    def liste_cav(self) -> list[dict]:
        """Centres de vente (services vendeurs)."""
        data = self.graphql(QUERY_CAV, {}, "getCavList")
        return data.get("getCavList") or []
