"""Transport HTTP du collecteur.

Le site protège son API par un contrôle anti-robot : un appel reçoit une page
``window.location.href='/redirect_<jeton>/…'`` au lieu du JSON. Demander cette
URL à jeton valide le cookie, après quoi il faut **redemander la ressource**.

Deux facteurs décident du taux de réussite, mesurés sur cinq pages :

* **la connexion doit rester ouverte** d'un appel à l'autre. Une session
  ``requests`` réutilise la connexion TCP/TLS, comme un navigateur ; relancer
  un processus curl par requête rouvre une poignée de main à chaque fois et se
  fait refouler bien plus souvent — 5/5 pages contre 2/4 ;
* **le challenge doit être résolu à chaque appel**, pas seulement à
  l'amorçage : sans cela, seule la première page passe (1/5).

``requests`` est donc utilisé quand il est présent, avec repli sur la
bibliothèque standard — au prix d'un taux de réussite plus faible.
"""
from __future__ import annotations

import gzip
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
import zlib
from http.cookiejar import CookieJar

from . import config

log = logging.getLogger(__name__)

REDIRECTION_JS = re.compile(r"window\.location\.href\s*=\s*'([^']+)'")
MAX_CHALLENGES = 6

# En-têtes d'un navigateur ordinaire. L'absence d'« Origin » est délibérée :
# sa présence fait basculer le serveur en traitement CORS et le challenge ne
# se résout plus.
ENTETES = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "User-Agent": config.USER_AGENT,
    "Referer": config.PAGE_CATEGORIE,
    "store": config.STORE,
    "x-magento-cache-id": config.MAGENTO_CACHE_ID,
}


class Transport:
    """Interface commune : ``get(url) -> bytes``, cookies conservés."""

    def get(self, url: str) -> bytes:  # pragma: no cover - interface
        raise NotImplementedError

    def fermer(self) -> None:
        pass


class TransportRequests(Transport):
    """Session HTTP persistante — la connexion reste ouverte entre les appels."""

    def __init__(self, entetes: dict[str, str]):
        try:
            import requests
        except ImportError as exc:                       # pragma: no cover
            raise RuntimeError("requests n'est pas installé") from exc
        self.session = requests.Session()
        self.session.headers.update(entetes)

    def get(self, url: str) -> bytes:
        reponse = self.session.get(url, timeout=config.REQUEST_TIMEOUT)
        reponse.raise_for_status()
        return reponse.content

    def fermer(self) -> None:
        try:
            self.session.close()
        except Exception:
            pass


class TransportUrllib(Transport):
    """Repli en bibliothèque standard, sans connexion persistante."""

    def __init__(self, entetes: dict[str, str]):
        self.entetes = entetes
        self.cookies = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies))

    def get(self, url: str) -> bytes:
        requete = urllib.request.Request(url, headers=self.entetes)
        with self.opener.open(requete, timeout=config.REQUEST_TIMEOUT) as reponse:
            brut = reponse.read()
            encodage = (reponse.headers.get("Content-Encoding") or "").lower()
        if encodage == "gzip":
            return gzip.decompress(brut)
        if encodage == "deflate":
            return zlib.decompress(brut, -zlib.MAX_WBITS)
        return brut


def creer(entetes: dict[str, str] | None = None, prefere: str = "auto") -> Transport:
    """Choisit le transport : session persistante si possible."""
    entetes = {**ENTETES, **(entetes or {})}
    if prefere in ("auto", "requests"):
        try:
            return TransportRequests(entetes)
        except RuntimeError as exc:
            if prefere == "requests":
                raise
            log.info("requests indisponible (%s) — repli sur urllib, "
                     "taux de réussite moindre", exc)
    return TransportUrllib(entetes)


def amorcer_session(transport: Transport) -> bool:
    """Valide la session sur la page d'accueil.

    Ce premier passage pose les cookies du contrôle anti-robot. Il ne dispense
    pas de résoudre le challenge sur les appels suivants.
    """
    try:
        corps = transport.get(config.BASE_URL)
    except Exception as exc:
        log.warning("page d'accueil inaccessible (%s)", exc)
        return False

    trouve = REDIRECTION_JS.search(corps[:8192].decode("utf-8", "replace"))
    if not trouve:
        return True
    try:
        transport.get(urllib.parse.urljoin(config.BASE_URL,
                                           trouve.group(1).replace("&amp;", "&")))
        return True
    except Exception as exc:
        log.warning("validation de session impossible (%s)", exc)
        return False


def resoudre_challenge(transport: Transport, url: str) -> bytes:
    """Demande une URL en franchissant le contrôle anti-robot.

    Le contrôle se déroule en deux temps : la réponse porte une URL à jeton,
    et demander cette URL valide le cookie — mais renvoie la page de retour du
    site, pas la ressource. Il faut donc **redemander l'URL d'origine**, que la
    session validée sert alors normalement.
    """
    corps = transport.get(url)
    for tour in range(MAX_CHALLENGES):
        trouve = REDIRECTION_JS.search(corps[:4096].decode("utf-8", "replace"))
        if not trouve:
            return corps
        jeton = urllib.parse.urljoin(config.BASE_URL,
                                     trouve.group(1).replace("&amp;", "&"))
        log.debug("contrôle anti-robot, tour %d", tour + 1)
        transport.get(jeton)          # valide le cookie
        corps = transport.get(url)    # la ressource, cette fois
    return corps
