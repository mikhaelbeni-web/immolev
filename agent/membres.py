"""Personnes autorisées à parler à l'agent, et demandes d'accès en attente.

Quiconque écrit au bot sans être autorisé (/start compris) devient une demande : elle s'affiche dans
le panneau et chez les membres déjà autorisés (boutons Accepter / Refuser dans Telegram).
Identifiants autorisés : coffre Windows (service optizien, TELEGRAM_MEMBRES), comme avant.
Noms : membres.json ; demandes : demandes.json ; refus : refus.json (une personne refusée ne relance plus).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Callable

SERVICE = "optizien"


def _keyring_lire() -> str | None:
    from . import coffre as keyring
    return keyring.get_password(SERVICE, "TELEGRAM_MEMBRES")


def _keyring_ecrire(valeur: str) -> None:
    from . import coffre as keyring
    keyring.set_password(SERVICE, "TELEGRAM_MEMBRES", valeur)


class Registre:
    def __init__(self, dossier: Path, lire: Callable[[], str | None] = _keyring_lire,
                 ecrire: Callable[[str], None] = _keyring_ecrire):
        self.dossier, self._lire_ids, self._ecrire_ids = dossier, lire, ecrire

    def _json(self, nom: str, defaut):
        f = self.dossier / nom
        try:
            return json.loads(f.read_text(encoding="utf-8")) if f.exists() else defaut
        except ValueError:
            return defaut

    def _ecrire_json(self, nom: str, valeur) -> None:
        self.dossier.mkdir(parents=True, exist_ok=True)
        (self.dossier / nom).write_text(json.dumps(valeur, ensure_ascii=False), encoding="utf-8")

    def ids(self) -> set[int]:
        return {int(m) for m in (self._lire_ids() or "").split(",") if m.strip().isdigit()}

    def demandes(self) -> list[dict]:
        return list(self._json("demandes.json", {}).values())

    def noter_demande(self, qui: dict, lieu: str) -> dict | None:
        """Enregistre la demande ; renvoie-la si elle est nouvelle (None si déjà connue ou refusée)."""
        ident = str(qui["id"])
        demandes = self._json("demandes.json", {})
        if ident in demandes or ident in self._json("refus.json", []) or int(ident) in self.ids():
            return None
        nom = " ".join(x for x in (qui.get("first_name"), qui.get("last_name")) if x) or "?"
        demandes[ident] = {"id": ident, "nom": nom[:60], "pseudo": qui.get("username"), "lieu": lieu,
                           "date": datetime.now().strftime("%d/%m %H:%M")}
        self._ecrire_json("demandes.json", demandes)
        return demandes[ident]

    def decider(self, ident: str, accepter: bool) -> dict | None:
        """Accepte ou refuse une demande. Renvoie la demande traitée (None si elle n'existait plus)."""
        demandes = self._json("demandes.json", {})
        demande = demandes.pop(str(ident), None)
        self._ecrire_json("demandes.json", demandes)
        if demande is None:
            return None
        if accepter:
            ids = sorted(self.ids() | {int(ident)})
            self._ecrire_ids(",".join(map(str, ids)))
            noms = self._json("membres.json", {})
            noms[str(ident)] = demande["nom"]
            self._ecrire_json("membres.json", noms)
        else:
            refus = self._json("refus.json", [])
            self._ecrire_json("refus.json", sorted(set(refus) | {str(ident)}))
        return demande

    def oublier_refus(self, ident: str) -> None:
        self._ecrire_json("refus.json", [r for r in self._json("refus.json", []) if r != str(ident)])
