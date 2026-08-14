/* Moteur de cube multidimensionnel.
 *
 * Les faits sont stockés en colonnes : chaque dimension est un tableau
 * d'entiers pointant vers son dictionnaire de valeurs. Filtrer revient à
 * parcourir des entiers, agréger à accumuler en un seul passage — ce qui
 * permet de manipuler plusieurs dizaines de milliers de lots dans le
 * navigateur, sans serveur.
 */

export const AUCUNE = "(non renseigné)";

/* --- formatage ----------------------------------------------------------- */
const nf = (min, max) => new Intl.NumberFormat("fr-FR", {
  minimumFractionDigits: min, maximumFractionDigits: max,
});
const F = {
  entier: nf(0, 0), euro: nf(0, 0), km: nf(0, 0),
  decimal: nf(1, 1), multiple: nf(2, 2), pourcent: nf(0, 1), an: nf(1, 1),
};

export function formater(valeur, format) {
  if (valeur === null || valeur === undefined || Number.isNaN(valeur)) return "—";
  switch (format) {
    case "euro": return F.euro.format(valeur) + " €";
    case "km": return F.km.format(valeur) + " km";
    case "pourcent": return F.pourcent.format(valeur) + " %";
    case "multiple": return "×" + F.multiple.format(valeur);
    case "an": return F.an.format(valeur) + " ans";
    case "decimal": return F.decimal.format(valeur);
    default: return F.entier.format(valeur);
  }
}

export function formaterCourt(valeur, format) {
  if (valeur === null || valeur === undefined || Number.isNaN(valeur)) return "—";
  const abs = Math.abs(valeur);
  let texte;
  if (abs >= 1e6) texte = nf(1, 1).format(valeur / 1e6) + " M";
  else if (abs >= 1e4) texte = nf(0, 0).format(valeur / 1e3) + " k";
  else return formater(valeur, format);
  if (format === "euro") return texte + "€";
  if (format === "km") return texte + "km";
  return texte;
}

/* --- accumulateur d'une cellule ------------------------------------------ */
class Accumulateur {
  constructor(mesures, garderValeurs) {
    this.nb = 0;
    this.etat = mesures.map(() => ({ n: 0, somme: 0, min: Infinity, max: -Infinity, vrais: 0 }));
    this.valeurs = garderValeurs ? mesures.map(() => []) : null;
  }
}

/* --- cube ----------------------------------------------------------------- */
export class Cube {
  constructor(dataset) {
    this.meta = dataset.meta;
    this.dim = dataset.dim;
    this.col = dataset.col;
    this.txt = dataset.txt;
    this.n = dataset.meta.nb_lots;

    this.dimensions = new Map(this.meta.dimensions.map((d) => [d.cle, d]));
    this.mesures = new Map(this.meta.mesures.map((m) => [m.cle, m]));

    /* index de tri des valeurs de chaque dimension */
    for (const d of this.meta.dimensions) {
      const valeurs = this.dim[d.cle] || [];
      let ordre;
      if (d.ordre && d.ordre.length) {
        const rang = new Map(d.ordre.map((v, i) => [v, i]));
        ordre = valeurs.map((v, i) => [i, rang.has(v) ? rang.get(v) : 9999]);
        ordre.sort((a, b) => a[1] - b[1]);
      } else if (d.type === "temps") {
        ordre = valeurs.map((v, i) => [i, v]);
        ordre.sort((a, b) => String(a[1]).localeCompare(String(b[1])));
      } else {
        ordre = valeurs.map((v, i) => [i, v]);
        ordre.sort((a, b) => String(a[1]).localeCompare(String(b[1]), "fr"));
      }
      d.ordreCodes = ordre.map(([i]) => i);
      d.rangCode = new Map(d.ordreCodes.map((code, rang) => [code, rang]));
    }

    this.filtresDim = new Map();   // cle -> Set(codes autorisés)
    this.filtresNum = new Map();   // champ -> [min, max]
    this.recherche = "";
    this._masque = null;
    this._indices = null;
  }

