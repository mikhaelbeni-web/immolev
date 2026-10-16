"""Visage et prénom de l'agent : choisis dans le panneau, appliqués au bot Telegram (photo + nom).

Choix enregistré dans <données>/visage.json : {"id": "lea", "nom": "Léa"}.
Images : panneau/avatars/<id>.jpg (dessinées par outils/avatars.py).
"""
from __future__ import annotations

import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

AVATARS = Path(__file__).with_name("avatars")


def liste() -> list[dict]:
    f = AVATARS / "liste.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []


def image(ident: str) -> bytes | None:
    if not any(a["id"] == ident for a in liste()):
        return None
    f = AVATARS / f"{ident}.jpg"
    return f.read_bytes() if f.exists() else None


def lire(donnees: Path) -> dict | None:
    f = donnees / "visage.json"
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    except ValueError:
        return None


def _telegram(jeton: str, methode: str, corps: bytes, type_: str) -> dict:
    req = urllib.request.Request(f"https://api.telegram.org/bot{jeton}/{methode}", data=corps,
                                 headers={"Content-Type": type_}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read() or b"{}")
        except ValueError:
            return {"ok": False, "description": f"HTTP {e.code}"}
    except OSError as e:
        return {"ok": False, "description": f"réseau : {e}"}


def _photo_bot(jeton: str, jpg: bytes) -> dict:
    limite = "----optizien" + secrets.token_hex(8)
    photo = json.dumps({"type": "static", "photo": "attach://visage"})
    corps = (f"--{limite}\r\nContent-Disposition: form-data; name=\"photo\"\r\n\r\n{photo}\r\n"
             f"--{limite}\r\nContent-Disposition: form-data; name=\"visage\"; filename=\"visage.jpg\"\r\n"
             f"Content-Type: image/jpeg\r\n\r\n").encode() + jpg + f"\r\n--{limite}--\r\n".encode()
    return _telegram(jeton, "setMyProfilePhoto", corps, f"multipart/form-data; boundary={limite}")


def _nom_bot(jeton: str, nom: str) -> dict:
    corps = urllib.parse.urlencode({"name": nom}).encode()
    return _telegram(jeton, "setMyName", corps, "application/x-www-form-urlencoded")


def choisir(donnees: Path, ident: str, nom: str, jeton: str | None) -> dict:
    jpg = image(ident)
    if jpg is None:
        raise ValueError("Visage inconnu.")
    nom = " ".join((nom or "").split())[:40] or next(a["nom"] for a in liste() if a["id"] == ident)
    donnees.mkdir(parents=True, exist_ok=True)
    (donnees / "visage.json").write_text(json.dumps({"id": ident, "nom": nom}, ensure_ascii=False), encoding="utf-8")
    if not jeton:
        return {"ok": True, "message": f"{nom} est enregistré(e). La photo du bot sera posée une fois le bot Telegram ajouté."}
    photo, appel = _photo_bot(jeton, jpg), _nom_bot(jeton, nom)
    soucis = [r.get("description", "?") for r in (photo, appel) if not r.get("ok")]
    if soucis:
        return {"ok": True, "message": f"{nom} est enregistré(e), mais Telegram a refusé : {' ; '.join(soucis)}"}
    return {"ok": True, "message": f"C'est fait : le bot s'appelle {nom} et a sa nouvelle photo dans Telegram."}
