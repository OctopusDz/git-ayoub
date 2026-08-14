"""Écriture des résultats : JSON, CSV, SQLite."""
from __future__ import annotations

import csv
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from .normalize import CHAMPS_EXPORT

log = logging.getLogger(__name__)


def _plat(valeur):
    """Aplatit les valeurs non scalaires pour CSV/SQLite."""
    if isinstance(valeur, (list, tuple)):
        return " | ".join(str(v) for v in valeur)
    if isinstance(valeur, bool):
        return int(valeur)
    return valeur


def to_json(lots: list[dict], path: Path, meta: dict | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "genere_le": datetime.now().isoformat(timespec="seconds"),
            "nb_lots": len(lots),
            **(meta or {}),
        },
        "lots": lots,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    log.info("écrit %s (%d lots)", path, len(lots))
    return path


def to_csv(lots: list[dict], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CHAMPS_EXPORT, delimiter=";",
                                extrasaction="ignore")
        writer.writeheader()
        for lot in lots:
            writer.writerow({c: _plat(lot.get(c)) for c in CHAMPS_EXPORT})
    log.info("écrit %s", path)
    return path


def to_sqlite(lots: list[dict], path: Path) -> Path:
    """Base SQLite requêtable en SQL (Excel, Power BI, Metabase, DBeaver…)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    colonnes = ", ".join(f'"{c}"' for c in CHAMPS_EXPORT)
    cur.execute(f"CREATE TABLE lots ({colonnes})")
    cur.executemany(
        f"INSERT INTO lots ({colonnes}) VALUES ({','.join('?' * len(CHAMPS_EXPORT))})",
        [[_plat(lot.get(c)) for c in CHAMPS_EXPORT] for lot in lots],
    )
    for index in ("marque", "region", "mois_vente", "statut", "tranche_prix"):
        cur.execute(f'CREATE INDEX idx_{index} ON lots("{index}")')

    # Vues d'analyse prêtes à l'emploi.
    cur.execute("""
        CREATE VIEW v_marque AS
        SELECT marque,
               COUNT(*)                            AS nb_lots,
               ROUND(AVG(prix))                    AS prix_moyen,
               ROUND(AVG(mise_a_prix))             AS mise_a_prix_moyenne,
               ROUND(AVG(multiple_mise_a_prix), 2) AS multiple_moyen,
               ROUND(AVG(kilometrage))             AS km_moyen,
               ROUND(AVG(age), 1)                  AS age_moyen
        FROM lots WHERE marque IS NOT NULL
        GROUP BY marque ORDER BY nb_lots DESC
    """)
    cur.execute("""
        CREATE VIEW v_region_mois AS
        SELECT region, mois_vente,
               COUNT(*)         AS nb_lots,
               ROUND(AVG(prix)) AS prix_moyen,
               ROUND(SUM(prix)) AS produit_total
        FROM lots WHERE region IS NOT NULL AND mois_vente IS NOT NULL
        GROUP BY region, mois_vente ORDER BY mois_vente DESC, nb_lots DESC
    """)
    cur.execute("""
        CREATE VIEW v_bonnes_affaires AS
        SELECT intitule, marque, modele, annee, kilometrage, gravite,
               mise_a_prix, prix, multiple_mise_a_prix, departement, url
        FROM lots
        WHERE prix IS NOT NULL AND multiple_mise_a_prix IS NOT NULL
        ORDER BY multiple_mise_a_prix ASC LIMIT 200
    """)
    conn.commit()
    conn.close()
    log.info("écrit %s", path)
    return path
