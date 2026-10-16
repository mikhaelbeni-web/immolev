"""Schéma d'une ordonnance optique française, tel que Claude doit le remplir."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Oeil(BaseModel):
    """Correction d'un œil. Valeurs en dioptries, axe en degrés."""

    sphere: Optional[float] = Field(None, description="Sphère, ex. -2.25. 'Plan' ou '0' = 0.0")
    cylindre: Optional[float] = Field(None, description="Cylindre, signe tel qu'écrit sur l'ordonnance")
    axe: Optional[int] = Field(None, description="Axe du cylindre, 0 à 180")
    addition: Optional[float] = Field(None, description="Addition vision de près, ex. 2.00")
    prisme: Optional[str] = Field(None, description="Prisme et base tels qu'écrits, ex. '1 base nasale'")


class Ordonnance(BaseModel):
    patient_nom: Optional[str] = None
    patient_prenom: Optional[str] = None
    patient_date_naissance: Optional[date] = None
    prescripteur_nom: Optional[str] = None
    prescripteur_rpps: Optional[str] = Field(None, description="N° RPPS (11 chiffres) si lisible")
    prescripteur_specialite: Optional[Literal["ophtalmologiste", "orthoptiste", "opticien", "autre"]] = None
    date_prescription: Optional[date] = None
    type_equipement: list[Literal["lunettes_vl", "lunettes_vp", "lunettes_progressifs", "lunettes_double_foyer", "lentilles"]] = Field(
        default_factory=list
    )
    od: Oeil = Field(default_factory=Oeil, description="Œil droit (OD)")
    og: Oeil = Field(default_factory=Oeil, description="Œil gauche (OG)")
    ecart_pupillaire_mm: Optional[float] = None
    mentions: list[str] = Field(default_factory=list, description="Mentions libres : 'renouvellement', 'adaptation autorisée', 'filtre', 'verres teintés', etc.")
    champs_illisibles: list[str] = Field(
        default_factory=list, description="Noms des champs présents sur la photo mais illisibles ou ambigus"
    )
