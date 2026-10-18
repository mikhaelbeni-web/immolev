"""Le coffre garde les secrets même sans keyring, et le jeton Telegram s'enregistre."""
import base64
import sys

from agent.coffre import Coffre


def _faux(tmp_path, **kw):
    return Coffre(tmp_path / "coffre.json", chiffrer=lambda b: b[::-1], dechiffrer=lambda b: b[::-1], **kw)


def test_repli_fichier_chiffre(tmp_path):
    c = _faux(tmp_path, utiliser_keyring=False)
    c.set_password("immolev", "TELEGRAM_TOKEN", "123:abc")
    assert c.get_password("immolev", "TELEGRAM_TOKEN") == "123:abc"
    assert "123:abc" not in (tmp_path / "coffre.json").read_text()
    c.delete_password("immolev", "TELEGRAM_TOKEN")
    assert c.get_password("immolev", "TELEGRAM_TOKEN") is None


def test_module_keyring_absent(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "keyring", None)  # « No module named 'keyring' »
    c = _faux(tmp_path)
    c.set_password("immolev", "x", "secret")
    assert c.get_password("immolev", "x") == "secret"


def test_coffre_systeme_en_erreur(tmp_path, monkeypatch):
    class Casse:
        def set_password(*a): raise RuntimeError("pas de coffre")
        def get_password(*a): raise RuntimeError("pas de coffre")
        def delete_password(*a): raise RuntimeError("pas de coffre")
    monkeypatch.setitem(sys.modules, "keyring", Casse())
    c = _faux(tmp_path)
    c.set_password("immolev", "x", "secret")
    assert c.get_password("immolev", "x") == "secret"


def test_coffre_systeme_prioritaire(tmp_path, monkeypatch):
    mem = {}
    class Ok:
        def set_password(self, s, n, v): mem[(s, n)] = v
        def get_password(self, s, n): return mem.get((s, n))
        def delete_password(self, s, n): mem.pop((s, n), None)
    monkeypatch.setitem(sys.modules, "keyring", Ok())
    c = _faux(tmp_path)
    c.set_password("immolev", "x", "v")
    assert mem[("immolev", "x")] == "v" and not (tmp_path / "coffre.json").exists()


def test_panneau_enregistre_le_jeton_sans_keyring(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "keyring", None)
    from agent import coffre
    from panneau import __main__ as pan
    faux = _faux(tmp_path)
    monkeypatch.setattr(coffre, "_defaut", faux)
    monkeypatch.setattr(coffre, "get_password", faux.get_password)
    monkeypatch.setattr(coffre, "set_password", faux.set_password)
    pan.ecrire_secret("TELEGRAM_TOKEN", "123:abc")
    assert pan.lire_secret("TELEGRAM_TOKEN") == "123:abc"
