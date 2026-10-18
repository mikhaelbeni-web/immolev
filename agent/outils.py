"""Catalogue des actions que l'agent sait faire. Toute action marquée `ecriture` attend un clic de confirmation."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from document.destination import Destination
from document.extract import extraire
from document.validation import valider
from document.schema import Document


class OutilIndisponible(RuntimeError):
    """Action prévue mais pas encore branchée (écrans du logiciel de gestion ou du portail pas encore relevés)."""


@dataclass
class Outil:
    nom: str
    description: str
    parametres: dict[str, Any]
    ecriture: bool
    executer: Callable[..., str]
    schema: dict[str, Any] | None = None  # schéma complet fourni tel quel (outils MCP)

    def definition(self) -> dict[str, Any]:
        return {
            "name": self.nom,
            "description": self.description + (" ACTION D'ÉCRITURE : exécutée seulement après confirmation du gestionnaire." if self.ecriture else ""),
            "input_schema": self.schema or {"type": "object", "properties": self.parametres, "required": list(self.parametres), "additionalProperties": False},
        }


@dataclass
class Contexte:
    """État d'une demande : photos reçues (en mémoire seulement) et documents lus."""

    photos: dict[str, tuple[bytes, str]] = field(default_factory=dict)
    documents: dict[str, Document] = field(default_factory=dict)
    echanges: list[tuple[str, str]] = field(default_factory=list)  # (demande, réponse) récents, pour « oui », un code reçu…


def _pas_encore(quoi: str) -> Callable[..., str]:
    def f(**_: Any) -> str:
        raise OutilIndisponible(f"{quoi} n'est pas encore branché : il faut d'abord relever les écrans correspondants.")
    return f


def catalogue(ctx: Contexte, destination: Destination, extracteur: Callable[[bytes, str], Document] = extraire) -> dict[str, Outil]:
    def lire_document(photo_id: str) -> str:
        if photo_id not in ctx.photos:
            return f"Photo {photo_id} introuvable. Photos disponibles : {', '.join(ctx.photos) or 'aucune'}"
        doc = extracteur(*ctx.photos[photo_id])
        ctx.documents[photo_id] = doc
        alertes = [f"[{a.niveau}] {a.champ} : {a.message}" for a in valider(doc)]
        return doc.model_dump_json() + "\nAlertes :\n" + ("\n".join(alertes) or "aucune")

    def classer_document(photo_id: str) -> str:
        doc = ctx.documents.get(photo_id)
        if doc is None:
            return "Lire le document d'abord."
        if any(a.niveau == "bloquant" for a in valider(doc)):
            return "Refusé : alertes bloquantes non résolues."
        return f"Document enregistré, référence {destination.envoyer(doc)}"

    def corriger_document(photo_id: str, champ: str, valeur: str) -> str:
        doc = ctx.documents.get(photo_id)
        if doc is None:
            return "Lire le document d'abord."
        donnees = doc.model_dump(mode="json")
        cible, *reste = champ.split(".")
        if cible not in donnees:
            return f"Champ inconnu : {champ}"
        v: Any = None if valeur == "" else json.loads(valeur) if valeur.lstrip("-").replace(".", "", 1).isdigit() else valeur
        if reste:  # ligne d'une liste, ex. lignes_tva.0.taux
            try:
                ligne = donnees[cible][int(reste[0])]
            except (ValueError, IndexError, TypeError):
                return f"Champ inconnu : {champ}"
            if len(reste) != 2 or reste[1] not in ligne:
                return f"Champ inconnu : {champ}"
            ligne[reste[1]] = v
        else:
            donnees[cible] = v
        ctx.documents[photo_id] = Document.model_validate(donnees)
        alertes = [f"[{a.niveau}] {a.champ} : {a.message}" for a in valider(ctx.documents[photo_id])]
        return "Corrigé. Alertes restantes :\n" + ("\n".join(alertes) or "aucune")

    outils = [
        Outil("lire_document", "Lit la photo d'un document (facture, devis, appel de fonds, quittance, avis d'impôt ou de taxe foncière, "
              "relevé, bulletin de paie) et renvoie les données et les alertes de contrôle.",
              {"photo_id": {"type": "string"}}, False, lire_document),
        Outil("corriger_document", "Corrige un champ d'un document déjà lu, sur indication du gestionnaire. champ : ex. 'montant_ttc', "
              "'date_echeance', 'lignes_tva.0.taux' ; valeur en texte, vide pour effacer.",
              {"photo_id": {"type": "string"}, "champ": {"type": "string"}, "valeur": {"type": "string"}}, False, corriger_document),
        Outil("rechercher_logiciel_gestion", "Cherche un lot, un copropriétaire, un locataire, une réservation ou un compte dans le logiciel de gestion "
              "indiqué (copropriete, gestion_locative, hotel, comptabilite).",
              {"logiciel": {"type": "string", "enum": ["copropriete", "gestion_locative", "hotel", "comptabilite"]},
               "recherche": {"type": "string"}}, False,
              _pas_encore("La recherche dans les logiciels de gestion")),
        Outil("classer_document", "Enregistre le document déjà lu dans le logiciel de comptabilité (pièce jointe et écriture à valider), "
              "dans le dossier de la bonne société ou du foyer.",
              {"photo_id": {"type": "string"}}, True, classer_document),
    ]
    return {o.nom: o for o in outils}


def apercu_document(doc: Document) -> str:
    """Ce que le gestionnaire doit vérifier contre le papier avant de confirmer. IBAN masqué sauf les 4 derniers caractères."""
    iban = f"\nIBAN …{doc.iban[-4:]}" if doc.iban else ""
    echeance = f", échéance {doc.date_echeance}" if doc.date_echeance else ""
    return (f"{doc.type_document or 'document'} de {doc.emetteur_nom or '?'} n° {doc.numero or '?'} du {doc.date_document}{echeance}\n"
            f"HT {doc.montant_ht} · TVA {doc.montant_tva} · TTC {doc.montant_ttc}{iban}")
