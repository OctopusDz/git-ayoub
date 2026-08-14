/* Portail décisionnel — assemblage de l'interface.
 *
 * Charge le cube produit par l'ETL, câble les filtres, et alimente les cinq
 * vues : synthèse, cube (tableau croisé), graphiques, lots et rapport.
 */

import { Cube, formater, formaterCourt, AUCUNE } from "./cube.js";
import * as G from "./charts.js";
import { TableauCroise } from "./pivot.js";
import { construireRapport } from "./rapport.js";

let cube = null;
let croise = null;
let etatLots = { tri: "prix", descendant: true, page: 0, parPage: 50 };

/* ------------------------------------------------------------------ outils */
const $ = (selecteur) => document.querySelector(selecteur);
const $$ = (selecteur) => [...document.querySelectorAll(selecteur)];

function options(select, entrees, selection = []) {
  select.replaceChildren();
  let groupeCourant = null;
  let conteneur = select;
  for (const entree of entrees) {
    if (entree.groupe && entree.groupe !== groupeCourant) {
      groupeCourant = entree.groupe;
      conteneur = document.createElement("optgroup");
      conteneur.label = groupeCourant;
      select.appendChild(conteneur);
    }
    const option = document.createElement("option");
    option.value = entree.valeur;
    option.textContent = entree.libelle;
    option.selected = selection.includes(entree.valeur);
    conteneur.appendChild(option);
  }
}

/* Enregistrement d'un fichier.
 *
 * En local, un lien de téléchargement suffit. Sur la page publiée, le
 * téléchargement passe par le visualiseur, qui demande son accord au lecteur
 * et n'accepte qu'une liste d'extensions : on retombe sur « .txt » quand le
 * format tableur n'est pas autorisé, le contenu restant identique. */
async function telecharger(nom, contenu) {
  const donnees = "﻿" + contenu;                 // en-tête d'encodage
  const enregistreur = window.claude?.use
    ? await window.claude.use("downloads").catch(() => null)
    : null;

  if (enregistreur) {
    try {
      await enregistreur.save({ filename: nom, data: donnees });
    } catch (erreur) {
      if (erreur?.code === "extension_not_enabled") {
        try {
          await enregistreur.save({
            filename: nom.replace(/\.csv$/, ".txt"), data: donnees });
        } catch (repli) {
          if (repli?.code !== "declined") signaler(repli);
        }
      } else if (erreur?.code !== "declined") {
        signaler(erreur);
      }
    }
    return;
  }

  const lien = document.createElement("a");
  lien.href = URL.createObjectURL(new Blob([donnees], { type: "text/csv;charset=utf-8" }));
  lien.download = nom;
  document.body.appendChild(lien);
  lien.click();
  lien.remove();
  setTimeout(() => URL.revokeObjectURL(lien.href), 1000);
}

function signaler(erreur) {
  const message = erreur?.code === "too_large"
    ? "Sélection trop volumineuse pour un export : filtrez davantage."
    : "L'export n'a pas abouti sur cet appareil.";
  const bulle = document.createElement("div");
  bulle.className = "avis";
  bulle.setAttribute("role", "status");
  bulle.textContent = message;
  document.body.appendChild(bulle);
  setTimeout(() => bulle.remove(), 4000);
}

/** Masque les boutons d'export là où l'enregistrement est impossible. */
async function verifierExport() {
  if (!window.claude?.use) return;                    // usage local : lien direct
  const enregistreur = await window.claude.use("downloads").catch(() => null);
  if (enregistreur) return;
  for (const bouton of [$("#export-croise"), $("#export-lots")]) {
    if (bouton) bouton.hidden = true;
  }
}

/* --------------------------------------------------------------- chargement */
async function charger() {
  // Version autonome (page publiée) : le cube est embarqué dans la page.
  if (window.__CUBE__) return window.__CUBE__;
  try {
    const reponse = await fetch("data/dataset.json", { cache: "no-store" });
    if (!reponse.ok) throw new Error(reponse.status);
    return await reponse.json();
  } catch {
    return null;
  }
}

function afficherAbsenceDeDonnees() {
  const message = document.createElement("div");
  message.className = "message-vide";
  const titre = document.createElement("h2");
  titre.textContent = "Aucun cube à afficher";
  const texte = document.createElement("p");
  texte.textContent = "Lancez la collecte puis la construction du cube :";
  const code = document.createElement("code");
  code.textContent = "python3 -m scraper\npython3 -m etl.build_cube";
  const note = document.createElement("p");
  note.textContent = "Le portail se sert du fichier portal/data/dataset.json.";
  message.append(titre, texte, code, note);
  document.querySelector("main").replaceChildren(message);
  $("#sous-titre").textContent = "aucune donnée";
}

