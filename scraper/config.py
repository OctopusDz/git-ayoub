"""Configuration du collecteur Enchères du Domaine (API GraphQL Magento)."""
from __future__ import annotations

import base64
import os
from pathlib import Path

BASE_URL = "https://encheres-domaine.gouv.fr"
GRAPHQL_URL = f"{BASE_URL}/gateway/magento/graphql/"

# Le site envoie ses appels GraphQL en GET avec un en-tête `store`.
STORE = "default"

# Catégories : identifiant Magento -> libellé. L'API attend le `category_uid`,
# qui est simplement l'identifiant encodé en base64 (5 -> "NQ==").
CATEGORIES = {
    5: "Véhicules de tourisme",
    6: "Véhicules utilitaires",
    7: "Motos",
    8: "Scooters",
    9: "Camions",
    10: "Remorques",
    11: "Tracteurs routiers",
    12: "Ensembles routiers",
    13: "Véhicules de chantier",
    14: "Engins agricoles",
    15: "Transports en commun",
    16: "Bateaux et navigation",
    17: "Voiturettes",
    18: "Quads",
    19: "Caravaning",
    20: "Aéronefs",
}

CATEGORIE_PARENTE_VEHICULES = 4
DEFAULT_CATEGORIE = 5

# Statuts de lot repris de l'URL cible (tous les états utiles à l'analyse).
DEFAULT_LOT_STATUS = ["13", "14", "15", "1", "2", "3", "6", "8", "11", "19"]


def category_uid(categorie_id: int) -> str:
    """5 -> 'NQ==' (encodage attendu par l'API)."""
    return base64.b64encode(str(categorie_id).encode()).decode()


# --- Politesse réseau -------------------------------------------------------
USER_AGENT = os.environ.get(
    "SCRAPER_UA",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36",
)
REQUEST_TIMEOUT = 45
REQUEST_DELAY = 0.7        # délai minimum entre deux appels (s)
MAX_RETRIES = 4            # back-off exponentiel 2, 4, 8, 16 s
PAGE_SIZE = 100            # lots par appel (le site utilise 8, l'API accepte plus)
MAX_PAGES = 2000           # garde-fou

# --- Chemins ----------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
PORTAL_DATA_DIR = ROOT / "portal" / "data"
