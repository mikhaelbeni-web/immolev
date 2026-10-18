from agent import fiche, orchestrateur


def test_date_connaissances_et_fiche_dans_le_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv("IMMOLEV_DONNEES", str(tmp_path))
    texte = orchestrateur.systeme()
    assert texte.startswith("Nous sommes le ")
    assert "Métiers de l'immobilier" in texte and "Vie personnelle du gestionnaire" in texte and "fiscalité de l'immobilier" in texte
    assert "Questions encore sans réponse" in texte and "biens" in texte


def test_questionnaire_et_completer(tmp_path, monkeypatch):
    monkeypatch.setenv("IMMOLEV_DONNEES", str(tmp_path))
    fiche.ecrire({"identite": "Mikhael, gestionnaire foncier", "inconnue": "x", "horaires": "  "})
    assert fiche.lire() == {"identite": "Mikhael, gestionnaire foncier"}
    assert "inconnue" in fiche.completer("inconnue", "x")
    fiche.completer("biens", "Hôtel Le Parc, Nice")
    fiche.completer("biens", "Résidence Les Pins, copro 38 lots")
    assert fiche.lire()["biens"] == "Hôtel Le Parc, Nice ; Résidence Les Pins, copro 38 lots"
    texte = orchestrateur.systeme()
    assert "gestionnaire foncier" in texte and "Résidence Les Pins" in texte


def test_procedures(tmp_path, monkeypatch):
    monkeypatch.setenv("IMMOLEV_DONNEES", str(tmp_path))
    fiche.retenir_procedure("Logiciel copro : saisir une facture", "1. Menu Comptabilité\n2. Bouton Nouvelle facture")
    assert "Logiciel copro : saisir une facture" in orchestrateur.systeme()
    fiche.supprimer_procedure("Logiciel copro : saisir une facture")
    assert fiche.procedures() == {}