/* -------------------------------------------------------------- navigation */
function câblerOnglets() {
  $$(".onglets button").forEach((bouton) => {
    bouton.addEventListener("click", () => {
      $$(".onglets button").forEach((b) => b.setAttribute("aria-selected", "false"));
      bouton.setAttribute("aria-selected", "true");
      $$(".vue").forEach((v) => v.classList.remove("active"));
      $("#vue-" + bouton.dataset.vue).classList.add("active");
      rafraichirVue(bouton.dataset.vue);
    });
  });
}

function câblerTheme() {
  const racine = document.documentElement;
  const memorise = localStorage.getItem("theme");
  if (memorise) racine.dataset.theme = memorise;
  $("#bascule-theme").addEventListener("click", () => {
    const sombre = racine.dataset.theme === "dark"
      || (!racine.dataset.theme
          && window.matchMedia("(prefers-color-scheme: dark)").matches);
    racine.dataset.theme = sombre ? "light" : "dark";
    localStorage.setItem("theme", racine.dataset.theme);
    rafraichirTout();
  });
}

/* ------------------------------------------------------------------ filtres */
function câblerFiltres() {
  $("#barre-filtres").hidden = false;
  $("#nb-total").textContent = `sur ${formater(cube.n, "entier")}`;

  const dimensions = cube.meta.dimensions
    .filter((d) => d.cardinalite > 0)
    .map((d) => ({ valeur: d.cle, libelle: d.libelle, groupe: d.groupe }));

  const ajout = $("#ajout-filtre");
  options(ajout, [{ valeur: "", libelle: "＋ Filtrer sur une dimension…" }, ...dimensions]);

  const listeValeurs = $("#valeurs-filtre");

  ajout.addEventListener("change", () => {
    const cle = ajout.value;
    if (!cle) { listeValeurs.hidden = true; return; }
    const dejaRetenues = cube.filtresDim.get(cle);
    const valeurs = cube.valeurs(cle).map(({ valeur }) => ({ valeur, libelle: valeur }));
    const nonRenseignes = cube.col[cle].some((c) => c === -1)
      ? [{ valeur: AUCUNE, libelle: AUCUNE }] : [];
    const selection = dejaRetenues
      ? [...dejaRetenues].map((code) => (code === -1 ? AUCUNE : cube.dim[cle][code]))
      : [];
    options(listeValeurs, [...valeurs, ...nonRenseignes], selection);
    listeValeurs.size = Math.min(10, valeurs.length + nonRenseignes.length);
    listeValeurs.hidden = false;
    listeValeurs.focus();
  });

  listeValeurs.addEventListener("change", () => {
    const cle = ajout.value;
    if (!cle) return;
    const retenues = new Set([...listeValeurs.selectedOptions].map((o) => o.value));
    cube.setFiltreDim(cle, retenues);
    rafraichirTout();
  });

  let minuteur;
  $("#recherche").addEventListener("input", (e) => {
    clearTimeout(minuteur);
    minuteur = setTimeout(() => {
      cube.setRecherche(e.target.value);
      rafraichirTout();
    }, 220);
  });

  $("#raz-filtres").addEventListener("click", () => {
    cube.reinitialiserFiltres();
    $("#recherche").value = "";
    listeValeurs.hidden = true;
    ajout.value = "";
    rafraichirTout();
  });
}

function afficherJetons() {
  const zone = $("#jetons-filtres");
  zone.replaceChildren();

  for (const [cle, codes] of cube.filtresDim) {
    const valeurs = [...codes].map((c) => (c === -1 ? AUCUNE : cube.dim[cle][c]));
    const jeton = document.createElement("span");
    jeton.className = "jeton";
    const texte = document.createElement("span");
    const resume = valeurs.length > 2
      ? `${valeurs.length} valeurs` : valeurs.join(", ");
    texte.textContent = `${cube.libelleDim(cle)} : ${resume}`;
    jeton.appendChild(texte);
    const fermer = document.createElement("button");
    fermer.textContent = "✕";
    fermer.setAttribute("aria-label", "Retirer ce filtre");
    fermer.addEventListener("click", () => {
      cube.setFiltreDim(cle, null);
      rafraichirTout();
    });
    jeton.appendChild(fermer);
    zone.appendChild(jeton);
  }

  if (cube.recherche) {
    const jeton = document.createElement("span");
    jeton.className = "jeton";
    const texte = document.createElement("span");
    texte.textContent = `Recherche : « ${cube.recherche} »`;
    const fermer = document.createElement("button");
    fermer.textContent = "✕";
    fermer.setAttribute("aria-label", "Effacer la recherche");
    fermer.addEventListener("click", () => {
      cube.setRecherche("");
      $("#recherche").value = "";
      rafraichirTout();
    });
    jeton.append(texte, fermer);
    zone.appendChild(jeton);
  }
}


