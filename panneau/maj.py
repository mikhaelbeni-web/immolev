"""Mise à jour en un clic : remplace le code (systeme/app) par celui d'un Optizien.zip plus récent.

Le Python embarqué n'est pas touché (ses fichiers .exe/.dll sont verrouillés pendant l'exécution) ;
les fichiers .py, eux, peuvent être remplacés à chaud. Le panneau se relance ensuite tout seul.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

PREFIXE = "Optizien/systeme/app/"


def version_de(app: Path) -> str:
    f = app / "VERSION"
    return f.read_text(encoding="utf-8").strip() if f.exists() else "0"


def version_zip(source: Path | bytes) -> str | None:
    try:
        with zipfile.ZipFile(io.BytesIO(source) if isinstance(source, bytes) else source) as z:
            return z.read(PREFIXE + "VERSION").decode().strip()
    except (OSError, KeyError, zipfile.BadZipFile):
        return None


def rang(version: str | None) -> int:
    """Numéro de version (1, 2, 3…). Les anciennes versions datées (2026.10.15-2302) valent 0."""
    v = (version or "").strip()
    return int(v) if v.isdigit() else 0


def chercher(dossiers: list[Path], actuelle: str) -> dict | None:
    """Le zip Optizien le plus récent trouvé dans ces dossiers, s'il est plus récent que la version installée."""
    meilleur = None
    for d in dossiers:
        try:
            candidats = list(d.glob("Optizien*.zip"))
        except OSError:
            continue
        for f in candidats:
            v = version_zip(f)
            if v and rang(v) > rang(actuelle) and (meilleur is None or rang(v) > rang(meilleur["version"])):
                meilleur = {"chemin": str(f), "version": v}
    return meilleur


def appliquer(source: Path | bytes, app: Path, lanceur: Path | None = None) -> str:
    """Extrait le code du zip dans app/. Renvoie la nouvelle version."""
    app = app.resolve()
    with zipfile.ZipFile(io.BytesIO(source) if isinstance(source, bytes) else source) as z:
        if PREFIXE + "VERSION" not in z.namelist():
            raise ValueError("Ce fichier n'est pas un zip Optizien.")
        for nom in z.namelist():
            if nom.endswith("/"):
                continue
            if nom.startswith(PREFIXE):
                cible = (app / nom[len(PREFIXE):]).resolve()
            elif lanceur and nom == "Optizien/Ouvrir Optizien.vbs":
                cible = lanceur
            else:
                continue
            if app not in cible.parents and cible != lanceur:
                raise ValueError(f"Chemin refusé dans le zip : {nom}")
            cible.parent.mkdir(parents=True, exist_ok=True)
            cible.write_bytes(z.read(nom))
        return z.read(PREFIXE + "VERSION").decode().strip()


# Mises à jour en ligne : espace protégé du site Optizien (compte + mot de passe du magasin) ----------
SITE = "https://optizien.vercel.app/telecharger"


def _requete(url: str, compte: dict, timeout: int = 20):
    import base64
    import urllib.request
    jeton = base64.b64encode(f"{compte['identifiant']}:{compte['mot_de_passe']}".encode()).decode()
    return urllib.request.urlopen(urllib.request.Request(url, headers={"Authorization": "Basic " + jeton}), timeout=timeout)


def version_en_ligne(compte: dict, site: str = SITE) -> dict:
    """{"version": "7", "fichier": "Optizien-v7.zip"} ; lève PermissionError si le compte est refusé."""
    import json
    import urllib.error
    try:
        with _requete(f"{site}/version.json", compte) as r:
            d = json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise PermissionError("Identifiant ou mot de passe refusé par le site Optizien.") from None
        raise
    return {"version": str(d["version"]), "url": f"{site}/{d['fichier']}"}


def chercher_en_ligne(compte: dict | None, actuelle: str, site: str = SITE) -> dict | None:
    if not compte:
        return None
    try:
        d = version_en_ligne(compte, site)
    except Exception:
        return None
    return d if rang(d["version"]) > rang(actuelle) else None


def telecharger(url: str, compte: dict, destination: Path) -> Path:
    with _requete(url, compte, timeout=300) as r, open(destination, "wb") as f:
        while bloc := r.read(1 << 20):
            f.write(bloc)
    return destination
