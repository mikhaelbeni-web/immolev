"""Tâches répétitives : « chaque lundi à 9 h, liste les loyers impayés sur Rentila ».

Le programme est dans taches-programmees.json (écrit par l'agent et par le panneau) ; l'heure du
dernier lancement de chacune est dans taches-programmees-etat.json (écrit par l'agent seul).
Une tâche manquée parce que le PC était éteint est lancée une fois, au démarrage suivant.
"""
from __future__ import annotations

import calendar
import json
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

FREQUENCES = {
    "jour": "chaque jour",
    "ouvre": "chaque jour ouvré (lundi au vendredi)",
    "semaine": "chaque semaine",
    "mois": "chaque mois",
}
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
PROGRAMME = "taches-programmees.json"
ETAT = "taches-programmees-etat.json"


def _lire(f: Path, defaut: Any) -> Any:
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defaut


def _ecrire(f: Path, donnees: Any) -> None:
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(donnees, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(f)


def lister(dossier: Path) -> list[dict[str, Any]]:
    return _lire(Path(dossier) / PROGRAMME, [])


def _heure(h: str) -> str:
    m = re.fullmatch(r"\s*(\d{1,2})\s*(?:[h:]\s*(\d{2})?)?\s*", str(h or ""))
    if not m or int(m.group(1)) > 23:
        raise ValueError("Heure invalide : écrire par exemple 9:00 ou 18h30.")
    return f"{int(m.group(1)):02d}:{m.group(2) or '00'}"


def ajouter(dossier: Path, consigne: str, frequence: str, heure: str, jour_semaine: Any = "", jour_mois: Any = 0,
            chat_id: int = 1) -> dict[str, Any]:
    consigne = str(consigne).strip()
    if not consigne:
        raise ValueError("Consigne vide.")
    if frequence not in FREQUENCES:
        raise ValueError("Fréquence inconnue : " + ", ".join(FREQUENCES))
    t: dict[str, Any] = {"id": uuid.uuid4().hex[:8], "consigne": consigne[:2000], "frequence": frequence,
                         "heure": _heure(heure), "chat_id": int(chat_id), "active": True,
                         "creee": datetime.now().isoformat(timespec="minutes")}
    if frequence == "semaine":
        j = str(jour_semaine).strip().lower()
        if j not in JOURS:
            raise ValueError("Jour de la semaine manquant : " + ", ".join(JOURS))
        t["jour_semaine"] = j
    if frequence == "mois":
        try:
            n = int(jour_mois)
        except (TypeError, ValueError):
            n = 0
        if not 1 <= n <= 31:
            raise ValueError("Jour du mois manquant (1 à 31 ; 31 = dernier jour du mois).")
        t["jour_mois"] = n
    taches = lister(dossier)
    taches.append(t)
    _ecrire(Path(dossier) / PROGRAMME, taches)
    return t


def modifier(dossier: Path, ident: str, active: bool | None = None, supprimer: bool = False) -> bool:
    taches = lister(dossier)
    garde = [t for t in taches if not (supprimer and t["id"] == ident)]
    trouve = len(garde) != len(taches)
    for t in garde:
        if t["id"] == ident and active is not None:
            t["active"], trouve = bool(active), True
    _ecrire(Path(dossier) / PROGRAMME, garde)
    return trouve


def description(t: dict[str, Any]) -> str:
    quand = FREQUENCES[t["frequence"]]
    if t["frequence"] == "semaine":
        quand = "chaque " + t["jour_semaine"]
    elif t["frequence"] == "mois":
        quand = "le dernier jour de chaque mois" if t["jour_mois"] == 31 else f"le {t['jour_mois']} de chaque mois"
    return f"{quand} à {t['heure'].replace(':', ' h ')}"


def _occurrence(t: dict[str, Any], jour: datetime) -> datetime | None:
    """L'heure prévue ce jour-là, ou None si la tâche ne tourne pas ce jour-là."""
    h, m = map(int, t["heure"].split(":"))
    f = t["frequence"]
    if f == "ouvre" and jour.weekday() >= 5:
        return None
    if f == "semaine" and jour.weekday() != JOURS.index(t["jour_semaine"]):
        return None
    if f == "mois" and jour.day != min(t["jour_mois"], calendar.monthrange(jour.year, jour.month)[1]):
        return None
    return jour.replace(hour=h, minute=m, second=0, microsecond=0)


def derniere_prevue(t: dict[str, Any], maintenant: datetime) -> datetime | None:
    """Dernière heure prévue passée (sur les 31 derniers jours)."""
    for i in range(32):
        o = _occurrence(t, maintenant - timedelta(days=i))
        if o and o <= maintenant:
            return o
    return None


def prochaine(t: dict[str, Any], maintenant: datetime) -> datetime | None:
    for i in range(32):
        o = _occurrence(t, maintenant + timedelta(days=i))
        if o and o > maintenant:
            return o
    return None


def a_lancer(dossier: Path, maintenant: datetime | None = None) -> list[tuple[dict[str, Any], bool]]:
    """Tâches dont l'heure est passée depuis leur dernier lancement : [(tâche, en_retard)].
    Les marque lancées tout de suite, pour ne jamais les mettre deux fois dans la file."""
    maintenant = maintenant or datetime.now()
    f = Path(dossier) / ETAT
    etat = _lire(f, {})
    dues = []
    for t in lister(dossier):
        prevue = derniere_prevue(t, maintenant)
        if not t.get("active", True) or prevue is None:
            continue
        depuis = max(etat.get(t["id"], ""), t.get("creee", ""))
        if depuis and datetime.fromisoformat(depuis) >= prevue:
            continue
        dues.append((t, maintenant - prevue > timedelta(minutes=30)))
        etat[t["id"]] = maintenant.isoformat(timespec="seconds")
    if dues:
        _ecrire(f, etat)
    return dues


def resume(dossier: Path, maintenant: datetime | None = None) -> str:
    maintenant = maintenant or datetime.now()
    taches = lister(dossier)
    if not taches:
        return "Aucune tâche répétitive."
    lignes = []
    for t in taches:
        p = prochaine(t, maintenant)
        suite = (f" (prochaine : {p.strftime('%d/%m %H:%M')})" if p else "") if t.get("active", True) else " (en pause)"
        lignes.append(f"[{t['id']}] {description(t)}{suite} : {t['consigne']}")
    return "\n".join(lignes)
