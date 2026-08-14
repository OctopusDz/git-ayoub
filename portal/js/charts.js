/* Graphiques SVG, sans dépendance.
 *
 * Règles de lecture appliquées partout : une seule échelle par graphique,
 * couleurs attribuées à l'entité et jamais recyclées, grille en retrait,
 * étiquettes directes plutôt qu'une valeur sur chaque point, et survol
 * systématique — un graphique dans une page est un objet interactif.
 */

import { formater, formaterCourt } from "./cube.js";

const SVG = "http://www.w3.org/2000/svg";

/* Emplacements de couleur : l'ordre est fixe, jamais permuté ni cyclé. */
export const SERIES = ["var(--serie-1)", "var(--serie-2)", "var(--serie-3)",
                       "var(--serie-4)", "var(--serie-5)", "var(--serie-6)",
                       "var(--serie-7)", "var(--serie-8)"];
/* Au-delà de trois séries, un nuage de points n'est plus discriminable :
   les formes qui superposent leurs marques s'y limitent. */
export const SERIES_SUPERPOSEES = 3;

function element(nom, attributs = {}) {
  const noeud = document.createElementNS(SVG, nom);
  for (const [cle, valeur] of Object.entries(attributs)) {
    if (valeur !== null && valeur !== undefined) noeud.setAttribute(cle, valeur);
  }
  return noeud;
}

function texte(contenu, attributs = {}) {
  const noeud = element("text", attributs);
  noeud.textContent = contenu;
  return noeud;
}

/* --- infobulle partagée --------------------------------------------------- */
let bulle;
function bulleUnique() {
  if (!bulle) {
    bulle = document.createElement("div");
    bulle.className = "infobulle";
    bulle.setAttribute("role", "status");
    document.body.appendChild(bulle);
  }
  return bulle;
}

function montrerBulle(evenement, lignes) {
  const noeud = bulleUnique();
  noeud.replaceChildren();
  for (const ligne of lignes) {
    const p = document.createElement("div");
    if (ligne.pastille) {
      const pastille = document.createElement("span");
      pastille.className = "pastille";
      pastille.style.background = ligne.pastille;
      p.appendChild(pastille);
    }
    const libelle = document.createElement("span");
    libelle.className = ligne.fort ? "bulle-fort" : "bulle-libelle";
    libelle.textContent = ligne.libelle;
    p.appendChild(libelle);
    if (ligne.valeur !== undefined) {
      const valeur = document.createElement("span");
      valeur.className = "bulle-valeur";
      valeur.textContent = ligne.valeur;
      p.appendChild(valeur);
    }
    noeud.appendChild(p);
  }
  noeud.classList.add("visible");
  deplacerBulle(evenement);
}

function deplacerBulle(evenement) {
  const noeud = bulleUnique();
  const marge = 14;
  const largeur = noeud.offsetWidth;
  const hauteur = noeud.offsetHeight;
  let x = evenement.clientX + marge;
  let y = evenement.clientY + marge;
  if (x + largeur > window.innerWidth - 8) x = evenement.clientX - largeur - marge;
  if (y + hauteur > window.innerHeight - 8) y = evenement.clientY - hauteur - marge;
  noeud.style.transform = `translate(${Math.max(4, x)}px, ${Math.max(4, y)}px)`;
}

function cacherBulle() {
  bulleUnique().classList.remove("visible");
}

function survol(noeud, lignes, auClic) {
  noeud.addEventListener("pointerenter", (e) => montrerBulle(e, lignes()));
  noeud.addEventListener("pointermove", deplacerBulle);
  noeud.addEventListener("pointerleave", cacherBulle);
  if (auClic) {
    noeud.style.cursor = "pointer";
    noeud.addEventListener("click", auClic);
  }
}

/* --- échelles -------------------------------------------------------------- */
function graduations(max, nb = 4) {
  if (!(max > 0)) return [0];
  const brut = max / nb;
  const magnitude = Math.pow(10, Math.floor(Math.log10(brut)));
  const pas = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((p) => p >= brut) || magnitude * 10;
  const valeurs = [];
  for (let v = 0; v <= max * 1.0001; v += pas) valeurs.push(v);
  if (valeurs[valeurs.length - 1] < max) valeurs.push(valeurs[valeurs.length - 1] + pas);
  return valeurs;
}

