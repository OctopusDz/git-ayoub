# L'application « Hybrides »

Une page unique, installable sur l'écran d'accueil d'un iPhone, qui montre les
véhicules hybrides des enchères du Domaine : ce qui est à vendre, ce qui s'est
déjà vendu, et pour chaque lot à venir le prix attendu et le plafond d'enchère
à ne pas dépasser.

Il n'y a pas de serveur. Une GitHub Action collecte les annonces deux fois par
jour et réécrit un fichier de données ; GitHub Pages sert la page. Ouvrir
l'application suffit à récupérer la collecte de la nuit.

## Les pièces

| Fichier | Rôle |
|---|---|
| `scraper/parallele.py` | collecte les annonces en parallèle, une session par fil |
| `scraper/transport.py` | franchit le contrôle anti-robot du site |
| `etl/estimation.py` | estime le prix par comparables, calcule le plafond d'enchère |
| `etl/couts.py` | coût de revient : plateau, carte grise, garde, déplacement |
| `etl/build_app.py` | produit `app/data/hybrides.json` |
| `app/index.html` | l'application elle-même (aucune dépendance) |
| `.github/workflows/veille.yml` | collecte programmée et déploiement |

## Mise en route

Deux réglages à faire une seule fois sur GitHub, dans le dépôt :

1. **Settings → Pages → Source : « GitHub Actions »**.
2. **Settings → Actions → General → Workflow permissions : « Read and write »**,
   pour que l'Action puisse committer les données collectées.

Puis fusionner ce travail dans `master`. C'est indispensable : **GitHub ne
déclenche les tâches programmées que depuis la branche par défaut**. Avant la
fusion, l'Action ne part qu'à la main (onglet *Actions* → *Veille hybrides* →
*Run workflow*).

L'adresse de l'application sera `https://octopusdz.github.io/git-ayoub/`.
Sur iPhone : ouvrir cette adresse dans Safari, bouton Partager, *Sur l'écran
d'accueil*.

> Si le dépôt est privé, GitHub Pages demande un abonnement Pro. À défaut,
> passer le dépôt en public — les données publiées ne sont que des annonces
> déjà publiques.

## Le cycle de vie d'une vente

Une annonce apparaît → la collecte suivante la trouve, l'estime, et l'affiche
dans « À vendre » avec le badge *nouveau*.

Elle est adjugée → au passage suivant, le lot a disparu des ventes ouvertes.
Son identifiant était mémorisé dans `data/suivi.json` : le collecteur va donc
chercher son résultat parmi les ventes closes, lues de la plus récente à la
plus ancienne, et s'arrête dès que tous les disparus sont retrouvés. En
pratique une à trois pages, quelques secondes.

Le lot rejoint alors `data/historique.json.gz` et devient une référence de prix
pour estimer les suivants. Le référentiel grossit donc tout seul, et les
estimations s'appuient sur des ventes de plus en plus fraîches.

Recollecter les 9 000 ventes closes à chaque réveil serait absurde — elles ne
bougent plus. C'est pourquoi seule leur frange récente est relue.

## Ce que l'application calcule

**Prix attendu.** Les ventes closes qui ressemblent au lot (même modèle, âge et
kilométrage proches, en desserrant les critères jusqu'à réunir un effectif
suffisant) donnent une médiane, corrigée de l'écart de kilométrage. La mise à
prix, fixée par un agent qui a vu le véhicule, entre pour 30 % dans le calcul :
c'est le réglage qui minimise l'erreur mesurée.

**Fourchette.** Les quartiles des mêmes comparables. L'erreur réellement
observée est affichée en tête de l'application, mesurée en prédisant des
hybrides déjà vendus dont on a masqué le prix.

**Plafond d'enchère.** La borne basse de la fourchette, moins une réserve
d'autant plus large que l'estimation est incertaine, moins les frais annexes,
le tout divisé par 1,11 pour absorber les frais de vente. Enchérir au-delà,
c'est payer le prix du marché sans marge.

**Frais annexes** (`etl/couts.py`, tarifs en tête de fichier) :

| Poste | Montant |
|---|---|
| Plateau | 300 € jusqu'à 200 km, puis 0,80 €/km |
| Carte grise hybride | 150 € |
| Garde du fourriériste | le montant annoncé, sinon 100 € (2 jours de dépassement) |
| Déplacement (train, repas) | 20 € en Île-de-France, jusqu'à 90 € à l'autre bout du pays |
| Frais de vente | 11 % du prix marteau |

Quand l'annonce mentionne des frais de garde sans les chiffrer, le lot est
marqué **« coût plancher »** : la facture peut être plus lourde.

## Régénérer à la main

```bash
pip install -r requirements.txt
python3 -m etl.quotidien      # collecte, estime, réécrit app/data/hybrides.json
python3 tools/icones.py       # seulement si app/icone.svg a changé
```

Pour prévisualiser :

```bash
cd app && python3 -m http.server 8899   # puis http://localhost:8899
```
