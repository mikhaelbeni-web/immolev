"""Catalogue des actions que l'agent sait faire. Toute action marquée `ecriture` attend un clic de confirmation."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from ordonnance.destination import Destination
from ordonnance.extract import extraire
from ordonnance.validation import valider
from ordonnance.schema import Ordonnance


class OutilIndisponible(RuntimeError):
    """Action prévue mais pas encore branchée (écrans MyEasyOptic ou portail pas encore relevés)."""


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
            "description": self.description + (" ACTION D'ÉCRITURE : exécutée seulement après confirmation de l'opticien." if self.ecriture else ""),
            "input_schema": self.schema or {"type": "object", "properties": self.parametres, "required": list(self.parametres), "additionalProperties": False},
        }


@dataclass
class Contexte:
    """État d'une demande : photos reçues (en mémoire seulement) et ordonnances lues."""

    photos: dict[str, tuple[bytes, str]] = field(default_factory=dict)
    ordonnances: dict[str, Ordonnance] = field(default_factory=dict)
    echanges: list[tuple[str, str]] = field(default_factory=list)  # (demande, réponse) récents, pour « oui », un code reçu…


def _pas_encore(quoi: str) -> Callable[..., str]:
    def f(**_: Any) -> str:
        raise OutilIndisponible(f"{quoi} n'est pas encore branché : il faut d'abord relever les écrans correspondants.")
    return f


def catalogue(ctx: Contexte, destination: Destination, extracteur: Callable[[bytes, str], Ordonnance] = extraire) -> dict[str, Outil]:
    def lire_ordonnance(photo_id: str) -> str:
        if photo_id not in ctx.photos:
            return f"Photo {photo_id} introuvable. Photos disponibles : {', '.join(ctx.photos) or 'aucune'}"
        ordo = extracteur(*ctx.photos[photo_id])
        ctx.ordonnances[photo_id] = ordo
        alertes = [f"[{a.niveau}] {a.champ} : {a.message}" for a in valider(ordo)]
        return ordo.model_dump_json() + "\nAlertes :\n" + ("\n".join(alertes) or "aucune")

    def saisir_ordonnance(photo_id: str) -> str:
        ordo = ctx.ordonnances.get(photo_id)
        if ordo is None:
            return "Lire l'ordonnance d'abord."
        if any(a.niveau == "bloquant" for a in valider(ordo)):
            return "Refusé : alertes bloquantes non résolues."
        return f"Ordonnance saisie, référence {destination.envoyer(ordo)}"

    def corriger_ordonnance(photo_id: str, champ: str, valeur: str) -> str:
        ordo = ctx.ordonnances.get(photo_id)
        if ordo is None:
            return "Lire l'ordonnance d'abord."
        donnees = ordo.model_dump(mode="json")
        cible, *reste = champ.split(".")
        if cible not in donnees or (reste and reste[0] not in (donnees[cible] or {})):
            return f"Champ inconnu : {champ}"
        v: Any = None if valeur == "" else json.loads(valeur) if valeur.lstrip("-").replace(".", "", 1).isdigit() else valeur
        if reste:
            donnees[cible][reste[0]] = v
        else:
            donnees[cible] = v
        ctx.ordonnances[photo_id] = Ordonnance.model_validate(donnees)
        alertes = [f"[{a.niveau}] {a.champ} : {a.message}" for a in valider(ctx.ordonnances[photo_id])]
        return "Corrigé. Alertes restantes :\n" + ("\n".join(alertes) or "aucune")

    outils = [
        Outil("lire_ordonnance", "Lit la photo d'une ordonnance optique et renvoie les données et les alertes de contrôle.",
              {"photo_id": {"type": "string"}}, False, lire_ordonnance),
        Outil("corriger_ordonnance", "Corrige un champ d'une ordonnance déjà lue, sur indication de l'opticien. champ : ex. 'og.axe', 'date_prescription' ; valeur en texte, vide pour effacer.",
              {"photo_id": {"type": "string"}, "champ": {"type": "string"}, "valeur": {"type": "string"}}, False, corriger_ordonnance),
        Outil("rechercher_client_myeasyoptic", "Cherche un client dans MyEasyOptic par nom, prénom et date de naissance (AAAA-MM-JJ, vide si inconnue).",
              {"nom": {"type": "string"}, "prenom": {"type": "string"}, "date_naissance": {"type": "string"}}, False,
              _pas_encore("La recherche client MyEasyOptic")),
        Outil("verifier_droits", "Vérifie les droits tiers payant d'un bénéficiaire sur le portail indiqué (almerys, viamedis, sp_sante, isante, tpplus).",
              {"portail": {"type": "string", "enum": ["almerys", "viamedis", "sp_sante", "isante", "tpplus"]},
               "numero_adherent": {"type": "string"}, "nom_beneficiaire": {"type": "string"}, "date_naissance": {"type": "string"}}, False,
              _pas_encore("La vérification des droits sur les portails")),
        Outil("saisir_ordonnance_myeasyoptic", "Crée ou complète la fiche client dans MyEasyOptic avec l'ordonnance déjà lue, et joint la photo.",
              {"photo_id": {"type": "string"}}, True, saisir_ordonnance),
    ]
    return {o.nom: o for o in outils}


def apercu_ordonnance(ordo: Ordonnance) -> str:
    """Ce que l'opticien doit vérifier contre l'ordonnance papier avant de confirmer. Initiales seulement."""
    def oeil(o):  # noqa: ANN001
        return f"sph {o.sphere} cyl {o.cylindre} axe {o.axe} add {o.addition}"
    initiales = "".join((x or "?")[0] for x in (ordo.patient_prenom, ordo.patient_nom))
    return f"{initiales}, ordonnance du {ordo.date_prescription}\nOD {oeil(ordo.od)}\nOG {oeil(ordo.og)}\nEP {ordo.ecart_pupillaire_mm}"
