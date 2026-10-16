"""Connexion de l'agent à Claude par la passerelle du site Optizien.

Le magasin n'a pas de clé API : l'agent s'identifie avec le compte Optizien du magasin (coffre Windows) et le serveur
ajoute la clé Anthropic, qu'il est seul à connaître. Le SDK Anthropic lit ANTHROPIC_BASE_URL et ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

URL = "https://optizien.vercel.app/api/ia"


def environnement(compte: dict, url: str = URL) -> dict[str, str]:
    return {"ANTHROPIC_BASE_URL": url, "ANTHROPIC_API_KEY": f"{compte['identifiant']}:{compte['mot_de_passe']}"}


def ping(compte: dict, url: str = URL, timeout: int = 20) -> dict:
    """{"ok": True|False|None, "message": …} : le compte est-il accepté, le serveur a-t-il sa clé ?"""
    req = urllib.request.Request(f"{url}/ping", headers={"x-api-key": environnement(compte)["ANTHROPIC_API_KEY"]})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            rep = json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return {"ok": False, "message": "Identifiant ou mot de passe refusé par le serveur Optizien."}
        return {"ok": None, "message": f"Le serveur Optizien répond une erreur ({e.code})."}
    except (OSError, ValueError) as e:
        return {"ok": None, "message": f"Serveur Optizien injoignable : {e}"}
    if not rep.get("cle"):
        return {"ok": None, "message": "Compte accepté, mais le serveur Optizien n'a pas encore sa clé IA : prévenez Optizien."}
    return {"ok": True, "message": "Connecté : l'agent est fourni par Optizien, rien d'autre à configurer."}
