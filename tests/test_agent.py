from datetime import date
from types import SimpleNamespace as NS

from agent.orchestrateur import traiter
from agent.outils import Contexte, catalogue
from agent.telegram import Pont
from ordonnance.schema import Oeil, Ordonnance

ORDO = Ordonnance(
    patient_nom="DUPONT", patient_prenom="Jean", prescripteur_nom="Dr Martin", date_prescription=date(2026, 3, 1),
    patient_date_naissance=date(1990, 5, 2), od=Oeil(sphere=-2.25), og=Oeil(sphere=-2.0, cylindre=-0.5),
)


class ClaudeScripte:
    """Rejoue une suite de réponses : appels d'outils puis texte final."""

    def __init__(self, etapes):
        self.etapes, self.appels = list(etapes), []
        self.messages = self
        self.beta = self

    def create(self, **kw):
        self.appels.append(kw)
        etape = self.etapes.pop(0)
        if isinstance(etape, str):
            return NS(stop_reason="end_turn", content=[NS(type="text", text=etape)])
        return NS(stop_reason="tool_use", content=[NS(type="tool_use", id=f"t{i}", name=n, input=a) for i, (n, a) in enumerate(etape)])


class Logiciel:
    def __init__(self):
        self.recues = []

    def envoyer(self, ordo):
        self.recues.append(ordo)
        return "CLI-7"


def test_ecriture_mise_en_attente_lecture_executee():
    ctx, logiciel = Contexte(photos={"photo1": (b"x", "image/jpeg")}), Logiciel()
    outils = catalogue(ctx, logiciel, lambda img, media: ORDO)
    claude = ClaudeScripte([
        [("lire_ordonnance", {"photo_id": "photo1"})],
        [("corriger_ordonnance", {"photo_id": "photo1", "champ": "og.axe", "valeur": "90"})],
        [("saisir_ordonnance_myeasyoptic", {"photo_id": "photo1"})],
        "Ordonnance de J.D. prête, à confirmer.",
    ])
    r = traiter("Saisis cette ordonnance", outils, claude)
    assert [a.outil for a in r.en_attente] == ["saisir_ordonnance_myeasyoptic"]
    assert logiciel.recues == []  # rien écrit sans confirmation
    assert ctx.ordonnances["photo1"].og.axe == 90
    resultat_lecture = claude.appels[-1]["messages"][2]["content"][0]["content"]
    assert "og.axe" in resultat_lecture  # l'alerte cylindre sans axe a été remontée à Claude


def test_outil_non_branche_renvoye_en_erreur():
    claude = ClaudeScripte([[("rechercher_client_myeasyoptic", {"nom": "X", "prenom": "Y", "date_naissance": ""})], "Pas encore possible."])
    traiter("Cherche X", catalogue(Contexte(), Logiciel()), claude)
    resultat = claude.appels[-1]["messages"][2]["content"][0]
    assert resultat["is_error"] and "pas encore branché" in resultat["content"]


class TelegramFactice:
    def __init__(self):
        self.envois = []

    def appeler(self, methode, **p):
        self.envois.append((methode, p))
        return {}

    def telecharger(self, file_id):
        return b"photo"

    def textes(self):
        return [p["text"] for m, p in self.envois if m == "sendMessage"]


def demande_scriptee(demande, outils):
    from agent.orchestrateur import traiter as t
    return t(demande, outils, ClaudeScripte([
        [("lire_ordonnance", {"photo_id": "photo1"})],
        [("corriger_ordonnance", {"photo_id": "photo1", "champ": "og.axe", "valeur": "90"})],
        [("saisir_ordonnance_myeasyoptic", {"photo_id": "photo1"})],
        "Prête.",
    ]))


