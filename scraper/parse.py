"""Extraction des lots depuis le HTML.

Trois stratégies successives, de la plus fiable à la plus tolérante :

1. **données structurées** — JSON-LD (``application/ld+json``) et JSON embarqué
   dans une balise ``<script>`` (``__NUXT__``, ``__NEXT_DATA__``, ``window.*``) ;
2. **sélecteurs CSS** déclarés dans ``selectors.json`` ;
3. **heuristiques** — repérage des liens ``/lot/`` ou ``/hermes/`` et lecture des
   paires libellé/valeur (``dl``, ``table``, ``li``) sur la fiche détaillée.

Aucune stratégie n'est bloquante : ce qui est trouvé est conservé, le reste
reste vide et sera signalé dans le rapport de qualité.
"""
from __future__ import annotations

import json
import logging
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from . import config

log = logging.getLogger(__name__)

LOT_URL_RE = re.compile(r"/(lot|hermes)/", re.I)
MONEY_RE = re.compile(r"(\d[\d\s .,]*)\s*(?:€|eur)", re.I)
NUMBER_RE = re.compile(r"\d[\d\s .,]*")
KM_RE = re.compile(r"(\d[\d\s .,]*)\s*(?:km|kilom)", re.I)
YEAR_RE = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")
DATE_RE = re.compile(r"(\d{1,2})[/\-. ](\d{1,2}|[a-zéûôA-Z]+)[/\-. ](\d{2,4})")

MOIS = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "août": 8, "aout": 8, "septembre": 9,
    "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}


