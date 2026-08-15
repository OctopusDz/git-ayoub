"""Estimation du prix d'adjudication et conseil d'enchère.

Principe retenu, dicté par les données : **estimer le prix par comparables**,
et non par un multiple sur la mise à prix. Sur les 9 130 ventes closes, le
multiple s'étale de ×1,1 (P10) à ×6,8 (P90) — inexploitable pour prédire. Le
prix absolu d'un même modèle, lui, est resserré : une Yaris Hybrid part entre
6 500 et 8 700 € dans trois cas sur quatre.

Pour un lot donné, on cherche donc les ventes déjà closes qui lui ressemblent,
en desserrant les critères jusqu'à disposer d'un effectif suffisant. Le prix
attendu est leur médiane, ajustée du kilométrage ; la fourchette vient de leurs
quartiles. La qualité de l'estimation est mesurée par validation croisée sur
les ventes passées, pas postulée.
"""
from __future__ import annotations

import json
import re
import statistics as st
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

# Frais de vente prélevés par la plateforme sur le prix d'adjudication : ils
# s'ajoutent à l'enchère et doivent donc en être retranchés. Le taux figure
# dans les descriptifs eux-mêmes (« frais de vente (11%) »).
TAUX_FRAIS = 0.11

# Effectif minimal pour qu'une médiane de comparables ait un sens.
MIN_COMPARABLES = 5
# Effectif à partir duquel on juge l'estimation solide.
BON_EFFECTIF = 15

def energie_reelle(lot: dict) -> str | None:
    """Énergie du lot, telle que classée à la collecte.

    Le champ distingue déjà hybride essence et hybride diesel : deux véhicules
    qui ne se comparent pas, ni techniquement ni au portefeuille.
    """
    return lot.get("carburant")


def _famille(lot: dict) -> str:
    """Premier mot du modèle : « YARIS HYBRID » et « YARIS » se comparent."""
    modele = (lot.get("modele") or "").strip()
    return modele.split()[0] if modele else ""


def _proche(valeur, reference, tolerance_relative, tolerance_absolue=0):
    """Deux valeurs sont proches, en tolérant l'absence d'information."""
    if valeur is None or reference is None:
        return True                        # ne pas exclure sur une donnée manquante
    ecart = abs(valeur - reference)
    return ecart <= max(tolerance_absolue, tolerance_relative * abs(reference))


def comparables(lot: dict, historique: list[dict]) -> tuple[list[dict], str]:
    """Ventes closes ressemblant au lot, avec le critère qui a été retenu.

    Les critères se desserrent par paliers jusqu'à réunir un effectif
    suffisant — l'appelant sait ainsi sur quelle base l'estimation repose.
    """
    # Un invendu ne porte pas de prix atteint : il reste dans l'historique
    # pour l'analyse, mais ne peut pas servir de référence de prix.
    historique = [c for c in historique if c.get("prix")]

    marque = lot.get("marque")
    famille = _famille(lot)
    energie = energie_reelle(lot)
    age, km = lot.get("age"), lot.get("kilometrage")

    paliers = [
        ("même modèle, âge et kilométrage proches",
         lambda c: c["marque"] == marque and _famille(c) == famille
         and _proche(c.get("age"), age, 0.25, 2)
         and _proche(c.get("kilometrage"), km, 0.35, 20000)),
        ("même modèle",
         lambda c: c["marque"] == marque and _famille(c) == famille),
        ("même marque et même énergie, âge proche",
         lambda c: c["marque"] == marque and energie_reelle(c) == energie
         and _proche(c.get("age"), age, 0.35, 3)),
        ("même énergie, âge et kilométrage proches",
         lambda c: energie_reelle(c) == energie
         and _proche(c.get("age"), age, 0.3, 3)
         and _proche(c.get("kilometrage"), km, 0.4, 25000)),
        ("même marque",
         lambda c: c["marque"] == marque),
    ]

    for libelle, critere in paliers:
        trouves = [c for c in historique if critere(c)]
        if len(trouves) >= MIN_COMPARABLES:
            return trouves, libelle
    return [], "aucun comparable"