/* ------------------------------------------------------------ opportunités */
/* La vue d'achat : pour chaque vente ouverte, ce qu'elle vaut d'après les
   ventes déjà closes, et jusqu'où il est raisonnable d'enchérir. */

const CIBLES = {
  "hybride-essence": {
    libelle: "hybrides essence",
    retient: (energie) => /^Hybride essence/.test(energie || ""),
  },
  "hybride-tout": {
    libelle: "hybrides, toutes bases",
    retient: (energie) => /^Hybride/.test(energie || ""),
  },
  "e85": {
    libelle: "superéthanol E85",
    retient: (energie) => /E85/.test(energie || ""),
  },
  toutes: { libelle: "ventes à venir", retient: () => true },
};

function câblerOpportunites() {
  ["#opp-cible", "#opp-tri", "#opp-metropole", "#opp-roulant", "#opp-pro"].forEach((s) =>
    $(s).addEventListener("change", rendreOpportunites));
}

function lotsAVenir() {
  const codes = cube.dim.statut || [];
  const rang = codes.findIndex((v) => /venir/i.test(v));
  if (rang < 0) return [];
  const colonne = cube.col.statut;
  const liste = [];
  for (let i = 0; i < cube.n; i++) if (colonne[i] === rang) liste.push(i);
  return liste;
}

function rendreOpportunites() {
  const cible = CIBLES[$("#opp-cible").value] || CIBLES.toutes;
  const tri = $("#opp-tri").value;
  const metropoleSeule = $("#opp-metropole").checked;
  const ecarterNonRoulants = $("#opp-roulant").checked;
  const ecarterPro = $("#opp-pro").checked;

  let lots = lotsAVenir().filter((i) => cible.retient(cube.valeur(i, "carburant")));
  const totalCible = lots.length;
  if (metropoleSeule) lots = lots.filter((i) => cube.valeur(i, "metropole") !== "Non");
  if (ecarterNonRoulants) lots = lots.filter((i) => cube.valeur(i, "non_roulant") !== "Oui");
  if (ecarterPro) lots = lots.filter((i) => cube.valeur(i, "reserve_aux_pros") !== "Oui");

  lots.sort((a, b) => {
    if (tri === "date_fin") {
      return String(cube.valeur(a, "date_fin") || "9")
        .localeCompare(String(cube.valeur(b, "date_fin") || "9"));
    }
    return (cube.col[tri]?.[b] ?? -Infinity) - (cube.col[tri]?.[a] ?? -Infinity);
  });

  const avertissement = $("#opp-avertissement");
  avertissement.textContent =
    `${lots.length} ${cible.libelle} en vente sur ${lotsAVenir().length} lots ouverts. `
    + "Les estimations viennent des ventes déjà closes : l'erreur médiane mesurée est "
    + "de 29 % tous véhicules confondus, nettement moindre sur les modèles très "
    + "représentés. Les 11 % de frais de vente sont déjà retranchés de l'enchère "
    + "maximum conseillée. Un prix conseillé n'est pas une garantie — la fiche du "
    + "lot et l'état réel priment.";

  const zone = $("#opp-liste");
  zone.replaceChildren();

  if (!lots.length) {
    const vide = document.createElement("p");
    vide.className = "table-vide";
    vide.textContent = totalCible
      ? "Tous les lots correspondants ont été écartés par les cases cochées."
      : `Aucun ${cible.libelle.replace(/s$/, "")} parmi les ventes ouvertes en ce moment.`;
    zone.appendChild(vide);
    return;
  }

  const liste = document.createElement("div");
  liste.className = "opp";
  for (const i of lots) liste.appendChild(carteOpportunite(i));
  zone.appendChild(liste);
}

