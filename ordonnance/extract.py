"""Appel à Claude : photo d'ordonnance -> Ordonnance (schéma validé par l'API)."""
from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

import anthropic

from .schema import Ordonnance

MODELE = "claude-opus-5-5"

CONSIGNES = """Tu lis une ordonnance optique française (photo, parfois manuscrite).
Remplis le schéma en recopiant exactement ce qui est écrit :
- Garde le signe du cylindre tel qu'écrit, ne transpose pas.
- 'Plan', 'pl' ou '0' en sphère = 0.0.
- OD = œil droit, OG = œil gauche ; 'ODG' s'applique aux deux.
- Ne devine jamais une valeur : si un champ est présent mais illisible ou ambigu, laisse-le vide et ajoute son nom (ex. 'og.axe') dans champs_illisibles.
- Dates au format AAAA-MM-JJ."""


class ExtractionRefusee(RuntimeError):
    pass


def extraire(image: bytes, media_type: str, client: anthropic.Anthropic | None = None) -> Ordonnance:
    client = client or anthropic.Anthropic()
    response = client.messages.parse(
        model=MODELE,
        max_tokens=16000,
        output_config={"effort": "high"},
        system=CONSIGNES,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": base64.standard_b64encode(image).decode()}},
                    {"type": "text", "text": "Extrais cette ordonnance."},
                ],
            }
        ],
        output_format=Ordonnance,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise ExtractionRefusee(f"Extraction impossible (stop_reason={response.stop_reason})")
    return response.parsed_output


def extraire_fichier(chemin: str | Path, client: anthropic.Anthropic | None = None) -> Ordonnance:
    chemin = Path(chemin)
    media_type = mimetypes.guess_type(chemin.name)[0] or "image/jpeg"
    return extraire(chemin.read_bytes(), media_type, client)
