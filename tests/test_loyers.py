import base64
import json
from datetime import date

import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from agent import banque, loyers


def _pem() -> tuple[str, object]:
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    return pem, k.public_key()


class CoffreMemoire:
    def __init__(self):
        self.d = {}

    def get_password(self, s, n):
        return self.d.get((s, n))

    def set_password(self, s, n, v):
        self.d[(s, n)] = v


APP_ID = "1a2b3c4d-0000-1111-2222-333344445555"


# ---------------------------------------------------------------- banque

def test_jeton_rs256_signe_avec_la_cle():
    pem, pub = _pem()
    j = banque.jeton({"app_id": APP_ID, "pem": pem}, maintenant=1000)
    entete, corps, sig = j.split(".")
    dec = lambda s: json.loads(base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)))
    assert dec(entete) == {"typ": "JWT", "alg": "RS256", "kid": APP_ID}
    assert dec(corps) == {"iss": "enablebanking.com", "aud": "api.enablebanking.com", "iat": 1000, "exp": 4600}
    pub.verify(base64.urlsafe_b64decode(sig + "=" * (-len(sig) % 4)), f"{entete}.{corps}".encode(), padding.PKCS1v15(), hashes.SHA256())


def test_enregistrer_application_controle_la_cle():
    c = CoffreMemoire()
    with pytest.raises(ValueError):
        banque.enregistrer_application(APP_ID, "pas une clé", c)
    pem, _ = _pem()
    banque.enregistrer_application(APP_ID, pem, c)
    assert banque.application(c)["app_id"] == APP_ID


def test_lecture_seule():
    assert banque.appel_lecture_seule("GET", "/accounts/abc-1/transactions?date_from=2026-01-01")
    assert banque.appel_lecture_seule("POST", "/sessions")
    assert not banque.appel_lecture_seule("POST", "/payments")
    assert not banque.appel_lecture_seule("POST", "/accounts/abc/transactions")
    assert not banque.appel_lecture_seule("GET", "/accounts/abc/transfers")
    pem, _ = _pem()
    cl = banque.Client({"app_id": APP_ID, "pem": pem}, http=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))))
    with pytest.raises(PermissionError):
        cl.appel("POST", "/payments", {})


def _transport(sessions_ok=True):
    def repondre(req: httpx.Request) -> httpx.Response:
        assert req.headers["authorization"].startswith("Bearer ")
        p = req.url.path
        if p == "/aspsps":
            return httpx.Response(200, json={"aspsps": [{"name": "CIC", "country": "FR", "maximum_consent_validity": 15552000},
                                                        {"name": "CIC Banque Privée", "country": "FR"}]})
        if p == "/auth":
            corps = json.loads(req.content)
            assert corps["aspsp"]["name"] == "CIC" and corps["redirect_url"] == banque.RETOUR
            assert corps["state"].startswith("51234.")
            repondre.state = corps["state"]
            return httpx.Response(200, json={"url": "https://banque.example/consentement", "authorization_id": "x"})
        if p == "/sessions":
            return httpx.Response(200, json={"session_id": "s-1", "aspsp": {"name": "CIC"}, "access": {"valid_until": "2027-05-15T10:00:00+00:00"},
                                             "accounts": [{"uid": "acc-1", "name": "Compte courant", "account_id": {"iban": "FR7630066000000000000012345"}}]})
        if p == "/accounts/acc-1/transactions":
            if not sessions_ok:
                return httpx.Response(401, json={"message": "EXPIRED_SESSION"})
            return httpx.Response(200, json={"transactions": [
                {"entry_reference": "r1", "status": "BOOK", "booking_date": "2026-12-03", "credit_debit_indicator": "CRDT",
                 "transaction_amount": {"amount": "52.13", "currency": "EUR"}, "debtor": {"name": "M SEAN GASNIER"},
                 "remittance_information": ["VIR SEPA LOYER DECEMBRE"]},
                {"entry_reference": "r2", "status": "BOOK", "booking_date": "2026-12-04", "credit_debit_indicator": "DBIT",
                 "transaction_amount": {"amount": "30.00", "currency": "EUR"}, "creditor": {"name": "EDF"}},
                {"entry_reference": "r3", "status": "PDNG", "booking_date": "2026-12-05", "credit_debit_indicator": "CRDT",
                 "transaction_amount": {"amount": "999", "currency": "EUR"}},
            ]})
        return httpx.Response(404, json={"message": p})
    return repondre