function carteOpportunite(i) {
  const verdict = cube.valeur(i, "verdict") || "Pas de référence";
  const carte = document.createElement("article");
  carte.className = "opp-carte " + verdict.toLowerCase()
    .normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z]+/g, "-");

  const tete = document.createElement("div");
  tete.className = "opp-tete";
  const titre = document.createElement("h3");
  titre.textContent = cube.valeur(i, "intitule") || "Lot sans intitulé";
  const etiquette = document.createElement("span");
  etiquette.className = "etiquette " + (
    verdict === "Très intéressant" ? "bon"
      : verdict === "À éviter" ? "critique" : "attention");
  etiquette.textContent = verdict;
  const echeance = document.createElement("span");
  echeance.className = "echeance";
  const fin = cube.valeur(i, "date_fin");
  echeance.textContent = fin ? "clôture le " + String(fin).slice(0, 10) : "";
  tete.append(titre, etiquette, echeance);

  const chiffres = document.createElement("div");
  chiffres.className = "opp-chiffres";
  const cases = [
    { libelle: "Mise à prix", valeur: cube.col.mise_a_prix[i], format: "euro" },
    { libelle: "Prix attendu", valeur: cube.col.estimation[i], format: "euro" },
    { libelle: "Enchère max", valeur: cube.col.prix_max_conseille[i],
      format: "euro", classe: "plafond" },
    { libelle: "Coût total, frais compris", valeur: cube.col.cout_total_max[i],
      format: "euro", classe: "plafond" },
    { libelle: "Marge", valeur: cube.col.marge_pct[i], format: "pourcent" },
  ];
  for (const c of cases) {
    const bloc = document.createElement("div");
    bloc.className = "opp-chiffre" + (c.classe ? " " + c.classe : "");
    const libelle = document.createElement("div");
    libelle.className = "libelle";
    libelle.textContent = c.libelle;
    const valeur = document.createElement("div");
    valeur.className = "valeur";
    valeur.textContent = formater(c.valeur, c.format);
    bloc.append(libelle, valeur);
    chiffres.appendChild(bloc);
  }

  const detail = document.createElement("div");
  detail.className = "opp-detail";
  const bas = cube.col.fourchette_basse[i];
  const haut = cube.col.fourchette_haute[i];
  const morceaux = [
    cube.valeur(i, "carburant"),
    cube.valeur(i, "annee_douteuse") === "Oui"
      ? "millésime annoncé incohérent" : cube.valeur(i, "annee"),
    cube.col.kilometrage[i] ? formater(cube.col.kilometrage[i], "km") : "kilométrage inconnu",
    cube.valeur(i, "gravite"),
    cube.valeur(i, "departement"),
    cube.valeur(i, "reserve_aux_pros") === "Oui" ? "réservé aux professionnels" : null,
  ].filter(Boolean);
  const ligne1 = document.createElement("div");
  ligne1.textContent = morceaux.join(" · ");
  const ligne2 = document.createElement("div");
  ligne2.textContent = bas && haut
    ? `Fourchette observée ${formater(bas, "euro")} – ${formater(haut, "euro")}, `
      + `d'après ${cube.col.nb_comparables[i]} ventes comparables `
      + `(${cube.valeur(i, "base_comparables")}) — confiance ${cube.valeur(i, "confiance")}.`
    : "Pas assez de ventes comparables pour estimer ce lot.";
  detail.append(ligne1, ligne2);

  const description = cube.valeur(i, "description");
  if (description) {
    const ligne3 = document.createElement("div");
    ligne3.textContent = description;
    detail.appendChild(ligne3);
  }

  const url = cube.valeur(i, "url");
  if (url) {
    const lien = document.createElement("a");
    lien.href = url;
    lien.target = "_blank";
    lien.rel = "noopener noreferrer";
    lien.textContent = "Voir la fiche du lot →";
    detail.appendChild(lien);
  }

  carte.append(tete, chiffres, detail);
  return carte;
}

/* ----------------------------------------------------------------- synthèse */
const INDICATEURS = [
  { mesure: "nb_lots", libelle: "Lots sélectionnés" },
  { mesure: "produit_total", libelle: "Produit total" },
  { mesure: "prix_median", libelle: "Prix médian" },
  { mesure: "multiple_median", libelle: "Multiple médian sur mise à prix" },
  { mesure: "taux_depassement", libelle: "Lots au-dessus de la mise à prix" },
  { mesure: "km_median", libelle: "Kilométrage médian" },
];

