"""Chrome de l'agent fermé à la main : l'outil le rouvre et réessaie au lieu d'échouer."""
from agent import navigateur as nv


class PageFermee:
    def __init__(self, fermee):
        self.fermee = fermee

    def is_closed(self):
        return self.fermee


def test_relance_puis_reessaie(monkeypatch):
    nav = nv.Navigateur(PageFermee(False))
    relances, appels = [], []
    monkeypatch.setattr(nav, "relancer", lambda: relances.append(1))

    def lire():
        appels.append(1)
        if len(appels) == 1:
            raise RuntimeError("Target page, context or browser has been closed")
        return "page"
    assert nv._resistant(nav, lire)() == "page" and relances == [1] and len(appels) == 2


def test_autre_erreur_remontee_sans_relance(monkeypatch):
    nav = nv.Navigateur(PageFermee(False))
    monkeypatch.setattr(nav, "relancer", lambda: (_ for _ in ()).throw(AssertionError("pas de relance")))

    def lire():
        raise ValueError("Référence #9 introuvable")
    try:
        nv._resistant(nav, lire)()
    except ValueError as e:
        assert "#9" in str(e)


def test_page_fermee_relance_avant_l_action(monkeypatch):
    nav = nv.Navigateur(PageFermee(True))
    relances = []
    monkeypatch.setattr(nav, "relancer", lambda: relances.append(1))
    assert nv._resistant(nav, lambda: "ok")() == "ok" and relances == [1]
