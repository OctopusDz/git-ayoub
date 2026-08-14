"""Assemble le portail en une page autonome.

Une page publiée n'a droit à aucune requête sortante : ni fichier de données,
ni feuille de style, ni script externe, ni image distante. Ce script fond donc
tout dans un seul fichier HTML — styles, code et cube compris — et allège le
cube pour rester consultable depuis un téléphone :

* les vignettes sont retirées (les images distantes seraient bloquées) ;
* le descriptif n'est conservé en entier que pour les ventes à venir, les
  seules qu'on examine lot par lot ; ailleurs il est tronqué.

Usage :
    python3 -m etl.build_artifact [sortie.html]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
PORTAIL = RACINE / "portal"
CUBE = PORTAIL / "data" / "dataset.json"
SORTIE_DEFAUT = RACINE / "portal" / "mobile.html"

LONGUEUR_DESCRIPTION = 160          # caractères conservés pour les ventes closes


def alleger(cube: dict) -> dict:
    """Réduit le cube au nécessaire pour une consultation mobile."""
    textes = cube["txt"]
    statuts = cube["dim"].get("statut", [])
    codes_statut = cube["col"].get("statut", [])
    a_venir = {i for i, code in enumerate(codes_statut)
               if code >= 0 and "venir" in statuts[code].lower()}

    descriptions = textes.get("description") or []
    textes["description"] = [
        texte if (i in a_venir or not texte) else _tronquer(texte)
        for i, texte in enumerate(descriptions)
    ]
    textes.pop("image", None)
    cube["meta"]["champs_texte"] = [c for c in cube["meta"]["champs_texte"]
                                    if c != "image"]
    cube["meta"]["allege"] = {
        "descriptions_completes": len(a_venir),
        "description_tronquee_a": LONGUEUR_DESCRIPTION,
        "vignettes": "retirées (requêtes externes bloquées)",
    }
    return cube


def _tronquer(texte: str) -> str:
    if len(texte) <= LONGUEUR_DESCRIPTION:
        return texte
    coupe = texte[:LONGUEUR_DESCRIPTION]
    espace = coupe.rfind(" ")
    return (coupe[:espace] if espace > 80 else coupe) + "…"


EXPORT_NOMME = re.compile(r"^\s*export\s+(?:const|function|class|let|var)\s+(\w+)",
                          re.M)
# Import d'espace de noms : « import * as G from "./charts.js" ». Concaténer
# les modules supprime la notion d'espace de noms — il faut le reconstruire.
IMPORT_ESPACE = re.compile(r"^\s*import\s+\*\s+as\s+(\w+)\s+from\s+['\"]\./(\w+)\.js",
                           re.M)


def _module(chemin: Path) -> tuple[str, dict[str, str]]:
    """Lit un module ES, neutralise ses imports/exports et relève ses exports.

    Les modules sont concaténés dans un seul script : les dépendances sont
    résolues à la construction plutôt qu'au chargement.
    """
    code = chemin.read_text(encoding="utf-8")
    exports = EXPORT_NOMME.findall(code)
    espaces = {alias: module for alias, module in IMPORT_ESPACE.findall(code)}

    code = re.sub(r"^\s*import\s+[^;]+;\s*$", "", code, flags=re.M)
    code = re.sub(r"^\s*export\s+(?=(?:const|function|class|let|var))", "",
                  code, flags=re.M)
    code = re.sub(r"^\s*export\s*\{[^}]*\};\s*$", "", code, flags=re.M)
    return code, {"exports": exports, "espaces": espaces, "nom": chemin.stem}


def construire(sortie: Path = SORTIE_DEFAUT) -> Path:
    if not CUBE.exists():
        raise FileNotFoundError(
            f"{CUBE} est introuvable. Lancez d'abord : python3 -m etl.build_cube")

    cube = alleger(json.loads(CUBE.read_text(encoding="utf-8")))
    donnees = json.dumps(cube, ensure_ascii=False, separators=(",", ":"))

    css = (PORTAIL / "css" / "app.css").read_text(encoding="utf-8")
    corps = (PORTAIL / "index.html").read_text(encoding="utf-8")

    # Ne garder que le contenu du <body>, sans les appels de fichiers externes.
    debut = corps.index("<header")
    fin = corps.index("<script")
    corps = corps[debut:fin]

    # app.js vient en dernier : il consomme les autres modules et lance la page.
    ordre = ("cube.js", "charts.js", "pivot.js", "rapport.js", "app.js")
    morceaux, exports_par_module, espaces = [], {}, {}
    for nom in ordre:
        code, infos = _module(PORTAIL / "js" / nom)
        morceaux.append(code)
        exports_par_module[infos["nom"]] = infos["exports"]
        espaces.update(infos["espaces"])

    # Reconstruire chaque espace de noms importé à partir des exports réels du
    # module visé, et l'insérer avant le module qui s'en sert : une constante
    # n'est pas hissée, la déclarer après son usage la laisserait indéfinie.
    alias = "\n".join(
        f"const {nom} = {{ {', '.join(exports_par_module.get(module, []))} }};"
        for nom, module in espaces.items()
    )
    scripts = "\n".join(morceaux[:-1]) + "\n" + alias + "\n" + morceaux[-1]

    meta = cube["meta"]
    periode = meta.get("periode") or {}
    # Le jeu de caractères est déclaré en tout premier : sans lui, un serveur
    # qui ne l'annonce pas fait lire la page en latin-1 et le script casse.
    page = f"""<meta charset="utf-8">
<title>Véhicules du Domaine</title>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="description" content="{meta['nb_lots']} lots de véhicules vendus aux
enchères du Domaine, de {periode.get('debut')} à {periode.get('fin')}.">
<style>
{css}
</style>
{corps}
<script id="cube" type="application/json">{donnees}</script>
<script type="module">
window.__CUBE__ = JSON.parse(document.getElementById("cube").textContent);
{scripts}
</script>
"""

    sortie = Path(sortie)
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(page, encoding="utf-8")
    taille = sortie.stat().st_size / 1_048_576
    print(f"Page autonome écrite : {sortie}  ({taille:.1f} Mo, "
          f"{meta['nb_lots']} lots)")
    if taille > 15:
        print("  Attention : au-delà de 16 Mo, la page ne peut plus être publiée.")
    return sortie


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    try:
        construire(Path(argv[0]) if argv else SORTIE_DEFAUT)
    except Exception as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