function rendreSynthese() {
  const zone = $("#indicateurs");
  zone.replaceChildren();
  const p = cube.pivot([], [], INDICATEURS.map((i) => i.mesure), { sousTotaux: false });

  INDICATEURS.forEach((indicateur, rang) => {
    const mesure = cube.mesure(indicateur.mesure);
    const carte = document.createElement("div");
    carte.className = "indicateur";
    const libelle = document.createElement("div");
    libelle.className = "libelle";
    libelle.textContent = indicateur.libelle;
    const valeur = document.createElement("div");
    valeur.className = "valeur";
    const brut = p.total[rang];
    valeur.textContent = mesure.format === "euro" && Math.abs(brut ?? 0) >= 1e5
      ? formaterCourt(brut, mesure.format) : formater(brut, mesure.format);
    carte.append(libelle, valeur);
    zone.appendChild(carte);
  });

  /* Classement des marques */
  G.barresHorizontales($("#g-marques"),
    cube.serie("marque", "nb_lots", { limite: 12 }),
    { format: "entier", libelleValeur: "Lots", auClic: (pt) => forerDimension("marque", pt.libelle) });

  /* Prix médian par tranche de kilométrage — dimension ordinale, ordre imposé */
  G.barresVerticales($("#g-km-prix"),
    cube.serie("tranche_km", "prix_median", { trier: false }),
    { format: "euro", couleur: "var(--serie-3)", libelleValeur: "Prix médian",
      auClic: (pt) => forerDimension("tranche_km", pt.libelle) });

  G.barresHorizontales($("#g-energie"),
    cube.serie("carburant", "nb_lots", { limite: 8 }),
    { format: "entier", couleur: "var(--serie-2)", libelleValeur: "Lots",
      auClic: (pt) => forerDimension("carburant", pt.libelle) });

  G.barresHorizontales($("#g-etat"),
    cube.serie("gravite", "nb_lots", { trier: false }),
    { format: "entier", couleur: "var(--serie-4)", libelleValeur: "Lots",
      auClic: (pt) => forerDimension("gravite", pt.libelle) });

  /* Évolution : deux mesures d'échelles différentes → deux graphiques, jamais
     deux axes verticaux sur la même figure. */
  const mois = cube.serie("mois_vente", "produit_total", { trier: false });
  const volumes = cube.serie("mois_vente", "nb_lots", { trier: false });
  const zoneTemps = $("#g-temps");
  zoneTemps.replaceChildren();
  const hautTemps = document.createElement("div");
  const basTemps = document.createElement("div");
  zoneTemps.append(hautTemps, basTemps);
  G.courbes(hautTemps, [{ nom: "Produit total", points: mois, couleur: "var(--serie-1)" }],
    { format: "euro", hauteur: 220 });
  G.courbes(basTemps, [{ nom: "Nombre de lots", points: volumes, couleur: "var(--serie-3)" }],
    { format: "entier", hauteur: 180 });
  G.legende($("#l-temps"), [
    { nom: "Produit total (€) — graphique du haut", couleur: "var(--serie-1)" },
    { nom: "Nombre de lots — graphique du bas", couleur: "var(--serie-3)" },
  ]);

  G.barresHorizontales($("#g-regions"),
    cube.serie("region", "nb_lots", { limite: 14 }),
    { format: "entier", couleur: "var(--serie-7)", libelleValeur: "Lots",
      auClic: (pt) => forerDimension("region", pt.libelle) });
}

function forerDimension(cle, valeur) {
  cube.setFiltreDim(cle, new Set([valeur]));
  rafraichirTout();
}

/* --------------------------------------------------------------------- cube */
function câblerCube() {
  const dimensions = cube.meta.dimensions
    .filter((d) => d.cardinalite > 0)
    .map((d) => ({ valeur: d.cle, libelle: d.libelle, groupe: d.groupe }));
  const mesures = cube.meta.mesures.map((m) => ({ valeur: m.cle, libelle: m.libelle }));

  options($("#dim-lignes"), dimensions, ["marque"]);
  options($("#dim-colonnes"), dimensions, []);
  options($("#mesures"), mesures,
    cube.meta.mesures.filter((m) => m.defaut).map((m) => m.cle));

  croise = new TableauCroise($("#tableau-croise"), {
    auTriMesure: (cle) => {
      if (etatCroise.triMesure === cle) etatCroise.triDescendant = !etatCroise.triDescendant;
      else { etatCroise.triMesure = cle; etatCroise.triDescendant = true; }
      rendreCube();
    },
    auForage: ({ lignes, colonnes, dimLignes, dimColonnes }) => {
      lignes.forEach((valeur, i) => {
        if (dimLignes[i]) cube.setFiltreDim(dimLignes[i], new Set([valeur]));
      });
      colonnes.forEach((valeur, i) => {
        if (dimColonnes[i]) cube.setFiltreDim(dimColonnes[i], new Set([valeur]));
      });
      rafraichirTout();
    },
  });

  ["#dim-lignes", "#dim-colonnes", "#mesures", "#opt-heatmap",
   "#opt-soustotaux", "#opt-limite"].forEach((selecteur) => {
    $(selecteur).addEventListener("change", rendreCube);
  });

  $("#export-croise").addEventListener("click", () => {
    const { resultat, lignes, colonnes } = dernierPivot;
    const libelles = Object.fromEntries(
      cube.meta.dimensions.map((d) => [d.cle, d.libelle]));
    telecharger("tableau-croise.csv",
      croise.versCSV(resultat, lignes, colonnes, libelles));
  });
}

const etatCroise = { triMesure: null, triDescendant: true };
let dernierPivot = { resultat: null, lignes: [], colonnes: [] };

