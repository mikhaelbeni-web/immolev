"""Assistance à distance : RustDesk (libre, gratuit, sans compte ni installation) lancé d'un clic depuis le panneau.

Le client clique « Démarrer l'assistance », lit à l'écran son ID et son mot de passe à usage unique, et les donne à Immolev.
RustDesk demande au client d'accepter chaque connexion ; fermer sa fenêtre (ou « Arrêter ») coupe l'accès.
L'exécutable vient de la dernière version officielle sur GitHub, vérifié par son empreinte SHA-256 publiée par GitHub,
puis gardé dans %LOCALAPPDATA%\\Immolev\\assistance pour les fois suivantes.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import urllib.request
from pathlib import Path

from . import systeme

API = "https://api.github.com/repos/rustdesk/rustdesk/releases/latest"
NOM = re.compile(r"^rustdesk-[\d.]+-x86_64\.exe$")


def _lire(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Immolev", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def choisir(version: dict) -> dict:
    """L'exécutable Windows 64 bits de la version, avec son empreinte : sans empreinte publiée, on refuse."""
    for a in version.get("assets", []):
        if NOM.match(a.get("name", "")):
            if not str(a.get("digest", "")).startswith("sha256:"):
                raise ValueError("Empreinte de RustDesk absente : téléchargez-le vous-même sur rustdesk.com.")
            return a
    raise ValueError("RustDesk pour Windows introuvable dans la dernière version : téléchargez-le sur rustdesk.com.")


def obtenir(dossier: Path, lire=_lire) -> Path:
    """Chemin de RustDesk : déjà téléchargé, sinon téléchargé et vérifié."""
    dossier.mkdir(parents=True, exist_ok=True)
    deja = sorted(p for p in dossier.glob("rustdesk-*-x86_64.exe") if NOM.match(p.name))
    try:
        actif = choisir(json.loads(lire(API, 30)))
    except (OSError, ValueError):
        if deja:  # hors ligne ou GitHub indisponible : la copie déjà vérifiée suffit
            return deja[-1]
        raise
    cible = dossier / actif["name"]
    if cible.exists():
        return cible
    contenu = lire(actif["browser_download_url"], 300)
    if hashlib.sha256(contenu).hexdigest() != actif["digest"].split(":", 1)[1].lower():
        raise ValueError("Le fichier RustDesk téléchargé ne correspond pas à son empreinte officielle : rien n'a été lancé.")
    temp = cible.with_suffix(".part")
    temp.write_bytes(contenu)
    temp.replace(cible)
    for ancien in deja:
        ancien.unlink(missing_ok=True)
    return cible


class Assistance:
    def __init__(self, dossier: Path):
        self.dossier, self.pid = dossier, None

    def etat(self) -> dict:
        # RustDesk portable se relance lui-même dans un autre processus : on suit le clic, pas le PID
        return {"en_cours": self.pid is not None}

    def demarrer(self) -> None:
        if self.pid and systeme.processus_vivant(self.pid):
            return
        exe = obtenir(self.dossier)
        self.pid = subprocess.Popen([str(exe)], cwd=str(self.dossier)).pid

    def arreter(self) -> None:
        if self.pid:
            systeme.arreter_processus(self.pid)
        if systeme.WINDOWS:  # RustDesk relance des processus enfants détachés : on les ferme tous
            subprocess.run(["taskkill", "/IM", "rustdesk*", "/T", "/F"], capture_output=True, creationflags=systeme.SANS_FENETRE)
        self.pid = None
