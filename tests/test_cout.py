import json
from types import SimpleNamespace as NS

from agent import orchestrateur
from agent.orchestrateur import cout, reglages, traiter
from agent.outils import Outil


def test_cout_par_type_de_jeton():
    u = NS(input_tokens=1_000_000, cache_creation_input_tokens=0, cache_read_input_tokens=1_000_000, output_tokens=100_000)
    assert round(cout("claude-sonnet-5-5", u), 2) == 2.0 + 0.2 + 1.0
    assert cout("claude-haiku-5-5", u) < cout("claude-sonnet-5-5", u) / 15


def test_reglages_par_defaut_et_lus(tmp_path, monkeypatch):
    monkeypatch.setenv("IMMOLEV_DONNEES", str(tmp_path))
    assert reglages() == {"modele": "standard", "plafond": 1.0}
    (tmp_path / "reglages-ia.json").write_text('{"modele": "economique", "plafond": "0.3"}')
    assert reglages() == {"modele": "economique", "plafond": 0.3}


class Cher:
    """Claude qui lit une page à chaque tour, chaque tour coûtant 0,40 $."""

    def __init__(self):
        self.appels = []
        self.beta = self.messages = self

    def create(self, **kw):
        self.appels.append(kw)
        usage = NS(input_tokens=0, cache_creation_input_tokens=0, cache_read_input_tokens=0, output_tokens=40_000)
        return NS(stop_reason="tool_use", model=kw["model"], usage=usage,
                  content=[NS(type="tool_use", id=f"t{len(self.appels)}", name="lire_page", input={})])


def test_plafond_arrete_la_demande_et_requete_economique(tmp_path, monkeypatch):
    monkeypatch.setenv("IMMOLEV_DONNEES", str(tmp_path))
    (tmp_path / "reglages-ia.json").write_text(json.dumps({"modele": "standard", "plafond": 1.0}))
    claude = Cher()
    r = traiter("Va sur le site du syndic", {"lire_page": Outil("lire_page", "lit", {}, False, lambda: "page")}, claude)
    assert "plafond" in r.texte and len(claude.appels) == 3  # 0,40 + 0,40 + 0,40 ≥ 1 €
    kw = claude.appels[0]
    assert kw["model"] == "claude-sonnet-5-5" and kw["cache_control"] == {"type": "ephemeral"}
    assert kw["context_management"] == orchestrateur.CONTEXTE and kw["fallbacks"] == "default"
    couts = json.loads((tmp_path / "cout-demandes.json").read_text())
    assert couts[-1]["cout"] == 1.2
