"""Classification fine de la motorisation.

L'énergie annoncée dans le descriptif ne suffit pas : une Yaris Hybrid y est
souvent déclarée « Essence », et rien ne distingue un hybride essence d'un
hybride diesel — alors que ce sont deux véhicules très différents à l'achat.

La classification croise donc trois sources, de la plus sûre à la plus
indirecte :

1. **la mention explicite** du descriptif (« Gazole / électricité (hybride) ») ;
2. **le code moteur**, qui tranche sans ambiguïté : HDi, dCi, TDI, CDI, D-4D
   sont des diesels ; VVTi, HSD, PureTech, TCe, THP des essences ;
3. **le modèle**, en dernier recours, pour les gammes dont la motorisation est
   connue (aucune Toyota hybride vendue en France n'est diesel).

Rien n'est deviné : sans indice, la fonction renvoie « Hybride, base
indéterminée » plutôt qu'un classement arbitraire.
"""
from __future__ import annotations

import re

# --- Nature de la motorisation ---------------------------------------------
# Attention à l'ordre : « E-Tech Electric » est un électrique pur, alors que
# « E-Tech Hybrid » est un hybride. Le plus spécifique est testé en premier.
ELECTRIQUE_PUR = re.compile(
    r"\be-?tech\s+electric\b|\bev\d{2}\b|\bz\.?e\.?\b|électrique\s+pur|"
    r"\be-208\b|\be-2008\b|\be-expert\b|\bzo[eé]\b|\bleaf\b|\bid\.?[34]\b", re.I)
# « e-tech » exige ses frontières de mot : sans elles, le motif capture
# « PureTech », un moteur essence classique de Peugeot et Citroën, et classe
# des 208 ou 308 ordinaires en hybrides. Même prudence pour « e-power ».
HYBRIDE = re.compile(
    r"hybri|\bhsd\b|\be-?tech\b|\be-?power\b|\b\d{3}h\b(?!\w)", re.I)
# Le descriptif écrit aussi bien « hybride rechargeable » que « hybride NON
# rechargeable » : chercher « rechargeable » seul inverse le sens une fois sur
# deux. La négation est donc détectée d'abord et l'emporte.
NON_RECHARGEABLE = re.compile(r"non[\s-]*rechargeable", re.I)
RECHARGEABLE = re.compile(r"plug-?in|rechargeable|\bphev\b|\be-?hybrid\b", re.I)


def _est_rechargeable(texte: str) -> bool:
    if NON_RECHARGEABLE.search(texte):
        return False
    return bool(RECHARGEABLE.search(texte))

# --- Codes moteur : l'indice le plus fiable --------------------------------
MOTEUR_DIESEL = re.compile(
    r"\bhdi\b|\bbluehdi\b|\bdci\b|\btdi\b|\bcdi\b|\bd-?4d\b|\bcrdi\b|\bjtd\b|"
    r"\bmultijet\b|\bdtec\b|\btdci\b|\bcdti\b|\bbitdi\b|\bskyactiv-?d\b|\bdid\b",
    re.I)
MOTEUR_ESSENCE = re.compile(
    r"\bvvt-?i\b|\bhsd\b|\bpuretech\b|\btce\b|\bthp\b|\bvti\b|\btsi\b|\btfsi\b|"
    r"\bmpi\b|\bfsi\b|\bgdi\b|\bvvt\b|\becoboost\b|\bskyactiv-?g\b|\bfirefly\b",
    re.I)

# --- Gammes dont la motorisation hybride est connue ------------------------
# Toyota et Lexus n'ont jamais commercialisé d'hybride diesel en France.
HYBRIDE_ESSENCE_CERTAIN = re.compile(
    r"\btoyota\b|\blexus\b|\btoyata\b|\byaris\b|\bauris\b|\bprius\b|\bc-?hr\b|"
    r"\bcorolla\b|\brav4\b|\bcamry\b|\bhonda\b|\bjazz\b|\bcr-?z\b|\bkia\b|"
    r"\bniro\b|\bioniq\b|\bclio e-?tech\b|\bcaptur e-?tech\b", re.I)
