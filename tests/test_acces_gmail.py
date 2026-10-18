import json


def test_site_gmail_sans_mot_de_passe(tmp_path, monkeypatch):
    from types import SimpleNamespace as NS
    from agent import acces
    monkeypatch.setenv("OPTIZIEN_DONNEES", str(tmp_path))
    coffre = {}
    monkeypatch.setattr(acces, "_keyring", lambda: NS(
        set_password=lambda s, u, p: coffre.__setitem__(u, p), get_password=lambda s, u: coffre.get(u),
        delete_password=lambda s, u: coffre.pop(u, None)))
    site = acces.enregistrer("Portail Gmail", "https://exemple.fr/login", "", "", mode="gmail")
    assert site["mode"] == "gmail" and not coffre
    mdp = acces.enregistrer("Autre", "https://autre.fr", "u1", "pw")
    assert mdp["mode"] == "mdp" and coffre
    acces.enregistrer("Autre", "https://autre.fr", "", "", ident=mdp["id"], mode="gmail")
    assert not coffre
    assert {s["mode"] for s in json.loads((tmp_path / "acces.json").read_text())} == {"gmail"}
