"""Le modèle vocal se charge depuis le PC d'abord : une connexion lente ne doit plus faire échouer les vocaux."""
import sys
import types

from agent import voix


def test_charge_le_modele_local_sans_internet(monkeypatch):
    appels = []

    class Faux:
        def __init__(self, nom, device, compute_type, download_root, local_files_only):
            appels.append((nom, local_files_only))
            if not local_files_only:
                raise TimeoutError("ReadTimeout")  # internet inaccessible
    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=Faux))
    monkeypatch.setattr(voix, "_modele", None)
    assert voix.charger() is not None
    assert appels == [(voix.MODELE, True)]


def test_repli_sur_le_petit_modele_local(monkeypatch):
    appels = []

    class Faux:
        def __init__(self, nom, device, compute_type, download_root, local_files_only):
            appels.append((nom, local_files_only))
            if nom == voix.MODELE:
                raise OSError("absent")
    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=Faux))
    monkeypatch.setattr(voix, "_modele", None)
    voix.charger()
    assert appels == [(voix.MODELE, True), (voix.SECOURS, True)]
