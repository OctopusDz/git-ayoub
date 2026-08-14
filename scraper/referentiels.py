"""Référentiels métier : marques, énergies, départements, régions, tranches.

Ces tables servent au nettoyage et à l'enrichissement des lots afin de
construire des dimensions d'analyse propres (le cube ne vaut que ce que valent
ses dimensions).
"""
from __future__ import annotations

# --- Marques automobiles (détection dans les titres en texte libre) ---------
MARQUES = [
    "ALFA ROMEO", "ASTON MARTIN", "AUDI", "BMW", "CHEVROLET", "CHRYSLER",
    "CITROEN", "CITROËN", "CUPRA", "DACIA", "DAEWOO", "DAIHATSU", "DODGE",
    "DS", "FIAT", "FORD", "HONDA", "HYUNDAI", "INFINITI", "ISUZU", "IVECO",
    "JAGUAR", "JEEP", "KIA", "LADA", "LANCIA", "LAND ROVER", "LEXUS",
    "MAHINDRA", "MASERATI", "MAZDA", "MERCEDES", "MERCEDES-BENZ", "MG",
    "MINI", "MITSUBISHI", "NISSAN", "OPEL", "PEUGEOT", "PORSCHE", "RENAULT",
    "ROVER", "SAAB", "SEAT", "SKODA", "SMART", "SSANGYONG", "SUBARU",
    "SUZUKI", "TESLA", "TOYOTA", "VOLKSWAGEN", "VOLVO", "VW",
]

# Formes canoniques (le libellé retenu dans le cube).
ALIAS_MARQUES = {
    "CITROËN": "CITROEN",
    "VW": "VOLKSWAGEN",
    "MERCEDES": "MERCEDES-BENZ",
    "LAND-ROVER": "LAND ROVER",
}

# --- Énergies ---------------------------------------------------------------
ALIAS_CARBURANT = {
    "go": "Diesel", "gazole": "Diesel", "gasoil": "Diesel", "diesel": "Diesel",
    "dci": "Diesel", "hdi": "Diesel", "tdi": "Diesel",
    "es": "Essence", "essence": "Essence", "sp95": "Essence", "sp98": "Essence",
    "eh": "Hybride essence", "hybride": "Hybride", "hybride essence": "Hybride essence",
    "hybride rechargeable": "Hybride rechargeable", "phev": "Hybride rechargeable",
    "el": "Électrique", "electrique": "Électrique", "électrique": "Électrique",
    "ev": "Électrique",
    "gpl": "GPL", "gnv": "GNV", "gaz": "GPL",
}

ALIAS_BOITE = {
    "ba": "Automatique", "auto": "Automatique", "automatique": "Automatique",
    "bva": "Automatique", "edc": "Automatique", "dsg": "Automatique",
    "bm": "Manuelle", "manuelle": "Manuelle", "mecanique": "Manuelle",
    "mécanique": "Manuelle", "bvm": "Manuelle",
}

