"""Envoi de l'ordonnance validée vers le logiciel principal d'optique. Rien n'est stocké par la plateforme."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Protocol

from .schema import Ordonnance

journal = logging.getLogger("optizien.journal")


class Destination(Protocol):
    def envoyer(self, ordo: Ordonnance) -> str:
        """Écrit l'ordonnance dans le logiciel et renvoie la référence attribuée par celui-ci."""


class LogicielNonConfigure:
    """À remplacer par le connecteur du logiciel principal (API, import, ou script navigateur)."""

    def envoyer(self, ordo: Ordonnance) -> str:
        raise NotImplementedError("Connecteur du logiciel principal pas encore écrit : nom du logiciel inconnu")


def tracer(action: str, reference: str, statut: str) -> None:
    """Journal d'audit sans donnée médicale ni nom de patient."""
    journal.info(json.dumps({"horodatage": datetime.now(timezone.utc).isoformat(), "action": action, "reference": reference, "statut": statut}))
