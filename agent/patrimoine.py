"""Patrimoine : caractéristiques de chaque appartement (surface, pièces) et emplacement de chaque plan.

Fichier patrimoine.md dans le dossier des données, une section « ## » par immeuble. Consulté à la demande
(pas ajouté au prompt) : l'agent y trouve la surface exacte et le chemin du plan sans fouiller le OneDrive.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

FICHIER = "patrimoine.md"
LIMITE = 14000


def _simple(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def consulter(dossier: Path, recherche: str = "") -> str:
    try:
        texte = (Path(dossier) / FICHIER).read_text(encoding="utf-8")
    except OSError:
        return "Aucun inventaire des appartements pour l'instant (patrimoine.md absent)."
    sections = re.split(r"(?m)^(?=## )", texte)
    entete, sections = sections[0], [s for s in sections[1:] if s.strip()]
    mots = [m for m in re.findall(r"\w+", _simple(recherche)) if len(m) > 1]
    if not mots:
        return entete.strip() + "\n\nImmeubles : " + " ; ".join(s.splitlines()[0][3:] for s in sections)
    # l'immeuble nommé dans le titre d'abord (« commerce 1D » : la section du 93 rue du Commerce, pas une
    # autre qui contient « commerce » et « 1D ») ; sinon les sections qui contiennent tous les mots
    trouve = [s for s in sections if any(re.search(r"\b" + m + r"\b", _simple(s.splitlines()[0])) for m in mots)]
    if not trouve:
        trouve = [s for s in sections if all(m in _simple(s) for m in mots)]
    if not trouve:
        return "Rien trouvé. Immeubles connus : " + " ; ".join(s.splitlines()[0][3:] for s in sections)
    sortie = "\n".join(trouve)
    return sortie if len(sortie) <= LIMITE else sortie[:LIMITE] + "\n… (tronqué : préciser l'immeuble)"