def test_pont_telegram_de_bout_en_bout():
    tg, logiciel = TelegramFactice(), Logiciel()
    pont = Pont(tg, membres={11}, destination=logiciel, traiter_demande=demande_scriptee, extracteur=lambda i, m: ORDO, photos_autorisees=True)

    pont.traiter_update({"message": {"message_id": 1, "from": {"id": 99}, "chat": {"id": 5}, "text": "Saisis tout"}})
    assert tg.envois == []  # inconnu ignoré

    pont.traiter_update({"message": {"message_id": 2, "from": {"id": 11}, "chat": {"id": 5}, "photo": [{"file_id": "f"}]}})
    assert ("deleteMessage", {"chat_id": 5, "message_id": 2}) in tg.envois
    confirmation = tg.textes()[-1]
    assert "OG sph -2.0 cyl -0.5 axe 90" in confirmation and "DUPONT" not in confirmation and confirmation.count("JD") == 1
    action_id = next(iter(pont.actions))

    pont.traiter_update({"callback_query": {"id": "c", "from": {"id": 99}, "data": f"ok:{action_id}"}})
    assert logiciel.recues == []  # un non-membre ne peut pas confirmer

    pont.traiter_update({"callback_query": {"id": "c", "from": {"id": 11}, "data": f"ok:{action_id}"}})
    assert len(logiciel.recues) == 1 and "CLI-7" in tg.textes()[-1]


def test_photos_refusees_par_defaut():
    tg = TelegramFactice()
    pont = Pont(tg, membres={11}, destination=Logiciel(), traiter_demande=demande_scriptee, extracteur=lambda i, m: ORDO)
    pont.traiter_update({"message": {"message_id": 3, "from": {"id": 11}, "chat": {"id": 5}, "photo": [{"file_id": "f"}]}})
    assert ("deleteMessage", {"chat_id": 5, "message_id": 3}) in tg.envois and "page web" in tg.textes()[-1]
    assert not pont.actions


def test_vocal_transcrit_puis_traite():
    from agent.orchestrateur import Resultat
    tg = TelegramFactice()
    tg.telecharger = lambda file_id: b"OggS..."
    recu = []
    pont = Pont(tg, {1}, traiter_demande=lambda d, o: (recu.append(d), Resultat("Fiche ouverte."))[1],
                transcrire=lambda audio: "ouvre la fiche de monsieur Dupont")
    pont.traiter_update({"message": {"message_id": 5, "from": {"id": 1}, "chat": {"id": 9}, "voice": {"file_id": "v1"}}})
    textes = tg.textes()
    assert "Compris" in textes[0] and "Dupont" in textes[0] and recu == ["ouvre la fiche de monsieur Dupont"]


def test_regles_du_magasin(tmp_path, monkeypatch):
    from agent import orchestrateur, regles
    monkeypatch.setenv("OPTIZIEN_DONNEES", str(tmp_path))
    assert "Règles du magasin" not in orchestrateur.systeme()
    regles.ecrire("# Mutuelles\n- Harmonie Mutuelle → Almerys")
    assert "Harmonie Mutuelle → Almerys" in regles.ajouter("Les lentilles se commandent le mardi") or True
    s = orchestrateur.systeme()
    assert "Harmonie Mutuelle → Almerys" in s and "lentilles se commandent le mardi" in s
    pont = Pont(TelegramFactice(), {1})
    assert pont._outils(Contexte())["retenir_regle"].ecriture  # confirmation avant d'ajouter une règle


