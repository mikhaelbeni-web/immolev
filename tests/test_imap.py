import imaplib
from email.message import EmailMessage

import pytest

from connecteurs import imap_mcp


def _mail(de, sujet, texte, piece=None):
    m = EmailMessage()
    m["From"], m["Subject"], m["Date"] = de, sujet, "Wed, 15 Oct 2026 10:00:00 +0200"
    m.set_content(texte)
    if piece:
        m.add_attachment(b"%PDF", maintype="application", subtype="pdf", filename=piece)
    return m.as_bytes()


class ImapFactice:
    MAILS = {b"7": _mail("pec@almerys.fr", "Accord PEC 123", "Accord 180 EUR", "accord.pdf"),
             b"9": _mail("noreply@viamedis.fr", "Rejet facture 456", "Motif : droits fermés")}
    ajoutes = []

    def __init__(self, hote, port, ssl_context=None, timeout=None):
        self.hote = hote

    def login(self, u, p):
        if p != "abcdabcdabcdabcd":
            raise imaplib.IMAP4.error("AUTHENTICATIONFAILED")

    def list(self):
        return "OK", [b'(\\HasNoChildren \\All) "/" "[Gmail]/Tous les messages"', b'(\\Drafts) "/" "[Gmail]/Brouillons"']

    def select(self, dossier, readonly=False):
        self.dossier = dossier
        return "OK", [b"2"]

    def uid(self, commande, *args):
        if commande == "SEARCH":
            self.recherche = args
            return "OK", [b"7 9"]
        uid = args[0] if isinstance(args[0], bytes) else args[0].encode()
        return "OK", [(b"1 (UID)", self.MAILS[uid]), b")"]

    def append(self, dossier, drapeaux, date, message):
        self.ajoutes.append((dossier, message))
        return "OK", [b""]

    def logout(self):
        pass


@pytest.fixture
def boite(monkeypatch):
    monkeypatch.setattr(imap_mcp.imaplib, "IMAP4_SSL", ImapFactice)
    return imap_mcp.BoiteImap("magasin@gmail.com", "abcdabcdabcdabcd", "imap.gmail.com", "smtp.gmail.com")


def test_chercher_lire_brouillon(boite):
    res = boite.chercher("from:almerys newer_than:7d", 10)
    assert [r["sujet"] for r in res] == ["Rejet facture 456", "Accord PEC 123"]  # plus récent d'abord
    assert res[1]["id"] == '"[Gmail]/Tous les messages":7'
    mail = boite.lire(res[1]["id"])
    assert "180 EUR" in mail["texte"] and mail["pieces_jointes"] == ["accord.pdf"]
    assert boite.brouillon("pec@almerys.fr", "Relance", "Bonjour") == '"[Gmail]/Brouillons"'


def test_enregistrer_refuse_mauvais_code_et_hotmail(monkeypatch):
    monkeypatch.setattr(imap_mcp.imaplib, "IMAP4_SSL", ImapFactice)
    with pytest.raises(ValueError, match="apppasswords"):
        imap_mcp.enregistrer("magasin@gmail.com", "mauvais")
    with pytest.raises(ValueError, match="Outlook / Hotmail"):
        imap_mcp.enregistrer("magasin@hotmail.fr", "x")
    with pytest.raises(ValueError, match="Fournisseur inconnu"):
        imap_mcp.enregistrer("contact@opticien-levallois.fr", "x")
