"""Pièces jointes et fichiers : l'agent les télécharge et les lit lui-même (PDF, Excel, Word, images, texte).

Tout fichier récupéré va dans le dossier « pieces » des données Immolev (un sous-dossier par mail), d'où l'agent
peut le relire, le joindre à un mail ou le déposer dans son dossier de travail OneDrive (« Immolev »).
Lecture : texte du PDF (pypdf) ; PDF scanné ou image : transcrit par Claude ; Excel et Word : lus directement.
"""
from __future__ import annotations

import base64
import csv
import io
import json
import mimetypes
import re
import zipfile
from pathlib import Path
from typing import Any, Callable
from xml.etree import ElementTree

from .acces import dossier_donnees
from .outils import Outil

LIMITE_TEXTE = 30000
LIMITE_CLAUDE = 3_000_000  # au-delà, la passerelle refuse la requête : on se contente du texte
DOSSIER_ONEDRIVE = "Immolev"
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


def dossier_pieces() -> Path:
    d = dossier_donnees() / "pieces"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _nom_sur(nom: str) -> str:
    nom = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", Path(str(nom)).name).strip(" .")
    return nom[:150] or "fichier"


# ------------------------------------------------------------------ lecture des formats

def _xlsx(octets: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(octets)) as z:
        partages = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ElementTree.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
                partages.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))
        classeur = ElementTree.fromstring(z.read("xl/workbook.xml"))
        liens = {r.get("Id"): r.get("Target") for r in ElementTree.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
        sortie = []
        for feuille in classeur.find("m:sheets", NS):
            cible = liens.get(feuille.get(f"{{{NS['r']}}}id"), "")
            chemin = "xl/" + cible.lstrip("/").removeprefix("xl/")
            if chemin not in z.namelist():
                continue
            tampon = io.StringIO()
            ecrit = csv.writer(tampon, delimiter=";")
            for ligne in ElementTree.fromstring(z.read(chemin)).iter(f"{{{NS['m']}}}row"):
                valeurs = []
                for c in ligne.findall("m:c", NS):
                    v, t = c.find("m:v", NS), c.get("t")
                    if t == "s" and v is not None:
                        valeurs.append(partages[int(v.text)])
                    elif t == "inlineStr":
                        valeurs.append("".join(x.text or "" for x in c.iter(f"{{{NS['m']}}}t")))
                    else:
                        valeurs.append(v.text if v is not None else "")
                if any(valeurs):
                    ecrit.writerow(valeurs)
            sortie.append(f"## Feuille « {feuille.get('name')} »\n{tampon.getvalue()}")
        return "\n".join(sortie)


def _docx(octets: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(octets)) as z:
        racine = ElementTree.fromstring(z.read("word/document.xml"))
    return "\n".join("".join(t.text or "" for t in p.iter(f"{{{NS['w']}}}t")) for p in racine.iter(f"{{{NS['w']}}}p"))


def _pdf(octets: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        lecteur = PdfReader(io.BytesIO(octets))
        return "\n".join(f"--- page {i} ---\n{p.extract_text() or ''}" for i, p in enumerate(lecteur.pages, 1))
    except Exception:  # PDF abîmé ou chiffré : Claude essaiera
        return ""


def transcrire_par_claude(octets: bytes, media_type: str) -> str:
    """PDF scanné ou image : Claude recopie le contenu."""
    import anthropic
    from .orchestrateur import MODELE
    bloc = ({"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": base64.standard_b64encode(octets).decode()}}
            if media_type == "application/pdf" else
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": base64.standard_b64encode(octets).decode()}})
    r = anthropic.Anthropic(max_retries=3).messages.create(
        model=MODELE, max_tokens=8000,
        messages=[{"role": "user", "content": [bloc, {"type": "text", "text":
                   "Recopie fidèlement tout le contenu de ce document en texte (tableaux en lignes « colonne ; colonne »). "
                   "N'invente rien ; écris [illisible] là où tu ne peux pas lire."}]}])
    return "".join(b.text for b in r.content if getattr(b, "type", "") == "text")


def lire_octets(nom: str, octets: bytes, transcrire: Callable[[bytes, str], str] = transcrire_par_claude) -> str:
    ext = Path(nom).suffix.lower()
    media = mimetypes.guess_type(nom)[0] or ""
    try:
        if ext in (".xlsx", ".xlsm"):
            texte = _xlsx(octets)
        elif ext == ".docx":
            texte = _docx(octets)
        elif ext in (".txt", ".csv", ".md", ".json", ".xml", ".html", ".htm", ".eml"):
            texte = octets.decode("utf-8", errors="replace")
        elif ext == ".pdf":
            texte = _pdf(octets)
            if len(re.sub(r"--- page \d+ ---|\s", "", texte)) < 20:  # pas de couche texte : PDF scanné
                if len(octets) > LIMITE_CLAUDE:
                    return f"{nom} : PDF scanné trop lourd ({len(octets) // 1000} ko) pour être lu ici."
                texte = transcrire(octets, "application/pdf")
        elif media in ("image/jpeg", "image/png", "image/gif", "image/webp"):
            if len(octets) > LIMITE_CLAUDE:
                return f"{nom} : image trop lourde ({len(octets) // 1000} ko) pour être lue ici."
            texte = transcrire(octets, media)
        elif ext in (".xls", ".doc"):
            return f"{nom} : ancien format Office ({ext}) que je ne sais pas lire. Demander le fichier en {ext}x ou en PDF."
        else:
            return f"{nom} : format {ext or 'inconnu'} non lisible."
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as e:
        return f"{nom} : fichier abîmé ou protégé ({e})."
    texte = texte.strip() or "(vide)"
    return texte if len(texte) <= LIMITE_TEXTE else texte[:LIMITE_TEXTE] + f"\n… (tronqué, {len(texte)} caractères en tout)"


def _fichier_local(nom: str) -> Path:
    """Un fichier des dossiers pieces ou plans, donné par son nom ou son chemin relatif (« sous-dossier/nom »)."""
    for base in (dossier_pieces(), dossier_donnees() / "plans"):
        base = base.resolve()
        f = (base / nom).resolve()
        if f.is_file() and base in f.parents:
            return f
        trouves = sorted(base.rglob(_nom_sur(nom))) if base.is_dir() else []
        if trouves:
            return max(trouves, key=lambda p: p.stat().st_mtime)
    raise ValueError(f"Fichier introuvable : {nom}. Fichiers disponibles : {lister_fichiers()}")


def lister_fichiers() -> str:
    noms = []
    for base in (dossier_pieces(), dossier_donnees() / "plans"):
        if base.is_dir():
            noms += [str(p.relative_to(base)).replace("\\", "/") for p in sorted(base.rglob("*")) if p.is_file()]
    return ", ".join(noms[-80:]) or "aucun"


# ------------------------------------------------------------------ outils de l'agent

def _json(texte: str) -> Any:
    try:
        return json.loads(texte)
    except ValueError:
        m = re.search(r"[\[{].*[\]}]", texte, re.S)
        return json.loads(m.group(0)) if m else None


def outils_fichiers(connecteurs: Any) -> dict[str, Outil]:
    serveurs = set(getattr(connecteurs, "sessions", {}) or {})
    outlook = next((s for s in ("outlook", "ms365") if s in serveurs), None)
    gmail = "gmail" if "gmail" in serveurs else None
    drive: dict[str, str] = {}

    def piece_outlook(mail_id: str, nom: str) -> Path:
        brut = connecteurs.appeler(outlook, "list-mail-attachments", {"messageId": mail_id})
        pieces = (_json(brut) or {}).get("value", []) if isinstance(_json(brut), dict) else []
        if not pieces:
            raise ValueError(f"Aucune pièce jointe lue pour ce mail ({brut[:300]})")
        choix = [p for p in pieces if not nom or nom.lower() in str(p.get("name", "")).lower()]
        if not choix:
            raise ValueError("Pièce introuvable. Pièces du mail : " + ", ".join(str(p.get("name")) for p in pieces))
        p = choix[0]
        dossier = dossier_pieces() / re.sub(r"\W", "", mail_id)[-16:]
        dossier.mkdir(exist_ok=True)
        cible = dossier / _nom_sur(p.get("name", "piece"))
        if not cible.exists():
            rep = connecteurs.appeler(outlook, "download-bytes-to-file", {
                "target": f"/me/messages/{mail_id}/attachments/{p['id']}/$value", "outputPath": str(cible)})
            if not cible.exists():
                raise ValueError(f"Téléchargement refusé par le connecteur Outlook : {rep[:300]}")
        return cible

    def piece_gmail(mail_id: str, nom: str, compte: str) -> Path:
        rep = connecteurs.appeler(gmail, "enregistrer_piece_jointe", {"mail_id": mail_id, "nom": nom, "compte": compte})
        chemin = Path(rep.strip().splitlines()[-1].strip())
        if not chemin.is_file():
            raise ValueError(rep[:400])
        return chemin

    def lire_piece_jointe(mail_id: str, nom: str = "", boite: str = "outlook", compte: str = "") -> str:
        if boite == "gmail":
            if not gmail:
                return "Connecteur Gmail non branché."
            f = piece_gmail(mail_id, nom, compte)
        else:
            if not outlook:
                return "Connecteur Outlook non branché."
            f = piece_outlook(mail_id, nom)
        nom_local = str(f.relative_to(dossier_pieces())).replace("\\", "/")
        return f"Fichier enregistré : {nom_local} (réutilisable avec lire_fichier, deposer_onedrive, ou en pièce jointe)\n\n" + lire_octets(f.name, f.read_bytes())

    def lire_fichier(nom: str) -> str:
        f = _fichier_local(nom)
        return lire_octets(f.name, f.read_bytes())

    def id_onedrive() -> str:
        if "id" not in drive:
            lecteurs = (_json(connecteurs.appeler(outlook, "list-drives", {})) or {}).get("value", [])
            perso = [d for d in lecteurs if d.get("name") == "OneDrive"] or lecteurs
            if not perso:
                raise ValueError("OneDrive introuvable avec le connecteur Outlook.")
            drive["id"] = perso[0]["id"]
        return drive["id"]

    def deposer_onedrive(nom: str, sous_dossier: str = "") -> str:
        f = _fichier_local(nom)
        sous = "/".join(_nom_sur(x) for x in re.split(r"[\\/]", sous_dossier) if x.strip())
        chemin = "/".join(x for x in (DOSSIER_ONEDRIVE, sous, f.name) if x)
        rep = connecteurs.appeler(outlook, "upload-file-content", {
            "driveId": id_onedrive(), "driveItemId": f"root:/{chemin}:", "body": base64.b64encode(f.read_bytes()).decode()})
        info = _json(rep) if "rreur" not in rep[:40] else None
        if not isinstance(info, dict) or not info.get("id"):
            raise ValueError(f"Dépôt refusé : {rep[:300]}")
        return f"Déposé dans le OneDrive : {chemin}" + (f" ({info['webUrl']})" if info.get("webUrl") else "")

    def lire_onedrive(chemin: str) -> str:
        chemin = chemin.strip().strip("/")
        nom = _nom_sur(chemin.split("/")[-1])
        dossier = dossier_pieces() / "onedrive"
        dossier.mkdir(exist_ok=True)
        cible = dossier / nom
        if cible.exists():
            cible.unlink()
        rep = connecteurs.appeler(outlook, "download-bytes-to-file", {
            "target": f"/drives/{id_onedrive()}/root:/{chemin}:/content", "outputPath": str(cible)})
        if not cible.exists():
            raise ValueError(f"Téléchargement refusé : {rep[:300]}")
        return f"Fichier enregistré : onedrive/{nom}\n\n" + lire_octets(nom, cible.read_bytes())

    outils = {"lire_fichier": Outil(
        "lire_fichier", "Lit un fichier déjà enregistré sur ce PC (pièce jointe récupérée, plan, fichier du OneDrive) : "
        "PDF (même scanné), Excel, Word, image, texte. nom : nom ou chemin donné par lire_piece_jointe. Fichiers : "
        "voir le message d'erreur si le nom est inconnu.", {"nom": {"type": "string"}}, False, lire_fichier)}
    if outlook or gmail:
        outils["lire_piece_jointe"] = Outil(
            "lire_piece_jointe", "Télécharge une pièce jointe d'un mail sur ce PC et la lit (PDF même scanné, Excel, Word, "
            "image, texte), sans rien demander au gestionnaire. mail_id : identifiant du mail donné par le connecteur. "
            "nom : nom (ou morceau du nom) de la pièce, vide = la première. boite : 'outlook' (Hotmail) ou 'gmail' ; "
            "compte : adresse Gmail si boite = gmail.",
            {"mail_id": {"type": "string"}, "nom": {"type": "string"}, "boite": {"type": "string", "enum": ["outlook", "gmail"]},
             "compte": {"type": "string"}}, False, lire_piece_jointe)
    if outlook:
        outils["deposer_onedrive"] = Outil(
            "deposer_onedrive", f"Dépose un fichier de ce PC (pièce jointe récupérée, plan…) dans le dossier de travail "
            f"« {DOSSIER_ONEDRIVE} » du OneDrive du gestionnaire, pour qu'il le voie ou pour le partager. sous_dossier : "
            "facultatif, créé au besoin (ex. 'AMEX 2026'). N'écrit que dans ce dossier.",
            {"nom": {"type": "string"}, "sous_dossier": {"type": "string"}}, False, deposer_onedrive)
        outils["lire_onedrive"] = Outil(
            "lire_onedrive", "Télécharge et lit un fichier du OneDrive du gestionnaire. chemin : depuis la racine, ex. "
            "'plan immeuble/93 rue du commerce/PLANS IMMEUBLE 2019.pdf' ou 'Immolev/AMEX/factures.xlsx'.",
            {"chemin": {"type": "string"}}, False, lire_onedrive)
    return outils