function socle(conteneur, hauteur) {
  conteneur.replaceChildren();
  const largeur = Math.max(320, conteneur.clientWidth || 640);
  const svg = element("svg", {
    viewBox: `0 0 ${largeur} ${hauteur}`, width: "100%", height: hauteur,
    role: "img", class: "graphique",
  });
  conteneur.appendChild(svg);
  return { svg, largeur, hauteur };
}

function messageVide(conteneur, texteVide = "Aucune donnée pour cette sélection") {
  conteneur.replaceChildren();
  const vide = document.createElement("p");
  vide.className = "graphique-vide";
  vide.textContent = texteVide;
  conteneur.appendChild(vide);
}

/* --- barres horizontales (classement) -------------------------------------- */
export function barresHorizontales(conteneur, points, options = {}) {
  const { format = "entier", couleur = SERIES[0], auClic = null,
          libelleValeur = "" } = options;
  if (!points.length) return messageVide(conteneur);

  const hauteurBarre = 26;
  const interligne = 8;
  const margeGauche = Math.min(190, Math.max(90,
    ...points.map((p) => String(p.libelle).length * 7.2)));
  const margeDroite = 76;
  const hauteur = points.length * (hauteurBarre + interligne) + 26;
  const { svg, largeur } = socle(conteneur, hauteur);
  const largeurUtile = largeur - margeGauche - margeDroite;
  const max = Math.max(...points.map((p) => p.valeur || 0), 0);

  points.forEach((point, rang) => {
    const y = rang * (hauteurBarre + interligne) + 6;
    const largeurBarre = max > 0 ? Math.max(2, (point.valeur / max) * largeurUtile) : 2;

    const etiquette = texte(point.libelle, {
      x: margeGauche - 10, y: y + hauteurBarre / 2 + 4,
      "text-anchor": "end", class: "axe-libelle",
    });
    svg.appendChild(etiquette);

    const groupe = element("g");
    const piste = element("rect", {
      x: margeGauche, y, width: Math.max(largeurUtile, 1), height: hauteurBarre,
      fill: "var(--piste)", rx: 4,
    });
    const barre = element("rect", {
      x: margeGauche, y, width: largeurBarre, height: hauteurBarre,
      fill: couleur, rx: 4,
    });
    groupe.append(piste, barre);
    svg.appendChild(groupe);

    /* Étiquette directe, posée après la piste pour rester lisible : la valeur
       se lit sans passer par l'axe. */
    svg.appendChild(texte(formaterCourt(point.valeur, format), {
      x: margeGauche + largeurBarre + 8, y: y + hauteurBarre / 2 + 4,
      class: "valeur-directe",
    }));

    survol(groupe, () => [
      { libelle: point.libelle, fort: true },
      { libelle: libelleValeur, valeur: formater(point.valeur, format), pastille: couleur },
      ...(point.detail || []),
    ], auClic ? () => auClic(point) : null);
  });

  return svg;
}

