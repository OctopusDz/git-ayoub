"""Construction du cube multidimensionnel consommé par le portail.

La table de faits est transposée en colonnes et les dimensions sont
dictionnarisées : chaque valeur textuelle n'est stockée qu'une fois, les faits
ne portent qu'un index entier. Sur 10 000 lots, le fichier passe d'environ
25 Mo à 3 Mo, et le portail peut agréger côté navigateur sans serveur.

Usage :
    python -m etl.build_cube [entree.json] [sortie.json]
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
ENTREE_DEFAUT = RACINE / "data" / "lots.json"
SORTIE_DEFAUT = RACINE / "portal" / "data" / "dataset.json"

# --- Dimensions d'analyse ---------------------------------------------------
# type : "nominale" (libre), "ordinale" (ordre imposé), "temps" (ordre naturel)
DIMENSIONS = [
    {"cle": "categorie", "libelle": "Catégorie", "type": "nominale", "groupe": "Véhicule"},
    {"cle": "marque", "libelle": "Marque", "type": "nominale", "groupe": "Véhicule"},
    {"cle": "modele", "libelle": "Modèle", "type": "nominale", "groupe": "Véhicule"},
    {"cle": "carburant", "libelle": "Énergie", "type": "nominale", "groupe": "Véhicule"},
    {"cle": "boite_vitesses", "libelle": "Boîte de vitesses", "type": "nominale", "groupe": "Véhicule"},
    {"cle": "critair", "libelle": "Vignette Crit'Air", "type": "ordinale", "groupe": "Véhicule"},
    {"cle": "norme_euro", "libelle": "Norme Euro", "type": "ordinale", "groupe": "Véhicule"},
    {"cle": "annee", "libelle": "Année du véhicule", "type": "ordinale", "groupe": "Véhicule"},
    {"cle": "tranche_age", "libelle": "Tranche d'âge", "type": "ordinale", "groupe": "Véhicule",
     "ordre": ["0 – 3 ans", "3 – 6 ans", "6 – 10 ans", "10 – 15 ans", "15 – 20 ans", "20 ans et +"]},
    {"cle": "tranche_km", "libelle": "Tranche de kilométrage", "type": "ordinale", "groupe": "Véhicule",
     "ordre": ["0 – 20 000 km", "20 – 50 000 km", "50 – 100 000 km", "100 – 150 000 km",
               "150 – 200 000 km", "200 – 300 000 km", "300 000 km et +"]},

    {"cle": "gravite", "libelle": "État signalé", "type": "ordinale", "groupe": "État",
     "ordre": ["Aucun défaut signalé", "Défauts d'usage", "Défaut bloquant isolé", "Défauts majeurs"]},
    {"cle": "non_roulant", "libelle": "Non roulant", "type": "nominale", "groupe": "État"},
    {"cle": "sans_cle", "libelle": "Sans clé", "type": "nominale", "groupe": "État"},
    {"cle": "sans_carte_grise", "libelle": "Sans carte grise", "type": "nominale", "groupe": "État"},
    {"cle": "premiere_main", "libelle": "Première main", "type": "nominale", "groupe": "État"},
    {"cle": "distribution_faite", "libelle": "Distribution faite", "type": "nominale", "groupe": "État"},
    {"cle": "controle_technique_mentionne", "libelle": "Contrôle technique mentionné",
     "type": "nominale", "groupe": "État"},

    {"cle": "region", "libelle": "Région", "type": "nominale", "groupe": "Géographie"},
    {"cle": "departement", "libelle": "Département", "type": "nominale", "groupe": "Géographie"},
    {"cle": "ville", "libelle": "Ville de retrait", "type": "nominale", "groupe": "Géographie"},
    {"cle": "centre_vente", "libelle": "Centre de vente", "type": "nominale", "groupe": "Géographie"},
    {"cle": "metropole", "libelle": "France métropolitaine", "type": "nominale",
     "groupe": "Géographie"},

    {"cle": "statut", "libelle": "Statut du lot", "type": "nominale", "groupe": "Vente"},
    {"cle": "mode_vente", "libelle": "Mode de vente", "type": "nominale", "groupe": "Vente"},
    {"cle": "reserve_aux_pros", "libelle": "Réservé aux professionnels", "type": "nominale", "groupe": "Vente"},
    {"cle": "lot_prestige", "libelle": "Lot prestige", "type": "nominale", "groupe": "Vente"},
    {"cle": "a_depasse_mise_a_prix", "libelle": "Mise à prix dépassée", "type": "nominale", "groupe": "Vente"},
    {"cle": "vente_passee", "libelle": "Vente clôturée", "type": "nominale", "groupe": "Vente"},
    {"cle": "tranche_mise_a_prix", "libelle": "Tranche de mise à prix", "type": "ordinale", "groupe": "Vente",
     "ordre": ["< 500 €", "500 – 1 000 €", "1 000 – 2 500 €", "2 500 – 5 000 €",
               "5 000 – 10 000 €", "10 000 – 20 000 €", "20 000 € et +"]},
    {"cle": "tranche_prix", "libelle": "Tranche de prix atteint", "type": "ordinale", "groupe": "Vente",
     "ordre": ["< 500 €", "500 – 1 000 €", "1 000 – 2 500 €", "2 500 – 5 000 €",
               "5 000 – 10 000 €", "10 000 – 20 000 €", "20 000 € et +"]},

    {"cle": "verdict", "libelle": "Verdict d'enchère", "type": "ordinale", "groupe": "Opportunité",
     "ordre": ["Très intéressant", "Intéressant", "Marge faible", "À éviter",
               "Pas de référence", "Mise à prix inconnue"]},
    {"cle": "confiance", "libelle": "Confiance de l'estimation", "type": "ordinale",
     "groupe": "Opportunité", "ordre": ["bonne", "moyenne", "faible", "aucune"]},
    {"cle": "hybride", "libelle": "Hybride", "type": "nominale", "groupe": "Véhicule"},
    {"cle": "base_hybride", "libelle": "Base de l'hybride", "type": "nominale", "groupe": "Véhicule"},
    {"cle": "annee_douteuse", "libelle": "Millésime incohérent", "type": "nominale", "groupe": "Véhicule"},

    {"cle": "annee_vente", "libelle": "Année de vente", "type": "temps", "groupe": "Temps"},
    {"cle": "trimestre_vente", "libelle": "Trimestre de vente", "type": "temps", "groupe": "Temps"},
    {"cle": "mois_vente", "libelle": "Mois de vente", "type": "temps", "groupe": "Temps"},
    {"cle": "semaine_vente", "libelle": "Semaine de vente", "type": "temps", "groupe": "Temps"},
    {"cle": "jour_semaine_vente", "libelle": "Jour de clôture", "type": "ordinale", "groupe": "Temps",
     "ordre": ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]},
]

# --- Mesures ----------------------------------------------------------------
# agregat : nb | somme | moyenne | mediane | min | max | part_vrai
MESURES = [
    {"cle": "nb_lots", "libelle": "Nombre de lots", "champ": None, "agregat": "nb",
     "format": "entier", "defaut": True},
    {"cle": "prix_moyen", "libelle": "Prix moyen atteint", "champ": "prix",
     "agregat": "moyenne", "format": "euro", "defaut": True},
    {"cle": "prix_median", "libelle": "Prix médian atteint", "champ": "prix",
     "agregat": "mediane", "format": "euro"},
    {"cle": "produit_total", "libelle": "Produit total des ventes", "champ": "prix",
     "agregat": "somme", "format": "euro", "defaut": True},
    {"cle": "prix_max", "libelle": "Prix maximum", "champ": "prix", "agregat": "max", "format": "euro"},
    {"cle": "prix_min", "libelle": "Prix minimum", "champ": "prix", "agregat": "min", "format": "euro"},
    {"cle": "mise_a_prix_moyenne", "libelle": "Mise à prix moyenne", "champ": "mise_a_prix",
     "agregat": "moyenne", "format": "euro"},
    {"cle": "mise_a_prix_mediane", "libelle": "Mise à prix médiane", "champ": "mise_a_prix",
     "agregat": "mediane", "format": "euro"},
    {"cle": "mise_a_prix_totale", "libelle": "Total des mises à prix", "champ": "mise_a_prix",
     "agregat": "somme", "format": "euro"},
    {"cle": "derniere_enchere_mediane", "libelle": "Dernière enchère médiane",
     "champ": "derniere_enchere", "agregat": "mediane", "format": "euro"},
    {"cle": "derniere_enchere_moyenne", "libelle": "Dernière enchère moyenne",
     "champ": "derniere_enchere", "agregat": "moyenne", "format": "euro"},
    {"cle": "adjuge_median", "libelle": "Montant adjugé médian",
     "champ": "montant_adjuge", "agregat": "mediane", "format": "euro"},
    {"cle": "adjuge_total", "libelle": "Total des montants adjugés",
     "champ": "montant_adjuge", "agregat": "somme", "format": "euro"},
    {"cle": "multiple_moyen", "libelle": "Multiple moyen sur mise à prix",
     "champ": "multiple_mise_a_prix", "agregat": "moyenne", "format": "multiple", "defaut": True},
    {"cle": "multiple_median", "libelle": "Multiple médian sur mise à prix",
     "champ": "multiple_mise_a_prix", "agregat": "mediane", "format": "multiple"},
    {"cle": "plus_value_totale", "libelle": "Plus-value totale", "champ": "plus_value_euros",
     "agregat": "somme", "format": "euro"},
    {"cle": "plus_value_moyenne_pct", "libelle": "Plus-value moyenne", "champ": "plus_value_pct",
     "agregat": "moyenne", "format": "pourcent"},
    {"cle": "taux_depassement", "libelle": "Part des lots au-dessus de la mise à prix",
     "champ": "b_a_depasse_mise_a_prix", "agregat": "part_vrai", "format": "pourcent"},
    {"cle": "km_moyen", "libelle": "Kilométrage moyen", "champ": "kilometrage",
     "agregat": "moyenne", "format": "km"},
    {"cle": "km_median", "libelle": "Kilométrage médian", "champ": "kilometrage",
     "agregat": "mediane", "format": "km"},
    {"cle": "age_moyen", "libelle": "Âge moyen", "champ": "age", "agregat": "moyenne", "format": "an"},
    {"cle": "prix_par_1000km_median", "libelle": "Prix médian pour 1 000 km",
     "champ": "prix_par_1000km", "agregat": "mediane", "format": "euro"},
    {"cle": "km_par_an_moyen", "libelle": "Kilométrage annuel moyen", "champ": "km_par_an",
     "agregat": "moyenne", "format": "km"},
    {"cle": "defauts_moyen", "libelle": "Nombre moyen de défauts", "champ": "nb_defauts",
     "agregat": "moyenne", "format": "decimal"},
    {"cle": "part_non_roulant", "libelle": "Part de véhicules non roulants",
     "champ": "b_non_roulant", "agregat": "part_vrai", "format": "pourcent"},
    {"cle": "completude_moyenne", "libelle": "Complétude moyenne de la fiche",
     "champ": "completude_pct", "agregat": "moyenne", "format": "pourcent"},
]

# Colonnes numériques nécessaires aux mesures et aux filtres numériques.
CHAMPS_NUMERIQUES = [
    "prix", "mise_a_prix", "derniere_enchere", "montant_adjuge",
    "multiple_mise_a_prix", "plus_value_euros", "plus_value_pct",
    "kilometrage", "age", "prix_par_1000km", "km_par_an",
    "nb_defauts", "nb_defauts_majeurs", "completude_pct", "jours_restants",
    "estimation", "fourchette_basse", "fourchette_haute", "prix_max_conseille",
    "marge_pct", "nb_comparables",
    "nb_places", "nb_portes", "nb_cles", "duree_vente_heures",
]

# Colonnes booléennes servant aux mesures « part_vrai ». Elles sont préfixées
# « b_ » car ces champs existent aussi comme dimensions (valeurs Oui / Non) et
# les deux usages doivent cohabiter dans la même table de colonnes.
CHAMPS_BOOLEENS = ["a_depasse_mise_a_prix", "non_roulant", "sans_cle",
                   "sans_carte_grise", "premiere_main"]

# Colonnes de texte libre, affichées dans la table de détail.
CHAMPS_TEXTE = ["id_lot", "intitule", "url", "image", "sku", "numero_lot",
                "immatriculation", "vin", "date_fin", "date_debut",
                "date_mise_en_circulation", "description", "base_comparables"]

BOOLEENS_LISIBLES = {True: "Oui", False: "Non"}


def estimer_ventes_a_venir(lots: list[dict]) -> int:
    """Attache à chaque vente ouverte son estimation et son conseil d'enchère.

    Les ventes closes servent de référence ; elles ne reçoivent pas
    d'estimation, leur prix étant connu.
    """
    from etl.estimation import estimer, separer

    historique, a_venir = separer(lots)
    if not historique or not a_venir:
        return 0
    for lot in a_venir:
        resultat = estimer(lot, historique)
        lot.update({
            "estimation": resultat["estimation"],
            "fourchette_basse": resultat["fourchette_basse"],
            "fourchette_haute": resultat["fourchette_haute"],
            "prix_max_conseille": resultat["prix_max_conseille"],
            "verdict": resultat["verdict"],
            "confiance": resultat["confiance"],
            "marge_pct": resultat["marge_pct"],
            "nb_comparables": resultat["nb_comparables"],
            "base_comparables": resultat["base"],
        })
    print(f"  {len(a_venir)} ventes à venir estimées "
          f"sur {len(historique)} ventes closes")
    return len(a_venir)


def _valeur_dimension(lot: dict, cle: str):
    """Valeur d'une dimension, lisible par un humain (booléens compris)."""
    brut = lot.get(cle)
    if brut is None or brut == "":
        return None
    if isinstance(brut, bool):
        return BOOLEENS_LISIBLES[brut]
    return str(brut)


