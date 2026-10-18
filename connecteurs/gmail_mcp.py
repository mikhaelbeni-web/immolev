"""Serveur MCP Gmail d'Immolev (API Gmail officielle, OAuth). Lecture libre, brouillon et envoi sur confirmation.

Plusieurs boîtes : un seul serveur, un paramètre « compte » dans chaque outil.
    python -m connecteurs.gmail_mcp --comptes a@gmail.com,b@gmail.com
Les comptes s'ajoutent depuis le panneau Immolev (connexion()) ; chaque jeton OAuth est rangé dans
le coffre de Windows sous GMAIL_JETON:<adresse>, jamais dans un fichier.
Prérequis : un client OAuth « Application de bureau » Google Cloud (fichier JSON importé dans le panneau).
"""
from __future__ import annotations

import base64
import json
import os
import sys
from email.message import EmailMessage
from typing import Any, Protocol

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

PORTEES = ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.compose"]
SERVICE_COFFRE = "immolev"


def cle_jeton(adresse: str) -> str:
    return f"GMAIL_JETON:{adresse.lower()}"


class Boite(Protocol):
    def chercher(self, requete: str, nombre: int) -> list[dict[str, str]]: ...
    def lire(self, mail_id: str) -> dict[str, Any]: ...
    def brouillon(self, destinataire: str, sujet: str, texte: str) -> str: ...
    def envoyer(self, destinataire: str, sujet: str, texte: str) -> str: ...


def _brut(destinataire: str, sujet: str, texte: str) -> str:
    m = EmailMessage()
    m["To"], m["Subject"] = destinataire, sujet
    m.set_content(texte)
    return base64.urlsafe_b64encode(m.as_bytes()).decode()


class BoiteGmail:
    def __init__(self, adresse: str) -> None:
        from agent import coffre as keyring
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        jeton = keyring.get_password(SERVICE_COFFRE, cle_jeton(adresse))
        if not jeton:
            raise SystemExit(f"Gmail {adresse} non connecté : l'ajouter dans le panneau Immolev")
        cred = Credentials.from_authorized_user_info(json.loads(jeton), PORTEES)
        if cred.expired and cred.refresh_token:
            cred.refresh(Request())
            keyring.set_password(SERVICE_COFFRE, cle_jeton(adresse), cred.to_json())
        self.api = build("gmail", "v1", credentials=cred, cache_discovery=False).users()

    def chercher(self, requete: str, nombre: int) -> list[dict[str, str]]:
        ids = self.api.messages().list(userId="me", q=requete, maxResults=nombre).execute().get("messages", [])
        resultats = []
        for m in ids:
            d = self.api.messages().get(userId="me", id=m["id"], format="metadata", metadataHeaders=["From", "Subject", "Date"]).execute()
            entetes = {h["name"]: h["value"] for h in d["payload"].get("headers", [])}
            resultats.append({"id": m["id"], "de": entetes.get("From", ""), "sujet": entetes.get("Subject", ""),
                              "date": entetes.get("Date", ""), "extrait": d.get("snippet", "")})
        return resultats

    def lire(self, mail_id: str) -> dict[str, Any]:
        d = self.api.messages().get(userId="me", id=mail_id, format="full").execute()
        entetes = {h["name"]: h["value"] for h in d["payload"].get("headers", [])}
        textes, pieces = [], []

        def parcourir(partie: dict[str, Any]) -> None:
            if partie.get("filename"):
                pieces.append(partie["filename"])
            elif partie.get("mimeType") == "text/plain" and partie.get("body", {}).get("data"):
                textes.append(base64.urlsafe_b64decode(partie["body"]["data"]).decode("utf-8", "replace"))
            for p in partie.get("parts", []):
                parcourir(p)

        parcourir(d["payload"])
        return {"de": entetes.get("From", ""), "sujet": entetes.get("Subject", ""), "date": entetes.get("Date", ""),
                "texte": "\n".join(textes)[:8000] or d.get("snippet", ""), "pieces_jointes": pieces}

    def brouillon(self, destinataire: str, sujet: str, texte: str) -> str:
        d = self.api.drafts().create(userId="me", body={"message": {"raw": _brut(destinataire, sujet, texte)}}).execute()
        return d["id"]

    def envoyer(self, destinataire: str, sujet: str, texte: str) -> str:
        return self.api.messages().send(userId="me", body={"raw": _brut(destinataire, sujet, texte)}).execute()["id"]


