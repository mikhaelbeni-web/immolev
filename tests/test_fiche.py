from agent import fiche, orchestrateur


def test_date_reglementation_et_fiche_dans_le_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv("OPTIZIEN_DONNEES", str(tmp_path))
    texte = orchestrateur.systeme()
    assert texte.startswith("Nous sommes le ")
    assert "Fiche réglementaire optique" in texte and "Guide MyEasyOptic" in texte
    assert "Questions encore sans réponse" in texte and "portails" in texte


def test_questionnaire_et_completer(tmp_path, monkeypatch):
    monkeypatch.setenv("OPTIZIEN_DONNEES", str(tmp_path))
    fiche.ecrire({"magasin": "Optizien Eyewear, Paris", "inconnue": "x", "horaires": "  "})
    assert fiche.lire() == {"magasin": "Optizien Eyewear, Paris"}
    assert "inconnue" in fiche.completer("inconnue", "x")
    fiche.completer("portails", "Almerys → portail Almerys")
    fiche.completer("portails", "Viamedis → portail Viamedis")
    assert fiche.lire()["portails"] == "Almerys → portail Almerys ; Viamedis → portail Viamedis"
    texte = orchestrateur.systeme()
    assert "Optizien Eyewear, Paris" in texte and "Viamedis → portail Viamedis" in texte


def test_procedures(tmp_path, monkeypatch):
    monkeypatch.setenv("OPTIZIEN_DONNEES", str(tmp_path))
    fiche.retenir_procedure("MyEasyOptic : créer une fiche client", "1. Menu Clients\n2. Bouton Nouveau")
    assert "MyEasyOptic : créer une fiche client" in orchestrateur.systeme()
    fiche.supprimer_procedure("MyEasyOptic : créer une fiche client")
    assert fiche.procedures() == {}
