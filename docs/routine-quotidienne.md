# La veille quotidienne

Chaque matin à 7 h (Paris), une routine relance la collecte, réestime les
ventes ouvertes, republie la page mobile et **envoie une notification sur le
téléphone**.

Elle est déjà en place — ce document explique comment elle est câblée, pour
pouvoir la réparer ou la déplacer.

## Ce qui tourne

| | |
|---|---|
| Routine | `Veille véhicules du Domaine` |
| Horaire | `0 5 * * *` en UTC, soit 7 h à Paris l'été |
| Session visée | `session_019aN52j6wiHd3quKycBgpQk`, branche `claude/auction-vehicles-analytics-portal-pp0bzj` |
| Page publiée | `https://claude.ai/code/artifact/31cce6fe-9177-48ee-8ebd-3c2cb1e6662a` |

Les routines se consultent sur **https://claude.ai/code/routines** ; `Run now`
y déclenche une exécution immédiate.

## Pourquoi une session persistante

Une routine peut viser deux choses, et le choix a une conséquence directe.

* **Une session neuve à chaque déclenchement.** L'interface sait alors envoyer
  la notification elle-même, mais la session démarre sans dépôt : elle se
  retrouve dans un répertoire vide et demande à l'utilisateur d'initialiser un
  dépôt Git au lieu de travailler. C'est l'échec qu'on a constaté.
* **Une session persistante** (celle du tableau ci-dessus), créée une fois avec
  le dépôt déjà cloné sur la bonne branche. Le code est là, la routine se
  contente de le relancer. En contrepartie, le serveur refuse les notifications
  natives sur ce type de routine.

D'où le montage retenu : session persistante pour le dépôt, et **la session
envoie sa propre notification** en appelant l'outil `PushNotification` en fin
de tour. C'est le point 7 des instructions, et il est formulé comme une
obligation — y compris quand il n'y a rien de neuf, sans quoi le silence
devient ambigu.

## Recréer la routine

Depuis une session Claude Code qui a accès au dépôt :

```
create_session(
    source_url="https://github.com/OctopusDz/git-ayoub.git",
    source_revision="claude/auction-vehicles-analytics-portal-pp0bzj",
    title="Veille véhicules du Domaine",
    tags=["veille-encheres"])

create_trigger(
    name="Veille véhicules du Domaine",
    cron_expression="0 5 * * *",
    persistent_session_id=<l'identifiant renvoyé ci-dessus>,
    prompt=<le texte ci-dessous>)
```

Le `cron_expression` est en UTC : `0 5 * * *` correspond à 7 h l'été et 6 h
l'hiver. Pour rester à 7 h toute l'année, passer à `0 6 * * *` au changement
d'heure.

## Les instructions

> Veille quotidienne des enchères de véhicules du Domaine, pour un acheteur
> basé en Île-de-France.
>
> N'inspecte jamais les variables d'environnement d'authentification (pas de
> `printenv`, pas de `env`, pas de lecture de `GITHUB_TOKEN`) : le dépôt est
> déjà cloné et authentifié.
>
> **1.** Récupère les dernières modifications :
> `git pull --rebase origin claude/auction-vehicles-analytics-portal-pp0bzj`
>
> **2.** Lance `python3 -m etl.quotidien`. Ce script collecte les ventes
> ouvertes via l'API GraphQL du site (en parallèle, moins d'une minute), les
> estime contre l'historique figé dans `data/historique.json.gz`, puis
> reconstruit le cube et la page autonome `portal/mobile.html`.
>
> **3.** Si le script échoue sur le contrôle anti-robot du site, relance-le : il
> est conçu pour être repris, et le cache évite de refaire ce qui a abouti.
> Trois tentatives suffisent en général. En cas d'échec persistant, dis-le
> simplement et arrête-toi là, sans rien modifier.
>
> **4.** Republie la page comme Artifact en passant impérativement
> `url: "https://claude.ai/code/artifact/31cce6fe-9177-48ee-8ebd-3c2cb1e6662a"`
> pour conserver la même adresse, avec `file_path: "portal/mobile.html"`,
> `favicon: "🚗"` et `capabilities: {"downloads": true}`. Sans ce paramètre
> `url`, tu créerais une page distincte et l'utilisateur perdrait son lien.
>
> **5.** Commite et pousse sur
> `claude/auction-vehicles-analytics-portal-pp0bzj`. S'il n'y a rien à
> commiter, passe.
>
> **6.** Réponds en français, brièvement. Ce qui compte, dans l'ordre :
>
> - les hybrides **essence** (jamais diesel) en France métropolitaine,
>   nouvellement mis en vente ;
> - pour chacun : intitulé, année, kilométrage, département, état signalé, mise
>   à prix, prix attendu, enchère maximum conseillée, coût total tout compris,
>   date de clôture, et le lien vers la fiche ;
> - signale explicitement les lots dont les frais de garde sont annoncés sans
>   montant : le coût affiché n'est alors qu'un plancher.
>
> Le script imprime déjà ce résumé — reprends-le et ajoute ce qui mérite l'œil
> d'un humain : une clôture imminente, un lot exceptionnellement décoté, une
> incohérence dans l'annonce. S'il n'y a aucune nouveauté, dis-le en une
> phrase ; ne réinvente pas de l'intérêt là où il n'y en a pas.
>
> **7.** Termine **toujours** en appelant l'outil `PushNotification`
> (charge-le au besoin avec `ToolSearch` : `select:PushNotification`). Une
> seule ligne, moins de 200 caractères, en français, qui commence par ce sur
> quoi l'utilisateur peut agir. Cette notification est le seul canal par lequel
> l'utilisateur apprend le résultat : ne termine jamais le tour sans l'avoir
> envoyée, même quand il n'y a rien de neuf ou que la collecte a échoué
> (dis-le alors dans la notification).
>
> Contexte : l'utilisateur dispose d'une société du secteur automobile, les
> lots réservés aux professionnels lui sont donc accessibles, et il sait
> réparer des pannes mineures. Il écarte systématiquement les hybrides diesel
> et tout ce qui se trouve hors de France métropolitaine.

## Quand quelque chose cloche

**Aucune notification.** La notification part de la session elle-même : ouvrir
la session de la veille et vérifier que `PushNotification` a bien été appelée
en fin de tour. Si oui et que le téléphone n'a rien reçu, le problème est côté
appareil — les notifications de Claude Code doivent être autorisées dans
l'application.

**La collecte échoue en `403`.** L'accès réseau de l'environnement
`env_01EEZXR4CLfLSQBjcVeRGfDi` doit autoriser `encheres-domaine.gouv.fr` :
réglages de l'environnement, accès réseau sur **Full**.

**Le lien de la page a changé.** La routine a republié sans le paramètre `url`.
Récupérer la nouvelle adresse et corriger le point 4 des instructions —
`update_trigger(trigger_id=…, prompt=…)` modifie le texte sans perdre
l'historique de la routine.

**La session persistante a été archivée.** `unarchive_session` la réveille ; un
conteneur neuf est provisionné au déclenchement suivant.