def _client(sessions_ok=True):
    pem, _ = _pem()
    t = _transport(sessions_ok)
    return banque.Client({"app_id": APP_ID, "pem": pem}, http=httpx.Client(transport=httpx.MockTransport(t))), t


def test_connexion_puis_releve(tmp_path):
    cl, t = _client()
    url = banque.lien_connexion(tmp_path, "lm invest", 51234, cl)
    assert url == "https://banque.example/consentement"
    with pytest.raises(ValueError):
        banque.valider_retour(tmp_path, "code", "51234.faux", cl)
    assert "LM INVEST : 1 compte(s)" in banque.valider_retour(tmp_path, "code", t.state, cl)
    assert banque.resume_connexions(tmp_path, date(2027, 5, 5))[0]["jours_restants"] == 10
    res = banque.releve(tmp_path, cl, aujourd_hui=date(2026, 12, 6))
    assert res["nouvelles"] == 2 and not res["erreurs"]
    assert banque.releve(tmp_path, cl, aujourd_hui=date(2026, 12, 6))["nouvelles"] == 0  # pas de doublon
    ops = banque.operations(tmp_path)
    assert ops[0]["montant"] == 52.13 and ops[0]["payeur"] == "M SEAN GASNIER" and ops[1]["montant"] == -30
    assert "12345" not in json.dumps(banque.etat(tmp_path)).replace("•••• 2345", "")  # IBAN masqué


def test_acces_expire_signale(tmp_path):
    cl, t = _client(sessions_ok=False)
    banque.lien_connexion(tmp_path, "LM INVEST", 51234, cl)
    banque.valider_retour(tmp_path, "code", t.state, cl)
    res = banque.releve(tmp_path, cl, aujourd_hui=date(2026, 12, 6))
    assert res["expirees"] == ["LM INVEST"]


# ---------------------------------------------------------------- loyers

def _op(ref, jour, montant, payeur="", libelle="", societe="LM INVEST"):
    return {"ref": ref, "date": jour, "montant": montant, "payeur": payeur, "libelle": libelle or payeur, "societe": societe,
            "compte": "acc-1", "iban": ""}


def _baux(tmp_path, auto=False):
    loyers.enregistrer_bail(tmp_path, {"id": "livry-2e", "societe": "LM INVEST", "bien": "Livry 2e étage", "locataires": ["Sean GASNIER", "Vénus GASNIER"],
                                       "emails": ["sean@example.fr"], "loyer": 716, "jour_echeance": 1, "debut": "2026-11-16",
                                       "payeurs": ["GASNIER"], "garantie": "Visale", "ajustements": {"2026-11": 15, "2026-12": 52.13}})
    loyers.enregistrer_bail(tmp_path, {"id": "livry-cave", "societe": "LM INVEST", "bien": "Cave Livry", "locataires": ["Sean GASNIER"],
                                       "emails": ["sean@example.fr"], "loyer": 144, "jour_echeance": 16, "debut": "2026-11-16",
                                       "payeurs": ["GASNIER"], "cautions": ["Florence GRANDJEAN"], "ajustements": {"2026-11": 0, "2026-12": 74.32}})
    loyers.enregistrer_bail(tmp_path, {"id": "livry-1er", "societe": "LM INVEST", "bien": "Livry 1er étage", "locataires": ["Paul MARTIN"],
                                       "emails": ["paul@example.fr"], "loyer": 800, "jour_echeance": 5, "debut": "2025-01-05", "payeurs": ["P MARTIN", "MARTIN PAUL"]})
    loyers.regler(tmp_path, debut_suivi="2026-12", auto=auto, envoi={"serveur": "gmail", "outil": "envoyer_mail", "compte": ""})


