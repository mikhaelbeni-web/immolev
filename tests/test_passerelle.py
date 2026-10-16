import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import anthropic
import pytest

from agent import passerelle

COMPTE = {"identifiant": "essai", "mot_de_passe": "Secret1"}


@pytest.fixture
def serveur():
    """Faux serveur Optizien : accepte essai:Secret1, répond au ping et à /v1/messages."""
    vu = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _rep(self, code, corps):
            data = json.dumps(corps).encode()
            self.send_response(code)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _traiter(self):
            vu.append((self.command, self.path, self.headers.get("x-api-key")))
            if self.headers.get("x-api-key") != "essai:Secret1":
                return self._rep(401, {"type": "error", "error": {"type": "authentication_error", "message": "refusé"}})
            if self.path.endswith("/ping"):
                return self._rep(200, {"ok": True, "cle": True})
            n = int(self.headers.get("content-length") or 0)
            self.rfile.read(n)
            self._rep(200, {"id": "m1", "type": "message", "role": "assistant", "model": "claude-sonnet-5-5", "stop_reason": "end_turn",
                            "stop_sequence": None, "content": [{"type": "text", "text": "Bonjour"}],
                            "usage": {"input_tokens": 3, "output_tokens": 2}})

        do_GET = do_POST = _traiter

    s = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_port}/api/ia", vu
    s.shutdown()


def test_ping_compte_accepte_et_refuse(serveur):
    url, _ = serveur
    assert passerelle.ping(COMPTE, url)["ok"] is True
    refuse = passerelle.ping({"identifiant": "essai", "mot_de_passe": "faux"}, url)
    assert refuse["ok"] is False and "refusé" in refuse["message"]


def test_ping_serveur_sans_cle():
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            data = b'{"ok": true, "cle": false}'
            self.send_response(200)
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    s = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    r = passerelle.ping(COMPTE, f"http://127.0.0.1:{s.server_port}/api/ia")
    s.shutdown()
    assert r["ok"] is None and "clé IA" in r["message"]


def test_le_sdk_passe_par_la_passerelle_avec_le_compte(serveur, monkeypatch):
    url, vu = serveur
    for k, v in passerelle.environnement(COMPTE, url).items():
        monkeypatch.setenv(k, v)
    rep = anthropic.Anthropic().beta.messages.create(model="claude-sonnet-5-5", max_tokens=5, messages=[{"role": "user", "content": "Salut"}],
                                                      betas=["context-management-2025-06-27"])
    assert rep.content[0].text == "Bonjour"
    methode, chemin, cle = vu[-1]
    assert methode == "POST" and chemin.startswith("/api/ia/v1/messages") and cle == "essai:Secret1"
