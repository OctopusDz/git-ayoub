"""Coût de revient d'un lot, au-delà du prix d'adjudication.

Le prix marteau n'est qu'une partie de la dépense. Les postes ci-dessous sont
les tarifs réels de l'acheteur, qui part d'Île-de-France :

* les **frais de vente** de la plateforme — 11 % du prix d'adjudication ;
* le **plateau** pour sortir le véhicule du parc — 300 € de location, au-delà
  de 200 km un supplément kilométrique ;
* la **carte grise** — 150 € pour un hybride ;
* les **frais de garde** du fourriériste : l'acheteur sait qu'il dépassera de
  deux jours environ, soit 100 € quand l'annonce n'affiche pas de montant ;
* le **déplacement** (train + repas) pour aller chercher le véhicule, de 20 €
  en Île-de-France à 90 € à l'autre bout du pays.

Ce qui est lu dans l'annonce prime toujours sur le forfait : un montant de
garde chiffré remplace l'hypothèse des deux jours.

Tous les tarifs sont rassemblés en tête de fichier pour être ajustés d'une
seule main quand les prix bougent.
"""
from __future__ import annotations

import re

# --- Paramètres ajustables --------------------------------------------------
DEPART = "Île-de-France"          # d'où part l'acheteur

# Location d'un plateau pour sortir le véhicule du parc. Forfait négocié par
# l'acheteur, valable pour un aller-retour de proximité ; au-delà, le loueur
# facture la distance.
PLATEAU_FORFAIT = 300.0
PLATEAU_KM_INCLUS = 200
PLATEAU_KM_SUPPLEMENT = 0.80

# Retour par la route quand le véhicule roule et dispose de ses papiers :
# carburant et péage seulement.
COUT_KM_ROUTE = 0.30

# Carte grise d'un hybride, forfait constaté par l'acheteur.
CARTE_GRISE_HYBRIDE = 150.0
# Repli pour les autres énergies, au cheval fiscal (tarif Île-de-France).
TARIF_CHEVAL_FISCAL = 54.95

# Garde du fourriériste. Quand l'annonce mentionne des frais sans les chiffrer,
# l'acheteur table sur deux jours de dépassement.
GARDE_DEPASSEMENT_FORFAIT = 100.0
# Quand l'annonce affiche un tarif journalier, on chiffre ce même dépassement.
JOURS_AVANT_ENLEVEMENT = 2

# Déplacement de l'acheteur (train aller + repas), par tranche de distance.
# Le premier palier couvre l'Île-de-France : transports locaux, pas de train.
PALIERS_DEPLACEMENT = [(60, 20.0), (200, 45.0), (400, 70.0), (10_000, 90.0)]

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
    r"|s['’]?[ée]levant\s+[àa]\s*)([\d\s ]{2,9}(?:[,.]\d{1,2})?)\s*€", re.I)
TARIF_JOURNALIER = re.compile(
    r"([\d\s ]{1,6}(?:[,.]\d{1,2})?)\s*€\s*(?:ttc\s*)?/\s*jour", re.I)
MENTION_GARDE = re.compile(r"frais de (?:garde|gardiennage)|fourri[èe]riste", re.I)
PLATEAU = re.compile(r"plateau", re.I)


def _nombre(brut: str) -> float | None:
    try:
        return float(brut.replace(" ", "").replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def distance_km(region: str | None) -> int:
    """Distance routière approximative depuis le domicile de l'acheteur."""
    return DISTANCES.get(region or "", DISTANCE_INCONNUE)


def frais_garde(description: str | None) -> dict:
    """Frais de garde à prévoir, lus dans l'annonce.

    Trois cas, du plus sûr au plus incertain : un montant est affiché, un tarif
    journalier l'est, ou l'annonce se contente de mentionner des frais. Dans ce
    dernier cas le forfait de dépassement s'applique, mais ``incertain`` reste
    vrai : le total affiché n'est qu'un plancher.
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
        return {"montant": GARDE_DEPASSEMENT_FORFAIT,
                "origine": "frais annoncés sans montant — 2 jours de dépassement",
                "incertain": True}
    return {"montant": 0.0, "origine": "aucune mention", "incertain": False}


def rapatriement(region: str | None, description: str | None,
                 non_roulant: bool = False, sans_carte_grise: bool = False) -> dict:
    """Coût d'acheminement du lot jusqu'au domicile de l'acheteur.

    Le plateau s'impose dès que l'annonce l'exige, que le véhicule ne roule pas
    ou qu'il lui manque ses papiers — sans carte grise, un retour par la route
    n'est pas légal.
    """
    distance = distance_km(region)
    sur_plateau = (bool(PLATEAU.search(description or ""))
                   or non_roulant or sans_carte_grise)

    if sur_plateau:
        montant = PLATEAU_FORFAIT
        if distance > PLATEAU_KM_INCLUS:
            montant += (distance - PLATEAU_KM_INCLUS) * PLATEAU_KM_SUPPLEMENT
        mode = "plateau"
    else:
        montant = distance * COUT_KM_ROUTE
        mode = "par la route"

    return {"montant": round(montant), "mode": mode, "distance_km": distance,
            "region_connue": region in DISTANCES}


def deplacement(region: str | None) -> dict:
    """Aller de l'acheteur pour récupérer le véhicule : train et repas."""
    distance = distance_km(region)
    for limite, montant in PALIERS_DEPLACEMENT:
        if distance <= limite:
            return {"montant": montant, "distance_km": distance}
    return {"montant": PALIERS_DEPLACEMENT[-1][1], "distance_km": distance}


def carte_grise(puissance_fiscale: float | None, energie: str | None = None) -> dict:
    """Coût du certificat d'immatriculation."""
    hybride = bool(energie and re.search(r"hybride|électrique", energie, re.I))
    if hybride:
        return {"montant": CARTE_GRISE_HYBRIDE, "origine": "forfait hybride"}
    if not puissance_fiscale:
        return {"montant": CARTE_GRISE_HYBRIDE,
                "origine": "puissance fiscale inconnue, forfait retenu"}
    montant = puissance_fiscale * TARIF_CHEVAL_FISCAL
    return {"montant": round(montant),
            "origine": f"{puissance_fiscale:.0f} CV × {TARIF_CHEVAL_FISCAL:.2f} €"}


def cout_annexe(lot: dict) -> dict:
    """Somme des frais qui s'ajoutent au prix d'adjudication.

    ``incertain`` signale que la garde repose sur une hypothèse plutôt que sur
    un montant annoncé : le total est alors un plancher, pas une prévision.
    """
    description = lot.get("description")
    garde = frais_garde(description)
    transport = rapatriement(lot.get("region"), description,
                             bool(lot.get("non_roulant")),
                             bool(lot.get("sans_carte_grise")))
    trajet = deplacement(lot.get("region"))
    immatriculation = carte_grise(lot.get("puissance_fiscale"), lot.get("carburant"))

    postes = {
        "garde": garde["montant"],
        "rapatriement": transport["montant"],
        "deplacement": trajet["montant"],
        "carte_grise": immatriculation["montant"],
    }
    connus = [v for v in postes.values() if v is not None]
    manquants = [nom for nom, v in postes.items() if v is None]

    return {
        "total": round(sum(connus)),
        "postes": postes,
        "detail": {"garde": garde["origine"], "rapatriement": transport["mode"],
                   "distance_km": transport["distance_km"],
                   "deplacement": f"train et repas, {trajet['distance_km']} km",
                   "carte_grise": immatriculation["origine"]},
        "incertain": bool(manquants) or garde["incertain"],
        "postes_non_chiffres": manquants,
    }