def _ecrire_ops(tmp_path, ops):
    (tmp_path / banque.OPERATIONS).write_text(json.dumps(ops), encoding="utf-8")


def test_bail_controle():
    with pytest.raises(ValueError):
        loyers.enregistrer_bail("/tmp", {"id": "x", "societe": "Autre SARL", "bien": "b", "loyer": 1, "debut": "2026-01-01", "payeurs": ["ABC"]})
    with pytest.raises(ValueError):
        loyers.enregistrer_bail("/tmp", {"id": "x", "societe": "LM INVEST", "bien": "b", "loyer": 1, "debut": "2026-01-01", "payeurs": []})


def test_echeances_franchise_et_debut_suivi(tmp_path):
    _baux(tmp_path)
    d = loyers.charger(tmp_path)
    cave = next(b for b in d["baux"] if b["id"] == "livry-cave")
    assert loyers.echeances(cave, "2026-11", date(2027, 1, 20)) == [
        {"mois": "2026-12", "date": "2026-12-16", "montant": 74.32}, {"mois": "2027-01", "date": "2027-01-16", "montant": 144.0}]
    log = next(b for b in d["baux"] if b["id"] == "livry-2e")
    assert [e["montant"] for e in loyers.echeances(log, "2026-12", date(2027, 1, 2))] == [52.13, 716.0]


def test_rapprochement_payeurs_partage_et_inconnus(tmp_path):
    _baux(tmp_path)
    _ecrire_ops(tmp_path, [
        _op("a", "2026-12-02", 52.13, "M SEAN GASNIER"),              # logement : montant de son échéance
        _op("b", "2026-12-15", 74.32, "GASNIER SEAN"),                # cave
        _op("c", "2026-12-06", 400, "", "VIR MARTIN PAUL LOYER"),     # partiel
        _op("d", "2026-12-07", 1200, "SCI VOISINE"),                  # inconnu
        _op("e", "2026-12-07", 500, "INCONNU", societe="MIKALEVINVEST"),  # autre société sans bail : ignoré
        _op("f", "2026-12-01", -50, "EDF"),
    ])
    rap = loyers.rapprocher(loyers.charger(tmp_path), json.loads((tmp_path / banque.OPERATIONS).read_text()), date(2026, 12, 20))
    b = rap["baux"]
    assert b["livry-2e"]["solde"] == 0 and b["livry-cave"]["solde"] == 0
    assert b["livry-1er"]["solde"] == 400 and b["livry-1er"]["echeances"][0]["retard"] == 15
    assert [o["ref"] for o in rap["inconnus"]] == ["d"]
    texte = loyers.point(rap)
    assert "✅ à jour" in texte and "🟠 partiel : 400,00 € dus" in texte and "[ref d]" in texte


def test_un_virement_pour_deux_baux_est_partage(tmp_path):
    _baux(tmp_path)
    ops = [_op("a", "2026-12-16", 126.45, "GASNIER")]  # 52,13 + 74,32 en un seul virement
    rap = loyers.rapprocher(loyers.charger(tmp_path), ops, date(2026, 12, 20))
    assert rap["baux"]["livry-2e"]["solde"] == 0 and rap["baux"]["livry-cave"]["solde"] == 0 and not rap["a_repartir"]
    rap = loyers.rapprocher(loyers.charger(tmp_path), [_op("a", "2026-12-16", 100, "GASNIER")], date(2026, 12, 20))
    assert rap["a_repartir"] and rap["baux"]["livry-cave"]["bloque"]


