import sys
from pathlib import Path

import pytest

from agent.connecteurs_mcp import ConnecteursMCP
from agent.orchestrateur import traiter
from agent.telegram import Pont
from tests.test_agent import ClaudeScripte, Logiciel, TelegramFactice

SERVEUR = str(Path(__file__).parent / "serveur_mcp_test.py")


@pytest.fixture(scope="module")
def connecteurs():
    c = ConnecteursMCP({
        "mail": {"commande": sys.executable, "args": [SERVEUR]},
        "panne": {"commande": "commande-qui-n-existe-pas"},
    })
    yield c
    c.fermer()


def test_decouverte_et_classement(connecteurs):
    outils = connecteurs.outils()
    assert outils["mail__chercher_mails"].ecriture is False  # déclaré en lecture seule
    assert outils["mail__envoyer_mail"].ecriture is True     # rien déclaré : confirmation exigée
    assert "requete" in outils["mail__chercher_mails"].definition()["input_schema"]["properties"]
    assert "panne : HORS SERVICE" in connecteurs.etat() and "mail : 2 outils" in connecteurs.etat()
    assert "accord PEC Almerys" in outils["mail__chercher_mails"].executer(requete="PEC")


def test_mail_envoye_seulement_apres_confirmation(connecteurs):
    tg = TelegramFactice()
    etapes = [
        [("mail__chercher_mails", {"requete": "rejets"})],
        [("mail__envoyer_mail", {"destinataire": "compta@magasin.fr", "sujet": "Rejet Viamedis"})],
        "Rejet trouvé, mail préparé.",
    ]
    pont = Pont(tg, membres={11}, destination=Logiciel(), connecteurs=connecteurs,
                traiter_demande=lambda d, o: traiter(d, o, ClaudeScripte(etapes)))
    pont.traiter_update({"message": {"message_id": 1, "from": {"id": 11}, "chat": {"id": 5}, "text": "Préviens la compta des rejets"}})
    assert "envoyé" not in " ".join(tg.textes())
    assert "mail__envoyer_mail" in tg.textes()[-1]
    action_id = next(iter(pont.actions))
    pont.traiter_update({"callback_query": {"id": "c", "from": {"id": 11}, "data": f"ok:{action_id}"}})
    assert "Mail « Rejet Viamedis » envoyé à compta@magasin.fr" in tg.textes()[-1]


def test_connecteur_gmail_optizien():
    racine = str(Path(__file__).resolve().parent.parent)
    c = ConnecteursMCP({"gmail": {"commande": sys.executable, "args": ["-m", "connecteurs.gmail_mcp"],
                                  "env": {"GMAIL_FAUX": "1", "PYTHONPATH": racine}}})
    try:
        assert "gmail : 5 outils" in c.etat(), c.etat()
        outils = c.outils()
        assert not outils["gmail__chercher_mails"].ecriture and not outils["gmail__lire_mail"].ecriture
        assert outils["gmail__envoyer_mail"].ecriture and outils["gmail__creer_brouillon"].ecriture
        assert "Rejet facture 456" in outils["gmail__chercher_mails"].executer(requete="viamedis")
        assert "accord.pdf" in outils["gmail__lire_mail"].executer(mail_id="m1")
    finally:
        c.fermer()


def test_lecture_gmail_reelle_sur_reponse_simulee():
    import base64
    from connecteurs.gmail_mcp import BoiteGmail

    class Appel:
        def __init__(self, r): self.r = r
        def execute(self): return self.r

    class Messages:
        def get(self, **kw):
            corps = base64.urlsafe_b64encode("Accord de 180 €".encode()).decode()
            return Appel({"snippet": "Accord", "payload": {"headers": [{"name": "From", "value": "pec@almerys.fr"}, {"name": "Subject", "value": "Accord PEC"}],
                          "parts": [{"mimeType": "text/plain", "body": {"data": corps}}, {"filename": "accord.pdf", "mimeType": "application/pdf", "body": {}}]}})

    boite = BoiteGmail.__new__(BoiteGmail)
    boite.api = type("Api", (), {"messages": lambda self: Messages()})()
    lu = boite.lire("x")
    assert lu["texte"] == "Accord de 180 €" and lu["pieces_jointes"] == ["accord.pdf"] and lu["de"] == "pec@almerys.fr"
