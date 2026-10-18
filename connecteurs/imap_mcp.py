"""Serveur MCP « mail par code » : IMAP + SMTP avec un mot de passe d'application.

Le plus simple pour le gestionnaire : adresse + code de 16 caractères (Gmail : myaccount.google.com/apppasswords,
validation en 2 étapes requise). Marche aussi pour Orange, Free, SFR, OVH, Yahoo, iCloud…
Plusieurs boîtes dans un seul serveur, paramètre « compte » dans chaque outil.
Les codes sont dans le coffre Windows (service immolev, clé MAIL:<adresse>), jamais dans un fichier.

    python -m connecteurs.imap_mcp --comptes a@gmail.com,b@orange.fr
"""
from __future__ import annotations

import email
import email.header
import email.policy
import imaplib
import json
import re
import smtplib
import ssl
import sys
import time
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

SERVICE_COFFRE = "immolev"

# domaine → (serveur IMAP, serveur SMTP SSL)
SERVEURS = {
    "gmail.com": ("imap.gmail.com", "smtp.gmail.com"), "googlemail.com": ("imap.gmail.com", "smtp.gmail.com"),
    "orange.fr": ("imap.orange.fr", "smtp.orange.fr"), "wanadoo.fr": ("imap.orange.fr", "smtp.orange.fr"),
    "free.fr": ("imap.free.fr", "smtp.free.fr"), "sfr.fr": ("imap.sfr.fr", "smtp.sfr.fr"),
    "laposte.net": ("imap.laposte.net", "smtp.laposte.net"), "yahoo.fr": ("imap.mail.yahoo.com", "smtp.mail.yahoo.com"),
    "yahoo.com": ("imap.mail.yahoo.com", "smtp.mail.yahoo.com"), "icloud.com": ("imap.mail.me.com", "smtp.mail.me.com"),
}


def cle(adresse: str) -> str:
    return f"MAIL:{adresse.lower()}"


def serveurs_pour(adresse: str) -> tuple[str, str] | None:
    return SERVEURS.get(adresse.rsplit("@", 1)[-1].lower())


def _decoder(valeur: str | None) -> str:
    return str(email.header.make_header(email.header.decode_header(valeur or ""))) if valeur else ""


