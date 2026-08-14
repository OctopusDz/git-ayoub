/* Rapport imprimable.
 *
 * Compose un document lisible à partir de la sélection courante : une phrase
 * de cadrage, puis des tableaux chiffrés. Rien n'est masqué à l'impression,
 * et les tableaux tiennent lieu de vue accessible des graphiques.
 */

import { formater } from "./cube.js";

function titre(niveau, texte) {
  const noeud = document.createElement(niveau);
  noeud.textContent = texte;
  return noeud;
}

function paragraphe(texte) {
  const p = document.createElement("p");
  p.textContent = texte;
  return p;
}

/** Tableau simple : en-têtes, lignes de valeurs déjà formatées. */
function tableau(entetes, lignes) {
  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const rang = document.createElement("tr");
  for (const entete of entetes) {
    const th = document.createElement("th");
    th.textContent = entete;
    rang.appendChild(th);
  }
  thead.appendChild(rang);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  for (const ligne of lignes) {
    const tr = document.createElement("tr");
    for (const cellule of ligne) {
      const td = document.createElement("td");
      td.textContent = cellule;
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  return table;
}

/** Extrait les lignes d'un pivot à une dimension, en valeurs formatées. */
function lignesPivot(cube, dimension, mesures, { limite = 15, trier = true } = {}) {
  const p = cube.pivot([dimension], [], mesures, { sousTotaux: false });
  let lignes = p.lignes.map((entete) => ({
    libelle: entete.libelle,
    valeurs: p.lire(entete.chemin, ""),
  }));
  if (trier) lignes.sort((a, b) => (b.valeurs[0] ?? -Infinity) - (a.valeurs[0] ?? -Infinity));
  if (limite) lignes = lignes.slice(0, limite);
  return lignes.map((ligne) => [
    ligne.libelle,
    ...ligne.valeurs.map((v, i) => formater(v, p.mesures[i].format)),
  ]);
}

function libellesMesures(cube, cles) {
  return cles.map((c) => cube.mesure(c).libelle);
}

export function construireRapport(conteneur, cube, sections) {
  conteneur.replaceChildren();

  const periode = cube.meta.periode || {};
  const aujourdhui = new Date().toLocaleDateString("fr-FR",
    { day: "numeric", month: "long", year: "numeric" });

  conteneur.appendChild(titre("h1", "Ventes de véhicules du Domaine — rapport d'analyse"));
  conteneur.appendChild(paragraphe(
    `Édité le ${aujourdhui}. Source : ${cube.meta.source}. `
    + `Période couverte : ${periode.debut ?? "?"} à ${periode.fin ?? "?"}. `
    + `${formater(cube.nbSelectionnes, "entier")} lots retenus `
    + `sur ${formater(cube.n, "entier")} collectés.`));

  if (cube.nbFiltresActifs) {
    const filtres = [];
    for (const [cle, codes] of cube.filtresDim) {
      const valeurs = [...codes].map((c) => (c === -1 ? "(non renseigné)" : cube.dim[cle][c]));
      filtres.push(`${cube.libelleDim(cle)} : ${valeurs.join(", ")}`);
    }
    if (cube.recherche) filtres.push(`recherche « ${cube.recherche} »`);
    conteneur.appendChild(paragraphe("Filtres appliqués — " + filtres.join(" ; ") + "."));
  } else {
    conteneur.appendChild(paragraphe("Aucun filtre : le rapport porte sur l'ensemble des lots."));
  }

  /* --- synthèse --- */
  if (sections.includes("synthese")) {
    conteneur.appendChild(titre("h2", "Chiffres clés"));
    const cles = ["nb_lots", "produit_total", "prix_median", "prix_moyen",
                  "mise_a_prix_moyenne", "multiple_median", "taux_depassement",
                  "km_median", "age_moyen", "part_non_roulant"];
    const p = cube.pivot([], [], cles, { sousTotaux: false });
    conteneur.appendChild(tableau(["Indicateur", "Valeur"],
      cles.map((cle, rang) => [
        cube.mesure(cle).libelle,
        formater(p.total[rang], cube.mesure(cle).format),
      ])));
  }

  /* --- marques --- */
  if (sections.includes("marques")) {
    conteneur.appendChild(titre("h2", "Les quinze premières marques"));
    conteneur.appendChild(paragraphe(
      "Classées par nombre de lots. Le multiple médian rapporte le prix atteint "
      + "à la mise à prix : au-dessus de 1, la vente dépasse le prix de départ."));
    const mesures = ["nb_lots", "prix_median", "multiple_median", "km_median", "age_moyen"];
    conteneur.appendChild(tableau(
      ["Marque", ...libellesMesures(cube, mesures)],
      lignesPivot(cube, "marque", mesures)));
  }

  /* --- géographie --- */
  if (sections.includes("geo")) {
    conteneur.appendChild(titre("h2", "Répartition géographique"));
    const mesures = ["nb_lots", "produit_total", "prix_median", "multiple_median"];
    conteneur.appendChild(tableau(
      ["Région", ...libellesMesures(cube, mesures)],
      lignesPivot(cube, "region", mesures)));
  }

  /* --- temps --- */
  if (sections.includes("temps")) {
    conteneur.appendChild(titre("h2", "Évolution mensuelle"));
    const mesures = ["nb_lots", "produit_total", "prix_median", "taux_depassement"];
    conteneur.appendChild(tableau(
      ["Mois de vente", ...libellesMesures(cube, mesures)],
      lignesPivot(cube, "mois_vente", mesures, { limite: 24, trier: false })));
  }

  /* --- état --- */
  if (sections.includes("etat")) {
    conteneur.appendChild(titre("h2", "État des véhicules"));
    conteneur.appendChild(paragraphe(
      "L'état est déduit des mentions du descriptif : absence de clé ou de carte "
      + "grise, véhicule non roulant, chocs, pneumatiques hors service. "
      + "Un défaut « majeur » conditionne la remise en circulation."));
    const mesures = ["nb_lots", "prix_median", "multiple_median", "km_median"];
    conteneur.appendChild(tableau(
      ["État signalé", ...libellesMesures(cube, mesures)],
      lignesPivot(cube, "gravite", mesures, { trier: false })));
  }

  /* --- meilleures affaires --- */
  if (sections.includes("affaires")) {
    conteneur.appendChild(titre("h2", "Lots adjugés au plus près de la mise à prix"));
    conteneur.appendChild(paragraphe(
      "Vingt lots dont le prix atteint dépasse le moins la mise à prix — "
      + "là où la concurrence a été la plus faible."));
    const { indices } = cube.lots({ tri: "multiple_mise_a_prix", descendant: false,
                                    limite: 400 });
    const lignes = [];
    for (const i of indices) {
      const multiple = cube.col.multiple_mise_a_prix[i];
      if (multiple === null || multiple === undefined) continue;
      lignes.push([
        cube.valeur(i, "intitule") ?? "—",
        cube.valeur(i, "annee") ?? "—",
        formater(cube.col.kilometrage[i], "km"),
        cube.valeur(i, "gravite") ?? "—",
        formater(cube.col.mise_a_prix[i], "euro"),
        formater(cube.col.prix[i], "euro"),
        formater(multiple, "multiple"),
        cube.valeur(i, "departement") ?? "—",
      ]);
      if (lignes.length >= 20) break;
    }
    conteneur.appendChild(tableau(
      ["Lot", "Année", "Kilométrage", "État", "Mise à prix", "Prix atteint",
       "Multiple", "Département"], lignes));
  }

  conteneur.appendChild(titre("h2", "Note de lecture"));
  conteneur.appendChild(paragraphe(
    "Les mesures ignorent les valeurs manquantes : une moyenne de prix ne porte "
    + "que sur les lots dont le prix est connu, et son effectif peut différer du "
    + "nombre de lots affiché. Le kilométrage et l'année proviennent du descriptif "
    + "rédigé par le service vendeur ; ils sont indicatifs et non garantis."));
}
