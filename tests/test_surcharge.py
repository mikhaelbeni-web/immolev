"""Claude surchargé : l'agent patiente et réessaie au lieu d'abandonner la demande."""
import anthropic
import httpx
import pytest

from agent import orchestrateur as orch


def _erreur(code):
    rep = httpx.Response(code, request=httpx.Request("POST", "https://x/v1/messages"), json={"error": {"type": "overloaded_error"}})
    classe = anthropic.RateLimitError if code == 429 else anthropic.InternalServerError
    return classe("surcharge", response=rep, body=None)


class Client:
    def __init__(self, echecs, code=529):
        self.echecs, self.code, self.appels = echecs, code, 0
        self.beta = self
        self.messages = self

    def create(self, **kw):
        self.appels += 1
        if self.appels <= self.echecs:
            raise _erreur(self.code)
        return "ok"


def test_reessaie_apres_surcharge(monkeypatch):
    attentes = []
    monkeypatch.setattr(orch.time, "sleep", attentes.append)
    c = Client(2)
    assert orch._appeler(c, model="m") == "ok" and c.appels == 3 and attentes == [15, 30]


def test_abandonne_apres_toutes_les_attentes(monkeypatch):
    monkeypatch.setattr(orch.time, "sleep", lambda s: None)
    c = Client(99, 429)
    with pytest.raises(anthropic.RateLimitError):
        orch._appeler(c, model="m")
    assert c.appels == len(orch.ATTENTES_SURCHARGE) + 1


def test_message_distingue_debit_et_surcharge():
    from agent.telegram import message_erreur
    assert "débit" in message_erreur(_erreur(429)) and "surchargé" in message_erreur(_erreur(529))
