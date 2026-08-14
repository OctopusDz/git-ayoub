"""Normalisation : de la réponse API au fait analytique.

Une ligne = un lot, avec ses dimensions (quoi, où, quand, dans quel état) et
ses mesures (mise à prix, dernière enchère, plus-value…), prêtes pour le cube.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone

from . import config
from . import description as desc
from . import energie as nrj
from . import referentiels as ref

# Marques en deux mots : à tester avant le découpage sur le premier espace.
MARQUES_COMPOSEES = ["ALFA ROMEO", "ASTON MARTIN", "LAND ROVER", "MERCEDES BENZ",
                     "MERCEDES-BENZ", "ROLLS ROYCE", "GREAT WALL", "SSANG YONG"]


def _horodatage(valeur: str | None) -> str | None:
    """'2025-07-11T08:00:00+00:00' -> '2025-07-11T08:00:00' (heure UTC)."""
    if not valeur:
        return None
    try:
        return datetime.fromisoformat(valeur.replace("Z", "+00:00")) \
            .astimezone(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")
    except Exception:
        return None


def _jour(valeur: str | None) -> str | None:
    return valeur[:10] if valeur else None


def _nombre(valeur) -> float | None:
    if valeur in (None, "", False):
        return None
    try:
        nombre = float(valeur)
    except (TypeError, ValueError):
        return None
    return nombre


def separer_marque_modele(nom: str | None) -> tuple[str | None, str | None]:
    """'RENAULT Twingo' -> ('RENAULT', 'TWINGO')."""
    if not nom:
        return None, None
    propre = re.sub(r"\s+", " ", nom.strip())
    majuscules = desc.sans_accents(propre).upper()

    for composee in MARQUES_COMPOSEES:
        if majuscules.startswith(composee):
            marque = ref.ALIAS_MARQUES.get(composee, composee)
            modele = propre[len(composee):].strip(" -–,/").upper()
            return marque, modele or None

    morceaux = propre.split(" ", 1)
    marque = desc.sans_accents(morceaux[0]).upper()
    marque = ref.ALIAS_MARQUES.get(marque, marque)
    modele = morceaux[1].strip(" -–,/").upper() if len(morceaux) > 1 else None
    return marque or None, modele or None


def normalize_lot(brut: dict, categorie_id: int, date_collecte: str) -> dict:
    """Transforme un item de l'API en fait analytique enrichi."""
    infos = desc.analyser((brut.get("short_description") or {}).get("html"),
                          (brut.get("description") or {}).get("html"))

    # Motorisation : le descriptif seul confond hybride essence et hybride
    # diesel, et déclare « Essence » une Yaris Hybrid. La classification croise
    # mention explicite, code moteur et modèle.
    motorisation = nrj.classer(brut.get("name"), infos.get("description"),
                               infos.get("carburant"))

    marque, modele = separer_marque_modele(brut.get("name"))
    lieu = brut.get("dropoff_location") or {}
    code_postal = (lieu.get("postcode") or "").strip() or None
    ville = (lieu.get("city") or "").strip().title() or None

    code_dept, nom_dept, region = ref.departement_depuis_cp(code_postal)

    mise_a_prix = _nombre(brut.get("price_auction"))
    derniere_enchere = _nombre(brut.get("last_bid"))
    montant_adjuge = _nombre(brut.get("bid_winner_amount"))
    prix = montant_adjuge or derniere_enchere or None

    debut = _horodatage(brut.get("start_auction_lot_at") or brut.get("start_date"))
    fin = _horodatage(brut.get("end_auction_lot_at") or brut.get("end_date"))
    limite_offres = _horodatage(brut.get("offers_submission_deadline"))

    annee = infos.get("annee")
    mise_en_circulation = infos.get("date_mise_en_circulation")
    kilometrage = infos.get("kilometrage")

    # Âge du véhicule à la date de vente (à défaut, à aujourd'hui).
    reference = date.fromisoformat(fin[:10]) if fin else date.today()
    age = None
    if mise_en_circulation:
        naissance = date.fromisoformat(mise_en_circulation)
        age = round((reference - naissance).days / 365.25, 1)
    elif annee:
        age = reference.year - annee

    fait = {
        # -- identité --------------------------------------------------------
        "id_lot": brut.get("id"),
        "uid": brut.get("uid"),
        "sku": brut.get("sku"),
        "numero_lot": brut.get("lot_number"),
        "url": f"{config.BASE_URL}/lot/{brut['url_key']}.html" if brut.get("url_key") else None,
        "intitule": brut.get("name"),
        "image": (brut.get("small_image") or {}).get("url"),
        "categorie_id": categorie_id,
        "categorie": config.CATEGORIES.get(categorie_id, str(categorie_id)),

        # -- dimensions véhicule ---------------------------------------------
        "marque": marque,
        "modele": modele,
        "annee": annee,
        "date_mise_en_circulation": mise_en_circulation,
        "age": age,
        "kilometrage": kilometrage,
        "kilometrage_methode": infos.get("kilometrage_methode"),
        "carburant": motorisation.get("energie") or infos.get("carburant"),
        "hybride": motorisation.get("hybride"),
        "base_hybride": motorisation.get("base_hybride"),
        "rechargeable": motorisation.get("rechargeable"),
        "indice_energie": motorisation.get("indice"),
        "boite_vitesses": infos.get("boite_vitesses"),
        "critair": infos.get("critair"),
        "norme_euro": infos.get("norme_euro"),
        "nb_places": infos.get("nb_places"),
        "nb_portes": infos.get("nb_portes"),
        "nb_cles": infos.get("nb_cles"),
        "immatriculation": infos.get("immatriculation"),
        "vin": infos.get("vin"),
        "type_mines": infos.get("type_mines"),

        # -- état --------------------------------------------------------------
        "gravite": infos.get("gravite"),
        "defauts": infos.get("defauts") or [],
        "nb_defauts": infos.get("nb_defauts"),
        "nb_defauts_majeurs": infos.get("nb_defauts_majeurs"),
        "sans_cle": infos.get("sans_cle"),
        "sans_carte_grise": infos.get("sans_carte_grise"),
        "non_roulant": infos.get("non_roulant"),
        "premiere_main": infos.get("premiere_main"),
        "controle_technique_mentionne": infos.get("controle_technique_mentionne"),
        "distribution_faite": infos.get("distribution_faite"),
        "revision_recente": infos.get("revision_recente"),
        "date_entree_parc": infos.get("date_entree_parc"),

        # -- dimensions géographiques -----------------------------------------
        "ville": ville,
        "code_postal": code_postal,
        "code_departement": code_dept,
        "departement": nom_dept,
        "region": region,
        "centre_vente": (brut.get("sales_inspector_data") or {}).get("cav_name"),

        # -- dimensions vente ---------------------------------------------------
        "statut_code": brut.get("lot_status"),
        "statut": brut.get("lot_status_label"),
        "mode_vente": "Appel d'offres" if limite_offres else "Enchère",
        "reserve_aux_pros": bool(brut.get("professional_only")),
        "lot_prestige": bool(brut.get("luxury")),

        # -- mesures ------------------------------------------------------------
        "mise_a_prix": mise_a_prix,
        "derniere_enchere": derniere_enchere,
        "montant_adjuge": montant_adjuge,
        "prix": prix,
        "prix_reserve": _nombre(brut.get("reserve_price")) or None,

        # -- dimensions temps ----------------------------------------------------
        "date_debut": debut,
        "date_fin": fin,
        "jour_debut": _jour(debut),
        "jour_fin": _jour(fin),
        "limite_offres": limite_offres,

        # -- traçabilité ----------------------------------------------------------
        "date_collecte": date_collecte,
        "source": "encheres-domaine.gouv.fr",
        "description": infos.get("description"),
    }

    # -- indicateurs dérivés ----------------------------------------------------
    if prix and mise_a_prix and mise_a_prix > 0:
        fait["multiple_mise_a_prix"] = round(prix / mise_a_prix, 3)
        fait["plus_value_euros"] = round(prix - mise_a_prix, 2)
        fait["plus_value_pct"] = round((prix / mise_a_prix - 1) * 100, 1)
        fait["a_depasse_mise_a_prix"] = prix > mise_a_prix
    else:
        fait["multiple_mise_a_prix"] = None
        fait["plus_value_euros"] = None
        fait["plus_value_pct"] = None
        fait["a_depasse_mise_a_prix"] = None

    fait["prix_par_1000km"] = (round(prix / (kilometrage / 1000), 2)
                               if prix and kilometrage else None)
    fait["km_par_an"] = (round(kilometrage / age) if kilometrage and age and age >= 1
                         else None)

    # Cohérence du millésime : le service vendeur saisit parfois une date de
    # première mise en circulation erronée (une Yaris annoncée de 2026 avec
    # 144 000 km au compteur). Au-delà de 60 000 km par an, la date n'est pas
    # crédible ; on le signale plutôt que de fausser âge et comparaisons.
    fait["annee_douteuse"] = bool(
        kilometrage and age is not None and 0 < age < 2 and kilometrage > 60_000)
    if fait["annee_douteuse"]:
        fait["age"] = None
        fait["tranche_age"] = None
        fait["km_par_an"] = None

    # -- tranches d'analyse -------------------------------------------------------
    fait["tranche_km"] = ref.tranche(kilometrage, ref.TRANCHES_KM)
    fait["tranche_prix"] = ref.tranche(prix, ref.TRANCHES_PRIX)
    fait["tranche_mise_a_prix"] = ref.tranche(mise_a_prix, ref.TRANCHES_PRIX)
    fait["tranche_age"] = ref.tranche(age, ref.TRANCHES_AGE)

    # -- hiérarchie temps ----------------------------------------------------------
    if fin:
        jour_fin = date.fromisoformat(fin[:10])
        iso = jour_fin.isocalendar()
        fait["annee_vente"] = jour_fin.year
        fait["trimestre_vente"] = f"{jour_fin.year}-T{(jour_fin.month - 1) // 3 + 1}"
        fait["mois_vente"] = f"{jour_fin.year}-{jour_fin.month:02d}"
        fait["semaine_vente"] = f"{iso.year}-S{iso.week:02d}"
        fait["jour_semaine_vente"] = ["Lundi", "Mardi", "Mercredi", "Jeudi",
                                      "Vendredi", "Samedi", "Dimanche"][jour_fin.weekday()]
        fait["jours_restants"] = (jour_fin - date.today()).days
        fait["vente_passee"] = jour_fin < date.today()
    else:
        for champ in ("annee_vente", "trimestre_vente", "mois_vente", "semaine_vente",
                      "jour_semaine_vente", "jours_restants", "vente_passee"):
            fait[champ] = None

    if debut and fin:
        fait["duree_vente_heures"] = round(
            (datetime.fromisoformat(fin) - datetime.fromisoformat(debut)).total_seconds() / 3600, 1)
    else:
        fait["duree_vente_heures"] = None

    # -- complétude ------------------------------------------------------------------
    champs_cles = ["marque", "modele", "annee", "kilometrage", "carburant",
                   "prix", "mise_a_prix", "departement", "date_fin", "vin"]
    remplis = sum(1 for c in champs_cles if fait.get(c) not in (None, "", []))
    fait["completude_pct"] = round(100 * remplis / len(champs_cles))

    return fait