function selection(selecteur) {
  return [...$(selecteur).selectedOptions].map((o) => o.value);
}

function rendreCube() {
  const lignes = selection("#dim-lignes");
  const colonnes = selection("#dim-colonnes");
  let mesures = selection("#mesures");
  if (!mesures.length) mesures = ["nb_lots"];

  const resultat = cube.pivot(lignes, colonnes, mesures, {
    sousTotaux: $("#opt-soustotaux").checked,
    triMesure: etatCroise.triMesure,
    triDescendant: etatCroise.triDescendant,
    limiteLignes: Number($("#opt-limite").value) || 0,
  });
  dernierPivot = { resultat, lignes, colonnes };

  const libelles = Object.fromEntries(
    cube.meta.dimensions.map((d) => [d.cle, d.libelle]));
  croise.rendre(resultat, lignes, colonnes, {
    heatmap: $("#opt-heatmap").checked,
    triMesure: etatCroise.triMesure,
    triDescendant: etatCroise.triDescendant,
    libelles,
  });
}

/* --------------------------------------------------------------- graphiques */
function câblerGraphiques() {
  const dimensions = cube.meta.dimensions
    .filter((d) => d.cardinalite > 0)
    .map((d) => ({ valeur: d.cle, libelle: d.libelle, groupe: d.groupe }));
  const mesures = cube.meta.mesures.map((m) => ({ valeur: m.cle, libelle: m.libelle }));

  options($("#g-dimension"), dimensions, ["marque"]);
  options($("#g-mesure"), mesures, ["nb_lots"]);
  options($("#g-serie"), [{ valeur: "", libelle: "— aucun —" }, ...dimensions], [""]);

  ["#g-dimension", "#g-mesure", "#g-type", "#g-serie"].forEach((s) =>
    $(s).addEventListener("change", rendreGraphiques));
}

function rendreGraphiques() {
  const dimension = $("#g-dimension").value;
  const cleMesure = $("#g-mesure").value;
  const type = $("#g-type").value;
  const dimSerie = $("#g-serie").value;
  const mesure = cube.mesure(cleMesure);
  const zone = $("#g-principal");
  const legende = $("#g-legende");
  legende.replaceChildren();

  $("#g-titre").textContent = `${mesure.libelle} par ${cube.libelleDim(dimension)}`;
  $("#g-note").textContent = `${formater(cube.nbSelectionnes, "entier")} lots sélectionnés`;

  const dim = cube.dimension(dimension);
  const ordonne = dim.type === "ordinale" || dim.type === "temps";

  if (type === "empilees" && dimSerie) {
    const p = cube.pivot([dimension], [dimSerie], [cleMesure], { sousTotaux: false });
    const categories = p.lignes.map((l) => l.libelle);
    /* Au-delà de huit séries, les couleurs ne suffisent plus : on garde les
       sept premières et on regroupe le reste. */
    const colonnes = p.colonnes.slice(0, 7);
    const series = colonnes.map((c, rang) => ({
      nom: c.libelle,
      couleur: G.SERIES[rang % G.SERIES.length],
      valeurs: p.lignes.map((l) => p.lire(l.chemin, c.chemin)[0] || 0),
    }));
    if (p.colonnes.length > 7) {
      series.push({
        nom: "Autres",
        couleur: G.SERIES[7],
        valeurs: p.lignes.map((l) => p.colonnes.slice(7).reduce(
          (somme, c) => somme + (p.lire(l.chemin, c.chemin)[0] || 0), 0)),
      });
    }
    G.barresEmpilees(zone, categories, series, { format: mesure.format });
    G.legende(legende, series);
  } else {
    const points = cube.serie(dimension, cleMesure,
      { limite: ordonne ? 0 : 20, trier: !ordonne });
    if (type === "courbe") {
      G.courbes(zone, [{ nom: mesure.libelle, points }], { format: mesure.format });
    } else if (type === "barresV") {
      G.barresVerticales(zone, points,
        { format: mesure.format, libelleValeur: mesure.libelle,
          auClic: (pt) => forerDimension(dimension, pt.libelle) });
    } else {
      G.barresHorizontales(zone, points,
        { format: mesure.format, libelleValeur: mesure.libelle,
          auClic: (pt) => forerDimension(dimension, pt.libelle) });
    }
  }

  rendreNuage();
}

