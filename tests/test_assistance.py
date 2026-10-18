"""Assistance à distance : RustDesk officiel, vérifié par son empreinte avant d'être lancé."""
import hashlib
import json

import pytest

from panneau import assistance

EXE = b"MZ rustdesk factice"


def _lecteur(contenu=EXE, digest=None, appels=None):
    version = {"assets": [
        {"name": "rustdesk-1.4.2-x86_64.msi", "browser_download_url": "https://x/msi", "digest": "sha256:00"},
        {"name": "rustdesk-1.4.2-x86_64.exe", "browser_download_url": "https://x/exe",
         "digest": digest or "sha256:" + hashlib.sha256(EXE).hexdigest()},
    ]}

    def lire(url, timeout=60):
        (appels if appels is not None else []).append(url)
        return json.dumps(version).encode() if url == assistance.API else contenu
    return lire


def test_telecharge_verifie_puis_garde_en_cache(tmp_path):
    appels = []
    exe = assistance.obtenir(tmp_path, _lecteur(appels=appels))
    assert exe.name == "rustdesk-1.4.2-x86_64.exe" and exe.read_bytes() == EXE and "https://x/exe" in appels
    appels.clear()
    assert assistance.obtenir(tmp_path, _lecteur(appels=appels)) == exe and "https://x/exe" not in appels


def test_refuse_un_fichier_qui_ne_correspond_pas_a_l_empreinte(tmp_path):
    with pytest.raises(ValueError, match="empreinte"):
        assistance.obtenir(tmp_path, _lecteur(contenu=b"autre chose"))
    assert not list(tmp_path.glob("*.exe"))


def test_hors_ligne_reprend_la_copie_deja_verifiee(tmp_path):
    exe = assistance.obtenir(tmp_path, _lecteur())

    def coupe(url, timeout=60):
        raise OSError("hors ligne")
    assert assistance.obtenir(tmp_path, coupe) == exe
    with pytest.raises(OSError):
        assistance.obtenir(tmp_path / "vide", coupe)


def test_sans_empreinte_publiee_on_refuse():
    with pytest.raises(ValueError, match="Empreinte"):
        assistance.choisir({"assets": [{"name": "rustdesk-1.4.2-x86_64.exe", "browser_download_url": "u"}]})