# --------------------------------------------------------------------------
# Utilitaires
# --------------------------------------------------------------------------
def soup(html: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


def text(node) -> str:
    if node is None:
        return ""
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()


def first(node, selectors: list[str]):
    """Premier élément correspondant à l'un des sélecteurs proposés."""
    for sel in selectors:
        try:
            found = node.select_one(sel)
        except Exception:
            continue
        if found is not None:
            return found
    return None


def to_number(value: str | None) -> float | None:
    """`12 345,67 €` -> 12345.67 (gère espaces insécables, points milliers)."""
    if not value:
        return None
    match = NUMBER_RE.search(str(value))
    if not match:
        return None
    raw = match.group(0)
    raw = raw.replace(" ", "").replace(" ", "")
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        raw = raw.replace(",", ".")
    elif raw.count(".") == 1 and len(raw.split(".")[-1]) == 3:
        raw = raw.replace(".", "")   # 12.345 = milliers
    else:
        raw = raw.replace(".", "")
    try:
        return float(raw)
    except ValueError:
        return None


def to_money(value: str | None) -> float | None:
    if not value:
        return None
    match = MONEY_RE.search(value)
    return to_number(match.group(1) if match else value)


def to_date(value: str | None) -> str | None:
    """Retourne une date ISO ``AAAA-MM-JJ`` à partir des formats du site."""
    if not value:
        return None
    value = value.strip()
    iso = re.search(r"(\d{4})-(\d{2})-(\d{2})", value)
    if iso:
        return iso.group(0)
    match = DATE_RE.search(value)
    if not match:
        return None
    day, month, year = match.groups()
    if not month.isdigit():
        month = MOIS.get(month.lower().strip(), 0)
        if not month:
            return None
    month, day, year = int(month), int(day), int(year)
    if year < 100:
        year += 2000
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def normalize_label(label: str) -> str:
    label = label.lower().strip().rstrip(":").strip()
    return re.sub(r"\s+", " ", label)


# --------------------------------------------------------------------------
# Stratégie 1 — données structurées
# --------------------------------------------------------------------------
def extract_structured(page: BeautifulSoup) -> list[dict]:
    """JSON-LD et JSON embarqué. Renvoie une liste de dicts bruts."""
    found: list[dict] = []

    for script in page.find_all("script", type="application/ld+json"):
        try:
            payload = json.loads(script.string or "{}")
        except Exception:
            continue
        for item in _iter_products(payload):
            found.append(item)

    for script in page.find_all("script"):
        raw = script.string or ""
        if not raw or len(raw) > 2_000_000:
            continue
        if not re.search(r"__NUXT__|__NEXT_DATA__|window\.\w+\s*=\s*[{\[]", raw):
            continue
        for blob in re.findall(r"(\{.*\}|\[.*\])", raw, re.S)[:3]:
            try:
                payload = json.loads(blob)
            except Exception:
                continue
            for item in _iter_products(payload):
                found.append(item)
    return found


def _iter_products(payload, depth: int = 0):
    """Parcourt un JSON à la recherche d'objets ressemblant à un lot."""
    if depth > 8:
        return
    if isinstance(payload, list):
        for item in payload:
            yield from _iter_products(item, depth + 1)
        return
    if not isinstance(payload, dict):
        return

    keys = {k.lower() for k in payload.keys()}
    is_product = payload.get("@type") in ("Product", "Vehicle", "Car", "Offer")
    looks_like_lot = {"name", "price"} <= keys or {"titre", "prix"} <= keys \
        or ("lot" in keys and "prix" in keys)
    if is_product or looks_like_lot:
        yield payload
    for value in payload.values():
        yield from _iter_products(value, depth + 1)


# --------------------------------------------------------------------------
# Stratégie 2 + 3 — page de liste
# --------------------------------------------------------------------------
def parse_listing(html: str, page_url: str, selectors: dict) -> tuple[list[dict], str | None]:
    """Extrait les lots d'une page de résultats et l'URL de la page suivante."""
    page = soup(html)
    sel = selectors["liste"]
    lots: list[dict] = []
    seen: set[str] = set()

    cards = []
    for candidate in sel["carte_lot"]:
        try:
            cards = page.select(candidate)
        except Exception:
            continue
        if len(cards) >= 3:      # une vraie grille de résultats
            log.debug("cartes trouvées via %s (%d)", candidate, len(cards))
            break
        cards = []

    if cards:
        for card in cards:
            lot = _parse_card(card, page_url, sel)
            if lot and lot["url"] not in seen:
                seen.add(lot["url"])
                lots.append(lot)
    else:
        # Repli heuristique : tous les liens vers une fiche de lot.
        log.debug("aucune carte reconnue — repli sur les liens /lot/ et /hermes/")
        for link in page.find_all("a", href=True):
            href = link["href"]
            if not LOT_URL_RE.search(href):
                continue
            url = urljoin(page_url, href)
            if url in seen:
                continue
            seen.add(url)
            lots.append({
                "url": url,
                "titre": text(link) or None,
                "prix_liste": to_money(text(link.parent)),
                "image": None,
                "statut_liste": None,
                "lieu_liste": None,
                "date_fin_liste": None,
            })

    # JSON-LD en complément (prix/titres parfois absents du HTML rendu).
    for item in extract_structured(page):
        url = item.get("url") or item.get("@id")
        if not url:
            continue
        url = urljoin(page_url, str(url))
        if url in seen:
            continue
        seen.add(url)
        offer = item.get("offers") or {}
        if isinstance(offer, list):
            offer = offer[0] if offer else {}
        lots.append({
            "url": url,
            "titre": item.get("name") or item.get("titre"),
            "prix_liste": to_number(str(offer.get("price") or item.get("price") or "")),
            "image": item.get("image") if isinstance(item.get("image"), str) else None,
            "statut_liste": None,
            "lieu_liste": None,
            "date_fin_liste": None,
        })

    return lots, _next_page(page, page_url, sel)


def _parse_card(card, page_url: str, sel: dict) -> dict | None:
    link = first(card, sel["lien_lot"])
    if link is None or not link.get("href"):
        return None
    url = urljoin(page_url, link["href"])
    if not LOT_URL_RE.search(urlparse(url).path):
        return None

    image = first(card, sel["image"])
    return {
        "url": url,
        "titre": text(first(card, sel["titre"])) or text(link) or None,
        "prix_liste": to_money(text(first(card, sel["prix"]))),
        "mise_a_prix_liste": to_money(text(first(card, sel["mise_a_prix"]))),
        "statut_liste": text(first(card, sel["statut"])) or None,
        "lieu_liste": text(first(card, sel["lieu"])) or None,
        "date_fin_liste": to_date(text(first(card, sel["date_fin"]))) or None,
        "image": urljoin(page_url, image["src"]) if image and image.get("src") else None,
    }


def _next_page(page: BeautifulSoup, page_url: str, sel: dict) -> str | None:
    link = first(page, sel["pagination_suivant"])
    if link is not None and link.get("href"):
        return urljoin(page_url, link["href"])
    return None


def total_pages(html: str, selectors: dict) -> int | None:
    """Déduit le nombre total de pages à partir du bloc de pagination."""
    page = soup(html)
    block = first(page, selectors["liste"]["pagination_total"])
    if block is None:
        return None
    numbers = [int(n) for n in re.findall(r"\b(\d{1,4})\b", text(block))]
    return max(numbers) if numbers else None


# --------------------------------------------------------------------------
# Fiche détaillée
# --------------------------------------------------------------------------
def parse_detail(html: str, url: str, selectors: dict) -> dict:
    """Extrait toutes les caractéristiques d'une fiche de lot."""
    page = soup(html)
    sel = selectors["detail"]
    labels = selectors["libelles_caracteristiques"]

    lot: dict = {"url": url}
    lot["titre"] = text(first(page, sel["titre"])) or None
    lot["description"] = text(first(page, sel["description"])) or None
    lot["prix_courant"] = to_money(text(first(page, sel["prix_courant"])))
    lot["mise_a_prix"] = to_money(text(first(page, sel["mise_a_prix"])))
    lot["nb_encheres"] = to_number(text(first(page, sel["nb_encheres"])))
    lot["date_debut"] = to_date(text(first(page, sel["date_debut"])))
    lot["date_fin"] = to_date(text(first(page, sel["date_fin"])))
    lot["lieu"] = text(first(page, sel["lieu"])) or None
    lot["statut"] = text(first(page, sel["statut"])) or None

    images = []
    for sel_img in sel["images"]:
        for img in page.select(sel_img):
            src = img.get("src") or img.get("data-src")
            if src:
                images.append(urljoin(url, src))
        if images:
            break
    lot["images"] = images[:8]

    # Paires libellé / valeur, quelle que soit leur mise en forme.
    pairs = _extract_pairs(page)
    lot["caracteristiques_brutes"] = pairs
    for champ, alias in labels.items():
        value = _match_pair(pairs, alias)
        if value is not None and lot.get(champ) in (None, "", []):
            lot[champ] = value

    # Complément par données structurées.
    for item in extract_structured(page):
        if item.get("name") and not lot.get("titre"):
            lot["titre"] = item["name"]
        offer = item.get("offers") or {}
        if isinstance(offer, list):
            offer = offer[0] if offer else {}
        if offer.get("price") and lot.get("prix_courant") is None:
            lot["prix_courant"] = to_number(str(offer["price"]))
        for key_json, key_lot in (("brand", "marque"), ("model", "modele"),
                                  ("mileageFromOdometer", "kilometrage"),
                                  ("fuelType", "carburant"),
                                  ("vehicleTransmission", "boite_vitesses"),
                                  ("productionDate", "annee"),
                                  ("vehicleIdentificationNumber", "vin")):
            val = item.get(key_json)
            if isinstance(val, dict):
                val = val.get("name") or val.get("value")
            if val and not lot.get(key_lot):
                lot[key_lot] = str(val)

    # Derniers recours : le texte libre du titre et de la description.
    blob = " ".join(filter(None, [lot.get("titre"), lot.get("description")]))
    if blob:
        if lot.get("kilometrage") is None:
            km = KM_RE.search(blob)
            if km:
                lot["kilometrage"] = km.group(1)
        if lot.get("annee") is None:
            year = YEAR_RE.search(blob)
            if year:
                lot["annee"] = year.group(1)

    lot["id_lot"] = _lot_id(url)
    return lot


def _extract_pairs(page: BeautifulSoup) -> dict:
    """Récupère les couples libellé -> valeur (dl/dt/dd, table, li 'X : Y')."""
    pairs: dict[str, str] = {}

    for dl in page.find_all("dl"):
        terms, defs = dl.find_all("dt"), dl.find_all("dd")
        for term, definition in zip(terms, defs):
            key, value = normalize_label(text(term)), text(definition)
            if key and value:
                pairs.setdefault(key, value)

    for row in page.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) == 2:
            key, value = normalize_label(text(cells[0])), text(cells[1])
            if key and value:
                pairs.setdefault(key, value)

    for item in page.find_all(["li", "p", "div", "span"]):
        if item.find(["li", "p", "div", "table"]):
            continue                       # on ne lit que les feuilles
        raw = text(item)
        if not raw or len(raw) > 200 or ":" not in raw:
            continue
        key, _, value = raw.partition(":")
        key, value = normalize_label(key), value.strip()
        if key and value and len(key) < 60:
            pairs.setdefault(key, value)

    return pairs


def _match_pair(pairs: dict, alias: list[str]) -> str | None:
    for name in alias:
        name = normalize_label(name)
        if name in pairs:
            return pairs[name]
    for name in alias:                     # correspondance partielle
        name = normalize_label(name)
        for key, value in pairs.items():
            if name in key:
                return value
    return None


def _lot_id(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    match = re.search(r"(\d{4,})", path)
    return match.group(1) if match else path.rsplit("/", 1)[-1].replace(".html", "")


def build_listing_url(category_path: str, statuses: list[int], page_num: int) -> str:
    status = "%2C".join(str(s) for s in statuses)
    return f"{config.BASE_URL}{category_path}?lot_status={status}&page={page_num}"
