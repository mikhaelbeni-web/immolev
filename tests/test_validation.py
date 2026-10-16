from datetime import date

from ordonnance.schema import Oeil, Ordonnance
from ordonnance.validation import duree_validite_ans, transposer, valider

AUJ = date(2026, 10, 15)


def ordo(**kw):
    base = dict(
        patient_nom="DUPONT", prescripteur_nom="Dr Martin", date_prescription=date(2026, 3, 1),
        patient_date_naissance=date(1990, 5, 2), type_equipement=["lunettes_vl"],
        od=Oeil(sphere=-2.25, cylindre=-0.75, axe=170), og=Oeil(sphere=-2.0),
    )
    base.update(kw)
    return Ordonnance(**base)


def niveaux(o):
    return {(a.niveau, a.champ) for a in valider(o, AUJ)}


def test_ordonnance_correcte_sans_alerte():
    assert valider(ordo(), AUJ) == []


def test_pas_de_025():
    assert ("bloquant", "od.sphere") in niveaux(ordo(od=Oeil(sphere=-2.3)))


def test_cylindre_sans_axe():
    assert ("bloquant", "od.axe") in niveaux(ordo(od=Oeil(sphere=1.0, cylindre=-1.0)))


def test_oeil_vide():
    assert ("bloquant", "og.sphere") in niveaux(ordo(og=Oeil()))


def test_champs_obligatoires():
    n = niveaux(ordo(patient_nom=None, prescripteur_nom=None))
    assert ("bloquant", "patient_nom") in n and ("bloquant", "prescripteur_nom") in n


def test_progressif_sans_addition():
    assert ("a_verifier", "addition") in niveaux(ordo(type_equipement=["lunettes_progressifs"]))


def test_validite_par_age():
    assert duree_validite_ans(ordo(patient_date_naissance=date(2015, 1, 1))) == 1
    assert duree_validite_ans(ordo()) == 5
    assert duree_validite_ans(ordo(patient_date_naissance=date(1970, 1, 1))) == 3
    assert duree_validite_ans(ordo(type_equipement=["lentilles"])) == 3


def test_ordonnance_expiree():
    o = ordo(patient_date_naissance=date(1970, 1, 1), date_prescription=date(2023, 1, 10))
    assert ("bloquant", "date_prescription") in niveaux(o)


def test_date_future():
    assert ("bloquant", "date_prescription") in niveaux(ordo(date_prescription=date(2027, 1, 1)))


def test_transposition_cylindre_positif():
    t = transposer(Oeil(sphere=-1.0, cylindre=0.5, axe=80))
    assert (t.sphere, t.cylindre, t.axe) == (-0.5, -0.5, 170)
    t = transposer(Oeil(sphere=2.0, cylindre=1.25, axe=135))
    assert (t.sphere, t.cylindre, t.axe) == (3.25, -1.25, 45)


def test_transposition_neutre_si_negatif():
    o = Oeil(sphere=-1.0, cylindre=-0.5, axe=80)
    assert transposer(o) == o