  /* -- métadonnées ------------------------------------------------------- */
  dimension(cle) { return this.dimensions.get(cle); }
  mesure(cle) { return this.mesures.get(cle); }
  libelleDim(cle) { return this.dimensions.get(cle)?.libelle ?? cle; }

  /** Valeurs distinctes d'une dimension, dans l'ordre d'affichage. */
  valeurs(cle) {
    const d = this.dimensions.get(cle);
    if (!d) return [];
    return d.ordreCodes.map((code) => ({ code, valeur: this.dim[cle][code] }));
  }

  /* -- filtres ------------------------------------------------------------ */
  setFiltreDim(cle, valeursRetenues) {
    if (!valeursRetenues || valeursRetenues.size === 0) this.filtresDim.delete(cle);
    else {
      const index = new Map(this.dim[cle].map((v, i) => [v, i]));
      const codes = new Set();
      for (const v of valeursRetenues) {
        if (v === AUCUNE) codes.add(-1);
        else if (index.has(v)) codes.add(index.get(v));
      }
      this.filtresDim.set(cle, codes);
    }
    this._invalider();
  }

  setFiltreNum(champ, bornes) {
    if (!bornes) this.filtresNum.delete(champ);
    else this.filtresNum.set(champ, bornes);
    this._invalider();
  }

  setRecherche(texte) {
    this.recherche = (texte || "").trim().toLowerCase();
    this._invalider();
  }

  reinitialiserFiltres() {
    this.filtresDim.clear();
    this.filtresNum.clear();
    this.recherche = "";
    this._invalider();
  }

  get nbFiltresActifs() {
    return this.filtresDim.size + this.filtresNum.size + (this.recherche ? 1 : 0);
  }

  _invalider() { this._masque = null; this._indices = null; }

  /* -- sélection ---------------------------------------------------------- */
  masque() {
    if (this._masque) return this._masque;
    const m = new Uint8Array(this.n).fill(1);

    for (const [cle, codes] of this.filtresDim) {
      const colonne = this.col[cle];
      for (let i = 0; i < this.n; i++) if (m[i] && !codes.has(colonne[i])) m[i] = 0;
    }
    for (const [champ, [min, max]] of this.filtresNum) {
      const colonne = this.col[champ];
      if (!colonne) continue;
      for (let i = 0; i < this.n; i++) {
        if (!m[i]) continue;
        const v = colonne[i];
        if (v === null || v === undefined || v < min || v > max) m[i] = 0;
      }
    }
    if (this.recherche) {
      const mots = this.recherche.split(/\s+/).filter(Boolean);
      const intitules = this.txt.intitule || [];
      const descriptions = this.txt.description || [];
      for (let i = 0; i < this.n; i++) {
        if (!m[i]) continue;
        const blob = ((intitules[i] || "") + " " + (descriptions[i] || "")).toLowerCase();
        if (!mots.every((mot) => blob.includes(mot))) m[i] = 0;
      }
    }
    this._masque = m;
    return m;
  }

  indices() {
    if (this._indices) return this._indices;
    const m = this.masque();
    const liste = [];
    for (let i = 0; i < this.n; i++) if (m[i]) liste.push(i);
    this._indices = liste;
    return liste;
  }

  get nbSelectionnes() { return this.indices().length; }

  /* -- agrégation ---------------------------------------------------------- */
  _calculer(acc, mesures, rang) {
    const m = mesures[rang];
    const etat = acc.etat[rang];
    switch (m.agregat) {
      case "nb": return acc.nb;
      case "somme": return etat.n ? etat.somme : null;
      case "moyenne": return etat.n ? etat.somme / etat.n : null;
      case "min": return etat.n ? etat.min : null;
      case "max": return etat.n ? etat.max : null;
      case "part_vrai": return etat.n ? (100 * etat.vrais) / etat.n : null;
      case "mediane": {
        const v = acc.valeurs?.[rang];
        if (!v || !v.length) return null;
        v.sort((a, b) => a - b);
        const milieu = v.length >> 1;
        return v.length % 2 ? v[milieu] : (v[milieu - 1] + v[milieu]) / 2;
      }
      default: return null;
    }
  }

