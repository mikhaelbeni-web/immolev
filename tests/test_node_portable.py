"""Node.js portable (pour Outlook) quand winget est absent : zip officiel vérifié par SHASUMS256.txt."""
import hashlib
import io
import json
import zipfile

import pytest

from panneau import messagerie


def _zip():
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("node-v22.1.0-win-x64/node.exe", b"MZ")
        z.writestr("node-v22.1.0-win-x64/npx.cmd", b"@echo off")
    return b.getvalue()


def _lecteur(contenu):
    bon = _zip()
    fichiers = {
        f"{messagerie.NODE}/index.json": json.dumps([{"version": "v23.0.0", "lts": False}, {"version": "v22.1.0", "lts": "Jod"}]).encode(),
        f"{messagerie.NODE}/v22.1.0/SHASUMS256.txt": f"{hashlib.sha256(bon).hexdigest()}  node-v22.1.0-win-x64.zip\n".encode(),
        f"{messagerie.NODE}/v22.1.0/node-v22.1.0-win-x64.zip": contenu,
    }
    return lambda url, timeout=300: fichiers[url]


def test_installe_la_lts_verifiee(tmp_path, monkeypatch):
    monkeypatch.setattr(messagerie.shutil, "which", lambda n: None)
    monkeypatch.delenv("ProgramFiles", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    d = messagerie.installer_node_portable(tmp_path / "nodejs", _lecteur(_zip()))
    assert (d / "npx.cmd").exists() and (d / "node.exe").exists()
    m = messagerie.Messagerie(tmp_path, tmp_path, tmp_path)
    assert m.npx() == str(d / "npx.cmd")


def test_refuse_un_zip_altere(tmp_path):
    with pytest.raises(RuntimeError, match="empreinte"):
        messagerie.installer_node_portable(tmp_path / "nodejs", _lecteur(b"autre"))
    assert not (tmp_path / "nodejs").exists()
