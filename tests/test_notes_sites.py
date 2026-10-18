def test_notes_sites_dans_le_prompt(tmp_path, monkeypatch):
    from agent import fiche
    monkeypatch.setattr(fiche, "dossier_donnees", lambda: tmp_path, raising=False)
    monkeypatch.setenv("OPTIZIEN_DONNEES", str(tmp_path))
    assert "rien" in fiche.noter_site("", "x")
    fiche.noter_site("Almerys", "captcha au login : équipe valide")
    fiche.noter_site("Almerys", "captcha au login : équipe valide")
    assert len(fiche.notes_sites()["Almerys"]) == 1
    assert "Almerys" in fiche.texte_prompt()
