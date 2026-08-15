"""Construit le jeu de données de l'application « Hybrides ».

L'application n'a pas besoin des 10 000 lots du corpus : elle ne montre que les
hybrides, quelques centaines de véhicules. Le fichier produit tient dans
quelques centaines de kilo-octets, ce qui permet à la page de tout charger
d'un coup et de filtrer instantanément, sans serveur.

Deux populations coexistent dans ce fichier, et c'est voulu :

* les **ventes à venir**, estimées contre l'historique complet — c'est là que
  se prend la décision d'enchérir ;
* les **ventes closes**, qui montrent ce que des véhicules comparables ont
  réellement atteint. Elles fondent l'estimation, et l'utilisateur doit pouvoir
  la vérifier de ses yeux plutôt que de croire un chiffre sorti d'une boîte.

Chaque lot à venir emporte donc ses propres comparables : l'application affiche
les ventes qui ont servi à le situer.
"""
from __future__ import annotations

import json
import random
import statistics as st
from datetime import date, datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SORTIE = RACINE / "app" / "data" / "hybrides.json"

# Nombre de comparables joints à chaque lot à venir : assez pour convaincre,
# pas au point d'alourdir le fichier.
COMPARABLES_JOINTS = 12
# Effectif tiré au sort pour mesurer l'erreur réelle sur les hybrides.
ECHANTILLON_VALIDATION = 150

# Champs conservés tels quels pour chaque lot.
CHAMPS = (
    "id_lot", "intitule", "url", "image", "marque", "modele", "annee",
    "kilometrage", "carburant", "rechargeable", "base_hybride", "boite_vitesses",
    "critair", "nb_places", "immatriculation", "region", "departement", "ville",
    "code_departement", "metropole", "gravite", "defauts", "nb_defauts",
    "nb_defauts_majeurs", "mentions_fourriere", "cout_mentions",
    "etat_non_constate", "usure_ordinaire",
    "non_roulant", "sans_cle", "sans_carte_grise",
    "premiere_main", "controle_technique_mentionne", "distribution_faite",
    "revision_recente", "reserve_aux_pros", "statut", "mode_vente",
    "mise_a_prix", "prix", "date_debut", "date_fin", "jour_fin", "description",
)

# Champs d'estimation recopiés pour les ventes à venir.
CHAMPS_ESTIMATION = (
    "estimation", "fourchette_basse", "fourchette_haute", "prix_max_conseille",
    "cout_total_max", "cout_si_prix_attendu", "verdict", "confiance",
    "marge_pct", "nb_comparables", "base", "frais_annexes", "frais_garde",
    "frais_rapatriement", "frais_deplacement", "frais_carte_grise",
    "frais_incertains", "detail_frais", "taux_frais_pct",
)


def est_hybride(lot: dict) -> bool:
    return bool((lot.get("carburant") or "").startswith("Hybride"))


def _jours_restants(lot: dict) -> int | None:
    fin = lot.get("date_fin")
    if not fin:
        return None
    try:
        return (datetime.fromisoformat(fin).date() - date.today()).days
    except ValueError:
        return None


def _alleger(lot: dict) -> dict:
    """Ne garde que les champs utiles à l'application."""
    return {c: lot.get(c) for c in CHAMPS if lot.get(c) is not None}


def _comparable_resume(lot: dict) -> dict:
    """Vente close réduite à ce qui permet de juger sa ressemblance."""
    return {
        "intitule": lot.get("intitule"),
        "annee": lot.get("annee"),
        "kilometrage": lot.get("kilometrage"),
        "mise_a_prix": lot.get("mise_a_prix"),
        "prix": lot.get("prix"),
        "jour_fin": lot.get("jour_fin"),
        "departement": lot.get("departement"),
        "url": lot.get("url"),
    }


def _multiple(lot: dict) -> float | None:
    mise, prix = lot.get("mise_a_prix"), lot.get("prix")
    if mise and prix and mise > 0:
        return round(prix / mise, 2)
    return None