function rendreNuage() {
  /* Trois séries au plus : au-delà, des points superposés de teintes voisines
     ne se distinguent plus, notamment en vision déficiente des couleurs. */
  const top = cube.serie("carburant", "nb_lots", { limite: G.SERIES_SUPERPOSEES });
  const parEnergie = new Map(top.map((t, rang) => [t.libelle,
    { nom: t.libelle, couleur: G.SERIES[rang], points: [] }]));

  const indices = cube.indices();
  const pas = Math.max(1, Math.ceil(indices.length / 1200));   // densité lisible
  for (let i = 0; i < indices.length; i += pas) {
    const ligne = indices[i];
    const km = cube.col.kilometrage[ligne];
    const prix = cube.col.prix[ligne];
    if (km === null || prix === null || km === undefined || prix === undefined) continue;
    const energie = cube.valeur(ligne, "carburant");
    const groupe = parEnergie.get(energie);
    if (!groupe) continue;
    groupe.points.push({ x: km, y: prix, libelle: cube.valeur(ligne, "intitule") });
  }

  const groupes = [...parEnergie.values()];
  G.nuage($("#g-nuage"), groupes, {
    formatX: "km", formatY: "euro",
    titreX: "Kilométrage", titreY: "Prix atteint",
  });
  G.legende($("#l-nuage"), groupes);
}

/* --------------------------------------------------------------------- lots */
const COLONNES_LOTS = [
  { champ: "image", libelle: "", type: "image" },
  { champ: "intitule", libelle: "Lot", type: "lien" },
  { champ: "annee", libelle: "Année" },
  { champ: "kilometrage", libelle: "Kilométrage", type: "nombre", format: "km" },
  { champ: "carburant", libelle: "Énergie" },
  { champ: "gravite", libelle: "État", type: "etat" },
  { champ: "mise_a_prix", libelle: "Mise à prix", type: "nombre", format: "euro" },
  { champ: "prix", libelle: "Prix atteint", type: "nombre", format: "euro" },
  { champ: "multiple_mise_a_prix", libelle: "Multiple", type: "nombre", format: "multiple" },
  { champ: "departement", libelle: "Département" },
  { champ: "date_fin", libelle: "Fin de vente", type: "date" },
  { champ: "statut", libelle: "Statut" },
];

function colonnesLots() {
  return COLONNES_LOTS.filter(
    (c) => c.type !== "image" || (cube.txt.image && cube.txt.image.some(Boolean)));
}

function câblerLots() {
  const triables = colonnesLots()
    .filter((c) => c.type !== "image")
    .map((c) => ({ valeur: c.champ, libelle: c.libelle }));
  options($("#tri-lots"), triables, ["prix"]);

  $("#tri-lots").addEventListener("change", () => {
    etatLots.tri = $("#tri-lots").value; etatLots.page = 0; rendreLots();
  });
  $("#sens-lots").addEventListener("change", () => {
    etatLots.descendant = $("#sens-lots").value === "desc";
    etatLots.page = 0; rendreLots();
  });
  $("#page-precedente").addEventListener("click", () => {
    if (etatLots.page > 0) { etatLots.page--; rendreLots(); }
  });
  $("#page-suivante").addEventListener("click", () => {
    etatLots.page++; rendreLots();
  });
  $("#export-lots").addEventListener("click", exporterLots);
}