class BoiteImap:
    def __init__(self, adresse: str, mot_de_passe: str, imap: str, smtp: str):
        self.adresse, self.mdp, self.hote_imap, self.hote_smtp = adresse, mot_de_passe, imap, smtp
        self.gmail = imap == "imap.gmail.com"

    def _imap(self) -> imaplib.IMAP4_SSL:
        c = imaplib.IMAP4_SSL(self.hote_imap, 993, ssl_context=ssl.create_default_context(), timeout=30)
        c.login(self.adresse, self.mdp)
        return c

    def tester(self) -> None:
        c = self._imap()
        c.logout()

    def _dossier(self, c: imaplib.IMAP4_SSL, drapeau: str) -> str | None:
        _, lignes = c.list()
        for brut in lignes or []:
            ligne = brut.decode(errors="replace")
            if drapeau in ligne:
                return ligne.rsplit(' "/" ', 1)[-1].strip() if ' "/" ' in ligne else ligne.split()[-1]
        return None

    def chercher(self, requete: str, nombre: int) -> list[dict]:
        c = self._imap()
        try:
            dossier = (self._dossier(c, "\\All") if self.gmail else None) or "INBOX"
            c.select(dossier, readonly=True)
            if self.gmail:  # syntaxe de recherche Gmail complète (from:, newer_than:, has:attachment…)
                _, d = c.uid("SEARCH", None, "X-GM-RAW", '"' + (requete.replace('"', "") or "in:inbox") + '"')
            elif requete.strip():
                c.literal = requete.encode("utf-8")
                _, d = c.uid("SEARCH", "CHARSET", "UTF-8", "TEXT")
            else:
                _, d = c.uid("SEARCH", None, "ALL")
            uids = (d[0] or b"").split()[-nombre:][::-1]
            res = []
            for uid in uids:
                _, f = c.uid("FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
                m = email.message_from_bytes(f[0][1]) if f and f[0] else {}
                res.append({"id": f"{dossier}:{uid.decode()}", "de": _decoder(m.get("From")), "sujet": _decoder(m.get("Subject")),
                            "date": m.get("Date", "")})
            return res
        finally:
            c.logout()

    def lire(self, mail_id: str) -> dict:
        dossier, _, uid = mail_id.rpartition(":")
        c = self._imap()
        try:
            c.select(dossier or "INBOX", readonly=True)
            _, f = c.uid("FETCH", uid, "(BODY.PEEK[])")
            if not f or not f[0] or not isinstance(f[0], tuple):
                raise LookupError(f"Mail {mail_id} introuvable")
            m = email.message_from_bytes(f[0][1], policy=email.policy.default)
            corps = m.get_body(preferencelist=("plain", "html"))
            texte = corps.get_content() if corps else ""
            if corps is not None and corps.get_content_type() == "text/html":
                texte = re.sub(r"<[^>]+>", " ", texte)
            pieces = [p.get_filename() for p in m.iter_attachments() if p.get_filename()]
            return {"de": str(m["From"] or ""), "sujet": str(m["Subject"] or ""), "date": str(m["Date"] or ""),
                    "texte": re.sub(r"\s+\n", "\n", texte)[:8000], "pieces_jointes": pieces}
        finally:
            c.logout()

    def _message(self, destinataire: str, sujet: str, texte: str) -> EmailMessage:
        m = EmailMessage()
        m["From"], m["To"], m["Subject"] = self.adresse, destinataire, sujet
        m["Date"], m["Message-ID"] = formatdate(localtime=True), make_msgid()
        m.set_content(texte)
        return m

    def brouillon(self, destinataire: str, sujet: str, texte: str) -> str:
        c = self._imap()
        try:
            dossier = self._dossier(c, "\\Drafts") or "Drafts"
            c.append(dossier, "\\Draft", imaplib.Time2Internaldate(time.time()), self._message(destinataire, sujet, texte).as_bytes())
            return dossier
        finally:
            c.logout()

    def envoyer(self, destinataire: str, sujet: str, texte: str) -> str:
        m = self._message(destinataire, sujet, texte)
        with smtplib.SMTP_SSL(self.hote_smtp, 465, context=ssl.create_default_context(), timeout=30) as s:
            s.login(self.adresse, self.mdp)
            s.send_message(m)
        return m["Message-ID"]


def charger(adresse: str) -> BoiteImap:
    from agent import coffre as keyring
    brut = keyring.get_password(SERVICE_COFFRE, cle(adresse))
    if not brut:
        raise SystemExit(f"Boîte {adresse} absente du coffre : l'ajouter dans le panneau Immolev")
    d = json.loads(brut)
    return BoiteImap(adresse, d["mot_de_passe"], d["imap"], d["smtp"])


def enregistrer(adresse: str, mot_de_passe: str, imap: str = "", smtp: str = "") -> BoiteImap:
    """Teste la connexion puis range le code dans le coffre. Lève ValueError avec un message clair."""
    from agent import coffre as keyring
    adresse = adresse.strip().lower()
    mot_de_passe = mot_de_passe.replace(" ", "").strip() if serveurs_pour(adresse) == SERVEURS["gmail.com"] else mot_de_passe.strip()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", adresse):
        raise ValueError("Adresse mail invalide.")
    if adresse.endswith(("@hotmail.com", "@hotmail.fr", "@outlook.com", "@outlook.fr", "@live.fr", "@live.com")):
        raise ValueError("Microsoft n'accepte plus les codes pour Hotmail / Outlook : utilisez « Ajouter une boîte Outlook / Hotmail ».")
    if not (imap and smtp):
        connus = serveurs_pour(adresse)
        if not connus:
            raise ValueError("Fournisseur inconnu : indiquez les serveurs IMAP et SMTP (dans « Autre fournisseur »).")
        imap, smtp = connus
    boite = BoiteImap(adresse, mot_de_passe, imap, smtp)
    try:
        boite.tester()
    except imaplib.IMAP4.error:
        aide = (" Pour Gmail : activez la validation en 2 étapes, puis créez un mot de passe d'application sur "
                "myaccount.google.com/apppasswords (pas votre mot de passe Gmail habituel).") if imap == "imap.gmail.com" else ""
        raise ValueError("Adresse ou code refusé par la messagerie." + aide) from None
    except OSError as e:
        raise ValueError(f"Serveur de messagerie injoignable ({e}).") from None
    keyring.set_password(SERVICE_COFFRE, cle(adresse), json.dumps({"mot_de_passe": mot_de_passe, "imap": imap, "smtp": smtp}))
    return boite


if __name__ == "__main__":
    from connecteurs.gmail_mcp import creer_serveur  # mêmes outils : comptes, chercher, lire, brouillon, envoyer
    comptes = sys.argv[sys.argv.index("--comptes") + 1].split(",") if "--comptes" in sys.argv else []
    if not comptes:
        raise SystemExit("Aucune boîte : l'ajouter dans le panneau Immolev")
    serveur = creer_serveur({c: charger(c) for c in comptes if c}, nom="mail")
    serveur.run()
