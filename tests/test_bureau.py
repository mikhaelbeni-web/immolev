from agent import bureau, telegram
from agent.orchestrateur import ActionEnAttente, Resultat
from agent.telegram import Pont
from tests.test_agent import TelegramFactice


def _pont(tmp_path, monkeypatch, traiter):
    monkeypatch.setattr(telegram, "dossier_donnees", lambda: tmp_path)
    tg = TelegramFactice()
    return Pont(tg, membres={11}, traiter_demande=traiter, bureau=bureau.Bureau(tmp_path)), tg


def _passer(pont):
    for u in pont.bureau.nouvelles():
        pont.traiter_update(u)


def test_demande_du_panneau_traitee_en_prive_sans_telegram(tmp_path, monkeypatch):
    vues = []
    pont, tg = _pont(tmp_path, monkeypatch, lambda d, o: vues.append(d) or Resultat("Trois loyers impayés."))
    bureau.envoyer(tmp_path, "Liste les loyers impayés")
    _passer(pont)
    assert "Conversation : privée" in vues[0] and "Liste les loyers impayés" in vues[0]
    assert tg.envois == []  # rien ne part sur Telegram
    fil = bureau.conversation(tmp_path)
    assert [(m["de"], m["texte"]) for m in fil] == [("moi", "Liste les loyers impayés"), ("agent", "Trois loyers impayés.")]
    _passer(pont)
    assert len(vues) == 1  # une demande n'est lue qu'une fois


def test_confirmation_depuis_le_panneau(tmp_path, monkeypatch):
    executees = []
    pont, tg = _pont(tmp_path, monkeypatch, lambda d, o: Resultat("Je prépare le mail.", [ActionEnAttente("a1", "creer_brouillon", {"sujet": "x"})]))
    monkeypatch.setattr(telegram, "executer_confirmee", lambda a, o: executees.append(a.id) or "Brouillon créé.")
    bureau.envoyer(tmp_path, "Prépare un mail")
    _passer(pont)
    fil = bureau.conversation(tmp_path)
    assert fil[-1]["action"] == "a1" and fil[-1]["choix"] is None
    bureau.envoyer(tmp_path, bouton="ok:a1")
    _passer(pont)
    fil = bureau.conversation(tmp_path)
    assert executees == ["a1"] and fil[-1]["texte"] == "Brouillon créé."
    assert [m for m in fil if m.get("action") == "a1"][0]["choix"] == "ok" and tg.envois == []


def test_demandes_ecrites_avant_le_demarrage_ignorees_et_bouton_controle(tmp_path, monkeypatch):
    bureau.envoyer(tmp_path, "ancienne")
    pont, _ = _pont(tmp_path, monkeypatch, lambda d, o: Resultat("x"))
    assert pont.bureau.nouvelles() == []
    try:
        bureau.envoyer(tmp_path, bouton="ok:a1\nautre")
        assert False
    except ValueError:
        pass
