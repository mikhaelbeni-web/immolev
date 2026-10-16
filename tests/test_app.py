from datetime import date

from fastapi.testclient import TestClient

import app as module_app
from ordonnance.destination import LogicielNonConfigure
from ordonnance.schema import Oeil, Ordonnance

FAUSSE = Ordonnance(
    patient_nom="DUPONT", prescripteur_nom="Dr Martin", date_prescription=date(2026, 3, 1),
    patient_date_naissance=date(1990, 5, 2), od=Oeil(sphere=-2.25), og=Oeil(sphere=-2.0, cylindre=-0.5),
)


class LogicielFactice:
    def __init__(self):
        self.recues = []

    def envoyer(self, ordo):
        self.recues.append(ordo)
        return "CLI-42"


def test_parcours(caplog):
    logiciel = LogicielFactice()
    module_app.app.state.extracteur = lambda image, media: FAUSSE
    module_app.app.state.destination = logiciel
    c = TestClient(module_app.app)
    r = c.post("/extraire", files={"photo": ("o.jpg", b"x", "image/jpeg")})
    assert "og.axe" in r.text  # cylindre sans axe signalé
    r = c.post("/valider", data={"donnees": FAUSSE.model_dump_json()})
    assert "Relecture" in r.text and not logiciel.recues  # bloqué, rien envoyé
    corrigee = FAUSSE.model_copy(update={"og": Oeil(sphere=-2.0, cylindre=-0.5, axe=90)})
    with caplog.at_level("INFO", logger="optizien.journal"):
        r = c.post("/valider", data={"donnees": corrigee.model_dump_json()})
    assert "CLI-42" in r.text and logiciel.recues == [corrigee]
    assert "DUPONT" not in caplog.text and "CLI-42" in caplog.text  # journal sans donnée patient


def test_logiciel_non_configure_ne_perd_rien():
    module_app.app.state.destination = LogicielNonConfigure()
    corrigee = FAUSSE.model_copy(update={"og": Oeil(sphere=-2.0, cylindre=-0.5, axe=90)})
    r = TestClient(module_app.app).post("/valider", data={"donnees": corrigee.model_dump_json()})
    assert "Non envoyée" in r.text