function rendreLots() {
  const { total, indices } = cube.lots({
    tri: etatLots.tri, descendant: etatLots.descendant,
    limite: etatLots.parPage, decalage: etatLots.page * etatLots.parPage,
  });

  const zone = $("#table-lots");
  zone.replaceChildren();

  if (!total) {
    const vide = document.createElement("p");
    vide.className = "table-vide";
    vide.textContent = "Aucun lot ne correspond à la sélection.";
    zone.appendChild(vide);
    $("#etat-pagination").textContent = "";
    return;
  }

  const table = document.createElement("table");
  table.className = "lots";
  const thead = document.createElement("thead");
  const rang = document.createElement("tr");
  for (const colonne of colonnesLots()) {
    const th = document.createElement("th");
    th.textContent = colonne.libelle;
    if (colonne.type === "nombre") th.className = "nombre";
    if (colonne.type !== "image") {
      th.addEventListener("click", () => {
        if (etatLots.tri === colonne.champ) etatLots.descendant = !etatLots.descendant;
        else { etatLots.tri = colonne.champ; etatLots.descendant = true; }
        $("#tri-lots").value = etatLots.tri;
        $("#sens-lots").value = etatLots.descendant ? "desc" : "asc";
        etatLots.page = 0;
        rendreLots();
      });
    }
    rang.appendChild(th);
  }
  thead.appendChild(rang);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  for (const ligne of indices) {
    const tr = document.createElement("tr");
    for (const colonne of colonnesLots()) {
      const td = document.createElement("td");
      const valeur = cube.valeur(ligne, colonne.champ);

      if (colonne.type === "image") {
        if (valeur) {
          const img = document.createElement("img");
          img.className = "vignette";
          img.src = valeur;
          img.alt = "";
          img.loading = "lazy";
          td.appendChild(img);
        }
      } else if (colonne.type === "lien") {
        const url = cube.valeur(ligne, "url");
        if (url) {
          const a = document.createElement("a");
          a.href = url;
          a.target = "_blank";
          a.rel = "noopener noreferrer";
          a.textContent = valeur ?? "—";
          td.appendChild(a);
        } else td.textContent = valeur ?? "—";
      } else if (colonne.type === "etat") {
        if (valeur) {
          const badge = document.createElement("span");
          badge.className = "etiquette " + (
            valeur === "Aucun défaut signalé" ? "bon"
            : valeur === "Défauts majeurs" ? "critique" : "attention");
          badge.textContent = valeur;
          td.appendChild(badge);
        } else td.textContent = "—";
      } else if (colonne.type === "date") {
        td.textContent = valeur ? String(valeur).slice(0, 10) : "—";
      } else if (colonne.type === "nombre") {
        td.className = "nombre";
        td.textContent = valeur === null || valeur === undefined
          ? "—" : formater(valeur, colonne.format || "entier");
      } else {
        td.textContent = valeur ?? "—";
      }
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);

  const cadre = document.createElement("div");
  cadre.className = "lots-cadre";
  cadre.appendChild(table);
  zone.appendChild(cadre);

  const debut = etatLots.page * etatLots.parPage + 1;
  const fin = Math.min(total, debut + etatLots.parPage - 1);
  $("#etat-pagination").textContent =
    `${formater(debut, "entier")} – ${formater(fin, "entier")} sur ${formater(total, "entier")}`;
  $("#page-precedente").disabled = etatLots.page === 0;
  $("#page-suivante").disabled = fin >= total;
}

function exporterLots() {
  const champs = ["id_lot", "intitule", "marque", "modele", "annee", "kilometrage",
    "carburant", "boite_vitesses", "gravite", "mise_a_prix", "prix",
    "multiple_mise_a_prix", "departement", "region", "centre_vente",
    "statut", "date_fin", "immatriculation", "vin", "url"];
  const echapper = (v) => {
    const texte = v === null || v === undefined ? "" : String(v);
    return /[";\n]/.test(texte) ? '"' + texte.replace(/"/g, '""') + '"' : texte;
  };
  const lignes = [champs.join(";")];
  for (const i of cube.indices()) {
    lignes.push(champs.map((c) => echapper(cube.valeur(i, c))).join(";"));
  }
  telecharger("lots-selection.csv", lignes.join("\n"));
}

/* ------------------------------------------------------------------ rapport */
function câblerRapport() {
  $$(".section-rapport").forEach((c) => c.addEventListener("change", rendreRapport));
  $("#imprimer-rapport").addEventListener("click", () => window.print());
}

function rendreRapport() {
  const sections = $$(".section-rapport").filter((c) => c.checked).map((c) => c.value);
  construireRapport($("#contenu-rapport"), cube, sections);
}

/* ------------------------------------------------------------ orchestration */
function rafraichirVue(nom) {
  if (nom === "opportunites") rendreOpportunites();
  else if (nom === "synthese") rendreSynthese();
  else if (nom === "cube") rendreCube();
  else if (nom === "graphiques") rendreGraphiques();
  else if (nom === "lots") rendreLots();
  else if (nom === "rapport") rendreRapport();
}

function rafraichirTout() {
  $("#nb-selection").textContent = formater(cube.nbSelectionnes, "entier");
  afficherJetons();
  etatLots.page = 0;
  const active = $$(".onglets button").find((b) => b.getAttribute("aria-selected") === "true");
  rafraichirVue(active?.dataset.vue || "opportunites");
}

async function demarrer() {
  câblerTheme();
  const donnees = await charger();
  if (!donnees) { afficherAbsenceDeDonnees(); return; }

  cube = new Cube(donnees);
  window.cube = cube;                   // exploration en console

  const periode = donnees.meta.periode || {};
  $("#sous-titre").textContent =
    `${formater(cube.n, "entier")} lots · ${periode.debut ?? "?"} → ${periode.fin ?? "?"}`
    + ` · collecte du ${(donnees.meta.genere_le || "").slice(0, 10)}`;

  câblerOnglets();
  câblerFiltres();
  câblerOpportunites();
  câblerCube();
  câblerGraphiques();
  câblerLots();
  câblerRapport();
  rafraichirTout();
  verifierExport();

  let redimensionnement;
  window.addEventListener("resize", () => {
    clearTimeout(redimensionnement);
    redimensionnement = setTimeout(rafraichirTout, 200);
  });
}

demarrer();
