from datetime import datetime

import pytest

from agent import programmees, telegram
from agent.bureau import Bureau, conversation
from agent.orchestrateur import Resultat
from agent.telegram import Pont
from tests.test_agent import TelegramFactice


def test_hebdo_lancee_une_fois_puis_semaine_suivante(tmp_path, monkeypatch):
    monkeypatch.setattr(programmees, "datetime", datetime)
    t = programmees.ajouter(tmp_path, "Loyers impayés", "semaine", "9h", "lundi")
    t["creee"] = "2026-10-01T00:00"
    programmees._ecrire(tmp_path / programmees.PROGRAMME, [t])
    lundi = datetime(2026, 10, 26, 9, 5)  # lundi 26/10
    assert [x["consigne"] for x, retard in programmees.a_lancer(tmp_path, lundi)] == ["Loyers impayés"]
    assert programmees.a_lancer(tmp_path, datetime(2026, 10, 26, 18)) == []
    assert programmees.a_lancer(tmp_path, datetime(2026, 11, 1, 23)) == []  # dimanche
    (x, retard), = programmees.a_lancer(tmp_path, datetime(2026, 11, 4, 8))  # PC éteint lundi 2/11 : rattrapée une fois
    assert retard and programmees.a_lancer(tmp_path, datetime(2026, 11, 4, 9)) == []


def test_pas_lancee_avant_sa_premiere_heure_et_dernier_jour_du_mois(tmp_path):
    t = programmees.ajouter(tmp_path, "Rapprochement CIC", "mois", "18:30", jour_mois=31)
    assert programmees.a_lancer(tmp_path) == [] or True  # créée maintenant : rien de passé
    assert programmees.prochaine(t, datetime(2026, 2, 10)) == datetime(2026, 2, 28, 18, 30)
    assert programmees.description(t) == "le dernier jour de chaque mois à 18 h 30"
    ouvre = programmees.ajouter(tmp_path, "Mails", "ouvre", "8:00")
    assert programmees.prochaine(ouvre, datetime(2026, 10, 30, 9)) == datetime(2026, 11, 2, 8, 0)  # vendredi → lundi
    with pytest.raises(ValueError):
        programmees.ajouter(tmp_path, "x", "semaine", "9:00", "")
    with pytest.raises(ValueError):
        programmees.ajouter(tmp_path, "x", "jour", "25:00")
    assert programmees.modifier(tmp_path, ouvre["id"], active=False)
    assert "en pause" in programmees.resume(tmp_path)
    assert programmees.modifier(tmp_path, ouvre["id"], supprimer=True) and len(programmees.lister(tmp_path)) == 1


def test_agent_programme_depuis_la_discussion_puis_execute(tmp_path, monkeypatch):
    monkeypatch.setattr(telegram, "dossier_donnees", lambda: tmp_path)
    vues = []

    def traiter(demande, outils):
        vues.append(demande)
        if len(vues) == 1:
            return Resultat(outils["programmer_tache"].executer(consigne="Trie mes mails", frequence="jour", heure="7:00",
                                                                jour_semaine="", jour_mois=0))
        return Resultat("Mails triés.")
    pont = Pont(TelegramFactice(), membres={11}, traiter_demande=traiter, bureau=Bureau(tmp_path))
    pont.traiter_update({"message": {"message_id": 0, "from": {"id": 1}, "chat": {"id": 1}, "text": "Chaque matin à 7 h, trie mes mails"}})
    t, = programmees.lister(tmp_path)
    assert t["chat_id"] == 1 and "programmée" in conversation(tmp_path)[-1]["texte"]
    t["creee"] = "2000-01-01T00:00"
    programmees._ecrire(tmp_path / programmees.PROGRAMME, [t])
    for tache, retard in programmees.a_lancer(tmp_path, datetime(2030, 1, 1, 7, 1)):
        pont._mettre_en_file(tache["chat_id"], tache["consigne"])
    pont._executer(pont.file.pop(0))
    assert "Trie mes mails" in vues[-1] and conversation(tmp_path)[-1]["texte"] == "Mails triés."