def _ajuster_kilometrage(prix: float, lot: dict, echantillon: list[dict]) -> float:
    """Corrige le prix de l'écart de kilométrage au comparable médian.

    La pente est mesurée sur l'échantillon lui-même plutôt que postulée ; en
    l'absence de données exploitables, aucun ajustement n'est appliqué.
    """
    km = lot.get("kilometrage")
    if km is None:
        return prix
    couples = [(c["kilometrage"], c["prix"]) for c in echantillon
               if c.get("kilometrage") and c.get("prix")]
    if len(couples) < 8:
        return prix

    km_median = st.median(k for k, _ in couples)
    prix_median = st.median(p for _, p in couples)
    if km_median == 0 or prix_median == 0:
        return prix

    # Pente par moindres carrés, bornée : au-delà, c'est du bruit d'échantillon.
    moyenne_km = sum(k for k, _ in couples) / len(couples)
    moyenne_prix = sum(p for _, p in couples) / len(couples)
    variance = sum((k - moyenne_km) ** 2 for k, _ in couples)
    if variance == 0:
        return prix
    covariance = sum((k - moyenne_km) * (p - moyenne_prix) for k, p in couples)
    pente = covariance / variance
    if pente > 0:
        return prix                        # pente positive = artefact, on ignore

    correction = pente * (km - km_median)
    plafond = 0.35 * prix                  # l'ajustement ne refait pas le prix
    correction = max(-plafond, min(plafond, correction))
    return max(prix * 0.4, prix + correction)