def construire(entree: Path = ENTREE_DEFAUT, sortie: Path = SORTIE_DEFAUT) -> Path:
    """Lit ``lots.json`` et écrit le cube du portail."""
    if not Path(entree).exists():
        raise FileNotFoundError(
            f"{entree} est introuvable. Lancez d'abord la collecte : python -m scraper")

    charge = json.loads(Path(entree).read_text(encoding="utf-8"))
    lots = charge["lots"]
    if not lots:
        raise ValueError("aucun lot dans le fichier d'entrée")

    estimer_ventes_a_venir(lots)

    dim_valeurs: dict[str, list] = {}
    dim_index: dict[str, dict] = {}
    colonnes: dict[str, list] = {}

    # --- dimensions : dictionnarisation ------------------------------------
    for dimension in DIMENSIONS:
        cle = dimension["cle"]
        valeurs: list[str] = []
        index: dict[str, int] = {}
        codes: list[int] = []
        for lot in lots:
            valeur = _valeur_dimension(lot, cle)
            if valeur is None:
                codes.append(-1)
                continue
            position = index.get(valeur)
            if position is None:
                position = len(valeurs)
                index[valeur] = position
                valeurs.append(valeur)
            codes.append(position)
        dim_valeurs[cle] = valeurs
        dim_index[cle] = index
        colonnes[cle] = codes
        dimension["cardinalite"] = len(valeurs)
        dimension["nb_renseignes"] = sum(1 for c in codes if c >= 0)

    # --- mesures et colonnes numériques ------------------------------------
    for champ in CHAMPS_NUMERIQUES:
        colonnes[champ] = [lot.get(champ) for lot in lots]
    for champ in CHAMPS_BOOLEENS:
        colonnes["b_" + champ] = [None if lot.get(champ) is None else int(bool(lot.get(champ)))
                                  for lot in lots]

    textes = {champ: [lot.get(champ) for lot in lots] for champ in CHAMPS_TEXTE}

    # --- ordre d'affichage des dimensions ordinales ------------------------
    for dimension in DIMENSIONS:
        if dimension["type"] == "ordinale" and "ordre" not in dimension:
            # Ordre naturel : numérique si possible, alphabétique sinon.
            valeurs = dim_valeurs[dimension["cle"]]
            try:
                dimension["ordre"] = sorted(valeurs, key=lambda v: float(v))
            except (TypeError, ValueError):
                dimension["ordre"] = sorted(valeurs)

    # --- métadonnées ---------------------------------------------------------
    dates = sorted((lot.get("date_fin") or "")[:10] for lot in lots if lot.get("date_fin"))
    prix_connus = [lot["prix"] for lot in lots if lot.get("prix") is not None]

    meta = {
        "genere_le": datetime.now().isoformat(timespec="seconds"),
        "source": "encheres-domaine.gouv.fr — API GraphQL",
        "nb_lots": len(lots),
        "periode": {"debut": dates[0] if dates else None,
                    "fin": dates[-1] if dates else None},
        "lots_avec_prix": len(prix_connus),
        "produit_total": round(sum(prix_connus)) if prix_connus else 0,
        "collecte": charge.get("meta", {}),
        "dimensions": DIMENSIONS,
        "mesures": MESURES,
        "champs_texte": CHAMPS_TEXTE,
        "champs_numeriques": CHAMPS_NUMERIQUES,
        "champs_booleens": ["b_" + c for c in CHAMPS_BOOLEENS],
    }

    cube = {"meta": meta, "dim": dim_valeurs, "col": colonnes, "txt": textes}

    sortie = Path(sortie)
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(json.dumps(cube, ensure_ascii=False, separators=(",", ":")),
                      encoding="utf-8")

    taille = sortie.stat().st_size / 1_048_576
    print(f"Cube écrit : {sortie}  ({len(lots)} lots, {taille:.1f} Mo, "
          f"{len(DIMENSIONS)} dimensions, {len(MESURES)} mesures)")
    return sortie


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    entree = Path(argv[0]) if len(argv) > 0 else ENTREE_DEFAUT
    sortie = Path(argv[1]) if len(argv) > 1 else SORTIE_DEFAUT
    try:
        construire(entree, sortie)
    except Exception as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
