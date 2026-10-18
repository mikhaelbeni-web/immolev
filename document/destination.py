"""Envoi du document validé vers le logiciel de comptabilité ou de gestion. Rien n'est stocké par la plateforme."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Protocol

from .schema import Document

journal = logging.getLogger("immolev.journal")


class Destination(Protocol):
    def envoyer(self, doc: Document) -> str:
        """Enregistre le document dans le logiciel et renvoie la référence attribuée par celui-ci."""


class LogicielNonConfigure:
    """À remplacer par le connecteur du logiciel de comptabilité ou de gestion (API, import, ou script navigateur)."""

    def envoyer(self, doc: Document) -> str:
        raise NotImplementedError("Connecteur du logiciel de comptabilité pas encore écrit : nom du logiciel inconnu")


def tracer(action: str, reference: str, statut: str) -> None:
    """Journal d'audit sans montant, sans IBAN ni nom de personne."""
    journal.info(json.dumps({"horodatage": datetime.now(timezone.utc).isoformat(), "action": action, "reference": reference, "statut": statut}))
