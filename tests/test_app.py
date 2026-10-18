from datetime import date

from fastapi.testclient import TestClient

import app as module_app
from document.destination import LogicielNonConfigure
from document.schema import Document

FAUSSE = Document(
    type_document="appel_de_fonds_copropriete", emetteur_nom="Syndic DUPONT", destinataire_nom="M. DURAND",
    date_document=date(2026, 3, 1), montant_ttc=None, iban="FR7630006000011234567890189",
)


class LogicielFactice:
    def __init__(self):
        self.recues = []

    def envoyer(self, doc):
        self.recues.append(doc)
        return "CLI-42"


def test_parcours(caplog):
    logiciel = LogicielFactice()
    module_app.app.state.extracteur = lambda image, media: FAUSSE
    module_app.app.state.destination = logiciel
    c = TestClient(module_app.app)
    r = c.post("/extraire", files={"photo": ("d.jpg", b"x", "image/jpeg")})
    assert "montant_ttc" in r.text  # montant à payer absent signalé
    r = c.post("/valider", data={"donnees": FAUSSE.model_dump_json()})
    assert "Relecture" in r.text and not logiciel.recues  # bloqué, rien envoyé
    corrigee = FAUSSE.model_copy(update={"montant_ttc": 1250.0})
    with caplog.at_level("INFO", logger="immolev.journal"):
        r = c.post("/valider", data={"donnees": corrigee.model_dump_json()})
    assert "CLI-42" in r.text and logiciel.recues == [corrigee]
    assert "DUPONT" not in caplog.text and "1250" not in caplog.text and "CLI-42" in caplog.text  # journal sans nom ni montant


def test_logiciel_non_configure_ne_perd_rien():
    module_app.app.state.destination = LogicielNonConfigure()
    corrigee = FAUSSE.model_copy(update={"montant_ttc": 1250.0})
    r = TestClient(module_app.app).post("/valider", data={"donnees": corrigee.model_dump_json()})
    assert "Non envoyé" in r.text
