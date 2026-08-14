# Véhicules aux enchères du Domaine — collecte et portail décisionnel

Collecte les lots de véhicules mis en vente sur
[encheres-domaine.gouv.fr](https://encheres-domaine.gouv.fr) (Direction nationale
d'interventions domaniales), les transforme en table de faits exploitable, et
les expose dans un portail d'analyse multidimensionnelle : tableau croisé
dynamique, graphiques, table détaillée et rapport imprimable.

```
scraper/      collecte via l'API GraphQL du site
etl/          construction du cube consommé par le portail
portal/       portail web (aucun serveur applicatif, aucune dépendance)
data/         fichiers produits (JSON, CSV, SQLite) + cache des pages
```

## Démarrage

Aucune dépendance à installer : Python 3.11 et `curl`, présents sur macOS,
Linux et Windows 10+, suffisent.

```bash
python3 -m scraper                      # collecte, écrit data/ et le cube
python3 -m http.server -d portal 8000   # portail sur http://localhost:8000
```

La collecte construit le cube automatiquement. Pour le reconstruire seul :

```bash
python3 -m etl.build_cube
```

## Collecte

Le site sert ses données par une API **Magento GraphQL** (`getCategoryLots`).
On rejoue la requête du site à l'identique plutôt que d'analyser du HTML :
toute évolution du schéma casserait d'abord leur propre interface.

```bash
python3 -m scraper --max-lots 200            # essai rapide
python3 -m scraper --categories toutes       # les 16 catégories de véhicules
python3 -m scraper --categories 6,9          # utilitaires et camions
python3 -m scraper --statuts 13,14,15        # ventes en cours seulement
python3 -m scraper --depuis-cache            # reconstruire sans appel réseau
python3 -m scraper --help                    # catégories et options
```

### Contrôle anti-robot

L'API est protégée : le premier appel reçoit une page
`window.location.href='/redirect_<jeton>/…'` au lieu du JSON. Trois éléments la
font céder, tous implémentés dans `scraper/transport.py` et `scraper/api.py` :

1. demander l'URL à jeton et **suivre la redirection HTTP** qu'elle renvoie ;
2. joindre l'empreinte `x-magento-cache-id` que le site envoie à chaque appel ;
3. **ne pas** envoyer d'en-tête `Origin`, qui bascule le serveur en mode CORS.

Le contrôle ne cède pas à tous les coups et se durcit si on insiste. La
collecte est donc conçue pour être patiente et reprenable :

- chaque page obtenue est écrite dans `data/pages/` ;
- **relancer la commande repart de ce cache** — rien n'est redemandé deux fois ;
- les pages en échec sont reprises en fin de parcours ;
- la session est renouvelée régulièrement, ce qui remet le contrôle à zéro.

Si la collecte s'arrête avant la fin, relancez-la : elle reprendra où elle en
était. Ralentir améliore nettement le taux de réussite :

```bash
python3 -m scraper --pause 6 --pages-par-session 8
```

Deux options de repli existent si le contrôle bloque durablement :
`--har fichier.har` reprend les cookies d'une session de navigation réelle
(export HAR depuis le navigateur, valable une heure), et `scraper/navigateur.py`
passe par Chromium via Playwright.

## Données produites

| Fichier | Usage |
|---|---|
| `data/lots.json` | table de faits complète, avec le rapport de collecte |
| `data/lots.csv` | ouverture directe dans un tableur (séparateur `;`) |
| `data/lots.sqlite` | requêtes SQL, Power BI, Metabase — avec vues d'analyse |
| `portal/data/dataset.json` | cube compact lu par le portail |

Chaque lot porte ses champs d'origine et un enrichissement :

- **véhicule** — marque, modèle, année, date de première mise en circulation,
  kilométrage, énergie, boîte, Crit'Air, norme Euro, VIN, immatriculation ;
- **état** — défauts signalés dans le descriptif (sans clé, sans carte grise,
  non roulant, chocs, pneumatiques hors service…) et gravité qui en découle ;
- **géographie** — ville et code postal de retrait, département, région,
  centre de vente ;
- **vente** — mise à prix, dernière enchère, montant adjugé, statut, mode de
  vente, dates d'ouverture et de clôture ;
- **indicateurs dérivés** — multiple sur mise à prix, plus-value, prix pour
  1 000 km, kilométrage annuel, tranches d'analyse, complétude de la fiche.

Marque, modèle, énergie et kilométrage sont lus dans le descriptif rédigé par
le service vendeur (`scraper/description.py`). Ces informations sont indicatives
et non garanties ; quand la source dit « kilométrage inconnu », le champ reste
vide plutôt que d'être deviné. Le champ `completude_pct` mesure, lot par lot,
la part des champs clés effectivement renseignés.

## Portail

Ouvrez `http://localhost:8000` après avoir lancé le serveur. Le portail est un
ensemble de fichiers statiques : ni build, ni serveur applicatif, ni accès
réseau. Il fonctionne hors ligne une fois le cube produit.

- **Synthèse** — indicateurs clés et graphiques d'ensemble ; cliquer une barre
  filtre le cube sur cette valeur.
- **Cube** — tableau croisé dynamique : hiérarchies en lignes et en colonnes,
  20 mesures (dont médianes et parts), sous-totaux repliables, coloration
  proportionnelle, tri par mesure, forage au clic, export CSV.
- **Graphiques** — n'importe quelle dimension croisée avec n'importe quelle
  mesure, en barres, courbe ou barres empilées ; nuage kilométrage/prix.
- **Lots** — table détaillée triable, avec lien vers la fiche du site.
- **Rapport** — document imprimable (PDF via l'impression du navigateur),
  sections au choix, reflétant les filtres actifs.

Les filtres s'appliquent à toutes les vues simultanément.

### Cube

`etl/build_cube.py` définit **34 dimensions** et **20 mesures**. La table de
faits est transposée en colonnes et les dimensions dictionnarisées : sur
10 000 lots, le cube pèse environ 3 Mo au lieu de 25, et le navigateur agrège
sans serveur. Ajouter une dimension ou une mesure se fait en une ligne dans ce
fichier — le portail se configure à partir des métadonnées du cube.

## Lecture des chiffres

- Les mesures ignorent les valeurs manquantes : une moyenne de prix ne porte
  que sur les lots dont le prix est connu, et son effectif peut différer du
  nombre de lots affiché.
- Le **multiple sur mise à prix** rapporte le prix atteint au prix de départ.
  Au-dessus de 1, la vente a dépassé la mise à prix.
- Les lots invendus n'ont pas de prix : ils comptent dans les effectifs, pas
  dans les moyennes de prix.
- L'état signalé est déduit du texte du descriptif. Il reflète ce que le
  service vendeur a écrit, pas une expertise.

## Usage

Les données proviennent d'un service public et restent la propriété de leur
éditeur. La collecte respecte un rythme mesuré et ne contourne aucune
authentification : elle n'accède qu'à des pages publiques, celles que le site
sert à tout visiteur.
