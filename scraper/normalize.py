"""Normalisation et enrichissement : du lot brut au fait analytique.

Sortie : un enregistrement plat, une ligne = un lot, prêt à alimenter le cube.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime

from . import referentiels as ref
from .parse import to_date, to_money, to_number

CODE_POSTAL_RE = re.compile(r"\b(\d{5})\b")
CODE_DEPT_RE = re.compile(r"\b(2[AB]|9[7][1-6]|\d{2})\b")


def sans_accents(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", value)
                   if unicodedata.category(c) != "Mn")


def detect_marque(*sources: str | None) -> str | None:
    """Repère une marque connue dans le titre ou la description."""
    blob = sans_accents(" ".join(s for s in sources if s).upper())
    trouvees = [m for m in ref.MARQUES if re.search(rf"\b{re.escape(sans_accents(m))}\b", blob)]
    if not trouvees:
        return None
    marque = max(trouvees, key=len)          # « LAND ROVER » plutôt que « ROVER »
    return ref.ALIAS_MARQUES.get(marque, marque)


def detect_modele(titre: str | None, marque: str | None) -> str | None:
    """Mot(s) suivant la marque dans le titre — approximation acceptable."""
    if not titre or not marque:
        return None
    plat = sans_accents(titre).upper()
    cible = sans_accents(marque).upper()
    idx = plat.find(cible)
    if idx < 0:
        for alias, canon in ref.ALIAS_MARQUES.items():
            if canon == marque:
                idx = plat.find(sans_accents(alias).upper())
                if idx >= 0:
                    cible = sans_accents(alias).upper()
                    break
    if idx < 0:
        return None
    suite = titre[idx + len(cible):].strip(" -–—,/")
    mots = [m for m in re.split(r"[\s,/]+", suite) if m][:2]
    modele = " ".join(mots).strip(" -–—,.")
    modele = re.sub(r"^(de|du|type)\b\s*", "", modele, flags=re.I)
    return modele.upper() or None


def normalize_carburant(value: str | None) -> str | None:
    if not value:
        return None
    key = sans_accents(str(value)).lower().strip()
    for alias, canon in ref.ALIAS_CARBURANT.items():
        if key == sans_accents(alias).lower() or sans_accents(alias).lower() in key:
            return canon
    return value.strip().capitalize()


def normalize_boite(value: str | None) -> str | None:
    if not value:
        return None
    key = sans_accents(str(value)).lower().strip()
    for alias, canon in ref.ALIAS_BOITE.items():
        if key == sans_accents(alias).lower() or sans_accents(alias).lower() in key:
            return canon
    return value.strip().capitalize()


def detect_departement(*sources: str | None) -> tuple[str | None, str | None, str | None]:
    """(code, nom, région) déduits d'un code postal ou d'un nom de département."""
    blob = " ".join(s for s in sources if s)
    if not blob:
        return None, None, None

    cp = CODE_POSTAL_RE.search(blob)
    if cp:
        code = cp.group(1)[:2]
        if code == "20":
            code = "2A"
        if cp.group(1).startswith("97"):
            code = cp.group(1)[:3]
        if code in ref.DEPARTEMENTS:
            nom, region = ref.DEPARTEMENTS[code]
            return code, nom, region

    plat = sans_accents(blob).lower()
    for nom_dept, code in ref.NOM_VERS_CODE.items():
        if sans_accents(nom_dept) in plat:
            nom, region = ref.DEPARTEMENTS[code]
            return code, nom, region

    dept = CODE_DEPT_RE.search(blob)
    if dept and dept.group(1) in ref.DEPARTEMENTS:
        code = dept.group(1)
        nom, region = ref.DEPARTEMENTS[code]
        return code, nom, region
    return None, None, None


def detect_ville(lieu: str | None) -> str | None:
    if not lieu:
        return None
    nettoye = CODE_POSTAL_RE.sub(" ", lieu)
    morceaux = [m.strip() for m in re.split(r"[,;()\-–]", nettoye) if m.strip()]
    if not morceaux:
        return None
    ville = max(morceaux, key=len).strip()
    return ville.title()[:60] or None


def extract_annee(*sources) -> int | None:
    for source in sources:
        if source is None:
            continue
        if isinstance(source, (int, float)):
            annee = int(source)
            if 1950 <= annee <= date.today().year + 1:
                return annee
            continue
        match = re.search(r"\b(19[5-9]\d|20[0-4]\d)\b", str(source))
        if match:
            return int(match.group(1))
    return None


def normalize_lot(brut: dict, contexte: dict | None = None) -> dict:
    """Transforme un lot brut (scrapé) en fait analytique enrichi."""
    contexte = contexte or {}
    titre = (brut.get("titre") or "").strip() or None
    description = brut.get("description")

    marque = (brut.get("marque") or "").strip().upper() or None
    if marque:
        marque = ref.ALIAS_MARQUES.get(marque, marque)
    marque = marque or detect_marque(titre, description)

    modele = (brut.get("modele") or "").strip().upper() or detect_modele(titre, marque)

    annee = extract_annee(brut.get("annee"), brut.get("date_mise_en_circulation"), titre)
    kilometrage = to_number(brut.get("kilometrage"))
    if kilometrage is not None and kilometrage > 1_500_000:
        kilometrage = None                          # valeur aberrante

    prix = to_money(brut.get("prix_courant")) or to_money(brut.get("prix_liste"))
    mise_a_prix = to_money(brut.get("mise_a_prix")) or to_money(brut.get("mise_a_prix_liste"))
    nb_encheres = to_number(brut.get("nb_encheres"))

    lieu = brut.get("lieu") or brut.get("lieu_liste")
    code_dept, nom_dept, region = detect_departement(lieu, brut.get("departement"))

    date_fin = to_date(brut.get("date_fin")) or to_date(brut.get("date_fin_liste"))
    date_debut = to_date(brut.get("date_debut"))

    annee_courante = date.today().year
    age = annee_courante - annee if annee else None

    fait = {
        # -- identité ------------------------------------------------------
        "id_lot": brut.get("id_lot"),
        "url": brut.get("url"),
        "titre": titre,
        "categorie": contexte.get("categorie") or brut.get("categorie"),
        "statut": brut.get("statut") or brut.get("statut_liste"),
        "image": brut.get("image") or (brut.get("images") or [None])[0],

        # -- dimensions véhicule -------------------------------------------
        "marque": marque,
        "modele": modele,
        "annee": annee,
        "age": age,
        "kilometrage": kilometrage,
        "carburant": normalize_carburant(brut.get("carburant")),
        "boite_vitesses": normalize_boite(brut.get("boite_vitesses")),
        "puissance_fiscale": to_number(brut.get("puissance_fiscale")),
        "puissance_din": to_number(brut.get("puissance_din")),
        "nb_places": to_number(brut.get("nb_places")),
        "nb_portes": to_number(brut.get("nb_portes")),
        "couleur": (brut.get("couleur") or "").strip().capitalize() or None,
        "etat": (brut.get("etat") or "").strip().capitalize() or None,
        "controle_technique": brut.get("controle_technique"),
        "immatriculation": brut.get("immatriculation"),

        # -- dimensions géographiques --------------------------------------
        "lieu": lieu,
        "ville": detect_ville(lieu),
        "code_departement": code_dept,
        "departement": nom_dept,
        "region": region,
        "service_vendeur": brut.get("service_vendeur"),

        # -- mesures --------------------------------------------------------
        "mise_a_prix": mise_a_prix,
        "prix": prix,
        "nb_encheres": nb_encheres,

        # -- dimensions temps -----------------------------------------------
        "date_debut": date_debut,
        "date_fin": date_fin,

        # -- traçabilité -----------------------------------------------------
        "date_collecte": contexte.get("date_collecte") or datetime.now().isoformat(timespec="seconds"),
        "source": "encheres-domaine.gouv.fr",
    }

    # -- indicateurs dérivés -------------------------------------------------
    if prix and mise_a_prix and mise_a_prix > 0:
        fait["multiple_mise_a_prix"] = round(prix / mise_a_prix, 3)
        fait["plus_value_euros"] = round(prix - mise_a_prix, 2)
        fait["plus_value_pct"] = round((prix / mise_a_prix - 1) * 100, 1)
    else:
        fait["multiple_mise_a_prix"] = None
        fait["plus_value_euros"] = None
        fait["plus_value_pct"] = None

    if prix and kilometrage and kilometrage > 0:
        fait["prix_par_1000km"] = round(prix / (kilometrage / 1000), 2)
    else:
        fait["prix_par_1000km"] = None

    if prix and fait["puissance_fiscale"]:
        fait["prix_par_cv"] = round(prix / fait["puissance_fiscale"], 2)
    else:
        fait["prix_par_cv"] = None

    if kilometrage is not None and age and age > 0:
        fait["km_par_an"] = round(kilometrage / age)
    else:
        fait["km_par_an"] = None

    # -- dimensions ordinales (tranches) ------------------------------------
    fait["tranche_km"] = ref.tranche(kilometrage, ref.TRANCHES_KM)
    fait["tranche_prix"] = ref.tranche(prix, ref.TRANCHES_PRIX)
    fait["tranche_age"] = ref.tranche(age, ref.TRANCHES_AGE)

    # -- dimension temps (hiérarchie année > trimestre > mois) ---------------
    if date_fin:
        d = datetime.fromisoformat(date_fin).date()
        fait["annee_vente"] = d.year
        fait["trimestre_vente"] = f"{d.year}-T{(d.month - 1) // 3 + 1}"
        fait["mois_vente"] = f"{d.year}-{d.month:02d}"
        fait["semaine_vente"] = f"{d.isocalendar().year}-S{d.isocalendar().week:02d}"
        fait["jour_semaine_vente"] = ["Lundi", "Mardi", "Mercredi", "Jeudi",
                                      "Vendredi", "Samedi", "Dimanche"][d.weekday()]
        fait["jours_restants"] = (d - date.today()).days
    else:
        for champ in ("annee_vente", "trimestre_vente", "mois_vente",
                      "semaine_vente", "jour_semaine_vente", "jours_restants"):
            fait[champ] = None

    # -- qualité de la donnée -------------------------------------------------
    champs_cles = ["marque", "modele", "annee", "kilometrage", "carburant",
                   "prix", "mise_a_prix", "departement", "date_fin"]
    remplis = sum(1 for c in champs_cles if fait.get(c) not in (None, ""))
    fait["completude_pct"] = round(100 * remplis / len(champs_cles))

    return fait


CHAMPS_EXPORT = [
    "id_lot", "url", "titre", "categorie", "statut", "image",
    "marque", "modele", "annee", "age", "kilometrage", "carburant",
    "boite_vitesses", "puissance_fiscale", "puissance_din", "nb_places",
    "nb_portes", "couleur", "etat", "controle_technique", "immatriculation",
    "lieu", "ville", "code_departement", "departement", "region",
    "service_vendeur", "mise_a_prix", "prix", "nb_encheres",
    "multiple_mise_a_prix", "plus_value_euros", "plus_value_pct",
    "prix_par_1000km", "prix_par_cv", "km_par_an",
    "tranche_km", "tranche_prix", "tranche_age",
    "date_debut", "date_fin", "annee_vente", "trimestre_vente", "mois_vente",
    "semaine_vente", "jour_semaine_vente", "jours_restants",
    "completude_pct", "date_collecte", "source",
]
