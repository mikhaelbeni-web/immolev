"""Schéma d'un document reçu par le gestionnaire (facture, appel de fonds, avis d'imposition…), tel que Claude doit le remplir."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

TypeDocument = Literal[
    "facture_fournisseur", "facture_emise", "devis", "appel_de_fonds_copropriete", "appel_de_fonds_vefa",
    "quittance_loyer", "avis_echeance_loyer", "avis_impot_revenu", "avis_taxe_fonciere", "avis_cfe",
    "releve_bancaire", "bulletin_paie", "autre",
]


class LigneTVA(BaseModel):
    """Une ligne du récapitulatif de TVA d'une facture."""

    taux: Optional[float] = Field(None, description="Taux en %, ex. 20, 10, 5.5, 2.1, 0")
    base_ht: Optional[float] = None
    montant_tva: Optional[float] = None


class Document(BaseModel):
    type_document: Optional[TypeDocument] = None
    emetteur_nom: Optional[str] = Field(None, description="Société, syndic, administration ou personne qui a émis le document")
    emetteur_siret: Optional[str] = Field(None, description="SIRET (14 chiffres) ou SIREN (9 chiffres) si lisible")
    destinataire_nom: Optional[str] = Field(None, description="Société, SCI, copropriété ou personne destinataire")
    numero: Optional[str] = Field(None, description="N° de facture, d'appel, d'avis ou référence de l'avis d'impôt")
    date_document: Optional[date] = None
    date_echeance: Optional[date] = Field(None, description="Date limite de paiement, si indiquée")
    montant_ht: Optional[float] = None
    montant_tva: Optional[float] = None
    montant_ttc: Optional[float] = Field(None, description="Total à payer ou net à payer")
    lignes_tva: list[LigneTVA] = Field(default_factory=list)
    iban: Optional[str] = Field(None, description="IBAN du bénéficiaire tel qu'écrit, sans espaces")
    bien: Optional[str] = Field(None, description="Bien concerné : immeuble, lot, programme, hôtel, adresse")
    periode: Optional[str] = Field(None, description="Période couverte, ex. '4e trimestre 2026', 'octobre 2026', 'revenus 2025'")
    revenu_fiscal_reference: Optional[float] = Field(None, description="Revenu fiscal de référence, avis d'impôt sur le revenu seulement")
    nombre_parts: Optional[float] = Field(None, description="Nombre de parts du foyer fiscal, avis d'impôt sur le revenu seulement")
    mentions: list[str] = Field(default_factory=list, description="Mentions libres : 'autoliquidation', 'avoir', 'retenue de garantie 5 %', 'acompte'…")
    champs_illisibles: list[str] = Field(
        default_factory=list, description="Noms des champs présents sur la photo mais illisibles ou ambigus"
    )