def construire(source: Path | None = None, destination: Path | None = None) -> Path:
    from etl.estimation import estimer, comparables
    from etl.quotidien import charger_historique

    source = Path(source) if source else RACINE / "data" / "lots.json"
    destination = Path(destination) if destination else SORTIE

    lots = json.loads(source.read_text(encoding="utf-8"))["lots"]
    # L'estimation se fonde sur tout le corpus, pas seulement sur les hybrides :
    # une Yaris thermique renseigne sur la cote d'une Yaris, et les paliers de
    # comparaison savent déjà quand exiger la même énergie.
    historique = [l for l in lots if l.get("prix")]
    if len(historique) < 1000:                      # collecte partielle
        historique = [l for l in charger_historique() if l.get("prix")]

    hybrides = [l for l in lots if est_hybride(l)]
    sortie: list[dict] = []

    for lot in hybrides:
        allege = _alleger(lot)
        allege["multiple_mise_a_prix"] = _multiple(lot)
        allege["a_venir"] = lot.get("statut") == "Vente à venir"
        allege["jours_restants"] = _jours_restants(lot)
        allege["hybride_diesel"] = lot.get("base_hybride") == "Gazole"
        allege["base_incertaine"] = lot.get("base_hybride") is None

        if allege["a_venir"]:
            # Un lot à venir n'est utile que chiffré : estimation, plafond
            # d'enchère et comparables qui les justifient.
            resultat = estimer(lot, historique)
            allege.update({c: resultat.get(c) for c in CHAMPS_ESTIMATION})
            echantillon, _ = comparables(lot, historique)
            recents = sorted(echantillon, key=lambda c: c.get("jour_fin") or "",
                             reverse=True)[:COMPARABLES_JOINTS]
            allege["comparables"] = [_comparable_resume(c) for c in recents]
        sortie.append(allege)

    sortie.sort(key=lambda l: (not l["a_venir"], l.get("date_fin") or ""))

    charge = {
        "meta": _meta(sortie, historique, lots),
        "lots": sortie,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(charge, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8")

    taille = destination.stat().st_size / 1024
    a_venir = sum(1 for l in sortie if l["a_venir"])
    print(f"App : {destination} ({len(sortie)} hybrides dont {a_venir} à venir, "
          f"{taille:.0f} Ko)")
    return destination


def _meta(hybrides: list[dict], historique: list[dict], lots: list[dict]) -> dict:
    """En-tête du fichier : ce que l'application affiche pour se situer."""
    vendus = [l for l in hybrides if l.get("prix")]
    multiples = [l["multiple_mise_a_prix"] for l in hybrides
                 if l.get("multiple_mise_a_prix")]
    return {
        "genere_le": datetime.now().isoformat(timespec="seconds"),
        "source": "encheres-domaine.gouv.fr",
        "nb_hybrides": len(hybrides),
        "nb_a_venir": sum(1 for l in hybrides if l["a_venir"]),
        "nb_vendus": len(vendus),
        "corpus_total": len(lots),
        "ventes_closes_referentiel": len(historique),
        "multiple_median": round(st.median(multiples), 2) if multiples else None,
        "prix_median_vendus": round(st.median(l["prix"] for l in vendus))
        if vendus else None,
        "fiabilite": _fiabilite(historique),
    }


def _fiabilite(historique: list[dict]) -> dict:
    """Erreur réellement observée en prédisant des hybrides déjà vendus.

    Mesurée en excluant le lot testé de son propre référentiel. C'est la seule
    base honnête pour annoncer une fourchette : l'application affiche ce
    chiffre plutôt que de laisser croire à une précision qu'elle n'a pas.
    """
    from etl.estimation import estimer

    vendus = [l for l in historique if est_hybride(l) and l.get("prix")]
    if len(vendus) < 20:
        return {"mesurable": False}

    random.seed(1)
    test = random.sample(vendus, min(ECHANTILLON_VALIDATION, len(vendus)))
    index = {l["id_lot"]: l for l in historique}

    erreurs, dans_fourchette = [], 0
    for lot in test:
        reste = [c for c in index.values() if c["id_lot"] != lot["id_lot"]]
        resultat = estimer(lot, reste)
        if not resultat.get("estimation"):
            continue
        reel = lot["prix"]
        erreurs.append(abs(resultat["estimation"] - reel) / reel * 100)
        if resultat["fourchette_basse"] <= reel <= resultat["fourchette_haute"]:
            dans_fourchette += 1

    if not erreurs:
        return {"mesurable": False}
    return {
        "mesurable": True,
        "lots_testes": len(erreurs),
        "erreur_mediane_pct": round(st.median(erreurs), 1),
        "part_dans_fourchette_pct": round(100 * dans_fourchette / len(erreurs)),
    }


if __name__ == "__main__":
    construire()
