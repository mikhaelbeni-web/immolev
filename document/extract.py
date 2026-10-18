"""Appel à Claude : photo d'un document -> Document (schéma validé par l'API)."""
from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

import anthropic

from .schema import Document

MODELE = "claude-opus-5-5"

CONSIGNES = """Tu lis un document français reçu par un gestionnaire immobilier (photo ou scan) : facture, devis, appel de fonds
de copropriété ou de VEFA, quittance ou avis d'échéance de loyer, avis d'impôt sur le revenu, de taxe foncière ou de CFE,
relevé bancaire, bulletin de paie.
Remplis le schéma en recopiant exactement ce qui est écrit :
- Montants en euros, point décimal, sans symbole ni espace (1 234,50 € = 1234.5). Un avoir garde son signe négatif.
- Recopie le récapitulatif de TVA ligne par ligne s'il existe, sans le recalculer.
- IBAN et SIRET sans espaces, tels qu'écrits : ne corrige aucun chiffre.
- Ne devine jamais une valeur : si un champ est présent mais illisible ou ambigu, laisse-le vide et ajoute son nom (ex. 'montant_ttc', 'iban') dans champs_illisibles.
- Dates au format AAAA-MM-JJ."""


class ExtractionRefusee(RuntimeError):
    pass


def extraire(image: bytes, media_type: str, client: anthropic.Anthropic | None = None) -> Document:
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
                    {"type": "text", "text": "Extrais ce document."},
                ],
            }
        ],
        output_format=Document,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise ExtractionRefusee(f"Extraction impossible (stop_reason={response.stop_reason})")
    return response.parsed_output


def extraire_fichier(chemin: str | Path, client: anthropic.Anthropic | None = None) -> Document:
    chemin = Path(chemin)
    media_type = mimetypes.guess_type(chemin.name)[0] or "image/jpeg"
    return extraire(chemin.read_bytes(), media_type, client)