CHAMPS_EXPORT = [
    "id_lot", "sku", "numero_lot", "url", "intitule", "categorie",
    "marque", "modele", "annee", "date_mise_en_circulation", "age",
    "kilometrage", "carburant", "boite_vitesses", "critair", "norme_euro",
    "nb_places", "nb_portes", "nb_cles", "immatriculation", "vin", "type_mines",
    "hybride", "base_hybride", "rechargeable", "indice_energie", "annee_douteuse",
    "gravite", "nb_defauts", "nb_defauts_majeurs", "sans_cle", "sans_carte_grise",
    "non_roulant", "premiere_main", "controle_technique_mentionne",
    "distribution_faite", "revision_recente", "defauts",
    "ville", "code_postal", "code_departement", "departement", "region",
    "centre_vente", "statut", "statut_code", "mode_vente", "reserve_aux_pros",
    "lot_prestige", "mise_a_prix", "derniere_enchere", "montant_adjuge", "prix",
    "multiple_mise_a_prix", "plus_value_euros", "plus_value_pct",
    "a_depasse_mise_a_prix", "prix_par_1000km", "km_par_an",
    "tranche_km", "tranche_prix", "tranche_mise_a_prix", "tranche_age",
    "date_debut", "date_fin", "annee_vente", "trimestre_vente", "mois_vente",
    "semaine_vente", "jour_semaine_vente", "jours_restants", "vente_passee",
    "duree_vente_heures", "completude_pct", "date_collecte", "source",
]
