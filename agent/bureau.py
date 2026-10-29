"""Discussion avec l'agent depuis le panneau Immolev, sans Telegram.

Deux fichiers dans le dossier des données, chacun écrit par un seul programme :
- bureau-demandes.jsonl : le panneau y ajoute les messages et les clics (Confirmer / Annuler) ;
- bureau-reponses.jsonl : l'agent y ajoute ses réponses.
Le panneau affiche les deux, triés par heure. Pour l'agent, le bureau est une conversation
privée de plus (identifiant BUREAU), traitée dans la même file que Telegram.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

BUREAU = 1  # identifiant de conversation : positif = privée (un vrai identifiant Telegram ne vaut jamais 1)
DEMANDES = "bureau-demandes.jsonl"
REPONSES = "bureau-reponses.jsonl"


def _ajouter(fichier: Path, ligne: dict[str, Any]) -> None:
    with fichier.open("a", encoding="utf-8") as f:
        f.write(json.dumps(ligne, ensure_ascii=False) + "\n")


def _lire(fichier: Path) -> list[dict[str, Any]]:
    try:
        lignes = fichier.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    sortie = []
    for ligne in lignes:
        try:
            sortie.append(json.loads(ligne))
        except ValueError:
            continue
    return sortie


# ------------------------------------------------------------ côté panneau

def envoyer(dossier: Path, texte: str = "", bouton: str = "") -> None:
    texte = texte.strip()
    if not texte and not bouton:
        raise ValueError("Message vide.")
    if bouton and not re.fullmatch(r"(ok|non):[\w-]{1,40}", bouton):
        raise ValueError("Bouton inconnu.")
    ligne: dict[str, Any] = {"id": uuid.uuid4().hex[:12], "le": time.time()}
    if bouton:
        ligne["bouton"] = bouton
    else:
        ligne["texte"] = texte[:8000]
    _ajouter(Path(dossier) / DEMANDES, ligne)


def conversation(dossier: Path, dernier: int = 200) -> list[dict[str, Any]]:
    """Messages des deux côtés, du plus ancien au plus récent ; les boutons déjà cliqués sont marqués."""
    demandes = _lire(Path(dossier) / DEMANDES)
    reponses = _lire(Path(dossier) / REPONSES)
    cliques = {d["bouton"].partition(":")[2]: d["bouton"].partition(":")[0] for d in demandes if d.get("bouton")}
    messages = []
    for d in demandes:
        if d.get("texte"):
            messages.append({"de": "moi", "le": d["le"], "texte": d["texte"]})
        elif d.get("bouton"):
            messages.append({"de": "moi", "le": d["le"], "texte": "✓ Confirmé" if d["bouton"].startswith("ok:") else "✕ Annulé"})
    for r in reponses:
        m = {"de": "agent", "le": r.get("le", 0), "texte": r.get("texte", "")}
        boutons = [b for rang in r.get("boutons") or [] for b in rang]
        if boutons:
            action = boutons[0]["callback_data"].partition(":")[2]
            m["action"] = action
            m["choix"] = cliques.get(action)  # None tant que personne n'a cliqué
        messages.append(m)
    messages.sort(key=lambda m: m["le"])
    return messages[-dernier:]


# ------------------------------------------------------------ côté agent

class Bureau:
    def __init__(self, dossier: Path):
        self.dossier = Path(dossier)
        f = self.dossier / DEMANDES
        self.position = f.stat().st_size if f.exists() else 0  # ce qui a été écrit avant le démarrage est ignoré

    def ecrire(self, texte: str, boutons: list[list[dict[str, str]]] | None = None) -> None:
        ligne: dict[str, Any] = {"le": time.time(), "texte": texte}
        if boutons:
            ligne["boutons"] = boutons
        _ajouter(self.dossier / REPONSES, ligne)

    def nouvelles(self) -> list[dict[str, Any]]:
        """Demandes arrivées depuis le dernier passage, converties au format d'une mise à jour Telegram."""
        f = self.dossier / DEMANDES
        try:
            with f.open("rb") as fh:
                fh.seek(self.position)
                octets = fh.read()
        except OSError:
            return []
        fin = octets.rfind(b"\n")
        if fin < 0:
            return []  # ligne en cours d'écriture : on attend la suite
        self.position += fin + 1
        updates = []
        for brut in octets[:fin].splitlines():
            try:
                d = json.loads(brut.decode("utf-8"))
            except ValueError:
                continue
            qui = {"id": BUREAU, "first_name": "Bureau"}
            if d.get("bouton"):
                updates.append({"callback_query": {"id": "bureau", "from": qui, "data": d["bouton"],
                                                   "message": {"chat": {"id": BUREAU}}}})
            elif d.get("texte"):
                updates.append({"message": {"message_id": 0, "from": qui, "chat": {"id": BUREAU, "type": "private"},
                                            "text": d["texte"]}})
        return updates