class BoiteFactice:
    """Pour les tests et les démonstrations, sans compte Google."""

    def __init__(self) -> None:
        self.mails = {"m1": {"de": "pec@almerys.fr", "sujet": "Accord PEC 123", "date": "15 Oct 2026", "texte": "Accord 180 EUR", "pieces_jointes": ["accord.pdf"]},
                      "m2": {"de": "noreply@viamedis.fr", "sujet": "Rejet facture 456", "date": "14 Oct 2026", "texte": "Motif : droits fermés", "pieces_jointes": []}}
        self.envoyes: list[str] = []

    def chercher(self, requete: str, nombre: int) -> list[dict[str, str]]:
        return [{"id": i, **{k: m[k] for k in ("de", "sujet", "date")}, "extrait": m["texte"][:80]}
                for i, m in self.mails.items() if requete.lower() in json.dumps(m, ensure_ascii=False).lower()][:nombre]

    def lire(self, mail_id: str) -> dict[str, Any]:
        return self.mails[mail_id]

    def brouillon(self, destinataire: str, sujet: str, texte: str) -> str:
        return "brouillon-1"

    def envoyer(self, destinataire: str, sujet: str, texte: str) -> str:
        self.envoyes.append(sujet)
        return f"envoi-{len(self.envoyes)}"


def creer_serveur(boites: "Boite | dict[str, Boite]", nom: str = "gmail") -> MCPServer:
    if not isinstance(boites, dict):
        boites = {"magasin": boites}
    serveur = MCPServer(f"{nom}-immolev")
    lecture = ToolAnnotations(read_only_hint=True)
    noms = ", ".join(boites)

    def boite(compte: str) -> Boite:
        if not compte:
            return next(iter(boites.values()))
        for nom, b in boites.items():
            if compte.lower() in nom.lower():
                return b
        raise ValueError(f"Compte Gmail inconnu : {compte}. Comptes : {noms}")

    @serveur.tool(annotations=lecture)
    def comptes() -> str:
        """Liste les boîtes mail branchées (la première est utilisée si « compte » est vide)."""
        return noms

    @serveur.tool(annotations=lecture)
    def chercher_mails(requete: str, nombre: int = 10, compte: str = "") -> str:
        """Cherche des mails (boîte Gmail : syntaxe Gmail, ex. 'from:almerys newer_than:7d' ; autre boîte : un mot du mail). compte : adresse de la boîte."""
        return json.dumps(boite(compte).chercher(requete, min(nombre, 50)), ensure_ascii=False)

    @serveur.tool(annotations=lecture)
    def lire_mail(mail_id: str, compte: str = "") -> str:
        """Lit un mail : expéditeur, sujet, date, texte, noms des pièces jointes."""
        return json.dumps(boite(compte).lire(mail_id), ensure_ascii=False)

    @serveur.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False))
    def creer_brouillon(destinataire: str, sujet: str, texte: str, compte: str = "") -> str:
        """Prépare un brouillon dans Gmail, sans l'envoyer."""
        return f"Brouillon créé ({boite(compte).brouillon(destinataire, sujet, texte)}) pour {destinataire}"

    @serveur.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False))
    def envoyer_mail(destinataire: str, sujet: str, texte: str, compte: str = "") -> str:
        """Envoie un mail depuis une boîte Gmail du gestionnaire."""
        return f"Mail « {sujet} » envoyé à {destinataire} ({boite(compte).envoyer(destinataire, sujet, texte)})"

    return serveur


def connexion(fichier_client: str) -> str:
    """Ouvre la page de consentement Google ; renvoie l'adresse de la boîte connectée."""
    from agent import coffre as keyring
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    flux = InstalledAppFlow.from_client_secrets_file(fichier_client, PORTEES)
    cred = flux.run_local_server(port=0, open_browser=True, timeout_seconds=290,
                                 success_message="Boîte Gmail connectée à Immolev. Vous pouvez fermer cet onglet.")
    adresse = build("gmail", "v1", credentials=cred, cache_discovery=False).users().getProfile(userId="me").execute()["emailAddress"]
    keyring.set_password(SERVICE_COFFRE, cle_jeton(adresse), cred.to_json())
    return adresse.lower()


if __name__ == "__main__":
    if "--connexion" in sys.argv:  # lancé par le panneau, dans un processus neuf ; résultat dans un fichier
        import json, traceback
        client, resultat = sys.argv[sys.argv.index("--connexion") + 1:][:2]
        try:
            sortie = {"adresse": connexion(client)}
        except BaseException as e:  # noqa: BLE001
            sortie = {"erreur": f"{type(e).__name__} : {e}", "trace": traceback.format_exc()}
        open(resultat, "w", encoding="utf-8").write(json.dumps(sortie))
    elif os.environ.get("GMAIL_FAUX") == "1":
        creer_serveur(BoiteFactice()).run()
    else:
        comptes = sys.argv[sys.argv.index("--comptes") + 1].split(",") if "--comptes" in sys.argv else []
        if not comptes:
            raise SystemExit("Aucune boîte Gmail : l'ajouter dans le panneau Immolev")
        creer_serveur({c: BoiteGmail(c) for c in comptes if c}).run()
