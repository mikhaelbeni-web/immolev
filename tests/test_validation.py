from datetime import date

from document.schema import Document, LigneTVA
from document.validation import iban_valide, siret_valide, valider

AUJ = date(2026, 10, 15)


def doc(**kw):
    base = dict(
        type_document="facture_fournisseur", emetteur_nom="Bâti Sud", emetteur_siret="73282932000074", numero="F-2026-118",
        date_document=date(2026, 10, 1), date_echeance=date(2026, 10, 31), montant_ht=1000.0, montant_tva=200.0, montant_ttc=1200.0,
        lignes_tva=[LigneTVA(taux=20, base_ht=1000.0, montant_tva=200.0)], iban="FR7630006000011234567890189",
    )
    base.update(kw)
    return Document(**base)


def niveaux(d):
    return {(a.niveau, a.champ) for a in valider(d, AUJ)}


def test_facture_correcte_sans_alerte():
    assert valider(doc(), AUJ) == []


def test_ht_tva_ttc_incoherents():
    assert ("bloquant", "montant_ttc") in niveaux(doc(montant_ttc=1250.0))


def test_ligne_tva_fausse_et_taux_inhabituel():
    n = niveaux(doc(lignes_tva=[LigneTVA(taux=19, base_ht=1000.0, montant_tva=200.0)]))
    assert ("a_verifier", "lignes_tva.0.taux") in n and ("bloquant", "lignes_tva.0.montant_tva") in n


def test_champs_obligatoires():
    n = niveaux(doc(emetteur_nom=None, date_document=None))
    assert ("bloquant", "emetteur_nom") in n and ("bloquant", "date_document") in n


def test_facture_sans_numero():
    assert ("a_verifier", "numero") in niveaux(doc(numero=None))


def test_iban_invalide_bloque():
    assert ("bloquant", "iban") in niveaux(doc(iban="FR7630006000011234567890188"))


def test_siret_invalide():
    assert ("a_verifier", "emetteur_siret") in niveaux(doc(emetteur_siret="73282932000075"))


def test_dates():
    assert ("bloquant", "date_document") in niveaux(doc(date_document=date(2027, 1, 1), date_echeance=None))
    assert ("bloquant", "date_echeance") in niveaux(doc(date_echeance=date(2026, 9, 1)))
    assert ("a_verifier", "date_echeance") in niveaux(doc(date_document=date(2026, 8, 1), date_echeance=date(2026, 9, 1)))


def test_avis_impot():
    d = Document(type_document="avis_impot_revenu", emetteur_nom="DGFiP", date_document=date(2026, 7, 20), nombre_parts=2.3)
    n = niveaux(d)
    assert ("a_verifier", "revenu_fiscal_reference") in n and ("a_verifier", "nombre_parts") in n
    assert valider(d.model_copy(update={"revenu_fiscal_reference": 84210.0, "nombre_parts": 3.0}), AUJ) == []


def test_cles_de_controle():
    assert siret_valide("732829320") and siret_valide("73282932000074") and not siret_valide("7328293200007")
    assert siret_valide("35600000049837")  # La Poste : règle de la somme multiple de 5
    assert iban_valide("FR76 3000 6000 0112 3456 7890 189") and iban_valide("DE89370400440532013000")
    assert not iban_valide("FR763000600001123456789018")  # longueur française fausse
