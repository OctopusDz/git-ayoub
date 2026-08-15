"""Lecture du descriptif technique des lots.

Le champ ``short_description`` de l'API suit une grammaire très régulière :

    RENAULT TWINGO I 1.2 i 60 Euro3, Essence, 4 places, imm. DM-900-QJ,
    type MRE1011FJ171, n° de série VF1C068AE34258952,
    1ère mise en circulation 29/07/2005, 183852 km indicatifs. 1 clé.
    Absence direction assistée… Pneumatiques HS. Choc aile AVG.

On en tire les dimensions qui n'existent pas en champ structuré dans l'API :
énergie, immatriculation, VIN, date de première mise en circulation,
kilométrage, équipement et défauts signalés.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date

# --- Énergie ----------------------------------------------------------------
ENERGIES = [
    (r"\bgazole\b|\bgasoil\b|\bdiesel\b", "Gazole"),
    (r"\bessence\b|\bsp\s?9[58]\b", "Essence"),
    (r"hybride\s+rechargeable|\bphev\b", "Hybride rechargeable"),
    (r"\bhybride\b|\bhev\b", "Hybride"),
    (r"\belectricite\b|\bélectricité\b|\belectrique\b|\bélectrique\b|\bev\b",
     "Électrique"),
    (r"\bgpl\b", "GPL"),
    (r"\bgnv\b|gaz naturel", "GNV"),
    (r"\bethanol\b|\béthanol\b|\be85\b", "Superéthanol E85"),
]

# --- Défauts et mentions d'état --------------------------------------------
# Les descriptifs de fourrière mélangent trois choses que l'acheteur ne doit
# surtout pas confondre :
#
# * des **mentions de série** — un véhicule de fourrière est sans clé et sans
#   carte grise par défaut, la formule figure sur des milliers d'annonces
#   identiques. Ce n'est pas un constat, et cela se chiffre en centaines
#   d'euros, pas en milliers ;
# * un **état non constaté** — « état de fonctionnement non connu » sur une
#   annonce sur six : le dépositaire dit qu'il n'a pas regardé. C'est un
#   risque, pas un défaut ;
# * un **défaut réellement observé** — moteur bloqué, épave, accident.
#
# Les confondre pénalisait des lots parfaitement sains : « sans clé » suffisait
# à classer un véhicule en « défaut bloquant ». Chaque catégorie est donc
# désormais distincte, et le poids sur le prix est calibré sur l'écart mesuré à
# véhicule comparable dans l'historique.

# (motif, libellé, majeur ?) — « majeur » = affecte la remise en circulation.
DEFAUTS = [
    (r"\b[ée]pave\b|destruction obligatoire|pour pi[eè]ces", "Épave / pour pièces", True),
    (r"non roulant|ne d[ée]marre pas|moteur hs|moteur bloqu[eé]", "Non roulant", True),
    (r"v[ée]hicule accident[ée]|sinistr[ée]|vgc\b|v[ée]hicule gravement", "Accidenté", True),
    (r"bo[iî]te.{0,15}hs|embrayage hs|transmission hs", "Transmission HS", True),
    (r"pneumatiques? hs|pneus? hs", "Pneumatiques HS", False),
    (r"batterie hs", "Batterie HS", False),
    (r"vitrage.{0,20}(fissur|d[ée]color)|pare-brise fissur", "Vitrage à revoir", False),
    (r"corrosion|rouille", "Corrosion", False),
    (r"fuite", "Fuite signalée", False),
    (r"distribution [àa] pr[ée]voir|imp[ée]ratif distribution", "Distribution à prévoir", False),
    (r"embrayage (?:dur|ferme|[àa] revoir)", "Embrayage à revoir", False),
    # Les chocs ne comptent que hors de la formule d'usage, traitée plus bas.
    (r"enfonc|\bcabossé|carrosserie endommag", "Carrosserie endommagée", False),
]

# Mentions de série : l'état normal d'un lot de fourrière. Informatives, avec
# leur coût réel, mesuré à véhicule comparable sur l'historique des ventes.
MENTIONS_SERIE = [
    (r"sans cl[eé]f?\b|absence de cl[eé]", "Sans clé", 300),
    (r"sans certificat d.immatriculation|absence de certificat d.immatriculation"
     r"|sans carte grise", "Sans carte grise", 150),
]

# Le dépositaire déclare ne pas savoir. Ce n'est pas un défaut : c'est une
# inconnue, qui appelle une visite plutôt qu'une décote automatique.
ETAT_NON_CONSTATE = re.compile(
    r"[ée]tat (?:de fonctionnement|m[ée]canique|g[ée]n[ée]ral) non connu"
    r"|[ée]tat non connu|fonctionnement non (?:connu|v[ée]rifi[ée])", re.I)

# Formule type décrivant l'usure ordinaire — à ne pas lire comme un accident.
USURE_ORDINAIRE = re.compile(
    r"(?:coups?|chocs?|rayures?|frottements?)[^.]{0,60}d.usage"
    r"|rayures? et frottements?", re.I)

MOTIFS = {
    "immatriculation": re.compile(
        r"imm(?:\.|atriculation)?\s*:?\s*([A-Z]{2}-\d{3}-[A-Z]{2}|\d{1,4}\s?[A-Z]{2,3}\s?\d{2,3})",
        re.I),
    "type_mines": re.compile(r"\btype\s*:?\s*([A-Z0-9]{6,20})\b", re.I),
    "vin": re.compile(r"n[°ºo]?\s*de\s*s[ée]rie\s*:?\s*([A-HJ-NPR-Z0-9]{11,17})", re.I),
    "mise_en_circulation": re.compile(
        r"1\s*[èe]?re?\s*mise\s+en\s+circulation\s*:?\s*(?:le\s+)?"
        r"(\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}/\d{4})", re.I),
    "critair": re.compile(r"crit.?air\s*(\d|e)", re.I),
    "places": re.compile(r"(\d{1,2})\s*places?\b", re.I),
    "portes": re.compile(r"(\d)\s*portes?\b", re.I),
    "cles": re.compile(r"(\d)\s*cl[eé]f?s?\b", re.I),
    "norme_euro": re.compile(r"\beuro\s?([1-6])\b", re.I),
    # « automatique » seul est ambigu (essuie-glaces, climatisation…) : on ne
    # le retient que rattaché à la boîte de vitesses.
    "boite_auto": re.compile(
        r"bo[iî]te\s*(?:de vitesses?\s*)?auto(?:matique)?|\bbva\b|s-?tronic|\bdsg\b"
        r"|\bedc\b|tiptronic|\bbv\s?a\b", re.I),
    "boite_meca": re.compile(r"bo[iî]te m[ée]canique|\bbvm\b|manuelle", re.I),
    "premiere_main": re.compile(r"1[èe]?re?\s*main", re.I),
    "controle_technique": re.compile(r"contr[oô]le technique", re.I),
    "sur_parc": re.compile(r"sur parc depuis le\s*(\d{1,2}/\d{1,2}/\d{2,4})", re.I),
    "distribution_faite": re.compile(r"distribution faite|kit distribution en", re.I),
    "revisee": re.compile(r"r[ée]vis[ée]e? (?:en|le)\b", re.I),
    "pro_seulement": re.compile(r"r[ée]serv[ée] aux professionnels", re.I),
}

# Kilométrage — du plus fiable au plus approximatif.
KM_PRIORITAIRE = [
    re.compile(r"(\d[\d\s.]{2,9})\s*km\s*(?:indicatifs?|r[ée]els?|compteur)", re.I),
    re.compile(r"km\s*[ée]lectronique[^)]*\(\s*(\d[\d\s.]{2,9})\s*km", re.I),
    re.compile(r"v[ée]hicule a\s*(\d[\d\s.]{2,9})\s*km", re.I),
    re.compile(r"compteur\D{0,20}(\d[\d\s.]{2,9})\s*km", re.I),
]
KM_TOUS = re.compile(r"(?<!\bà )(?<!\ba )(\d[\d\s.]{2,9})\s*km\b", re.I)
BALISE_HTML = re.compile(r"<[^>]+>")


def sans_accents(valeur: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", valeur)
                   if unicodedata.category(c) != "Mn")


def nettoyer_html(html: str | None) -> str:
    if not html:
        return ""
    texte = BALISE_HTML.sub(" ", html)
    texte = (texte.replace("&nbsp;", " ").replace("&amp;", "&")
                  .replace("&#039;", "'").replace("&quot;", '"')
                  .replace("’", "'"))
    return re.sub(r"\s+", " ", texte).strip()


def _entier(brut: str | None) -> int | None:
    if not brut:
        return None
    chiffres = re.sub(r"[^\d]", "", brut)
    return int(chiffres) if chiffres else None


def _date_iso(brut: str | None) -> str | None:
    if not brut:
        return None
    parties = re.split(r"[/\-.]", brut.strip())
    if len(parties) == 2:                  # « 03/2015 » : mois et année seuls
        parties = ["1", *parties]
    if len(parties) != 3:
        return None
    jour, mois, annee = (int(p) for p in parties)
    if annee < 100:
        annee += 2000 if annee <= date.today().year % 100 else 1900
    if not (1 <= mois <= 12 and 1 <= jour <= 31 and 1950 <= annee <= date.today().year + 1):
        return None
    return f"{annee:04d}-{mois:02d}-{jour:02d}"


def extraire_kilometrage(texte: str) -> tuple[int | None, str | None]:
    """Retourne (kilométrage, méthode retenue).

    Les mentions de type « distribution faite à 172 000 km » sont écartées :
    ce sont des km d'historique d'entretien, pas la valeur au compteur.
    """
    for motif in KM_PRIORITAIRE:
        trouve = motif.search(texte)
        if trouve:
            valeur = _entier(trouve.group(1))
            if valeur and 100 <= valeur <= 2_000_000:
                return valeur, "mention explicite"

    candidats = [_entier(m) for m in KM_TOUS.findall(texte)]
    candidats = [v for v in candidats if v and 100 <= v <= 2_000_000]
    if candidats:
        # Compteur remplacé : le texte cite le kilométrage réel, plus élevé.
        return max(candidats), "valeur maximale citée"
    return None, None


def extraire_energie(texte: str) -> str | None:
    plat = sans_accents(texte).lower()
    for motif, libelle in ENERGIES:
        if re.search(sans_accents(motif), plat):
            return libelle
    return None


def extraire_defauts(texte: str) -> tuple[list[str], int]:
    """Liste des défauts réellement signalés et nombre de défauts majeurs."""
    plat = sans_accents(texte).lower()
    trouves, majeurs = [], 0
    for motif, libelle, est_majeur in DEFAUTS:
        if re.search(sans_accents(motif), plat):
            trouves.append(libelle)
            if est_majeur:
                majeurs += 1

    # Un choc mentionné hors de la formule d'usage est un vrai constat.
    if re.search(r"\bchocs?\b|\bcoups?\b", plat) and not USURE_ORDINAIRE.search(texte):
        if "Carrosserie endommagée" not in trouves:
            trouves.append("Carrosserie endommagée")
    return trouves, majeurs


def extraire_mentions(texte: str) -> tuple[list[str], int]:
    """Mentions de série d'un lot de fourrière, et leur coût cumulé en euros."""
    plat = sans_accents(texte).lower()
    mentions, cout = [], 0
    for motif, libelle, prix in MENTIONS_SERIE:
        if re.search(sans_accents(motif), plat):
            mentions.append(libelle)
            cout += prix
    return mentions, cout


