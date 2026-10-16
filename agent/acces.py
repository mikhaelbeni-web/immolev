"""Coffre des accès aux sites (MyEasyOptic, portails de tiers payant…).

Saisis une fois dans le panneau. Identifiant et mot de passe vont dans le coffre Windows (service
« optizien-acces ») ; seuls le nom, l'adresse et le domaine sont dans acces.json. L'agent ne voit
jamais le mot de passe : Navigateur.se_connecter le tape directement dans la page, et seulement
sur le domaine enregistré.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from urllib.parse import urlparse

SERVICE = "optizien-acces"


def dossier_donnees() -> Path:
    d = Path(os.environ.get("OPTIZIEN_DONNEES") or
             Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share") / "Optizien")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _fichier() -> Path:
    return dossier_donnees() / "acces.json"


def domaine_de(url: str) -> str:
    """Domaine enregistrable approché : app.myeasyoptic.fr → myeasyoptic.fr."""
    hote = (urlparse(url if "://" in url else "https://" + url).hostname or "").lower()
    if not hote or "." not in hote:
        raise ValueError("Adresse invalide : copiez l'adresse complète de la page de connexion.")
    return ".".join(hote.split(".")[-2:])


def domaine_correspond(hote: str, domaine: str) -> bool:
    hote = (hote or "").lower()
    return hote == domaine or hote.endswith("." + domaine)


def _keyring():
    import keyring
    return keyring


def lister() -> list[dict]:
    f = _fichier()
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []


def _ecrire(sites: list[dict]) -> None:
    _fichier().write_text(json.dumps(sites, ensure_ascii=False, indent=1), encoding="utf-8")


def enregistrer(nom: str, url: str, identifiant: str, mot_de_passe: str, ident: str | None = None) -> dict:
    nom, url, identifiant = nom.strip(), url.strip(), identifiant.strip()
    if not nom or not url:
        raise ValueError("Indiquez le nom du site et l'adresse de sa page de connexion.")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    sites = lister()
    site = next((s for s in sites if s["id"] == ident), None) if ident else None
    if site is None:
        if not identifiant or not mot_de_passe:
            raise ValueError("Indiquez l'identifiant et le mot de passe.")
        site = {"id": uuid.uuid4().hex[:8]}
        sites.append(site)
    try:
        ancien = identifiants(site["id"]) if ident else ("", "")
    except LookupError:
        ancien = ("", "")
    secret = {"identifiant": identifiant or ancien[0], "mot_de_passe": mot_de_passe or ancien[1]}
    if not secret["identifiant"] or not secret["mot_de_passe"]:
        raise ValueError("Indiquez l'identifiant et le mot de passe.")
    _keyring().set_password(SERVICE, site["id"], json.dumps(secret))
    site.update(nom=nom, url=url, domaine=domaine_de(url), apercu=_masquer(secret["identifiant"]))
    _ecrire(sites)
    return site


def supprimer(ident: str) -> None:
    _ecrire([s for s in lister() if s["id"] != ident])
    try:
        _keyring().delete_password(SERVICE, ident)
    except Exception:
        pass


def identifiants(ident: str) -> tuple[str, str]:
    brut = _keyring().get_password(SERVICE, ident)
    if not brut:
        raise LookupError("Identifiants absents du coffre : ressaisissez-les dans le panneau Optizien.")
    d = json.loads(brut)
    return d["identifiant"], d["mot_de_passe"]


def trouver(site: str) -> dict:
    """Par nom (sans accents ni casse) ou par domaine."""
    def norm(s: str) -> str:
        s = s.lower()
        for a, b in (("é", "e"), ("è", "e"), ("ê", "e"), ("à", "a"), ("ç", "c")):
            s = s.replace(a, b)
        return re.sub(r"[^a-z0-9]", "", s)
    cible, sites = norm(site), lister()
    for s in sites:
        if norm(s["nom"]) == cible or s["domaine"] == site.lower() or cible and cible in norm(s["domaine"]):
            return s
    for s in sites:
        if cible and (cible in norm(s["nom"]) or norm(s["nom"]) in cible):
            return s
    noms = ", ".join(s["nom"] for s in sites) or "aucun"
    raise LookupError(f"Site « {site} » absent du coffre des accès (enregistrés : {noms}). "
                      "Ne demande pas l'adresse à l'équipe : dis-lui d'ajouter ce site (adresse, identifiant, mot de passe) "
                      "dans le panneau Optizien, carte « Accès aux sites ».")


def _masquer(identifiant: str) -> str:
    if len(identifiant) <= 3:
        return "•••"
    return identifiant[:2] + "•" * min(6, len(identifiant) - 3) + identifiant[-1]