/* --- barres verticales (distribution) --------------------------------------- */
export function barresVerticales(conteneur, points, options = {}) {
  const { format = "entier", couleur = SERIES[0], auClic = null,
          libelleValeur = "", hauteur = 260 } = options;
  if (!points.length) return messageVide(conteneur);

  const margeBas = 54;
  const margeHaut = 16;
  const margeGauche = 58;
  const { svg, largeur } = socle(conteneur, hauteur);
  const largeurUtile = largeur - margeGauche - 12;
  const hauteurUtile = hauteur - margeBas - margeHaut;
  const max = Math.max(...points.map((p) => p.valeur || 0), 0);
  const ticks = graduations(max);
  const echelleMax = ticks[ticks.length - 1] || 1;

  for (const tick of ticks) {
    const y = margeHaut + hauteurUtile - (tick / echelleMax) * hauteurUtile;
    svg.appendChild(element("line", {
      x1: margeGauche, x2: largeur - 12, y1: y, y2: y, class: "grille",
    }));
    svg.appendChild(texte(formaterCourt(tick, format), {
      x: margeGauche - 8, y: y + 4, "text-anchor": "end", class: "axe-libelle",
    }));
  }

  const pas = largeurUtile / points.length;
  const largeurBarre = Math.max(6, Math.min(56, pas - 6));

  points.forEach((point, rang) => {
    const x = margeGauche + rang * pas + (pas - largeurBarre) / 2;
    const h = max > 0 ? Math.max(2, (point.valeur / max) * hauteurUtile) : 2;
    const y = margeHaut + hauteurUtile - h;

    const groupe = element("g");
    groupe.appendChild(element("rect", {
      x, y, width: largeurBarre, height: h, fill: couleur, rx: 4,
    }));
    survol(groupe, () => [
      { libelle: point.libelle, fort: true },
      { libelle: libelleValeur, valeur: formater(point.valeur, format), pastille: couleur },
      ...(point.detail || []),
    ], auClic ? () => auClic(point) : null);
    svg.appendChild(groupe);

    const etiquette = texte(point.libelle, {
      x: x + largeurBarre / 2, y: hauteur - margeBas + 16,
      "text-anchor": "end", class: "axe-libelle",
      transform: `rotate(-35 ${x + largeurBarre / 2} ${hauteur - margeBas + 16})`,
    });
    svg.appendChild(etiquette);
  });

  svg.appendChild(element("line", {
    x1: margeGauche, x2: largeur - 12,
    y1: margeHaut + hauteurUtile, y2: margeHaut + hauteurUtile, class: "axe",
  }));
  return svg;
}

/* --- courbes (évolution) ----------------------------------------------------- */
export function courbes(conteneur, series, options = {}) {
  const { format = "entier", hauteur = 300, auClic = null } = options;
  const utiles = series.filter((s) => s.points.some((p) => p.valeur !== null));
  if (!utiles.length) return messageVide(conteneur);

  const etiquettes = utiles[0].points.map((p) => p.libelle);
  const margeGauche = 62, margeDroite = 16, margeHaut = 16, margeBas = 52;
  const { svg, largeur } = socle(conteneur, hauteur);
  const largeurUtile = largeur - margeGauche - margeDroite;
  const hauteurUtile = hauteur - margeHaut - margeBas;

  const max = Math.max(...utiles.flatMap((s) => s.points.map((p) => p.valeur || 0)), 0);
  const ticks = graduations(max);
  const echelleMax = ticks[ticks.length - 1] || 1;
  const x = (i) => margeGauche + (etiquettes.length === 1
    ? largeurUtile / 2 : (i / (etiquettes.length - 1)) * largeurUtile);
  const y = (v) => margeHaut + hauteurUtile - (v / echelleMax) * hauteurUtile;

  for (const tick of ticks) {
    svg.appendChild(element("line", {
      x1: margeGauche, x2: largeur - margeDroite, y1: y(tick), y2: y(tick), class: "grille",
    }));
    svg.appendChild(texte(formaterCourt(tick, format), {
      x: margeGauche - 8, y: y(tick) + 4, "text-anchor": "end", class: "axe-libelle",
    }));
  }

  const pasEtiquette = Math.ceil(etiquettes.length / 8);
  etiquettes.forEach((libelle, i) => {
    if (i % pasEtiquette !== 0 && i !== etiquettes.length - 1) return;
    svg.appendChild(texte(libelle, {
      x: x(i), y: hauteur - margeBas + 18, "text-anchor": "end", class: "axe-libelle",
      transform: `rotate(-35 ${x(i)} ${hauteur - margeBas + 18})`,
    }));
  });

  utiles.forEach((serie, rang) => {
    const couleur = serie.couleur || SERIES[rang % SERIES.length];
    const segments = [];
    let courant = [];
    serie.points.forEach((point, i) => {
      if (point.valeur === null) { if (courant.length) segments.push(courant); courant = []; }
      else courant.push([x(i), y(point.valeur)]);
    });
    if (courant.length) segments.push(courant);

    for (const segment of segments) {
      svg.appendChild(element("path", {
        d: segment.map(([px, py], i) => `${i ? "L" : "M"}${px.toFixed(1)},${py.toFixed(1)}`).join(" "),
        fill: "none", stroke: couleur, "stroke-width": 2,
        "stroke-linecap": "round", "stroke-linejoin": "round",
      }));
    }

    serie.points.forEach((point, i) => {
      if (point.valeur === null) return;
      const marque = element("circle", {
        cx: x(i), cy: y(point.valeur), r: 4.5, fill: couleur,
        stroke: "var(--surface-1)", "stroke-width": 2,
      });
      const cible = element("circle", {
        cx: x(i), cy: y(point.valeur), r: 13, fill: "transparent",
      });
      survol(cible, () => [
        { libelle: point.libelle, fort: true },
        { libelle: serie.nom, valeur: formater(point.valeur, format), pastille: couleur },
      ], auClic ? () => auClic(point, serie) : null);
      svg.append(marque, cible);
    });

    /* Étiquette directe en bout de courbe, tant que la lecture reste nette. */
    if (utiles.length <= 4) {
      const dernier = [...serie.points].reverse().find((p) => p.valeur !== null);
      if (dernier) {
        const i = serie.points.lastIndexOf(dernier);
        svg.appendChild(texte(serie.nom, {
          x: x(i) - 8, y: y(dernier.valeur) - 10, "text-anchor": "end",
          class: "valeur-directe", fill: couleur,
        }));
      }
    }
  });

  svg.appendChild(element("line", {
    x1: margeGauche, x2: largeur - margeDroite,
    y1: margeHaut + hauteurUtile, y2: margeHaut + hauteurUtile, class: "axe",
  }));
  return svg;
}

