"""Couche réseau : session HTTP polie, cache disque, reprise sur erreur."""
from __future__ import annotations

import hashlib
import logging
import time
import urllib.robotparser as robotparser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

from . import config

log = logging.getLogger(__name__)


class Fetcher:
    """Récupère des pages HTML en respectant le site.

    - un seul appel toutes les ``REQUEST_DELAY`` secondes ;
    - 4 tentatives max avec back-off exponentiel (2, 4, 8, 16 s) ;
    - cache disque : relancer le scraper ne re-télécharge pas tout ;
    - lecture de robots.txt (désactivable pour un usage ponctuel autorisé).
    """

    def __init__(self, cache_dir: Path | None = None, use_cache: bool = True,
                 delay: float | None = None, respect_robots: bool | None = None):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": config.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9",
        })
        self.cache_dir = Path(cache_dir or config.CACHE_DIR)
        self.use_cache = use_cache
        self.delay = config.REQUEST_DELAY if delay is None else delay
        self.respect_robots = config.RESPECT_ROBOTS if respect_robots is None else respect_robots
        self._last_call = 0.0
        self._robots: robotparser.RobotFileParser | None = None
        if self.use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    # -- robots.txt ---------------------------------------------------------
    def _robots_ok(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        if self._robots is None:
            parsed = urlparse(url)
            self._robots = robotparser.RobotFileParser()
            self._robots.set_url(f"{parsed.scheme}://{parsed.netloc}/robots.txt")
            try:
                self._robots.read()
            except Exception as exc:  # robots inaccessible : on n'empêche pas
                log.warning("robots.txt illisible (%s) — on poursuit", exc)
                return True
        return self._robots.can_fetch(config.USER_AGENT, url)

    # -- cache --------------------------------------------------------------
    def _cache_path(self, url: str) -> Path:
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
        return self.cache_dir / f"{key}.html"

    # -- API ----------------------------------------------------------------
    def get(self, url: str, force: bool = False) -> str | None:
        """Retourne le HTML d'une URL, ou ``None`` si définitivement inaccessible."""
        url = urljoin(config.BASE_URL, url)

        if self.use_cache and not force:
            cached = self._cache_path(url)
            if cached.exists():
                log.debug("cache  %s", url)
                return cached.read_text(encoding="utf-8", errors="replace")

        if not self._robots_ok(url):
            log.warning("robots.txt interdit %s — ignoré", url)
            return None

        delay = 2.0
        for attempt in range(1, config.MAX_RETRIES + 1):
            elapsed = time.time() - self._last_call
            if elapsed < self.delay:
                time.sleep(self.delay - elapsed)
            try:
                resp = self.session.get(url, timeout=config.REQUEST_TIMEOUT)
                self._last_call = time.time()
                if resp.status_code == 404:
                    log.warning("404 %s", url)
                    return None
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise requests.HTTPError(f"HTTP {resp.status_code}")
                resp.raise_for_status()
                html = resp.text
                if self.use_cache:
                    self._cache_path(url).write_text(html, encoding="utf-8")
                log.info("ok     %s", url)
                return html
            except Exception as exc:
                self._last_call = time.time()
                if attempt == config.MAX_RETRIES:
                    log.error("échec définitif %s (%s)", url, exc)
                    return None
                log.warning("échec %s (%s) — nouvelle tentative dans %.0f s",
                            url, exc, delay)
                time.sleep(delay)
                delay *= 2
        return None
