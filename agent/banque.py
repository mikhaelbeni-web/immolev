"""Banque en lecture seule (DSP2) par Enable Banking, comme dans TIBS : relevé des opérations des comptes des sociétés.

- L'application Enable Banking du gestionnaire (identifiant + clé privée .pem) est gardée dans le coffre Windows
  (service « immolev », nom ENABLEBANKING) ; elle est saisie dans le panneau, jamais dans la discussion.
- Connexion d'une société : le panneau ouvre la page de la banque (CIC). Le gestionnaire s'y identifie ; la banque
  renvoie vers https://immolev.vercel.app/banque/retour, qui renvoie le code au panneau de ce PC (port dans « state »).
- Les sessions (une par société, valables jusqu'à 180 jours) sont dans banque.json ; les opérations relevées dans
  banque-operations.json. Aucun identifiant bancaire ne passe par Immolev.
- Verrou : seuls les appels de lecture listés dans APPELS_LECTURE peuvent partir. Aucun paiement ni virement possible.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

API = "https://api.enablebanking.com"
RETOUR = "https://immolev.vercel.app/banque/retour"
SERVICE, NOM_COFFRE = "immolev", "ENABLEBANKING"
FICHIER, OPERATIONS = "banque.json", "banque-operations.json"
JOUR = 86400
SOCIETES = ["LM INVEST", "MIKALEVINVEST", "MILEV INVEST"]

APPELS_LECTURE = [
    ("GET", re.compile(r"^/aspsps(\?|$)")),
    ("POST", re.compile(r"^/auth$")),
    ("POST", re.compile(r"^/sessions$")),
    ("GET", re.compile(r"^/sessions/[\w-]+$")),
    ("DELETE", re.compile(r"^/sessions/[\w-]+$")),
    ("GET", re.compile(r"^/accounts/[\w-]+/(transactions|balances|details)(\?|$)")),
]


class BanqueNonConfiguree(RuntimeError):
    pass


class AccesExpire(RuntimeError):
    pass


def appel_lecture_seule(methode: str, chemin: str) -> bool:
    if re.search(r"payment|transfer|virement|beneficiar", chemin, re.I):
        return False
    return any(m == methode.upper() and r.search(chemin) for m, r in APPELS_LECTURE)


# ---------------------------------------------------------------- fichiers

def _lire(f: Path, defaut: Any) -> Any:
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defaut


def _ecrire(f: Path, donnees: Any) -> None:
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(donnees, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(f)


def etat(dossier: Path) -> dict[str, Any]:
    return _lire(Path(dossier) / FICHIER, {"sessions": {}, "en_attente": {}})


def iban_masque(iban: str | None) -> str:
    s = re.sub(r"\s+", "", iban or "")
    return f"{s[:4]} •••• {s[-4:]}" if s else ""


def societe_normale(nom: str) -> str:
    n = re.sub(r"[^A-Z]", "", (nom or "").upper())
    for s in SOCIETES:
        if re.sub(r"[^A-Z]", "", s) == n:
            return s
    raise ValueError(f"Société inconnue : {nom}. Sociétés : {', '.join(SOCIETES)}.")


# ---------------------------------------------------------------- application Enable Banking

def enregistrer_application(app_id: str, pem: str, coffre: Any = None) -> None:
    """Contrôle la clé (lisible, RSA) puis la range dans le coffre Windows."""
    from cryptography.hazmat.primitives import serialization
    app_id, pem = (app_id or "").strip(), (pem or "").strip()
    if not re.fullmatch(r"[0-9a-fA-F-]{20,}", app_id):
        raise ValueError("Identifiant d'application Enable Banking invalide (il ressemble à 1a2b3c4d-…).")
    if "BEGIN" not in pem:
        try:
            pem = base64.b64decode(pem).decode("ascii")
        except Exception:
            raise ValueError("Collez tout le contenu du fichier .pem, de -----BEGIN à END-----.") from None
    try:
        serialization.load_pem_private_key(pem.encode(), password=None)
    except Exception as e:
        raise ValueError(f"Clé privée illisible ({str(e)[:80]}) : recollez tout le fichier .pem.") from None
    if coffre is None:
        from . import coffre as coffre_mod
        coffre = coffre_mod
    coffre.set_password(SERVICE, NOM_COFFRE, json.dumps({"app_id": app_id, "pem": pem}))


def application(coffre: Any = None) -> dict[str, str] | None:
    if coffre is None:
        from . import coffre as coffre_mod
        coffre = coffre_mod
    try:
        brut = coffre.get_password(SERVICE, NOM_COFFRE)
        return json.loads(brut) if brut else None
    except Exception:
        return None


def _b64(d: bytes) -> str:
    return base64.urlsafe_b64encode(d).rstrip(b"=").decode("ascii")


def jeton(app: dict[str, str], maintenant: float | None = None) -> str:
    """JWT RS256 attendu par Enable Banking (kid = identifiant de l'application)."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    t = int(maintenant if maintenant is not None else time.time())
    entete = {"typ": "JWT", "alg": "RS256", "kid": app["app_id"]}
    corps = {"iss": "enablebanking.com", "aud": "api.enablebanking.com", "iat": t, "exp": t + 3600}
    signe = _b64(json.dumps(entete, separators=(",", ":")).encode()) + "." + _b64(json.dumps(corps, separators=(",", ":")).encode())
    cle = serialization.load_pem_private_key(app["pem"].encode(), password=None)
    return signe + "." + _b64(cle.sign(signe.encode(), padding.PKCS1v15(), hashes.SHA256()))


class Client:
    def __init__(self, app: dict[str, str] | None = None, http: httpx.Client | None = None):
        self.app = app or application()
        if not self.app:
            raise BanqueNonConfiguree("Banque non configurée : collez l'application Enable Banking dans le panneau (carte Banque).")
        self.http = http or httpx.Client(timeout=60, follow_redirects=False)

    def appel(self, methode: str, chemin: str, corps: dict | None = None) -> dict[str, Any]:
        if not appel_lecture_seule(methode, chemin):
            raise PermissionError(f"Appel bancaire refusé (lecture seule) : {methode} {chemin.split('?')[0]}")
        r = self.http.request(methode, API + chemin, json=corps,
                              headers={"Authorization": f"Bearer {jeton(self.app)}", "Accept": "application/json"})
        try:
            rep = r.json() if r.content else {}
        except ValueError:
            rep = {}
        if r.status_code >= 400:
            msg = str(rep.get("message") or rep.get("error") or rep.get("detail") or r.status_code)
            if (r.status_code in (401, 403) or re.search(r"expired|invalid session|revoked|closed", msg, re.I)) \
                    and chemin.startswith(("/accounts", "/sessions/")):
                raise AccesExpire("Accès bancaire expiré ou révoqué : reconnectez la banque dans le panneau.")
            raise RuntimeError(f"Banque (Enable Banking) : {msg}")
        return rep

    def banques(self) -> list[dict[str, Any]]:
        return self.appel("GET", "/aspsps?country=FR&service=AIS").get("aspsps", [])

    def operations(self, compte: str, depuis: str, pages: int = 30) -> list[dict[str, Any]]:
        sortie, suite = [], None
        for _ in range(pages):
            q = f"date_from={depuis}" + (f"&continuation_key={suite}" if suite else "")
            r = self.appel("GET", f"/accounts/{compte}/transactions?{q}")
            sortie += r.get("transactions") or []
            suite = r.get("continuation_key")
            if not suite:
                break
        return sortie


def choisir_banque(liste: list[dict[str, Any]], nom: str = "CIC") -> dict[str, Any]:
    exacts = [b for b in liste if b.get("name", "").strip().upper() == nom.upper()]
    proches = [b for b in liste if b.get("name", "").upper().startswith(nom.upper())]
    if exacts or len(proches) == 1:
        return (exacts or proches)[0]
    raise ValueError(f"Banque « {nom} » introuvable ou ambiguë : " + ", ".join(b.get("name", "?") for b in proches[:10]))


# ---------------------------------------------------------------- connexion d'une société

def lien_connexion(dossier: Path, societe: str, port: int, client: Client | None = None, banque: str = "CIC") -> str:
    """Adresse de la page de la banque. state = « port.nonce » : la page de retour renvoie le code au panneau."""
    societe = societe_normale(societe)
    client = client or Client()
    b = choisir_banque(client.banques(), banque)
    duree = min(int(b.get("maximum_consent_validity") or 90 * JOUR), 180 * JOUR) - 3600
    fin = (datetime.now(timezone.utc) + timedelta(seconds=duree)).isoformat(timespec="seconds")
    nonce = secrets.token_urlsafe(18)
    r = client.appel("POST", "/auth", {"access": {"valid_until": fin}, "aspsp": {"name": b["name"], "country": "FR"},
                                      "state": f"{int(port)}.{nonce}", "redirect_url": RETOUR, "psu_type": "business",
                                      "language": "fr"})
    e = etat(dossier)
    e["en_attente"] = {k: v for k, v in e.get("en_attente", {}).items() if v["le"] > time.time() - 1800}
    e["en_attente"][hashlib.sha256(nonce.encode()).hexdigest()] = {"societe": societe, "le": time.time()}
    _ecrire(Path(dossier) / FICHIER, e)
    return r["url"]


def valider_retour(dossier: Path, code: str, state: str, client: Client | None = None) -> str:
    """Retour de la banque : ouvre la session et range les comptes de la société. Renvoie un résumé."""
    nonce = (state or "").split(".", 1)[-1]
    e = etat(dossier)
    attente = e.get("en_attente", {}).pop(hashlib.sha256(nonce.encode()).hexdigest(), None)
    if not attente or attente["le"] < time.time() - 1800:
        raise ValueError("Lien de connexion inconnu ou expiré (30 minutes) : relancez la connexion depuis le panneau.")
    client = client or Client()
    s = client.appel("POST", "/sessions", {"code": code})
    comptes = [{"uid": c["uid"], "nom": c.get("name") or c.get("product") or "", "iban": iban_masque((c.get("account_id") or {}).get("iban"))}
               for c in s.get("accounts", [])]
    e.setdefault("sessions", {})[attente["societe"]] = {
        "session_id": s["session_id"], "banque": (s.get("aspsp") or {}).get("name", ""), "comptes": comptes,
        "valable_jusqu": (s.get("access") or {}).get("valid_until", ""), "connecte_le": date.today().isoformat()}
    _ecrire(Path(dossier) / FICHIER, e)
    return f"{attente['societe']} : {len(comptes)} compte(s) reliés ({', '.join(c['iban'] or c['nom'] for c in comptes)})."


def deconnecter(dossier: Path, societe: str, client: Client | None = None) -> None:
    societe = societe_normale(societe)
    e = etat(dossier)
    s = e.get("sessions", {}).pop(societe, None)
    _ecrire(Path(dossier) / FICHIER, e)
    if s:
        try:
            (client or Client()).appel("DELETE", f"/sessions/{s['session_id']}")
        except Exception:
            pass


def resume_connexions(dossier: Path, aujourd_hui: date | None = None) -> list[dict[str, Any]]:
    j = aujourd_hui or date.today()
    out = []
    for societe, s in etat(dossier).get("sessions", {}).items():
        fin = (s.get("valable_jusqu") or "")[:10]
        reste = (date.fromisoformat(fin) - j).days if fin else None
        out.append({"societe": societe, "banque": s.get("banque", ""), "comptes": [c["iban"] or c["nom"] for c in s["comptes"]],
                    "valable_jusqu": fin, "jours_restants": reste})
    return out


# ---------------------------------------------------------------- relevé des opérations

def ligne(t: dict[str, Any]) -> dict[str, Any] | None:
    """Opération comptabilisée → {date, montant (euros, + = crédit), libelle, payeur, ref}."""
    if t.get("status") and t["status"] != "BOOK":
        return None
    try:
        brut = float(str((t.get("transaction_amount") or {}).get("amount")).replace(",", "."))
    except (TypeError, ValueError):
        return None
    jour = next((d[:10] for d in (t.get("booking_date"), t.get("value_date"), t.get("transaction_date"))
                 if d and re.match(r"\d{4}-\d{2}-\d{2}", d)), None)
    if not jour:
        return None
    sens = t.get("credit_debit_indicator")
    montant = -abs(brut) if sens == "DBIT" else abs(brut) if sens == "CRDT" else brut
    payeur = ((t.get("debtor") if montant > 0 else t.get("creditor")) or {}).get("name") or ""
    libelle = " ".join(s.strip() for s in (t.get("remittance_information") or []) if s and s.strip())
    libelle = re.sub(r"\s+", " ", libelle or payeur or ((t.get("bank_transaction_code") or {}).get("description") or "")).strip()
    ref = t.get("entry_reference") or t.get("transaction_id") or \
        hashlib.sha1(f"{jour}|{montant}|{libelle}|{payeur}".encode()).hexdigest()[:16]
    return {"date": jour, "montant": round(montant, 2), "libelle": libelle, "payeur": payeur.strip(), "ref": str(ref)}


def releve(dossier: Path, client: Client | None = None, jours: int = 120,
           aujourd_hui: date | None = None) -> dict[str, Any]:
    """Relève les opérations de toutes les sociétés reliées et les ajoute à banque-operations.json (sans doublon).
    Renvoie {"nouvelles": n, "erreurs": {societe: message}, "expirees": [societes]}."""
    sessions = etat(dossier).get("sessions", {})
    f = Path(dossier) / OPERATIONS
    tout = _lire(f, [])
    connues = {(o["societe"], o["compte"], o["ref"]) for o in tout}
    depuis = ((aujourd_hui or date.today()) - timedelta(days=jours)).isoformat()
    res = {"nouvelles": 0, "erreurs": {}, "expirees": []}
    if not sessions:
        return res
    client = client or Client()
    for societe, s in sessions.items():
        try:
            for c in s["comptes"]:
                for t in client.operations(c["uid"], depuis):
                    l = ligne(t)
                    if l and (societe, c["uid"], l["ref"]) not in connues:
                        tout.append({**l, "societe": societe, "compte": c["uid"], "iban": c["iban"]})
                        connues.add((societe, c["uid"], l["ref"]))
                        res["nouvelles"] += 1
        except AccesExpire as e:
            res["expirees"].append(societe)
            res["erreurs"][societe] = str(e)
        except Exception as e:  # une société en panne n'empêche pas les autres
            res["erreurs"][societe] = str(e)[:300]
    tout.sort(key=lambda o: o["date"])
    _ecrire(f, tout)
    return res


def operations(dossier: Path) -> list[dict[str, Any]]:
    return _lire(Path(dossier) / OPERATIONS, [])