/* --- nuage de points (corrélation) -------------------------------------------- */
export function nuage(conteneur, groupes, options = {}) {
  const { formatX = "entier", formatY = "euro", hauteur = 340,
          titreX = "", titreY = "", auClic = null } = options;
  const utiles = groupes.filter((g) => g.points.length).slice(0, SERIES_SUPERPOSEES);
  if (!utiles.length) return messageVide(conteneur);

  const margeGauche = 66, margeDroite = 16, margeHaut = 16, margeBas = 46;
  const { svg, largeur } = socle(conteneur, hauteur);
  const largeurUtile = largeur - margeGauche - margeDroite;
  const hauteurUtile = hauteur - margeHaut - margeBas;

  const tous = utiles.flatMap((g) => g.points);
  const maxX = Math.max(...tous.map((p) => p.x), 1);
  const maxY = Math.max(...tous.map((p) => p.y), 1);
  const ticksX = graduations(maxX, 5);
  const ticksY = graduations(maxY, 4);
  const echelleX = ticksX[ticksX.length - 1] || 1;
  const echelleY = ticksY[ticksY.length - 1] || 1;
  const px = (v) => margeGauche + (v / echelleX) * largeurUtile;
  const py = (v) => margeHaut + hauteurUtile - (v / echelleY) * hauteurUtile;

  for (const tick of ticksY) {
    svg.appendChild(element("line", {
      x1: margeGauche, x2: largeur - margeDroite, y1: py(tick), y2: py(tick), class: "grille",
    }));
    svg.appendChild(texte(formaterCourt(tick, formatY), {
      x: margeGauche - 8, y: py(tick) + 4, "text-anchor": "end", class: "axe-libelle",
    }));
  }
  for (const tick of ticksX) {
    svg.appendChild(texte(formaterCourt(tick, formatX), {
      x: px(tick), y: hauteur - margeBas + 18, "text-anchor": "middle", class: "axe-libelle",
    }));
  }

  utiles.forEach((groupe, rang) => {
    const couleur = groupe.couleur || SERIES[rang % SERIES.length];
    for (const point of groupe.points) {
      const marque = element("circle", {
        cx: px(point.x), cy: py(point.y), r: 4.5, fill: couleur,
        "fill-opacity": 0.72, stroke: "var(--surface-1)", "stroke-width": 1.5,
      });
      survol(marque, () => [
        { libelle: point.libelle || groupe.nom, fort: true },
        { libelle: titreX, valeur: formater(point.x, formatX), pastille: couleur },
        { libelle: titreY, valeur: formater(point.y, formatY) },
      ], auClic ? () => auClic(point) : null);
      svg.appendChild(marque);
    }
  });

  svg.appendChild(element("line", {
    x1: margeGauche, x2: largeur - margeDroite,
    y1: margeHaut + hauteurUtile, y2: margeHaut + hauteurUtile, class: "axe",
  }));
  svg.appendChild(texte(titreX, {
    x: largeur - margeDroite, y: hauteur - 6, "text-anchor": "end", class: "axe-titre",
  }));
  svg.appendChild(texte(titreY, { x: 4, y: 12, class: "axe-titre" }));
  return svg;
}

