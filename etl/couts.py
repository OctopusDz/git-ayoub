"""Coût de revient d'un lot, au-delà du prix d'adjudication.

Le prix marteau n'est qu'une partie de la dépense. S'y ajoutent, dans l'ordre
d'importance observé sur les annonces :

* les **frais de vente** de la plateforme — 11 % du prix d'adjudication ;
* les **frais de garde** du fourriériste, souvent transférés à l'acquéreur dès
  le lendemain de la vente : jusqu'à 12 000 € sur un lot du corpus, avec une
  médiane à 754 € quand un montant est chiffré, et parfois un tarif journalier ;
* le **rapatriement**, qui dépend de la distance et de l'état : huit lots sur
  dix imposent un enlèvement sur plateau, bien plus coûteux qu'un trajet par
  la route ;
* la **carte grise**, proportionnelle à la puissance fiscale.

Les tarifs ci-dessous sont des ordres de grandeur, rassemblés en tête de
fichier pour être ajustés facilement. Ce qui est lu dans l'annonce prime
toujours sur l'estimation.
"""
from __future__ import annotations

import re

# --- Paramètres ajustables --------------------------------------------------
DEPART = "Île-de-France"          # d'où part l'acheteur

# Coût kilométrique d'un rapatriement par la route (carburant, péage, et
# acheminement de l'acheteur à l'aller).
COUT_KM_ROUTE = 0.30
# Coût kilométrique d'un enlèvement sur plateau, aller-retour du dépanneur
# compris, avec un plancher de déplacement.
COUT_KM_PLATEAU = 1.60
PLATEAU_MINIMUM = 250.0

# Tarif du cheval fiscal en Île-de-France. À vérifier chaque année : il a
# augmenté récemment et varie d'une région à l'autre.
TARIF_CHEVAL_FISCAL = 54.95
# Les véhicules à énergie propre bénéficient encore d'un abattement dans
# plusieurs régions ; mis à zéro, le calcul reste prudent.
ABATTEMENT_ENERGIE_PROPRE = 0.0

# Délai raisonnable entre l'adjudication et l'enlèvement, pour chiffrer une
# garde facturée à la journée.
JOURS_AVANT_ENLEVEMENT = 5

# Distances routières approximatives depuis Paris, par région (km).
DISTANCES = {
    "Île-de-France": 40,
    "Hauts-de-France": 180,
    "Normandie": 180,
    "Centre-Val de Loire": 190,
    "Grand Est": 350,
    "Bourgogne-Franche-Comté": 320,
    "Pays de la Loire": 340,
    "Bretagne": 400,
    "Nouvelle-Aquitaine": 500,
    "Auvergne-Rhône-Alpes": 460,
    "Occitanie": 650,
    "Provence-Alpes-Côte d'Azur": 750,
    "Corse": 1000,
}
DISTANCE_INCONNUE = 400            # à défaut, une distance médiane

# --- Lecture des frais de garde dans l'annonce ------------------------------
MONTANT_GARDE = re.compile(
    r"(?:frais\s+(?:de\s+)?(?:garde|gardiennage|enl[èe]vement)[^.]{0,80}?"
    r"|s['’]?[ée]levant\s+[àa]\s*)([\d\s]{2,9}(?:[,.]\d{1,2})?)\s*€", re.I)
TARIF_JOURNALIER = re.compile(
    r"([\d\s]{1,6}(?:[,.]\d{1,2})?)\s*€\s*(?:ttc\s*)?/\s*jour", re.I)
MENTION_GARDE = re.compile(r"frais de (?:garde|gardiennage)|fourri[èe]riste", re.I)
PLATEAU = re.compile(r"plateau", re.I)


def _nombre(brut: str) -> float | None:
    try:
        return float(brut.replace(" ", "").replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def frais_garde(description: str | None) -> dict:
    """Frais de garde à prévoir, lus dans l'annonce.

    Retourne le montant et la façon dont il a été obtenu. Quand l'annonce
    signale des frais sans les chiffrer, le montant est ``None`` et
    ``incertain`` vaut vrai : mieux vaut une alerte qu'un chiffre inventé.
    """
    texte = description or ""
    if not texte:
        return {"montant": 0.0, "origine": "aucune mention", "incertain": False}

    trouve = MONTANT_GARDE.search(texte)
    if trouve:
        montant = _nombre(trouve.group(1))
        if montant and 10 <= montant <= 50_000:
            return {"montant": montant, "origine": "montant annoncé",
                    "incertain": False}

    journalier = TARIF_JOURNALIER.search(texte)
    if journalier:
        tarif = _nombre(journalier.group(1))
        if tarif and 1 <= tarif <= 500:
            return {"montant": round(tarif * JOURS_AVANT_ENLEVEMENT, 2),
                    "origine": f"{tarif:.0f} €/jour sur {JOURS_AVANT_ENLEVEMENT} jours",
                    "incertain": True}

    if MENTION_GARDE.search(texte):
        return {"montant": None, "origine": "frais annoncés sans montant",
                "incertain": True}
    return {"montant": 0.0, "origine": "aucune mention", "incertain": False}


def rapatriement(region: str | None, description: str | None,
                 non_roulant: bool = False) -> dict:
    """Coût d'acheminement du lot jusqu'au domicile de l'acheteur."""
    distance = DISTANCES.get(region or "", DISTANCE_INCONNUE)
    sur_plateau = bool(PLATEAU.search(description or "")) or non_roulant

    if sur_plateau:
        montant = max(PLATEAU_MINIMUM, distance * COUT_KM_PLATEAU)
        mode = "plateau"
    else:
        montant = distance * COUT_KM_ROUTE
        mode = "par la route"

    return {"montant": round(montant), "mode": mode, "distance_km": distance,
            "region_connue": region in DISTANCES}


def carte_grise(puissance_fiscale: float | None, energie: str | None = None) -> dict:
    """Coût du certificat d'immatriculation, à la puissance fiscale."""
    if not puissance_fiscale:
        return {"montant": None, "origine": "puissance fiscale inconnue"}

    montant = puissance_fiscale * TARIF_CHEVAL_FISCAL
    propre = bool(energie and re.search(r"hybride|électrique|e85|gpl", energie, re.I))
    if propre and ABATTEMENT_ENERGIE_PROPRE:
        montant *= 1 - ABATTEMENT_ENERGIE_PROPRE
    return {"montant": round(montant),
            "origine": f"{puissance_fiscale:.0f} CV × {TARIF_CHEVAL_FISCAL:.2f} €"}


def cout_annexe(lot: dict) -> dict:
    """Somme des frais qui s'ajoutent au prix d'adjudication.

    ``incertain`` signale qu'au moins un poste n'a pas pu être chiffré : le
    total est alors un minimum, pas une prévision.
    """
    description = lot.get("description")
    garde = frais_garde(description)
    transport = rapatriement(lot.get("region"), description,
                             bool(lot.get("non_roulant")))
    immatriculation = carte_grise(lot.get("puissance_fiscale"), lot.get("carburant"))

    postes = {
        "garde": garde["montant"],
        "rapatriement": transport["montant"],
        "carte_grise": immatriculation["montant"],
    }
    connus = [v for v in postes.values() if v is not None]
    manquants = [nom for nom, v in postes.items() if v is None]

    return {
        "total": round(sum(connus)),
        "postes": postes,
        "detail": {"garde": garde["origine"], "rapatriement": transport["mode"],
                   "distance_km": transport["distance_km"],
                   "carte_grise": immatriculation["origine"]},
        "incertain": bool(manquants) or garde["incertain"],
        "postes_non_chiffres": manquants,
    }