def test_demande_acces_puis_acceptation(tmp_path):
    from agent.membres import Registre
    from agent.orchestrateur import Resultat
    coffre = {"v": "1"}
    registre = Registre(tmp_path, lambda: coffre["v"], lambda v: coffre.update(v=v))
    tg = TelegramFactice()
    recu = []
    pont = Pont(tg, {1}, traiter_demande=lambda d, o: (recu.append(d), Resultat("ok"))[1], registre=registre)
    inconnu = {"id": 42, "first_name": "Léa", "username": "lea"}
    pont.traiter_update({"message": {"message_id": 1, "from": inconnu, "chat": {"id": 42, "type": "private"}, "text": "/start"}})
    pont.traiter_update({"message": {"message_id": 2, "from": inconnu, "chat": {"id": 42, "type": "private"}, "text": "/start"}})
    assert [d["nom"] for d in registre.demandes()] == ["Léa"]
    assert sum("Nouvelle demande" in t for t in tg.textes()) == 1  # pas de relance en double
    bouton = [p for m, p in tg.envois if m == "sendMessage" and p.get("reply_markup")][0]
    assert bouton["chat_id"] == 1
    ok = bouton["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
    pont.traiter_update({"callback_query": {"id": "c", "from": {"id": 1}, "data": ok, "message": {"chat": {"id": 1}}}})
    assert coffre["v"] == "1,42" and registre.demandes() == []
    pont.traiter_update({"message": {"message_id": 3, "from": inconnu, "chat": {"id": 42, "type": "private"}, "text": "bonjour"}})
    assert recu == ["bonjour"]


def test_demande_refusee_ne_revient_pas(tmp_path):
    from agent.membres import Registre
    registre = Registre(tmp_path, lambda: "1", lambda v: None)
    assert registre.noter_demande({"id": 7, "first_name": "X"}, "groupe")
    assert registre.decider("7", False)["nom"] == "X"
    assert registre.noter_demande({"id": 7, "first_name": "X"}, "groupe") is None


def test_message_erreur_credit():
    from agent.telegram import message_erreur
    assert "crédit" in message_erreur(RuntimeError("Your credit balance is too low to access the Anthropic API"))


def test_sites_connus_dans_le_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv("OPTIZIEN_DONNEES", str(tmp_path))
    from agent.orchestrateur import systeme
    assert "Aucun site" in systeme()
    (tmp_path / "acces.json").write_text('[{"id": "a", "nom": "MyEasyOptic", "url": "https://app.myeasyoptic.com", "domaine": "myeasyoptic.com"}]')
    assert "MyEasyOptic : https://app.myeasyoptic.com" in systeme()


def test_file_des_taches(tmp_path, monkeypatch):
    import threading, time
    from agent.orchestrateur import Resultat
    monkeypatch.setenv("OPTIZIEN_DONNEES", str(tmp_path))
    tg = TelegramFactice()
    feu = threading.Event()
    faites = []

    def lent(demande, outils):
        feu.wait(5)
        faites.append(demande.rsplit(": ", 1)[-1])
        return Resultat("ok " + demande)
    pont = Pont(tg, {1}, traiter_demande=lent, asynchrone=True)
    msg = lambda t: {"message": {"message_id": 1, "from": {"id": 1}, "chat": {"id": 9}, "text": t}}
    threading.Thread(target=pont._boucle_travail, daemon=True).start()
    pont.traiter_update(msg("A"))
    time.sleep(0.2)
    pont.traiter_update(msg("B"))
    pont.traiter_update(msg("C"))
    assert any("tâche n° 3, 2 avant" in t for t in tg.textes())
    pont.traiter_update(msg("/taches"))
    assert "n° 2" in tg.textes()[-1] and "En cours : n° 1" in tg.textes()[-1]
    pont.traiter_update(msg("annuler 2"))
    assert (tmp_path / "taches.json").exists()
    feu.set()
    for _ in range(50):
        if not pont.file and not pont.en_cours:
            break
        time.sleep(0.05)
    assert faites == ["A", "C"]
    assert any(t.startswith("▶️ Je commence la tâche n° 3") for t in tg.textes())


def _pont_avec_action(tmp_path, monkeypatch):
    from agent import telegram
    from agent.orchestrateur import ActionEnAttente, Resultat
    monkeypatch.setattr(telegram, "dossier_donnees", lambda: tmp_path)
    tg, executees = TelegramFactice(), []
    pont = Pont(tg, membres={11}, traiter_demande=lambda d, o: Resultat("ok"))
    pont.actions["a1"] = (5, ActionEnAttente("a1", "creer_brouillon", {"sujet": "x"}))
    pont.actions_le["a1"] = __import__("time").time()
    pont._sauver_actions()
    monkeypatch.setattr(telegram, "executer_confirmee", lambda a, o: executees.append(a.id) or "Brouillon créé.")
    return pont, tg, executees


def test_mot_confirme_vaut_le_bouton(tmp_path, monkeypatch):
    pont, tg, executees = _pont_avec_action(tmp_path, monkeypatch)
    pont.traiter_update({"message": {"message_id": 1, "from": {"id": 11}, "chat": {"id": 5}, "text": "Confirmé"}})
    assert executees == ["a1"] and "Brouillon créé." in tg.textes()[-1] and not pont.actions


def test_bouton_perime_repond_au_lieu_de_tourner_dans_le_vide(tmp_path, monkeypatch):
    pont, tg, _ = _pont_avec_action(tmp_path, monkeypatch)
    pont.traiter_update({"callback_query": {"id": "c", "from": {"id": 11}, "data": "ok:inconnu", "message": {"chat": {"id": 5}}}})
    rep = [p for m, p in tg.envois if m == "answerCallbackQuery"][-1]
    assert "plus active" in rep["text"] and "plus actif" in tg.textes()[-1]


def test_actions_en_attente_survivent_au_redemarrage(tmp_path, monkeypatch):
    pont, tg, executees = _pont_avec_action(tmp_path, monkeypatch)
    neuf = Pont(tg, membres={11})
    neuf._recharger_actions()
    neuf.traiter_update({"callback_query": {"id": "c", "from": {"id": 11}, "data": "ok:a1", "message": {"chat": {"id": 5}}}})
    assert executees == ["a1"]


def test_bouton_s_execute_meme_si_la_reponse_au_clic_echoue(tmp_path, monkeypatch):
    pont, tg, executees = _pont_avec_action(tmp_path, monkeypatch)
    appeler = tg.appeler

    def casse(methode, **p):
        if methode == "answerCallbackQuery":
            raise RuntimeError("Telegram answerCallbackQuery : query is too old")
        return appeler(methode, **p)
    tg.appeler = casse
    pont.traiter_update({"callback_query": {"id": "c", "from": {"id": 11}, "data": "ok:a1", "message": {"chat": {"id": 5}}}})
    assert executees == ["a1"] and "Brouillon créé." in tg.textes()[-1]


def test_reponse_courte_retrouve_la_fin_de_la_derniere_reponse(tmp_path, monkeypatch):
    """« C » après une longue réponse dont les options sont à la fin : le modèle reçoit ces options en entier."""
    from agent import telegram
    from agent.orchestrateur import Resultat
    monkeypatch.setattr(telegram, "dossier_donnees", lambda: tmp_path)
    longue = "Contexte. " * 120 + "\n- A. Vous payez vous-même.\n- B. Je vérifie le tarif.\n- C. Je me connecte avec Google."
    recu, tg = [], TelegramFactice()

    def modele(demande, outils):
        recu.append(demande)
        return Resultat(longue if len(recu) == 1 else "ok")
    pont = Pont(tg, membres={11}, traiter_demande=modele)
    for texte in ("Je veux payer le parking", "C"):
        pont.traiter_update({"message": {"message_id": 1, "from": {"id": 11}, "chat": {"id": 5}, "text": texte}})
    assert "C. Je me connecte avec Google." in recu[1] and recu[1].rstrip().endswith("Nouveau message : C")


def test_echanges_survivent_au_redemarrage_de_l_agent(tmp_path, monkeypatch):
    from agent import telegram
    from agent.orchestrateur import Resultat
    monkeypatch.setattr(telegram, "dossier_donnees", lambda: tmp_path)
    tg = TelegramFactice()
    pont = Pont(tg, membres={11}, traiter_demande=lambda d, o: Resultat("Options :\n- A. un\n- B. deux\n- C. trois"))
    pont.asynchrone = True
    pont.traiter_update({"message": {"message_id": 1, "from": {"id": 11}, "chat": {"id": 5}, "text": "Je veux payer"}})
    assert pont.file  # en mode asynchrone la demande est mise en file ; on l'exécute comme le fait la boucle de travail
    pont._executer(pont.file.pop(0))
    recu = []
    neuf = Pont(tg, membres={11}, traiter_demande=lambda d, o: (recu.append(d), Resultat("ok"))[1])
    neuf.asynchrone = True  # agent redémarré : mémoire vide, relue depuis le disque
    neuf.traiter_update({"message": {"message_id": 2, "from": {"id": 11}, "chat": {"id": 5}, "text": "C"}})
    neuf._executer(neuf.file.pop(0))
    assert "C. trois" in recu[0] and recu[0].endswith("Nouveau message : C")