def estimer(lot: dict, historique: list[dict]) -> dict:
    """Estime le prix d'adjudication d'un lot et en tire un conseil.

    Retourne l'estimation, sa fourchette, le prix maximum conseillé, le degré
    de confiance et l'écart à la mise à prix.
    """
    echantillon, base = comparables(lot, historique)
    resultat = {
        "base": base,
        "nb_comparables": len(echantillon),
        "energie": energie_reelle(lot),
    }

    if not echantillon:
        resultat.update(estimation=None, cout_si_prix_attendu=None,
                        fourchette_basse=None, fourchette_haute=None,
                        prix_max_conseille=None, cout_total_max=None,
                        taux_frais_pct=round(TAUX_FRAIS * 100), confiance="aucune",
                        verdict="Pas de référence", marge_pct=None)
        return resultat

    prix = sorted(c["prix"] for c in echantillon)
    mediane = st.median(prix)
    p25 = prix[len(prix) // 4]
    p75 = prix[(3 * len(prix)) // 4]

    estimation = _ajuster_kilometrage(mediane, lot, echantillon)

    # La mise à prix est fixée par le service vendeur, qui a vu le véhicule :
    # elle porte une information que les comparables ignorent (état réel,
    # options, historique). La combiner améliore nettement la prédiction —
    # mesuré par validation croisée : 27 % d'erreur médiane contre 32 % avec
    # les seuls comparables. Le poids de 30 % est celui qui minimise l'erreur.
    mise = lot.get("mise_a_prix")
    multiples = [c["multiple_mise_a_prix"] for c in echantillon
                 if c.get("multiple_mise_a_prix")]
    if mise and len(multiples) >= MIN_COMPARABLES:
        par_mise = mise * st.median(multiples)
        estimation = 0.7 * estimation + 0.3 * par_mise

    facteur = estimation / mediane if mediane else 1
    basse, haute = p25 * facteur, p75 * facteur

    # Confiance : effectif et finesse du critère retenu.
    if len(echantillon) >= BON_EFFECTIF and base.startswith("même modèle"):
        confiance = "bonne"
    elif len(echantillon) >= MIN_COMPARABLES and "modèle" in base:
        confiance = "moyenne"
    else:
        confiance = "faible"

    # Prix maximum conseillé : la borne basse de la fourchette, minorée d'une
    # réserve d'autant plus large que l'estimation est incertaine. Enchérir
    # au-delà, c'est payer le prix du marché sans marge de manœuvre.
    reserve = {"bonne": 0.10, "moyenne": 0.18, "faible": 0.28}[confiance]
    defauts_majeurs = lot.get("nb_defauts_majeurs") or 0
    reserve += min(0.15, 0.05 * defauts_majeurs)     # remise en état à prévoir

    # Budget que l'opération doit respecter, tout compris.
    budget_max = basse * (1 - reserve)

    # Les frais annexes se paient quel que soit le prix marteau : garde du
    # fourriériste, rapatriement, carte grise. Ils viennent en déduction du
    # budget avant que l'enchère ne soit calculée.
    from etl.couts import cout_annexe
    annexes = cout_annexe(lot)
    budget_enchere = budget_max - annexes["total"]

    # L'enchère elle-même doit tenir dans ce solde une fois les frais de vente
    # ajoutés : enchérir « à hauteur du budget » revient à le dépasser de 11 %.
    prix_max = max(0.0, budget_enchere / (1 + TAUX_FRAIS))

    if mise and prix_max:
        marge = (prix_max - mise) / mise * 100
        if prix_max <= mise:
            verdict = "À éviter"
        elif marge >= 100:
            verdict = "Très intéressant"
        elif marge >= 40:
            verdict = "Intéressant"
        else:
            verdict = "Marge faible"
    else:
        marge, verdict = None, "Mise à prix inconnue"

    resultat.update(
        estimation=round(estimation),
        cout_si_prix_attendu=round(estimation * (1 + TAUX_FRAIS)),
        fourchette_basse=round(basse),
        fourchette_haute=round(haute),
        prix_max_conseille=round(prix_max),
        cout_total_max=round(prix_max * (1 + TAUX_FRAIS) + annexes["total"]),
        taux_frais_pct=round(TAUX_FRAIS * 100),
        frais_annexes=annexes["total"],
        frais_garde=annexes["postes"]["garde"],
        frais_rapatriement=annexes["postes"]["rapatriement"],
        frais_deplacement=annexes["postes"]["deplacement"],
        frais_carte_grise=annexes["postes"]["carte_grise"],
        frais_incertains=annexes["incertain"],
        detail_frais=(f"garde : {annexes['detail']['garde']} · "
                      f"rapatriement {annexes['detail']['rapatriement']} "
                      f"({annexes['detail']['distance_km']} km) · "
                      f"{annexes['detail']['deplacement']} · "
                      f"carte grise : {annexes['detail']['carte_grise']}"),
        confiance=confiance,
        verdict=verdict,
        marge_pct=round(marge) if marge is not None else None,
    )
    return resultat


# --------------------------------------------------------------------------
# Mesure de la qualité prédictive
# --------------------------------------------------------------------------
def valider(historique: list[dict], echantillon_max: int = 800) -> dict:
    """Validation croisée : prédire des ventes closes en les excluant.

    Donne l'erreur réellement observée, seule base honnête pour annoncer une
    fourchette à l'utilisateur.
    """
    import random
    random.seed(1)
    lots = [l for l in historique if l.get("prix")]
    test = random.sample(lots, min(echantillon_max, len(lots)))

    erreurs, dans_fourchette, sans_estimation = [], 0, 0
    par_confiance: dict[str, list[float]] = {}

    for lot in test:
        reste = [c for c in historique if c["id_lot"] != lot["id_lot"]]
        resultat = estimer(lot, reste)
        if resultat["estimation"] is None:
            sans_estimation += 1
            continue
        reel = lot["prix"]
        erreur = abs(resultat["estimation"] - reel) / reel * 100
        erreurs.append(erreur)
        par_confiance.setdefault(resultat["confiance"], []).append(erreur)
        if resultat["fourchette_basse"] <= reel <= resultat["fourchette_haute"]:
            dans_fourchette += 1

    return {
        "lots_testes": len(test),
        "sans_estimation": sans_estimation,
        "erreur_mediane_pct": round(st.median(erreurs), 1) if erreurs else None,
        "erreur_moyenne_pct": round(sum(erreurs) / len(erreurs), 1) if erreurs else None,
        "part_dans_fourchette_pct": round(100 * dans_fourchette / len(erreurs))
        if erreurs else None,
        "erreur_par_confiance": {
            niveau: {"n": len(v), "erreur_mediane_pct": round(st.median(v), 1)}
            for niveau, v in sorted(par_confiance.items())
        },
    }


def charger_lots(chemin: Path | None = None) -> list[dict]:
    chemin = chemin or RACINE / "data" / "lots.json"
    return json.loads(Path(chemin).read_text(encoding="utf-8"))["lots"]


def separer(lots: list[dict]) -> tuple[list[dict], list[dict]]:
    """(ventes closes exploitables, ventes à venir)."""
    historique = [l for l in lots if l.get("prix") and l.get("statut") != "Vente à venir"]
    a_venir = [l for l in lots if l.get("statut") == "Vente à venir"]
    return historique, a_venir


if __name__ == "__main__":
    lots = charger_lots()
    historique, a_venir = separer(lots)
    print(f"{len(historique)} ventes closes, {len(a_venir)} à venir\n")
    rapport = valider(historique)
    for cle, valeur in rapport.items():
        print(f"  {cle} : {valeur}")