def analyser(short_description_html: str | None,
             description_html: str | None = None) -> dict:
    """Extrait toutes les caractéristiques lisibles du descriptif."""
    texte = nettoyer_html(short_description_html)
    complement = nettoyer_html(description_html)
    complet = f"{texte} {complement}".strip()
    if not complet:
        return {"description": None}

    infos: dict = {"description": texte or complement or None}

    for champ in ("immatriculation", "type_mines", "vin"):
        trouve = MOTIFS[champ].search(complet)
        infos[champ] = trouve.group(1).upper().strip() if trouve else None

    mec = MOTIFS["mise_en_circulation"].search(complet)
    infos["date_mise_en_circulation"] = _date_iso(mec.group(1)) if mec else None
    infos["annee"] = int(infos["date_mise_en_circulation"][:4]) \
        if infos["date_mise_en_circulation"] else None

    kilometrage, methode = extraire_kilometrage(complet)
    infos["kilometrage"] = kilometrage
    infos["kilometrage_methode"] = methode

    infos["carburant"] = extraire_energie(complet)

    for champ in ("places", "portes", "cles", "norme_euro"):
        trouve = MOTIFS[champ].search(complet)
        infos[f"nb_{champ}" if champ in ("places", "portes", "cles") else champ] = (
            _entier(trouve.group(1)) if trouve else None)

    critair = MOTIFS["critair"].search(complet)
    infos["critair"] = critair.group(1).upper() if critair else None

    if MOTIFS["boite_auto"].search(complet):
        infos["boite_vitesses"] = "Automatique"
    elif MOTIFS["boite_meca"].search(complet):
        infos["boite_vitesses"] = "Manuelle"
    else:
        infos["boite_vitesses"] = None

    infos["premiere_main"] = bool(MOTIFS["premiere_main"].search(complet))
    infos["controle_technique_mentionne"] = bool(MOTIFS["controle_technique"].search(complet))
    infos["distribution_faite"] = bool(MOTIFS["distribution_faite"].search(complet))
    infos["revision_recente"] = bool(MOTIFS["revisee"].search(complet))

    parc = MOTIFS["sur_parc"].search(complet)
    infos["date_entree_parc"] = _date_iso(parc.group(1)) if parc else None

    defauts, majeurs = extraire_defauts(complet)
    mentions, cout_mentions = extraire_mentions(complet)
    infos["defauts"] = defauts
    infos["nb_defauts"] = len(defauts)
    infos["nb_defauts_majeurs"] = majeurs
    infos["mentions_fourriere"] = mentions
    infos["cout_mentions"] = cout_mentions
    infos["sans_cle"] = "Sans clé" in mentions
    infos["sans_carte_grise"] = "Sans carte grise" in mentions
    infos["non_roulant"] = "Non roulant" in defauts or "Épave / pour pièces" in defauts
    infos["etat_non_constate"] = bool(ETAT_NON_CONSTATE.search(complet))
    infos["usure_ordinaire"] = bool(USURE_ORDINAIRE.search(complet))

    # La gravité ne retient que ce qui a été réellement observé. Un lot dont
    # l'état n'a pas été vérifié n'est pas sain pour autant : il est marqué
    # comme tel, pour appeler une visite plutôt qu'une confiance aveugle.
    if majeurs >= 2:
        infos["gravite"] = "Défauts majeurs"
    elif majeurs == 1:
        infos["gravite"] = "Défaut bloquant isolé"
    elif defauts:
        infos["gravite"] = "Défauts d'usage"
    elif infos["etat_non_constate"]:
        infos["gravite"] = "État non constaté"
    else:
        infos["gravite"] = "Aucun défaut signalé"

    return infos