  _accumuler(acc, mesures, i) {
    acc.nb++;
    for (let r = 0; r < mesures.length; r++) {
      const m = mesures[r];
      if (!m.champ) continue;
      const valeur = this.col[m.champ]?.[i];
      if (valeur === null || valeur === undefined) continue;
      const etat = acc.etat[r];
      etat.n++;
      etat.somme += valeur;
      if (valeur < etat.min) etat.min = valeur;
      if (valeur > etat.max) etat.max = valeur;
      if (valeur) etat.vrais++;
      if (acc.valeurs) acc.valeurs[r].push(valeur);
    }
  }

  /**
   * Tableau croisé.
   * @param {string[]} lignes     dimensions en lignes (hiérarchie)
   * @param {string[]} colonnes   dimensions en colonnes (hiérarchie)
   * @param {string[]} mesuresCles mesures à calculer
   * @param {object}   options    {sousTotaux, triMesure, triDescendant, limiteLignes}
   */
  pivot(lignes, colonnes, mesuresCles, options = {}) {
    const { sousTotaux = true, triMesure = null, triDescendant = true,
            limiteLignes = 0 } = options;
    const mesures = mesuresCles.map((c) => this.mesures.get(c)).filter(Boolean);
    const besoinValeurs = mesures.some((m) => m.agregat === "mediane");
    const actifs = this.indices();

    /* Chemins hiérarchiques : le préfixe vide porte le total général. */
    const cheminsDe = (dims, i) => {
      const chemins = [""];
      let courant = "";
      for (const cle of dims) {
        const code = this.col[cle][i];
        const valeur = code === -1 ? AUCUNE : this.dim[cle][code];
        courant = courant === "" ? valeur : courant + " " + valeur;
        chemins.push(courant);
      }
      return chemins;
    };

    const cellules = new Map();
    const clesLignes = new Map();     // chemin -> profondeur
    const clesColonnes = new Map();

    for (const i of actifs) {
      const cheminsL = cheminsDe(lignes, i);
      const cheminsC = cheminsDe(colonnes, i);
      for (let a = 0; a < cheminsL.length; a++) {
        if (!sousTotaux && a !== 0 && a !== cheminsL.length - 1) continue;
        const cl = cheminsL[a];
        if (!clesLignes.has(cl)) clesLignes.set(cl, a);
        for (let b = 0; b < cheminsC.length; b++) {
          if (!sousTotaux && b !== 0 && b !== cheminsC.length - 1) continue;
          const cc = cheminsC[b];
          if (!clesColonnes.has(cc)) clesColonnes.set(cc, b);
          const cle = cl + "" + cc;
          let acc = cellules.get(cle);
          if (!acc) { acc = new Accumulateur(mesures, besoinValeurs); cellules.set(cle, acc); }
          this._accumuler(acc, mesures, i);
        }
      }
    }

    /* Mise à plat ordonnée de l'arbre des lignes / colonnes. */
    const aplatir = (cles, dims) => {
      const noeuds = [...cles.entries()]
        .filter(([chemin]) => chemin !== "")
        .map(([chemin, profondeur]) => ({
          chemin,
          profondeur,
          parties: chemin.split(" "),
          libelle: chemin.split(" ").pop(),
          dimension: dims[profondeur - 1],
        }));
      const rang = (noeud) => {
        const d = this.dimensions.get(noeud.dimension);
        if (!d) return 0;
        const code = this.dim[noeud.dimension]?.indexOf(noeud.libelle);
        return d.rangCode?.get(code) ?? 9999;
      };
      noeuds.sort((a, b) => {
        const n = Math.min(a.parties.length, b.parties.length);
        for (let k = 0; k < n; k++) {
          if (a.parties[k] !== b.parties[k]) {
            if (k === a.parties.length - 1 && k === b.parties.length - 1) {
              const ra = rang(a), rb = rang(b);
              if (ra !== rb) return ra - rb;
            }
            return String(a.parties[k]).localeCompare(String(b.parties[k]), "fr");
          }
        }
        return a.parties.length - b.parties.length;
      });
      return noeuds;
    };

    let entetesLignes = aplatir(clesLignes, lignes);
    const entetesColonnes = aplatir(clesColonnes, colonnes);

    /* Tri des lignes de premier niveau sur une mesure. */
    if (triMesure && lignes.length) {
      const rangMesure = mesuresCles.indexOf(triMesure);
      if (rangMesure >= 0) {
        const valeurDe = (chemin) => {
          const acc = cellules.get(chemin + "");
          return acc ? this._calculer(acc, mesures, rangMesure) : null;
        };
        const racines = entetesLignes.filter((e) => e.profondeur === 1);
        racines.sort((a, b) => {
          const va = valeurDe(a.chemin) ?? -Infinity;
          const vb = valeurDe(b.chemin) ?? -Infinity;
          return triDescendant ? vb - va : va - vb;
        });
        const ordonnees = [];
        for (const racine of racines) {
          ordonnees.push(racine);
          for (const e of entetesLignes) {
            if (e.profondeur > 1 && e.chemin.startsWith(racine.chemin + " ")) ordonnees.push(e);
          }
        }
        entetesLignes = ordonnees;
      }
    }

    if (limiteLignes > 0) {
      const gardees = new Set(entetesLignes.filter((e) => e.profondeur === 1)
        .slice(0, limiteLignes).map((e) => e.chemin));
      entetesLignes = entetesLignes.filter(
        (e) => gardees.has(e.chemin) || [...gardees].some((g) => e.chemin.startsWith(g + " ")));
    }

    const lire = (cheminLigne, cheminColonne) => {
      const acc = cellules.get(cheminLigne + "" + cheminColonne);
      if (!acc) return mesures.map(() => null);
      return mesures.map((_, r) => this._calculer(acc, mesures, r));
    };

    return {
      lignes: entetesLignes,
      colonnes: entetesColonnes,
      mesures,
      lire,
      total: lire("", ""),
      nbFaits: actifs.length,
    };
  }