# --- Départements -> (nom, région) -----------------------------------------
DEPARTEMENTS = {
    "01": ("Ain", "Auvergne-Rhône-Alpes"), "02": ("Aisne", "Hauts-de-France"),
    "03": ("Allier", "Auvergne-Rhône-Alpes"), "04": ("Alpes-de-Haute-Provence", "Provence-Alpes-Côte d'Azur"),
    "05": ("Hautes-Alpes", "Provence-Alpes-Côte d'Azur"), "06": ("Alpes-Maritimes", "Provence-Alpes-Côte d'Azur"),
    "07": ("Ardèche", "Auvergne-Rhône-Alpes"), "08": ("Ardennes", "Grand Est"),
    "09": ("Ariège", "Occitanie"), "10": ("Aube", "Grand Est"),
    "11": ("Aude", "Occitanie"), "12": ("Aveyron", "Occitanie"),
    "13": ("Bouches-du-Rhône", "Provence-Alpes-Côte d'Azur"), "14": ("Calvados", "Normandie"),
    "15": ("Cantal", "Auvergne-Rhône-Alpes"), "16": ("Charente", "Nouvelle-Aquitaine"),
    "17": ("Charente-Maritime", "Nouvelle-Aquitaine"), "18": ("Cher", "Centre-Val de Loire"),
    "19": ("Corrèze", "Nouvelle-Aquitaine"), "2A": ("Corse-du-Sud", "Corse"),
    "2B": ("Haute-Corse", "Corse"), "21": ("Côte-d'Or", "Bourgogne-Franche-Comté"),
    "22": ("Côtes-d'Armor", "Bretagne"), "23": ("Creuse", "Nouvelle-Aquitaine"),
    "24": ("Dordogne", "Nouvelle-Aquitaine"), "25": ("Doubs", "Bourgogne-Franche-Comté"),
    "26": ("Drôme", "Auvergne-Rhône-Alpes"), "27": ("Eure", "Normandie"),
    "28": ("Eure-et-Loir", "Centre-Val de Loire"), "29": ("Finistère", "Bretagne"),
    "30": ("Gard", "Occitanie"), "31": ("Haute-Garonne", "Occitanie"),
    "32": ("Gers", "Occitanie"), "33": ("Gironde", "Nouvelle-Aquitaine"),
    "34": ("Hérault", "Occitanie"), "35": ("Ille-et-Vilaine", "Bretagne"),
    "36": ("Indre", "Centre-Val de Loire"), "37": ("Indre-et-Loire", "Centre-Val de Loire"),
    "38": ("Isère", "Auvergne-Rhône-Alpes"), "39": ("Jura", "Bourgogne-Franche-Comté"),
    "40": ("Landes", "Nouvelle-Aquitaine"), "41": ("Loir-et-Cher", "Centre-Val de Loire"),
    "42": ("Loire", "Auvergne-Rhône-Alpes"), "43": ("Haute-Loire", "Auvergne-Rhône-Alpes"),
    "44": ("Loire-Atlantique", "Pays de la Loire"), "45": ("Loiret", "Centre-Val de Loire"),
    "46": ("Lot", "Occitanie"), "47": ("Lot-et-Garonne", "Nouvelle-Aquitaine"),
    "48": ("Lozère", "Occitanie"), "49": ("Maine-et-Loire", "Pays de la Loire"),
    "50": ("Manche", "Normandie"), "51": ("Marne", "Grand Est"),
    "52": ("Haute-Marne", "Grand Est"), "53": ("Mayenne", "Pays de la Loire"),
    "54": ("Meurthe-et-Moselle", "Grand Est"), "55": ("Meuse", "Grand Est"),
    "56": ("Morbihan", "Bretagne"), "57": ("Moselle", "Grand Est"),
    "58": ("Nièvre", "Bourgogne-Franche-Comté"), "59": ("Nord", "Hauts-de-France"),
    "60": ("Oise", "Hauts-de-France"), "61": ("Orne", "Normandie"),
    "62": ("Pas-de-Calais", "Hauts-de-France"), "63": ("Puy-de-Dôme", "Auvergne-Rhône-Alpes"),
    "64": ("Pyrénées-Atlantiques", "Nouvelle-Aquitaine"), "65": ("Hautes-Pyrénées", "Occitanie"),
    "66": ("Pyrénées-Orientales", "Occitanie"), "67": ("Bas-Rhin", "Grand Est"),
    "68": ("Haut-Rhin", "Grand Est"), "69": ("Rhône", "Auvergne-Rhône-Alpes"),
    "70": ("Haute-Saône", "Bourgogne-Franche-Comté"), "71": ("Saône-et-Loire", "Bourgogne-Franche-Comté"),
    "72": ("Sarthe", "Pays de la Loire"), "73": ("Savoie", "Auvergne-Rhône-Alpes"),
    "74": ("Haute-Savoie", "Auvergne-Rhône-Alpes"), "75": ("Paris", "Île-de-France"),
    "76": ("Seine-Maritime", "Normandie"), "77": ("Seine-et-Marne", "Île-de-France"),
    "78": ("Yvelines", "Île-de-France"), "79": ("Deux-Sèvres", "Nouvelle-Aquitaine"),
    "80": ("Somme", "Hauts-de-France"), "81": ("Tarn", "Occitanie"),
    "82": ("Tarn-et-Garonne", "Occitanie"), "83": ("Var", "Provence-Alpes-Côte d'Azur"),
    "84": ("Vaucluse", "Provence-Alpes-Côte d'Azur"), "85": ("Vendée", "Pays de la Loire"),
    "86": ("Vienne", "Nouvelle-Aquitaine"), "87": ("Haute-Vienne", "Nouvelle-Aquitaine"),
    "88": ("Vosges", "Grand Est"), "89": ("Yonne", "Bourgogne-Franche-Comté"),
    "90": ("Territoire de Belfort", "Bourgogne-Franche-Comté"), "91": ("Essonne", "Île-de-France"),
    "92": ("Hauts-de-Seine", "Île-de-France"), "93": ("Seine-Saint-Denis", "Île-de-France"),
    "94": ("Val-de-Marne", "Île-de-France"), "95": ("Val-d'Oise", "Île-de-France"),
    "971": ("Guadeloupe", "Guadeloupe"), "972": ("Martinique", "Martinique"),
    "973": ("Guyane", "Guyane"), "974": ("La Réunion", "La Réunion"),
    "976": ("Mayotte", "Mayotte"),
}

NOM_VERS_CODE = {nom.lower(): code for code, (nom, _) in DEPARTEMENTS.items()}

# --- Tranches d'analyse (dimensions ordinales du cube) ---------------------
TRANCHES_KM = [
    (0, 20_000, "0 – 20 000 km"),
    (20_000, 50_000, "20 – 50 000 km"),
    (50_000, 100_000, "50 – 100 000 km"),
    (100_000, 150_000, "100 – 150 000 km"),
    (150_000, 200_000, "150 – 200 000 km"),
    (200_000, 300_000, "200 – 300 000 km"),
    (300_000, float("inf"), "300 000 km et +"),
]

TRANCHES_PRIX = [
    (0, 500, "< 500 €"),
    (500, 1_000, "500 – 1 000 €"),
    (1_000, 2_500, "1 000 – 2 500 €"),
    (2_500, 5_000, "2 500 – 5 000 €"),
    (5_000, 10_000, "5 000 – 10 000 €"),
    (10_000, 20_000, "10 000 – 20 000 €"),
    (20_000, float("inf"), "20 000 € et +"),
]

TRANCHES_AGE = [
    (0, 3, "0 – 3 ans"),
    (3, 6, "3 – 6 ans"),
    (6, 10, "6 – 10 ans"),
    (10, 15, "10 – 15 ans"),
    (15, 20, "15 – 20 ans"),
    (20, float("inf"), "20 ans et +"),
]


def tranche(valeur, table) -> str | None:
    """Range une valeur numérique dans la bonne tranche (borne haute exclue)."""
    if valeur is None:
        return None
    for mini, maxi, libelle in table:
        if mini <= valeur < maxi:
            return libelle
    return None


def ordre_tranches(table) -> list[str]:
    """Ordre d'affichage d'une dimension ordinale."""
    return [libelle for _, _, libelle in table]
