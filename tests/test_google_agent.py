"""Carte « Compte Google de l'agent » : Chrome ordinaire sur le profil de l'agent, agent arrêté puis relancé."""
import pytest

from panneau import __main__ as pan


def _etat(tmp_path, monkeypatch, en_marche):
    monkeypatch.setattr(pan, "DONNEES", tmp_path)
    journal = []
    monkeypatch.setattr(pan.systeme, "ouvrir_chrome_profil", lambda url, profil: journal.append(("chrome", url, profil.name)))
    e = pan.Etat.__new__(pan.Etat)
    e.agent = lambda: {"en_marche": en_marche}
    e.arreter_agent = lambda: journal.append("arret")
    e.demarrer_agent = lambda: journal.append("demarrage")
    e.pret = lambda: []
    return e, journal


def test_connexion_google_arrete_puis_relance_l_agent(tmp_path, monkeypatch):
    e, journal = _etat(tmp_path, monkeypatch, True)
    monkeypatch.setattr(pan.time, "sleep", lambda s: None)
    monkeypatch.setattr(pan.systeme, "profil_utilise", lambda p: False)
    e.ouvrir_google_agent()
    assert journal == ["arret", ("chrome", "https://accounts.google.com/", "chrome-agent")]
    assert e.google_agent() == {"fait": False, "ouvert": True, "relancer": True}
    e.terminer_google_agent()
    assert journal[-1] == "demarrage" and e.google_agent()["fait"] is True and not e.google_agent()["ouvert"]


def test_terminer_refuse_tant_que_la_fenetre_chrome_est_ouverte(tmp_path, monkeypatch):
    e, journal = _etat(tmp_path, monkeypatch, False)
    e.ouvrir_google_agent()
    monkeypatch.setattr(pan.systeme, "profil_utilise", lambda p: True)
    with pytest.raises(ValueError, match="Fermez d'abord"):
        e.terminer_google_agent()
    assert "demarrage" not in journal and not e.google_agent()["fait"]


def test_consigne_dit_si_google_est_connecte(tmp_path, monkeypatch):
    from agent import acces, orchestrateur
    monkeypatch.setattr(acces, "dossier_donnees", lambda: tmp_path)
    assert "aucun compte Google" in orchestrateur.google_agent() and "Compte Google de l'agent" in orchestrateur.google_agent()
    (tmp_path / "google-agent.json").write_text('{"fait": true}')
    assert "connecté à un compte Google" in orchestrateur.google_agent()
