"""Configuration centrale du scraper Enchères du Domaine.

Tout ce qui est susceptible de bouger côté site (URL, sélecteurs CSS, libellés
de caractéristiques) est isolé ici ou dans ``selectors.json`` afin de pouvoir
être corrigé sans toucher au code.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

BASE_URL = "https://encheres-domaine.gouv.fr"

# Page de catégorie visée par défaut (véhicules de tourisme, tous statuts utiles).
DEFAULT_CATEGORY_PATH = "/categorie-de-produit/vehicules/vehicules-de-tourisme.html"

# Codes de statut de lot utilisés par le site dans le paramètre `lot_status`.
# La liste par défaut reprend celle de l'URL fournie (doublons retirés).
DEFAULT_LOT_STATUS = [13, 14, 15, 1, 2, 3, 6, 8, 11, 19]

# Libellés connus des statuts. Un code inconnu est conservé tel quel.
LOT_STATUS_LABELS = {
    1: "À venir",
    2: "En cours",
    3: "En cours",
    6: "Clôture imminente",
    8: "Adjugé",
    11: "Terminé",
    13: "Publié",
    14: "Ouvert aux enchères",
    15: "Prolongé",
    19: "Retiré",
}

# Catégories véhicules exposées par le site (utilisable via --category).
CATEGORY_PATHS = {
    "vehicules-de-tourisme": "/categorie-de-produit/vehicules/vehicules-de-tourisme.html",
    "vehicules-utilitaires": "/categorie-de-produit/vehicules/vehicules-utilitaires.html",
    "poids-lourds": "/categorie-de-produit/vehicules/poids-lourds.html",
    "deux-roues": "/categorie-de-produit/vehicules/deux-roues.html",
    "engins": "/categorie-de-produit/vehicules/engins.html",
}

# --- Politesse / robustesse réseau ------------------------------------------
USER_AGENT = os.environ.get(
    "SCRAPER_UA",
    "Mozilla/5.0 (compatible; VeilleEncheresDomaine/1.0; +analyse-decisionnelle)",
)
REQUEST_TIMEOUT = 30          # secondes
REQUEST_DELAY = 1.2           # délai minimum entre deux requêtes (s)
MAX_RETRIES = 4               # nombre de tentatives (backoff exponentiel 2,4,8,16 s)
MAX_PAGES = 200               # garde-fou pagination
RESPECT_ROBOTS = True

# --- Chemins ----------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
PORTAL_DATA_DIR = ROOT / "portal" / "data"

SELECTORS_FILE = Path(__file__).resolve().parent / "selectors.json"


def load_selectors() -> dict:
    """Charge les sélecteurs CSS (fichier éditable sans toucher au code)."""
    with open(SELECTORS_FILE, "r", encoding="utf-8") as fh:
        return json.load(fh)
