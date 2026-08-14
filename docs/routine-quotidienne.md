# Mettre en place la veille quotidienne

Une routine ne peut pas être créée depuis une session Claude Code sur le web ;
elle se crée depuis l'interface, à l'adresse **https://claude.ai/code/routines**,
bouton **New routine**.

Voici quoi renseigner.

## Nom

```
Veille véhicules du Domaine
```

## Dépôt

`OctopusDz/git-ayoub`

## Environnement

Celui dont l'accès réseau autorise `encheres-domaine.gouv.fr`. Si la collecte
échoue avec une erreur `403`, ouvrir les réglages de l'environnement et passer
l'accès réseau sur **Full**, ou ajouter ce domaine aux **Allowed domains**.

## Déclencheur

**Schedule** → **Daily**, à l'heure voulue. L'heure est saisie dans votre fuseau
et convertie automatiquement.

## Instructions

Texte à coller tel quel dans le champ **Instructions** :

---

Veille quotidienne des enchères de véhicules du Domaine, pour un acheteur basé
en Île-de-France.

Place-toi sur la branche de développement :
`git fetch origin claude/auction-vehicles-analytics-portal-pp0bzj && git checkout claude/auction-vehicles-analytics-portal-pp0bzj`

**1.** Lance `python3 -m etl.quotidien`. Ce script collecte les ventes ouvertes
via l'API GraphQL du site, les estime contre l'historique figé dans
`data/historique.json.gz`, puis reconstruit le cube et la page autonome
`portal/mobile.html`. Il dure moins d'une minute.

**2.** Si le script échoue sur le contrôle anti-robot du site, relance-le : il
est conçu pour être repris, et le cache évite de refaire ce qui a abouti. Trois
tentatives suffisent en général. En cas d'échec persistant, dis-le simplement et
arrête-toi là, sans rien modifier.

**3.** Republie la page comme Artifact en passant impérativement
`url: "https://claude.ai/code/artifact/31cce6fe-9177-48ee-8ebd-3c2cb1e6662a"`
pour conserver la même adresse, avec `file_path: "portal/mobile.html"`,
`favicon: "🚗"` et `capabilities: {"downloads": true}`. Sans ce paramètre `url`,
tu créerais une page distincte et l'utilisateur perdrait son lien.

**4.** Commite et pousse sur la branche de développement.

**5.** Réponds en français, brièvement. Ce qui compte, dans l'ordre :

- les hybrides **essence** (jamais diesel) en France métropolitaine,
  nouvellement mis en vente ;
- pour chacun : intitulé, année, kilométrage, département, état signalé, mise à
  prix, prix attendu, enchère maximum conseillée, coût total tout compris, date
  de clôture, et le lien vers la fiche ;
- signale explicitement les lots dont les frais de garde sont annoncés sans
  montant : le coût affiché n'est alors qu'un plancher.

Le script imprime déjà ce résumé — reprends-le et ajoute ce qui mérite l'œil
d'un humain : une clôture imminente, un lot exceptionnellement décoté, une
incohérence dans l'annonce. S'il n'y a aucune nouveauté, dis-le en une phrase ;
ne réinvente pas de l'intérêt là où il n'y en a pas.

Contexte : l'utilisateur dispose d'une société du secteur automobile, les lots
réservés aux professionnels lui sont donc accessibles, et il sait réparer des
pannes mineures. Il écarte systématiquement les hybrides diesel et tout ce qui
se trouve hors de France métropolitaine.

---

## Connecteurs

Aucun n'est nécessaire. Les décocher limite ce que la routine peut atteindre.

## Vérifier que ça tourne

Sur la page de la routine, **Run now** déclenche une exécution immédiate sans
attendre l'heure programmée. Un statut vert signifie que la session s'est
terminée sans erreur d'infrastructure — pas que la collecte a réussi. Ouvrir la
session pour lire le compte rendu.
