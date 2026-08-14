"""Transport HTTP du collecteur.

Le site protège son API par un contrôle anti-robot : le premier appel reçoit
une page ``window.location.href='/redirect_<jeton>/…'``. Demander cette URL à
jeton renvoie une redirection HTTP vers la réponse JSON — mais pas toujours du
premier coup : le contrôle se réarme parfois et fournit un nouveau jeton. La
résolution est donc une boucle, pas un aller-retour.

Deux transports sont disponibles :

* **curl** (par défaut) — présent sur macOS, Linux et Windows 10+, il négocie
  HTTP/2 et maintient la connexion, ce que le contrôle attend ;
* **urllib** — repli en bibliothèque standard pure, qui résout le challenge
  moins souvent.

Aucun paquet Python à installer dans les deux cas.
"""
from __future__ import annotations

import gzip
import logging
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zlib
from http.cookiejar import CookieJar
from pathlib import Path

from . import config

log = logging.getLogger(__name__)

REDIRECTION_JS = re.compile(r"window\.location\.href\s*=\s*'([^']+)'")
MAX_CHALLENGES = 6


class Transport:
    """Interface commune : ``get(url) -> bytes``."""

    def get(self, url: str) -> bytes:  # pragma: no cover - interface
        raise NotImplementedError

    def fermer(self) -> None:
        pass


class TransportCurl(Transport):
    """Transport adossé à curl, avec bocal à cookies persistant."""

    def __init__(self, entetes: dict[str, str]):
        self.binaire = shutil.which("curl")
        if not self.binaire:
            raise RuntimeError("curl est introuvable sur ce système")
        self.entetes = entetes
        self._repertoire = tempfile.mkdtemp(prefix="encheres-")
        self.bocal = str(Path(self._repertoire) / "cookies.txt")

    def get(self, url: str) -> bytes:
        commande = [
            self.binaire, "-sS", "--compressed", "--location", "--max-redirs", "8",
            "--max-time", str(config.REQUEST_TIMEOUT),
            "-b", self.bocal, "-c", self.bocal,
            "-A", self.entetes.get("User-Agent", config.USER_AGENT),
        ]
        for nom, valeur in self.entetes.items():
            if nom.lower() in ("user-agent", "accept-encoding"):
                continue                    # déjà couverts par -A et --compressed
            commande += ["-H", f"{nom}: {valeur}"]
        commande.append(url)

        resultat = subprocess.run(commande, capture_output=True,
                                  timeout=config.REQUEST_TIMEOUT + 15)
        if resultat.returncode != 0:
            message = resultat.stderr.decode("utf-8", "replace").strip()
            raise RuntimeError(f"curl a échoué ({resultat.returncode}) : {message}")
        return resultat.stdout

    def fermer(self) -> None:
        shutil.rmtree(self._repertoire, ignore_errors=True)


class TransportUrllib(Transport):
    """Repli en bibliothèque standard."""

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


def creer(entetes: dict[str, str], prefere: str = "auto") -> Transport:
    """Choisit le transport : curl si disponible, urllib sinon."""
    if prefere in ("auto", "curl"):
        try:
            transport = TransportCurl(entetes)
            log.debug("transport : curl")
            return transport
        except RuntimeError as exc:
            if prefere == "curl":
                raise
            log.info("curl indisponible (%s) — repli sur urllib", exc)
    log.debug("transport : urllib")
    return TransportUrllib(entetes)


def resoudre_challenge(transport: Transport, url: str) -> bytes:
    """Demande une URL et déroule le contrôle anti-robot jusqu'au contenu réel.

    Renvoie le corps de la réponse ; à l'appelant de vérifier que c'est bien
    du JSON exploitable.
    """
    corps = transport.get(url)
    for tour in range(MAX_CHALLENGES):
        tete = corps[:4096].decode("utf-8", "replace")
        trouve = REDIRECTION_JS.search(tete)
        if not trouve:
            return corps
        jeton = urllib.parse.urljoin(config.BASE_URL,
                                     trouve.group(1).replace("&amp;", "&"))
        log.debug("contrôle anti-robot, tour %d", tour + 1)
        corps = transport.get(jeton)
    return corps