# Hybrides diesel commercialisés en France.
HYBRIDE_DIESEL_CONNU = re.compile(
    r"hybrid4|\b3008 hybrid\b|\b508 rxh\b|\bds5 hybrid\b|\bc300h\b|\be300h\b|"
    r"\bc350h\b|\bv60 (?:plug-?in )?hybrid\b|\bxc90 d5 twin\b", re.I)

ESSENCE_SIMPLE = re.compile(r"\bessence\b|\bsp\s?9[58]\b", re.I)
DIESEL_SIMPLE = re.compile(r"\bgazole\b|\bgasoil\b|\bdiesel\b", re.I)


def classer(intitule: str | None, description: str | None,
            energie_declaree: str | None = None) -> dict:
    """Détermine la motorisation à partir du titre et du descriptif.

    Retourne ``{"energie", "hybride", "base_hybride", "rechargeable",
    "indice"}`` — ``indice`` nommant la source qui a permis de trancher.
    """
    texte = " ".join(filter(None, [intitule, description]))
    resultat = {"hybride": False, "base_hybride": None,
                "rechargeable": False, "indice": None}

    if not texte.strip():
        resultat["energie"] = energie_declaree
        return resultat

    # 1. Électrique pur — à écarter avant toute recherche d'hybride, « E-Tech »
    #    désignant chez Renault aussi bien l'un que l'autre.
    if ELECTRIQUE_PUR.search(texte) and not HYBRIDE.search(
            ELECTRIQUE_PUR.sub("", texte)):
        resultat.update(energie="Électrique", indice="mention électrique")
        return resultat

    if not HYBRIDE.search(texte):
        if DIESEL_SIMPLE.search(texte):
            resultat.update(energie="Gazole", indice="mention descriptif")
        elif ESSENCE_SIMPLE.search(texte):
            resultat.update(energie="Essence", indice="mention descriptif")
        elif MOTEUR_DIESEL.search(texte):
            resultat.update(energie="Gazole", indice="code moteur")
        elif MOTEUR_ESSENCE.search(texte):
            resultat.update(energie="Essence", indice="code moteur")
        else:
            resultat["energie"] = energie_declaree
            resultat["indice"] = "énergie déclarée" if energie_declaree else None
        return resultat

    # 2. Hybride : reste à établir sur quelle base thermique.
    resultat["hybride"] = True
    resultat["rechargeable"] = _est_rechargeable(texte)

    if HYBRIDE_DIESEL_CONNU.search(texte):
        base, indice = "Gazole", "modèle hybride diesel connu"
    elif re.search(r"gazole\s*/\s*[ée]lectricit[ée]|diesel.{0,12}hybride", texte, re.I):
        base, indice = "Gazole", "mention explicite"
    elif MOTEUR_DIESEL.search(texte):
        base, indice = "Gazole", "code moteur diesel"
    elif MOTEUR_ESSENCE.search(texte):
        base, indice = "Essence", "code moteur essence"
    elif HYBRIDE_ESSENCE_CERTAIN.search(texte):
        base, indice = "Essence", "gamme hybride essence"
    elif ESSENCE_SIMPLE.search(texte):
        base, indice = "Essence", "mention descriptif"
    elif DIESEL_SIMPLE.search(texte):
        base, indice = "Gazole", "mention descriptif"
    else:
        base, indice = None, "base indéterminée"

    resultat["base_hybride"] = base
    resultat["indice"] = indice

    suffixe = " rechargeable" if resultat["rechargeable"] else ""
    if base == "Essence":
        resultat["energie"] = f"Hybride essence{suffixe}"
    elif base == "Gazole":
        resultat["energie"] = f"Hybride diesel{suffixe}"
    else:
        resultat["energie"] = f"Hybride{suffixe}, base indéterminée"
    return resultat
