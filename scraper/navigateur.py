"""Collecte via navigateur, pour franchir le contrôle anti-robot.

Le site protège son API GraphQL par un contrôle qui répond une page
``window.location.href='/redirect_<jeton>/…'``. Ce jeton ne se valide qu'en
exécutant le JavaScript : en HTTP nu, il s'empile indéfiniment.

Ce module ouvre donc une fois la page d'accueil dans Chromium — le temps que
le contrôle pose son cookie — puis exécute les appels GraphQL **depuis le
contexte de la page**. Aucune page de lot n'est chargée, aucune image :
seules les réponses JSON de l'API sont récupérées, comme en HTTP direct.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from . import config

log = logging.getLogger(__name__)

# Chromium fourni avec l'environnement ; sinon celui de Playwright.
CHROME_CANDIDATS = [
    os.environ.get("CHROME_PATH", ""),
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
]

# Appel exécuté dans la page : même origine, donc ni blocage CORS ni cookie
# à recopier — le navigateur les joint lui-même.
APPEL_JS = """
async ({url, query, variables, operation}) => {
  const parametres = new URLSearchParams({
    query, variables: JSON.stringify(variables), operationName: operation,
  });
  const reponse = await fetch(url + '?' + parametres.toString(), {
    headers: {'store': 'default', 'Content-Type': 'application/json'},
    credentials: 'include',
  });
  const texte = await reponse.text();
  try { return {ok: true, data: JSON.parse(texte)}; }
  catch (e) { return {ok: false, status: reponse.status, extrait: texte.slice(0, 200)}; }
}
"""


def chemin_chrome() -> str | None:
    for candidat in CHROME_CANDIDATS:
        if candidat and Path(candidat).exists():
            return candidat
    return None


class ClientNavigateur:
    """Même interface que ``DomaineClient``, mais adossé à Chromium."""

    def __init__(self, delay: float = 0.3, entete: bool = False):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright est requis pour ce mode : pip install playwright") from exc

        chrome = chemin_chrome()
        if not chrome:
            raise RuntimeError(
                "aucun Chromium trouvé — indiquez son chemin via CHROME_PATH")

        self.delay = delay
        self._playwright = sync_playwright().start()

        # Chromium ne lit pas HTTPS_PROXY : quand l'environnement impose un
        # proxy sortant, il faut le lui passer explicitement.
        proxy_url = (os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
                     or os.environ.get("HTTP_PROXY") or "")
        proxy = {"server": proxy_url} if proxy_url else None
        if proxy:
            log.info("proxy sortant : %s", proxy_url)

        self._navigateur = self._playwright.chromium.launch(
            headless=not entete, executable_path=chrome, proxy=proxy,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
        self._contexte = self._navigateur.new_context(
            locale="fr-FR", user_agent=config.USER_AGENT,
            viewport={"width": 1280, "height": 900})
        # Rien d'autre que les documents et scripts n'est utile ici.
        self._contexte.route("**/*", self._filtrer)
        self.page = self._contexte.new_page()
        self._pret = False

    @staticmethod
    def _filtrer(route, requete):
        if requete.resource_type in ("image", "media", "font", "stylesheet"):
            route.abort()
        else:
            route.continue_()

    # -- session ------------------------------------------------------------
    def amorcer(self) -> None:
        """Charge la page d'accueil pour laisser le contrôle poser son cookie."""
        if self._pret:
            return
        log.info("ouverture de %s pour franchir le contrôle anti-robot", config.BASE_URL)
        self.page.goto(config.BASE_URL, wait_until="domcontentloaded", timeout=90_000)
        self.page.wait_for_timeout(4_000)
        cookies = [c["name"] for c in self._contexte.cookies()]
        log.info("cookies obtenus : %s", ", ".join(cookies) or "aucun")
        self._pret = True

    # -- appels -------------------------------------------------------------
    def graphql(self, query: str, variables: dict | None = None,
                operation: str | None = None) -> dict:
        self.amorcer()
        derniere = None
        for tentative in range(1, config.MAX_RETRIES + 1):
            resultat = self.page.evaluate(APPEL_JS, {
                "url": config.GRAPHQL_URL, "query": query,
                "variables": variables or {}, "operation": operation or "",
            })
            if resultat.get("ok"):
                charge = resultat["data"]
                if charge.get("errors"):
                    raise RuntimeError("; ".join(e.get("message", "?")
                                                 for e in charge["errors"]))
                return charge.get("data") or {}

            derniere = resultat
            # Réponse non-JSON : le contrôle anti-robot s'est réarmé.
            log.warning("réponse inattendue (tentative %d) — rechargement de la session",
                        tentative)
            self._pret = False
            self.page.goto(config.BASE_URL, wait_until="domcontentloaded", timeout=90_000)
            self.page.wait_for_timeout(3_000)
            self._pret = True

        raise RuntimeError(f"l'API ne renvoie pas de JSON : {derniere}")

    def page_de_lots(self, categorie_id: int, statuts: list[str],
                     page: int, taille: int) -> dict:
        from .api import QUERY_LOTS
        variables = {
            "currentPage": page,
            "pageSize": taille,
            "sort": {"start_auction_lot_at": "ASC"},
            "filter": {
                "category_uid": {"eq": config.category_uid(categorie_id)},
                "lot_status": {"in": list(statuts)},
            },
        }
        data = self.graphql(QUERY_LOTS, variables, "getCategoryLots")
        return data.get("products") or {}

    # -- cycle de vie -------------------------------------------------------
    def fermer(self) -> None:
        for fermeture in (self._contexte.close, self._navigateur.close,
                          self._playwright.stop):
            try:
                fermeture()
            except Exception:
                pass

    def __enter__(self): return self
    def __exit__(self, *_): self.fermer()