/* --- barres empilées (composition) ---------------------------------------------- */
export function barresEmpilees(conteneur, categories, series, options = {}) {
  const { format = "entier", hauteur = 300, auClic = null } = options;
  if (!categories.length || !series.length) return messageVide(conteneur);

  const margeGauche = 62, margeDroite = 16, margeHaut = 16, margeBas = 56;
  const { svg, largeur } = socle(conteneur, hauteur);
  const largeurUtile = largeur - margeGauche - margeDroite;
  const hauteurUtile = hauteur - margeHaut - margeBas;

  const totaux = categories.map((_, i) =>
    series.reduce((somme, s) => somme + (s.valeurs[i] || 0), 0));
  const max = Math.max(...totaux, 0);
  const ticks = graduations(max);
  const echelleMax = ticks[ticks.length - 1] || 1;

  for (const tick of ticks) {
    const y = margeHaut + hauteurUtile - (tick / echelleMax) * hauteurUtile;
    svg.appendChild(element("line", {
      x1: margeGauche, x2: largeur - margeDroite, y1: y, y2: y, class: "grille",
    }));
    svg.appendChild(texte(formaterCourt(tick, format), {
      x: margeGauche - 8, y: y + 4, "text-anchor": "end", class: "axe-libelle",
    }));
  }

  const pas = largeurUtile / categories.length;
  const largeurBarre = Math.max(8, Math.min(64, pas - 10));

  categories.forEach((categorie, i) => {
    const x = margeGauche + i * pas + (pas - largeurBarre) / 2;
    let cumul = 0;
    series.forEach((serie, rang) => {
      const valeur = serie.valeurs[i] || 0;
      if (!valeur) return;
      const couleur = serie.couleur || SERIES[rang % SERIES.length];
      const h = (valeur / echelleMax) * hauteurUtile;
      const y = margeHaut + hauteurUtile - (cumul / echelleMax) * hauteurUtile - h;
      /* 2 px de fond entre deux segments : la frontière reste lisible même
         quand deux couleurs voisines se ressemblent. */
      const hauteurVisible = Math.max(1, h - 2);
      const bloc = element("rect", {
        x, y, width: largeurBarre, height: hauteurVisible, fill: couleur, rx: 2,
      });
      survol(bloc, () => [
        { libelle: categorie, fort: true },
        { libelle: serie.nom, valeur: formater(valeur, format), pastille: couleur },
        { libelle: "Total", valeur: formater(totaux[i], format) },
      ], auClic ? () => auClic(categorie, serie) : null);
      svg.appendChild(bloc);
      cumul += valeur;
    });

    svg.appendChild(texte(categorie, {
      x: x + largeurBarre / 2, y: hauteur - margeBas + 16,
      "text-anchor": "end", class: "axe-libelle",
      transform: `rotate(-35 ${x + largeurBarre / 2} ${hauteur - margeBas + 16})`,
    }));
  });

  svg.appendChild(element("line", {
    x1: margeGauche, x2: largeur - margeDroite,
    y1: margeHaut + hauteurUtile, y2: margeHaut + hauteurUtile, class: "axe",
  }));
  return svg;
}

/* --- légende ------------------------------------------------------------------- */
export function legende(conteneur, entrees) {
  conteneur.replaceChildren();
  entrees.forEach((entree, rang) => {
    const item = document.createElement("span");
    item.className = "legende-item";
    const pastille = document.createElement("span");
    pastille.className = "pastille";
    pastille.style.background = entree.couleur || SERIES[rang % SERIES.length];
    const libelle = document.createElement("span");
    libelle.textContent = entree.nom;
    item.append(pastille, libelle);
    conteneur.appendChild(item);
  });
}
