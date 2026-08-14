"""Reprise d'une session de navigation à partir d'un fichier HAR.

L'API du site est protégée par un contrôle anti-robot qui ne se valide qu'en
exécutant du JavaScript : une requête HTTP nue reçoit en boucle une page de
redirection à jeton. En repartant des cookies d'une session de navigation
réelle (export HAR depuis le navigateur), on rejoue les appels GraphQL
directement, sans navigateur.

Les cookies de session expirent vite (PHPSESSID : une heure) : le HAR doit
être récent.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from urllib.parse import urlparse

log = logging.getLogger(__name__)

ENTETES_UTILES = {"user-agent", "store", "accept-language", "referer", "origin",
                  "authorization", "x-requested-with"}


def lire_har(chemin: str | Path) -> dict:
    """Extrait cookies et en-têtes exploitables d'un export HAR.

    Retourne ``{"cookies": "a=1; b=2", "entetes": {...}, "hote": "..."}``.
    """
    charge = json.loads(Path(chemin).read_text(encoding="utf-8"))
    entrees = charge.get("log", {}).get("entries", [])
    if not entrees:
        raise ValueError("HAR vide : aucune requête enregistrée")

    cookies: dict[str, str] = {}
    entetes: dict[str, str] = {}
    hote = None
    appels_api = 0

    for entree in entrees:
        requete = entree.get("request", {})
        url = requete.get("url", "")
        if "encheres-domaine.gouv.fr" not in url:
            continue
        hote = hote or urlparse(url).netloc
        if "graphql" in url:
            appels_api += 1

        for cookie in requete.get("cookies", []):
            if cookie.get("name"):
                cookies[cookie["name"]] = cookie.get("value", "")

        for entete in requete.get("headers", []):
            nom = entete.get("name", "").lower()
            if nom == "cookie":
                for morceau in entete.get("value", "").split(";"):
                    if "=" in morceau:
                        cle, _, valeur = morceau.strip().partition("=")
                        cookies.setdefault(cle, valeur)
            elif nom in ENTETES_UTILES and entete.get("value"):
                entetes.setdefault(nom, entete["value"])

        # Cookies posés par les réponses : les plus récents priment.
        for cookie in entree.get("response", {}).get("cookies", []):
            if cookie.get("name"):
                cookies[cookie["name"]] = cookie.get("value", "")

    if not cookies:
        raise ValueError("aucun cookie trouvé dans le HAR — l'export a-t-il été "
                         "réalisé avec l'option « contenu sensible » activée ?")

    log.info("HAR lu : %d cookies (%s), %d appels API, %d requêtes",
             len(cookies), ", ".join(sorted(cookies)), appels_api, len(entrees))

    return {
        "cookies": "; ".join(f"{cle}={valeur}" for cle, valeur in cookies.items()),
        "entetes": entetes,
        "hote": hote,
        "appels_api": appels_api,
    }


def appliquer(client, chemin: str | Path) -> dict:
    """Injecte la session HAR dans un ``DomaineClient``."""
    session = lire_har(chemin)
    client.entetes["Cookie"] = session["cookies"]
    for nom, valeur in session["entetes"].items():
        # Reprendre l'empreinte du navigateur d'origine (User-Agent en tête) :
        # le contrôle anti-robot lie le cookie à cette empreinte.
        client.entetes[nom.title() if nom != "store" else "store"] = valeur
    client._amorce_faite = True     # la session est déjà établie
    return session
