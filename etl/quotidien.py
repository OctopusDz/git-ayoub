"""Mise à jour quotidienne des ventes ouvertes.

Recollecter chaque matin les 9 000 ventes closes n'aurait pas de sens : elles
ne bougent plus. L'historique est donc figé une fois pour toutes dans le dépôt,
compressé, et seules les ventes ouvertes — quelques centaines de lots, quatre
appels — sont rafraîchies.

Deux commandes :

    python3 -m etl.quotidien figer     # après une collecte complète
    python3 -m etl.quotidien           # mise à jour du jour
"""
from __future__ import annotations

import gzip
import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
LOTS = RACINE / "data" / "lots.json"
HISTORIQUE = RACINE / "data" / "historique.json.gz"
JOURNAL = RACINE / "data" / "suivi.json"

# Tous les champs sont conservés : compressé, l'historique complet ne pèse que
# quelques centaines de kilo-octets, et le portail garde ainsi toute sa
# richesse d'analyse sur les ventes passées.

log = logging.getLogger(__name__)


def figer(source: Path | None = None, destination: Path | None = None) -> Path:
    """Fige les ventes closes en référence compressée et durable."""
    source, destination = Path(source or LOTS), Path(destination or HISTORIQUE)
    lots = json.loads(source.read_text(encoding="utf-8"))["lots"]
    # Les invendus font partie de l'historique : ils disent ce qui ne trouve
    # pas preneur, information aussi utile que les prix atteints.
    closes = [l for l in lots if l.get("statut") != "Vente à venir"]
    charge = {
        "fige_le": datetime.now().isoformat(timespec="seconds"),
        "nb_ventes_closes": len(closes),
        "dont_adjugees": sum(1 for l in closes if l.get("prix")),
        "lots": closes,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(destination, "wt", encoding="utf-8") as fh:
        json.dump(charge, fh, ensure_ascii=False, separators=(",", ":"))
    taille = destination.stat().st_size / 1_048_576
    print(f"Historique figé : {destination} ({len(closes)} ventes closes, {taille:.1f} Mo)")
    return destination


def charger_historique(chemin: Path | None = None) -> list[dict]:
    chemin = Path(chemin) if chemin else HISTORIQUE
    if not chemin.exists():
        raise FileNotFoundError(
            f"{chemin} est introuvable. Lancez d'abord : python3 -m etl.quotidien figer")
    with gzip.open(chemin, "rt", encoding="utf-8") as fh:
        return json.load(fh)["lots"]


def _lire_journal() -> dict:
    if JOURNAL.exists():
        try:
            return json.loads(JOURNAL.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"lots_connus": [], "lots_ouverts": [], "historique_des_jours": []}


# Statuts d'un lot dont la vente est terminée, adjugée ou non.
STATUTS_CLOS = ["1", "2", "3", "8"]
# Pages de ventes closes lues par passage, les plus récentes d'abord. Trois
# pages couvrent 300 clôtures : très au-delà d'une journée ordinaire.
PAGES_CLOSES = 3
# Jusqu'où insister quand des lots attendus manquent encore à l'appel.
PAGES_CLOSES_MAX = 12


def recuperer_closes(attendus: set, fils: int = 8) -> list[dict]:
    """Va chercher le résultat des ventes qui viennent de se clore.

    Recollecter les 10 000 ventes passées à chaque réveil n'aurait pas de sens :
    elles ne bougent plus. On ne cherche donc que les lots qui étaient en vente
    hier et ne le sont plus — on connaît leur identifiant — en lisant les
    ventes closes de la plus récente à la plus ancienne, et en s'arrêtant dès
    qu'ils sont tous retrouvés.
    """
    from scraper import config
    from scraper.parallele import collecter_parallele

    if not attendus:
        return []

    pages, trouves = PAGES_CLOSES, {}
    while True:
        faits, _ = collecter_parallele(
            categories=[config.DEFAULT_CATEGORIE], statuts=STATUTS_CLOS,
            taille_page=100, fils=fils, max_pages=pages,
            sens="DESC", forcer=True)
        trouves = {l["id_lot"]: l for l in faits if l["id_lot"] in attendus}
        manquants = attendus - set(trouves)
        if not manquants or pages >= PAGES_CLOSES_MAX:
            if manquants:
                # Sans doute des lots clos depuis longtemps, ou retirés de la
                # vente. Les poursuivre coûterait plus que ce qu'ils apportent.
                log.warning("%d lot(s) clos introuvables, abandonnés : %s",
                            len(manquants), sorted(manquants)[:5])
            break
        pages = min(pages * 2, PAGES_CLOSES_MAX)

    log.info("  %d vente(s) close(s) récupérée(s) sur %d attendue(s)",
             len(trouves), len(attendus))
    return list(trouves.values())


def enrichir_historique(nouvelles: list[dict],
                        chemin: Path | None = None) -> int:
    """Ajoute des ventes closes au référentiel figé. Retourne le nombre ajouté.

    C'est ce qui fait vivre l'outil : chaque vente terminée devient une
    référence de prix pour estimer les suivantes.

    Le chemin est résolu à l'appel et non à la définition : une valeur par
    défaut figée pointerait toujours sur le vrai fichier, y compris quand un
    test croit l'avoir détourné.
    """
    if not nouvelles:
        return 0

    chemin = Path(chemin) if chemin else HISTORIQUE
    lots = charger_historique(chemin)
    connus = {l["id_lot"] for l in lots}
    ajouts = [l for l in nouvelles if l["id_lot"] not in connus]
    if not ajouts:
        return 0

    lots.extend(ajouts)
    charge = {
        "fige_le": datetime.now().isoformat(timespec="seconds"),
        "nb_ventes_closes": len(lots),
        "dont_adjugees": sum(1 for l in lots if l.get("prix")),
        "lots": lots,
    }
    with gzip.open(chemin, "wt", encoding="utf-8") as fh:
        json.dump(charge, fh, ensure_ascii=False, separators=(",", ":"))
    return len(ajouts)


ALERTE = RACINE / "data" / "alerte.md"
TRAJECTOIRES = RACINE / "data" / "trajectoires.json"


def relever_encheres(faits: list[dict], chemin: Path | None = None) -> int:
    """Note où en est chaque enchère, pour reconstituer sa montée.

    L'API ne donne que l'enchère courante, jamais l'historique. En la relevant
    à chaque passage on reconstitue la courbe : c'est le seul moyen de chiffrer
    ce que tout enchérisseur observe — rien ne bouge pendant des jours, puis
    tout se joue à la fin. Savoir qu'un lot à J-1 n'est qu'à la moitié de son
    prix final évite de croire à une affaire qui n'en est pas une.

    Retourne le nombre de relevés ajoutés.
    """
    chemin = Path(chemin) if chemin else TRAJECTOIRES
    suivi = {}
    if chemin.exists():
        try:
            suivi = json.loads(chemin.read_text(encoding="utf-8"))
        except Exception:
            suivi = {}

    instant = datetime.now().isoformat(timespec="minutes")
    ajouts = 0
    for lot in faits:
        enchere = lot.get("derniere_enchere")
        if enchere is None:
            continue                      # enchères pas encore ouvertes
        cle = str(lot["id_lot"])
        releves = suivi.setdefault(cle, {"mise_a_prix": lot.get("mise_a_prix"),
                                         "date_fin": lot.get("date_fin"),
                                         "intitule": lot.get("intitule"),
                                         "releves": []})
        # Un relevé identique au précédent n'apprend rien : on ne garde que
        # les changements, et la courbe reste lisible.
        if releves["releves"] and releves["releves"][-1][1] == enchere:
            continue
        releves["releves"].append([instant, enchere])
        ajouts += 1

    if ajouts:
        chemin.write_text(json.dumps(suivi, ensure_ascii=False,
                                     separators=(",", ":")), encoding="utf-8")
    return ajouts


def _ecrire_alerte(lots: list[dict]) -> Path | None:
    """Écrit le corps du message d'alerte, ou efface le fichier s'il n'y a rien.

    Le fichier sert de signal au workflow : présent, il déclenche l'envoi ;
    absent, aucun mail ne part. Rien ne s'envoie donc quand rien n'est neuf.
    """
    if not lots:
        ALERTE.unlink(missing_ok=True)
        return None

    lignes = [f"{len(lots)} hybride(s) essence à saisir", ""]
    for lot in lots:
        km = (f"{lot['kilometrage']:,.0f} km".replace(",", " ")
              if lot.get("kilometrage") else "kilométrage inconnu")
        fin = (lot.get("date_fin") or "")[:16].replace("T", " à ")
        lignes += [
            f"## {lot['intitule']}",
            "",
            f"- {lot.get('annee') or 'année inconnue'} · {km} · "
            f"{lot.get('departement') or 'lieu inconnu'}",
            f"- État : {lot.get('gravite') or '—'}",
            f"- Mise à prix : **{lot['mise_a_prix']:.0f} €**",
            f"- Prix attendu : {lot.get('estimation')} € "
            f"(fourchette {lot.get('fourchette_basse')} – {lot.get('fourchette_haute')} €)",
            f"- **Enchère maximum : {lot.get('prix_max_conseille')} €** "
            f"— soit {lot.get('cout_total_max')} € tout compris",
            f"- Clôture : {fin}",
            f"- {lot.get('url')}",
            "",
        ]
        if lot.get("reserve_aux_pros"):
            lignes += ["> Réservé aux professionnels : moins de concurrence, "
                       "et 2 055 € de moins à véhicule comparable.", ""]
        if lot.get("frais_incertains"):
            lignes += ["> Frais de garde annoncés sans montant : le coût total "
                       "affiché est un plancher.", ""]

    lignes += ["---", "", "https://octopusdz.github.io/git-ayoub/"]
    ALERTE.write_text("\n".join(lignes), encoding="utf-8")
    return ALERTE


def mettre_a_jour(statuts: list[str] | None = None, fils: int = 8) -> dict:
    """Collecte les ventes ouvertes, les estime, reconstruit portail et page.

    Retourne le compte rendu du jour : nouveautés, occasions à retenir.
    """
    from scraper import config
    from scraper.parallele import collecter_parallele
    from etl.estimation import estimer
    from etl.build_app import construire as construire_app
    from scraper.export import to_csv, to_json

    statuts = statuts or ["13", "14", "15"]
    historique = charger_historique()

    faits, rapport = collecter_parallele(
        categories=[config.DEFAULT_CATEGORIE], statuts=statuts,
        taille_page=100, fils=fils, max_pages=20)
    if not faits:
        raise RuntimeError("aucune vente ouverte collectée")

    journal = _lire_journal()

    # Les lots qui étaient en vente au dernier passage et qui n'y sont plus
    # viennent d'être adjugés — ou sont restés invendus. Leur résultat est
    # exactement ce dont l'estimation a besoin pour rester à jour.
    ouverts_avant = set(journal.get("lots_ouverts") or [])
    disparus = ouverts_avant - {l["id_lot"] for l in faits}
    closes = recuperer_closes(disparus, fils=fils)
    ajoutes = enrichir_historique(closes)
    if ajoutes:
        historique = charger_historique()
        print(f"  {ajoutes} vente(s) close(s) ajoutée(s) au référentiel "
              f"({len(historique)} au total)")

    for lot in faits:
        lot.update({k: v for k, v in estimer(lot, historique).items()
                    if k in ("estimation", "cout_si_prix_attendu",
                             "fourchette_basse", "fourchette_haute",
                             "prix_max_conseille", "cout_total_max", "verdict",
                             "confiance", "marge_pct", "nb_comparables")})

    connus = set(journal.get("lots_connus") or [])
    nouveaux = [l for l in faits if l["id_lot"] not in connus]

    def interessant(lot):
        # L'outre-mer est écarté : l'acheminement vers la métropole coûte
        # davantage que la marge attendue sur ces montants.
        return (lot.get("verdict") in ("Très intéressant", "Intéressant")
                and (lot.get("carburant") or "").startswith("Hybride essence")
                and lot.get("metropole") is not False
                and not lot.get("non_roulant"))

    a_retenir = sorted([l for l in faits if interessant(l)],
                       key=lambda l: -(l.get("marge_pct") or 0))

    # Il n'y a qu'un hybride ouvert à la fois : sans alerte, il faut penser à
    # ouvrir l'application tous les jours. Seuls les lots jamais vus déclenchent
    # un envoi — sinon l'alerte se répéterait deux fois par jour et on
    # cesserait de la lire.
    alertes = [l for l in a_retenir if l["id_lot"] not in connus]
    _ecrire_alerte(alertes)

    # Relevé des enchères en cours : la courbe se construit passage après
    # passage, elle ne dira quelque chose qu'après plusieurs ventes.
    releves = relever_encheres(faits)
    if releves:
        print(f"  {releves} enchère(s) relevée(s)")

    # L'application réunit historique et ventes ouvertes : les ventes closes
    # servent de référence de prix, les ventes à venir portent la décision.
    ensemble = historique + faits
    to_json(ensemble, LOTS, meta={**rapport, "mode": "mise à jour quotidienne"})
    to_csv(ensemble, RACINE / "data" / "lots.csv")
    construire_app(LOTS)

    journal["lots_connus"] = sorted({l["id_lot"] for l in faits} | connus)
    # Photographie des lots en vente : c'est la comparaison avec celle du
    # prochain passage qui révélera les ventes closes entre-temps.
    journal["lots_ouverts"] = sorted(l["id_lot"] for l in faits)
    journal["historique_des_jours"] = (journal.get("historique_des_jours") or [])[-59:] + [{
        "jour": date.today().isoformat(),
        "ventes_ouvertes": len(faits),
        "nouveaux_lots": len(nouveaux),
        "closes_ajoutees": ajoutes,
        "a_retenir": len(a_retenir),
    }]
    JOURNAL.write_text(json.dumps(journal, ensure_ascii=False, indent=1), encoding="utf-8")

    return {"ventes_ouvertes": len(faits), "nouveaux": nouveaux,
            "a_retenir": a_retenir, "rapport": rapport}


def resumer(bilan: dict) -> str:
    """Compte rendu lisible du jour."""
    lignes = [f"{bilan['ventes_ouvertes']} ventes ouvertes, "
              f"{len(bilan['nouveaux'])} nouvelles depuis hier."]
    retenus = bilan["a_retenir"]
    if not retenus:
        lignes.append("Aucun hybride essence intéressant aujourd'hui.")
        return "\n".join(lignes)

    lignes.append(f"\n{len(retenus)} hybride(s) essence à regarder :")
    for lot in retenus[:10]:
        km = f"{lot['kilometrage']:,.0f} km".replace(",", " ") if lot.get("kilometrage") \
            else "km inconnu"
        lignes.append(
            f"  • {lot['intitule']} — {lot.get('annee') or '?'}, {km}, "
            f"{lot.get('departement') or 'lieu inconnu'}\n"
            f"    mise à prix {lot['mise_a_prix']:.0f} € · "
            f"attendu {lot.get('estimation')} € · "
            f"enchère max {lot.get('prix_max_conseille')} € "
            f"(soit {lot.get('cout_total_max')} € tout compris) "
            f"({lot.get('verdict')}, clôture {(lot.get('date_fin') or '')[:10]})\n"
            f"    {lot.get('url')}")
    return "\n".join(lignes)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if argv and argv[0] == "figer":
        figer()
        return 0
    try:
        print(resumer(mettre_a_jour()))
    except Exception as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