  /** Série simple dimension → mesure, triée, pour les graphiques. */
  serie(dimensionCle, mesureCle, options = {}) {
    const { limite = 0, trier = true, descendant = true, exclureVides = true } = options;
    const p = this.pivot([dimensionCle], [], [mesureCle], { sousTotaux: false });
    let points = p.lignes.map((e) => ({
      libelle: e.libelle,
      valeur: p.lire(e.chemin, "")[0],
    }));
    if (exclureVides) points = points.filter((pt) => pt.libelle !== AUCUNE && pt.valeur !== null);
    const d = this.dimensions.get(dimensionCle);
    if (trier && d?.type !== "temps" && d?.type !== "ordinale") {
      points.sort((a, b) => (descendant ? b.valeur - a.valeur : a.valeur - b.valeur));
    }
    if (limite > 0 && points.length > limite) points = points.slice(0, limite);
    return points;
  }

  /** Valeur brute d'un fait (colonne dimension, mesure ou texte). */
  valeur(i, champ) {
    if (this.txt[champ] !== undefined) return this.txt[champ][i];
    if (this.dimensions.has(champ)) {
      const code = this.col[champ][i];
      return code === -1 ? null : this.dim[champ][code];
    }
    return this.col[champ]?.[i] ?? null;
  }

  /** Lots sélectionnés, triés, pour la table de détail. */
  lots({ tri = "prix", descendant = true, limite = 200, decalage = 0 } = {}) {
    const actifs = [...this.indices()];
    if (tri) {
      actifs.sort((a, b) => {
        const va = this.valeur(a, tri), vb = this.valeur(b, tri);
        if (va === null || va === undefined) return 1;
        if (vb === null || vb === undefined) return -1;
        if (typeof va === "number" && typeof vb === "number") {
          return descendant ? vb - va : va - vb;
        }
        return descendant
          ? String(vb).localeCompare(String(va), "fr")
          : String(va).localeCompare(String(vb), "fr");
      });
    }
    return { total: actifs.length, indices: actifs.slice(decalage, decalage + limite) };
  }
}
