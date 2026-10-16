import json

from panneau import visage


def test_liste_et_images():
    l = visage.liste()
    assert {a["genre"] for a in l} == {"f", "m"} and len(l) >= 8
    assert visage.image(l[0]["id"])[:2] == b"\xff\xd8"  # JPEG
    assert visage.image("../page.html") is None


def test_choix_sans_bot(tmp_path):
    r = visage.choisir(tmp_path, "lea", "  Léa  B ", None)
    assert r["ok"] and json.loads((tmp_path / "visage.json").read_text(encoding="utf-8")) == {"id": "lea", "nom": "Léa B"}


def test_choix_envoie_photo_et_nom(tmp_path, monkeypatch):
    appels = []
    monkeypatch.setattr(visage, "_telegram", lambda j, m, corps, t: appels.append((m, corps, t)) or {"ok": True})
    r = visage.choisir(tmp_path, "hugo", "", "123:abc")
    assert [a[0] for a in appels] == ["setMyProfilePhoto", "setMyName"]
    assert b'"attach://visage"' in appels[0][1] and appels[0][2].startswith("multipart/form-data")
    assert b"name=Hugo" in appels[1][1] and "Hugo" in r["message"]


def test_prenom_dans_le_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv("OPTIZIEN_DONNEES", str(tmp_path))
    (tmp_path / "visage.json").write_text('{"id": "lea", "nom": "Léa"}', encoding="utf-8")
    from agent import orchestrateur
    assert orchestrateur.systeme().startswith("Tu t'appelles Léa")


def test_image_perso(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        visage.importer(tmp_path, b"pas une image")
    visage.importer(tmp_path, b"\xff\xd8\xff\xe0fin")
    assert visage.image("perso", tmp_path) == b"\xff\xd8\xff\xe0fin"
    with pytest.raises(ValueError):
        visage.choisir(tmp_path, "perso", "", None)
    assert visage.choisir(tmp_path, "perso", "Zoé", None)["ok"]