def test_inconnu_du_meme_montant_suspend_la_relance(tmp_path):
    _baux(tmp_path, auto=True)
    _ecrire_ops(tmp_path, [_op("a", "2026-12-02", 52.13, "GASNIER"), _op("b", "2026-12-16", 74.32, "GASNIER"),
                           _op("x", "2026-12-06", 800, "M OU MME DURAND")])
    envois = []
    msg = loyers.tour(tmp_path, date(2026, 12, 12), envoyer=lambda *a: envois.append(a) or "ok", relever=False)
    assert envois == [] and "suspendu" in msg and "800,00 €" in msg
    loyers.associer_operation(tmp_path, "x", "livry-1er")
    assert "DURAND" in " ".join(next(b for b in loyers.charger(tmp_path)["baux"] if b["id"] == "livry-1er")["payeurs"])
    assert "✅" in loyers.etat_actuel(tmp_path, date(2026, 12, 12)).split("Livry 1er")[1].split("\n")[0]


def test_paliers_envoi_auto_puis_mise_en_demeure(tmp_path):
    _baux(tmp_path, auto=True)
    _ecrire_ops(tmp_path, [_op("a", "2026-12-02", 52.13, "GASNIER"), _op("b", "2026-12-16", 74.32, "GASNIER")])
    envois = []
    envoyer = lambda serveur, outil, args: envois.append((serveur, outil, args)) or "Mail envoyé"
    assert loyers.tour(tmp_path, date(2026, 12, 9), envoyer=envoyer, relever=False, point_complet=False) is None  # J+4
    msg = loyers.tour(tmp_path, date(2026, 12, 10), envoyer=envoyer, relever=False, point_complet=False)  # J+5
    assert len(envois) == 1 and envois[0][2]["destinataire"] == "paul@example.fr" and "Rappel amiable envoyé" in msg
    assert loyers.tour(tmp_path, date(2026, 12, 11), envoyer=envoyer, relever=False, point_complet=False) is None  # pas de doublon
    loyers.tour(tmp_path, date(2026, 12, 20), envoyer=envoyer, relever=False, point_complet=False)  # J+15
    assert len(envois) == 2 and envois[1][2]["sujet"].startswith("Relance")
    msg = loyers.tour(tmp_path, date(2027, 1, 4), envoyer=envoyer, relever=False, point_complet=False)  # J+30
    assert len(envois) == 2  # jamais envoyée seule
    assert "Mises en demeure à valider" in msg and "livry-1er 2026-12" in msg
    courrier = (tmp_path / "courriers" / "mise-en-demeure_livry-1er_2026-12.txt").read_text(encoding="utf-8")
    assert "800,00 €" in courrier and "commandement de payer" in courrier
    rep = loyers.envoyer_mise_en_demeure(tmp_path, "livry-1er", "2026-12", envoyer)
    assert "recommandé" in rep and envois[-1][2]["sujet"].startswith("Mise en demeure")


def test_mode_essai_prepare_sans_envoyer(tmp_path):
    _baux(tmp_path, auto=False)
    _ecrire_ops(tmp_path, [])
    envois = []
    msg = loyers.tour(tmp_path, date(2026, 12, 10), envoyer=lambda *a: envois.append(a) or "ok", relever=False, point_complet=True)
    assert envois == [] and "Relances à faire à la main" in msg and "mode automatique non activé" in msg
    assert "Point des loyers" in msg and "🔴 impayé" in msg


def test_panneau_retour_banque(tmp_path, monkeypatch):
    import threading
    import urllib.request
    import panneau.__main__ as p
    monkeypatch.setattr(p, "DONNEES", tmp_path)
    serveur = p.creer_serveur(object(), "jeton", 0)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    try:
        port = serveur.server_address[1]
        page = urllib.request.urlopen(f"http://127.0.0.1:{port}/banque/retour?code=x&state={port}.inconnu").read().decode()
        assert "Connexion non terminée" in page and "expiré" in page
        page = urllib.request.urlopen(f"http://127.0.0.1:{port}/banque/retour?error=access_denied&state={port}.x").read().decode()
        assert "Connexion refusée" in page
        with pytest.raises(urllib.error.HTTPError):  # le reste du panneau exige toujours le jeton
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/etat")
    finally:
        serveur.shutdown()
