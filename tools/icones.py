"""Rasterise app/icone.svg en PNG pour l'écran d'accueil iOS et le manifeste.

iOS n'accepte pas de SVG pour ``apple-touch-icon`` : il faut de vrais PNG. Le
seul rasteriseur disponible ici est Chromium, dont le mode « headless » rend un
viewport plus court que la fenêtre demandée — le bas de l'image est rogné. On
rend donc dans une fenêtre volontairement trop haute, puis on recadre au carré.

Le recadrage est écrit à la main faute de Pillow : décodage PNG, défiltrage,
troncature des lignes, réencodage sans filtre.
"""
from __future__ import annotations

import re
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SVG = RACINE / "app" / "icone.svg"
TAILLES = (180, 192, 512)
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
# Marge ajoutée à la hauteur de fenêtre pour compenser le viewport tronqué.
MARGE_VIEWPORT = 160


# --- PNG : décodage et recadrage --------------------------------------------
def _morceaux(donnees: bytes):
    """Parcourt les chunks d'un PNG : (type, contenu)."""
    position = 8
    while position < len(donnees):
        taille = struct.unpack(">I", donnees[position:position + 4])[0]
        nom = donnees[position + 4:position + 8]
        yield nom, donnees[position + 8:position + 8 + taille]
        position += 12 + taille


def _chunk(nom: bytes, contenu: bytes) -> bytes:
    return (struct.pack(">I", len(contenu)) + nom + contenu
            + struct.pack(">I", zlib.crc32(nom + contenu) & 0xFFFFFFFF))


def _defiltrer(brut: bytes, largeur: int, hauteur: int, octets_pixel: int) -> list[bytearray]:
    """Applique à l'envers les filtres de ligne PNG (spécification, § 9)."""
    lignes, position, precedente = [], 0, bytearray(largeur * octets_pixel)
    pas = largeur * octets_pixel
    for _ in range(hauteur):
        filtre = brut[position]
        ligne = bytearray(brut[position + 1:position + 1 + pas])
        position += 1 + pas
        for i in range(pas):
            gauche = ligne[i - octets_pixel] if i >= octets_pixel else 0
            haut = precedente[i]
            coin = precedente[i - octets_pixel] if i >= octets_pixel else 0
            if filtre == 1:
                ligne[i] = (ligne[i] + gauche) & 0xFF
            elif filtre == 2:
                ligne[i] = (ligne[i] + haut) & 0xFF
            elif filtre == 3:
                ligne[i] = (ligne[i] + (gauche + haut) // 2) & 0xFF
            elif filtre == 4:
                p = gauche + haut - coin
                pa, pb, pc = abs(p - gauche), abs(p - haut), abs(p - coin)
                predit = gauche if (pa <= pb and pa <= pc) else (haut if pb <= pc else coin)
                ligne[i] = (ligne[i] + predit) & 0xFF
        lignes.append(ligne)
        precedente = ligne
    return lignes


def recadrer_carre(chemin: Path, cote: int) -> None:
    """Tronque un PNG à ``cote`` lignes, en partant du haut."""
    donnees = chemin.read_bytes()
    entete, pixels = None, b""
    for nom, contenu in _morceaux(donnees):
        if nom == b"IHDR":
            entete = contenu
        elif nom == b"IDAT":
            pixels += contenu

    largeur, hauteur, profondeur, couleur = struct.unpack(">IIBB", entete[:10])
    if hauteur == cote and largeur == cote:
        return
    if profondeur != 8 or couleur not in (2, 6):
        raise SystemExit(f"{chemin} : format PNG inattendu ({profondeur} bits, type {couleur})")

    octets_pixel = 4 if couleur == 6 else 3
    lignes = _defiltrer(zlib.decompress(pixels), largeur, hauteur, octets_pixel)[:cote]

    corps = b"".join(b"\x00" + bytes(l) for l in lignes)
    nouveau = (b"\x89PNG\r\n\x1a\n"
               + _chunk(b"IHDR", struct.pack(">IIBBBBB", cote, cote,
                                             profondeur, couleur, 0, 0, 0))
               + _chunk(b"IDAT", zlib.compress(corps, 9))
               + _chunk(b"IEND", b""))
    chemin.write_bytes(nouveau)


# --- Rendu -------------------------------------------------------------------
def rendre(taille: int, destination: Path, dossier: Path) -> None:
    svg = SVG.read_text(encoding="utf-8")
    svg = re.sub(r'width="\d+" height="\d+"', f'width="{taille}" height="{taille}"',
                 svg, count=1)
    gabarit = dossier / f"icone{taille}.html"
    gabarit.write_text(
        "<!doctype html><meta charset=utf8>"
        "<style>html,body{margin:0;padding:0;overflow:hidden}svg{display:block}</style>\n"
        + svg, encoding="utf-8")

    subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
         "--force-device-scale-factor=1", f"--screenshot={destination}",
         f"--window-size={taille},{taille + MARGE_VIEWPORT}", gabarit.as_uri()],
        check=True, capture_output=True)
    recadrer_carre(destination, taille)


def main() -> int:
    if not Path(CHROME).exists():
        print(f"Chromium introuvable : {CHROME}", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        for taille in TAILLES:
            cible = RACINE / "app" / f"icone-{taille}.png"
            rendre(taille, cible, Path(tmp))
            print(f"écrit {cible.relative_to(RACINE)} ({cible.stat().st_size} o)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
