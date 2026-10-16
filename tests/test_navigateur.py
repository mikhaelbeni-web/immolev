import os
import re
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from agent import navigateur as module_nav
from agent.navigateur import Navigateur
from agent.telegram import Pont
from tests.test_agent import Logiciel, TelegramFactice

SITE = Path(__file__).parent / "logiciel_factice"
CHROMIUM = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium")


@pytest.fixture
def nav(tmp_path):
    executable = CHROMIUM if Path(CHROMIUM).exists() else None  # sinon le Chrome installé sur le PC
    try:
        n = Navigateur.lancer(tmp_path / "profil", executable=executable, visible=False)
    except Exception as e:
        pytest.skip(f"Chrome introuvable : {e}")
    yield n
    n.fermer()


def ref(texte, motif):
    return re.search(rf"#([\d.]+) {motif}", texte).group(1)


def test_lecture_navigation_et_saisie(nav, tmp_path, monkeypatch):
    page = nav.aller_a((SITE / "liste.html").as_uri())
    assert "secret123" not in page and "••••" in page  # mot de passe jamais lu
    assert "se_connecter" in nav.remplir_champ(ref(page, r"champ « mdp »"), "x")
    page = nav.suivre_lien(ref(page, "lien « DUPONT Jean »"))
    assert "Fiche client" in page
    assert "ni un lien" in nav.suivre_lien(ref(page, "bouton « Enregistrer »"))
    assert "'-2.25'" in nav.remplir_champ(ref(page, "champ « Sphère OD »"), "-2.25")
    assert "'ALMERYS'" in nav.remplir_champ(ref(page, "liste « Mutuelle RC1 »"), "ALMERYS")
    nav.remplir_champ(ref(page, "champ « Consentement imprimé »"), "oui")
    apercu = nav.apercu_formulaire(ref(page, "bouton « Enregistrer »"))
    assert "Sphère OD : -2.25" in apercu and "Consentement imprimé : oui" in apercu
    apres = nav.cliquer_bouton(ref(page, "bouton « Enregistrer »"))
    assert "Enregistré : OD -2.25 / ALMERYS" in apres
    monkeypatch.setattr(module_nav, "DOSSIER_ECRANS", tmp_path / "ecrans")
    nav.relever_ecran("fiche client")
    releve = (tmp_path / "ecrans" / "fiche_client.json").read_text()
    assert "Sphère OD" in releve and "-2.25" not in releve  # structure seulement


class ClaudeNavigateur:
    """Simule Claude : chaque étape lit le dernier résultat d'outil et décide de l'appel suivant."""

    def __init__(self, etapes):
        self.etapes = list(etapes)
        self.messages = self

    def create(self, **kw):
        dernier = kw["messages"][-1]["content"]
        texte = dernier[0]["content"] if isinstance(dernier, list) else dernier
        etape = self.etapes.pop(0)(texte)
        if isinstance(etape, str):
            return NS(stop_reason="end_turn", content=[NS(type="text", text=etape)])
        nom, args = etape
        return NS(stop_reason="tool_use", content=[NS(type="tool_use", id="t", name=nom, input=args)])


def test_demande_telegram_pilote_chrome_avec_confirmation(nav):
    etapes = [
        lambda t: ("aller_a", {"url": (SITE / "liste.html").as_uri()}),
        lambda t: ("suivre_lien", {"ref": ref(t, "lien « DUPONT Jean »")}),
        lambda t: ("remplir_champ", {"ref": ref(t, "champ « Sphère OD »"), "valeur": "-1.50"}),
        lambda t: ("cliquer_bouton", {"ref": ref(nav.lire_page(), "bouton « Enregistrer »")}),
        lambda t: "Sphère OD saisie, enregistrement à confirmer.",
    ]
    from agent.orchestrateur import traiter
    tg = TelegramFactice()
    pont = Pont(tg, membres={11}, destination=Logiciel(), navigateur=nav,
                traiter_demande=lambda d, o: traiter(d, o, ClaudeNavigateur(etapes)))
    pont.traiter_update({"message": {"message_id": 1, "from": {"id": 11}, "chat": {"id": 5}, "text": "Mets -1.50 en OD pour Dupont"}})
    assert "Non enregistré" in nav.page.inner_text("#statut")  # rien d'enregistré avant le clic
    confirmation = tg.textes()[-1]
    assert "Enregistrer" in confirmation and "Sphère OD : -1.50" in confirmation
    action_id = next(iter(pont.actions))
    pont.traiter_update({"callback_query": {"id": "c", "from": {"id": 11}, "data": f"ok:{action_id}"}})
    assert "Enregistré : OD -1.50" in nav.page.inner_text("#statut")
    assert "Enregistré : OD -1.50" in tg.textes()[-1]


def test_cadres_et_boutons_sans_risque(nav):
    page = nav.aller_a((SITE / "cadres.html").as_uri())
    assert "Nom du client" in page and "cadre 1" in page
    champ = ref(page, r"champ « Nom du client »")
    assert champ.startswith("1.")
    nav.remplir_champ(champ, "DUPONT")
    apres = nav.cliquer_bouton_sans_risque(ref(page, "bouton « Rechercher »"))
    assert "1 résultat : DUPONT" in apres
    refus = nav.cliquer_bouton_sans_risque(ref(nav.lire_page(), "bouton « Supprimer le client »"))
    assert "pas dans la liste sans risque" in refus and "SUPPRIMÉ" not in nav.lire_page()


def test_connexion_avec_coffre_en_deux_etapes_puis_code(nav, tmp_path, monkeypatch):
    import functools
    import http.server
    import threading

    from agent import acces

    serveur = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(SITE)))
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{serveur.server_address[1]}/connexion.html"
    coffre = {}
    monkeypatch.setenv("OPTIZIEN_DONNEES", str(tmp_path))
    monkeypatch.setattr(acces, "_keyring", lambda: NS(
        set_password=lambda s, u, p: coffre.__setitem__(u, p), get_password=lambda s, u: coffre.get(u),
        delete_password=lambda s, u: coffre.pop(u)))
    try:
        acces.enregistrer("Portail Test", url, "opticien42", "s3cret!")
        assert "s3cret" not in (tmp_path / "acces.json").read_text()  # le mot de passe reste dans le coffre
        rep = nav.se_connecter("portail test")
        assert "code de vérification" in rep and "s3cret" not in rep
        page = nav.lire_page()
        nav.remplir_champ(ref(page, r"champ « Code reçu par SMS »"), "123456")
        page = nav.cliquer_bouton_sans_risque(ref(nav.lire_page(), r"bouton « Valider le code »"))
        assert "Bienvenue" in page
        # mauvais mot de passe : refus clair, sans boucle
        site = acces.lister()[0]
        acces.enregistrer("Portail Test", url, "", "faux", ident=site["id"])
        nav.aller_a(url)
        assert "refusée" in nav.se_connecter("Portail Test")
        with pytest.raises(LookupError):
            nav.se_connecter("Almerys")
    finally:
        serveur.shutdown()
