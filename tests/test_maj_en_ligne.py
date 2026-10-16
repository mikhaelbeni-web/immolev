import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from panneau import maj

ATTENDU = "Basic " + base64.b64encode(b"magasin:secret").decode()


class Site(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.headers.get("Authorization") != ATTENDU:
            self.send_response(401)
            self.end_headers()
            return
        corps = json.dumps({"version": "9", "fichier": "Optizien-v9.zip"}).encode() if self.path.endswith("version.json") else b"ZIP"
        self.send_response(200)
        self.end_headers()
        self.wfile.write(corps)

    def log_message(self, *a):
        pass


@pytest.fixture
def site():
    s = ThreadingHTTPServer(("127.0.0.1", 0), Site)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_port}/telecharger"
    s.shutdown()


def test_version_et_telechargement(site, tmp_path):
    bon = {"identifiant": "magasin", "mot_de_passe": "secret"}
    trouve = maj.chercher_en_ligne(bon, "6", site)
    assert trouve["version"] == "9" and trouve["url"].endswith("/Optizien-v9.zip")
    assert maj.chercher_en_ligne(bon, "9", site) is None
    assert maj.telecharger(trouve["url"], bon, tmp_path / "z.zip").read_bytes() == b"ZIP"
    with pytest.raises(PermissionError):
        maj.version_en_ligne({"identifiant": "magasin", "mot_de_passe": "faux"}, site)
