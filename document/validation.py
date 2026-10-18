"""Contrôles déterministes après extraction. Aucun document n'est classé ni aucun paiement préparé sans passer ici."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal, Optional

from .schema import Document

Niveau = Literal["bloquant", "a_verifier"]

TAUX_TVA = {0.0, 2.1, 5.5, 10.0, 20.0}  # France métropolitaine ; Corse et outre-mer ont leurs propres taux
A_PAYER = {"facture_fournisseur", "appel_de_fonds_copropriete", "appel_de_fonds_vefa", "avis_echeance_loyer",
           "avis_taxe_fonciere", "avis_cfe"}
TOLERANCE = 0.02  # arrondis au centime, ligne par ligne


@dataclass
class Alerte:
    niveau: Niveau
    champ: str
    message: str


def _luhn(chiffres: str) -> bool:
    total = 0
    for i, c in enumerate(reversed(chiffres)):
        n = int(c) * (2 if i % 2 else 1)
        total += n - 9 if n > 9 else n
    return total % 10 == 0


def siret_valide(numero: str) -> bool:
    """SIREN (9 chiffres) ou SIRET (14 chiffres), clé de Luhn ; les établissements de La Poste suivent une autre règle."""
    numero = numero.replace(" ", "")
    if not numero.isdigit() or len(numero) not in (9, 14):
        return False
    if len(numero) == 14 and numero.startswith("356000000"):
        return sum(int(c) for c in numero) % 5 == 0
    return _luhn(numero)


def iban_valide(iban: str) -> bool:
    """Clé ISO 13616 (modulo 97) ; un IBAN français compte 27 caractères."""
    iban = iban.replace(" ", "").upper()
    if len(iban) < 15 or not iban[:2].isalpha() or not iban[2:4].isdigit() or not iban.isalnum():
        return False
    if iban.startswith("FR") and len(iban) != 27:
        return False
    return int("".join(str(int(c, 36)) for c in iban[4:] + iban[:4])) % 97 == 1


def _proche(a: float, b: float, tolerance: float = TOLERANCE) -> bool:
    return abs(a - b) <= tolerance


def valider(doc: Document, aujourd_hui: Optional[date] = None) -> list[Alerte]:
    aujourd_hui = aujourd_hui or date.today()
    alertes: list[Alerte] = []

    for champ in ("type_document", "emetteur_nom", "date_document"):
        if getattr(doc, champ) is None:
            alertes.append(Alerte("bloquant", champ, "Champ obligatoire pour classer le document"))
    for champ in doc.champs_illisibles:
        alertes.append(Alerte("a_verifier", champ, "Signalé illisible ou ambigu par l'extraction"))

    a_payer = doc.type_document in A_PAYER
    if a_payer and doc.montant_ttc is None:
        alertes.append(Alerte("bloquant", "montant_ttc", "Montant à payer absent"))
    if doc.type_document == "facture_fournisseur" and not doc.numero:
        alertes.append(Alerte("a_verifier", "numero", "Facture sans numéro : mention obligatoire, à réclamer au fournisseur"))

    # Cohérence des montants
    ht, tva, ttc = doc.montant_ht, doc.montant_tva, doc.montant_ttc
    if None not in (ht, tva, ttc) and not _proche(ht + tva, ttc):
        alertes.append(Alerte("bloquant", "montant_ttc", f"HT {ht} + TVA {tva} ≠ TTC {ttc} : lecture probablement fausse"))
    for i, ligne in enumerate(doc.lignes_tva):
        champ = f"lignes_tva.{i}"
        if ligne.taux is not None and ligne.taux not in TAUX_TVA:
            alertes.append(Alerte("a_verifier", f"{champ}.taux", f"Taux {ligne.taux} % inhabituel en métropole (Corse, outre-mer ou erreur de lecture ?)"))
        if None not in (ligne.taux, ligne.base_ht, ligne.montant_tva) and not _proche(ligne.base_ht * ligne.taux / 100, ligne.montant_tva, 0.05):
            alertes.append(Alerte("bloquant", f"{champ}.montant_tva", f"{ligne.base_ht} × {ligne.taux} % ≠ {ligne.montant_tva}"))
    if doc.lignes_tva and tva is not None and all(l.montant_tva is not None for l in doc.lignes_tva):
        somme = round(sum(l.montant_tva for l in doc.lignes_tva), 2)
        if not _proche(somme, tva, 0.05):
            alertes.append(Alerte("bloquant", "montant_tva", f"Somme des lignes de TVA {somme} ≠ total TVA {tva}"))
    if ttc is not None and ttc < 0:
        alertes.append(Alerte("a_verifier", "montant_ttc", "Montant négatif : avoir ou remboursement, à confirmer"))
    if any("autoliquidation" in m.lower() for m in doc.mentions) and tva:
        alertes.append(Alerte("a_verifier", "montant_tva", "Mention d'autoliquidation mais TVA facturée : à faire vérifier"))

    # Dates
    if doc.date_document is not None and doc.date_document > aujourd_hui:
        alertes.append(Alerte("bloquant", "date_document", "Date dans le futur"))
    if doc.date_echeance is not None:
        if doc.date_document is not None and doc.date_echeance < doc.date_document:
            alertes.append(Alerte("bloquant", "date_echeance", "Échéance antérieure à la date du document"))
        elif a_payer and doc.date_echeance < aujourd_hui:
            alertes.append(Alerte("a_verifier", "date_echeance", f"Échue depuis le {doc.date_echeance:%d/%m/%Y} : vérifier si c'est déjà payé"))

    # Identifiants
    if doc.emetteur_siret and not siret_valide(doc.emetteur_siret):
        alertes.append(Alerte("a_verifier", "emetteur_siret", "SIREN/SIRET invalide (longueur ou clé) : lecture fausse ou fournisseur à vérifier"))
    if doc.iban and not iban_valide(doc.iban):
        alertes.append(Alerte("bloquant", "iban", "IBAN invalide (clé de contrôle) : ne rien payer sur cette base"))

    # Avis d'impôt sur le revenu
    if doc.type_document == "avis_impot_revenu":
        if doc.revenu_fiscal_reference is None:
            alertes.append(Alerte("a_verifier", "revenu_fiscal_reference", "Revenu fiscal de référence non lu"))
        elif doc.revenu_fiscal_reference < 0:
            alertes.append(Alerte("bloquant", "revenu_fiscal_reference", "Un revenu fiscal de référence n'est jamais négatif"))
        if doc.nombre_parts is not None and (doc.nombre_parts < 1 or abs(doc.nombre_parts * 4 - round(doc.nombre_parts * 4)) > 1e-6):
            alertes.append(Alerte("a_verifier", "nombre_parts", f"{doc.nombre_parts} part(s) : un nombre de parts va par quart, à partir de 1"))
    return alertes
