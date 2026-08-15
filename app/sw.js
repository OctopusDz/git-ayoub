/* Service worker de l'application « Hybrides ».
 *
 * Deux régimes, parce que les deux ressources n'ont pas le même besoin :
 *
 * - la coquille (page, icônes, manifeste) change rarement : on la sert depuis
 *   le cache, ce qui fait démarrer l'app instantanément, même dans le métro ;
 * - les données changent chaque nuit : on va toujours voir le réseau d'abord,
 *   et le cache ne sert que de filet quand la connexion manque. Ouvrir l'app
 *   le matin suffit donc à voir la collecte de la nuit.
 */
const VERSION = "hybrides-v1";
const COQUILLE = [
  "./",
  "./index.html",
  "./manifest.webmanifest",
  "./icone.svg",
  "./icone-180.png",
  "./icone-192.png",
  "./icone-512.png",
];

self.addEventListener("install", evenement => {
  evenement.waitUntil(
    caches.open(VERSION)
      .then(cache => cache.addAll(COQUILLE))
      .then(() => self.skipWaiting())
      // Un fichier manquant ne doit pas empêcher l'installation : l'app
      // fonctionnera simplement sans cache.
      .catch(() => self.skipWaiting())
  );
});

self.addEventListener("activate", evenement => {
  evenement.waitUntil(
    caches.keys()
      .then(noms => Promise.all(
        noms.filter(n => n !== VERSION).map(n => caches.delete(n))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", evenement => {
  const requete = evenement.request;
  if (requete.method !== "GET") return;

  const url = new URL(requete.url);
  if (url.origin !== location.origin) return;      // photos du site officiel

  // Données : réseau d'abord, cache en secours.
  if (url.pathname.endsWith("hybrides.json")) {
    evenement.respondWith(
      fetch(requete)
        .then(reponse => {
          const copie = reponse.clone();
          caches.open(VERSION).then(cache => cache.put(requete, copie));
          return reponse;
        })
        .catch(() => caches.match(requete))
    );
    return;
  }

  // Coquille : cache d'abord, réseau en secours (et mise à jour silencieuse).
  evenement.respondWith(
    caches.match(requete).then(cache => cache || fetch(requete).then(reponse => {
      const copie = reponse.clone();
      caches.open(VERSION).then(c => c.put(requete, copie));
      return reponse;
    }))
  );
});
