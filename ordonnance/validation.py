"""Contrôles déterministes après extraction. Aucune donnée n'entre dans un portail sans passer ici."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal, Optional

from .schema import Oeil, Ordonnance

Niveau = Literal["bloquant", "a_verifier"]


@dataclass
class Alerte:
    niveau: Niveau
    champ: str
    message: str


def _pas_025(v: float) -> bool:
    return abs(v * 4 - round(v * 4)) < 1e-6


def transposer(oeil: Oeil) -> Oeil:
    """Convertit en convention cylindre négatif (celle de la plupart des logiciels et portails)."""
    if oeil.cylindre is None or oeil.cylindre <= 0 or oeil.sphere is None or oeil.axe is None:
        return oeil
    axe = oeil.axe + 90 if oeil.axe <= 90 else oeil.axe - 90
    return oeil.model_copy(update={"sphere": round(oeil.sphere + oeil.cylindre, 2), "cylindre": -oeil.cylindre, "axe": axe})


def _age(naissance: date, a: date) -> int:
    return a.year - naissance.year - ((a.month, a.day) < (naissance.month, naissance.day))


def duree_validite_ans(ordo: Ordonnance) -> Optional[int]:
    """Durée de validité (Code de la santé publique, art. D4362-12-1) : verres 1 an < 16 ans, 5 ans 16-42 ans,
    3 ans > 42 ans ; lentilles 1 an < 16 ans, 3 ans au-delà. None si l'âge est inconnu."""
    if ordo.patient_date_naissance is None or ordo.date_prescription is None:
        return None
    age = _age(ordo.patient_date_naissance, ordo.date_prescription)
    lentilles_seules = ordo.type_equipement == ["lentilles"]
    if age < 16:
        return 1
    if lentilles_seules:
        return 3
    return 5 if age <= 42 else 3


def _controler_oeil(nom: str, o: Oeil, alertes: list[Alerte]) -> None:
    if o.sphere is None and o.cylindre is None:
        alertes.append(Alerte("bloquant", f"{nom}.sphere", "Ni sphère ni cylindre lus pour cet œil"))
        return
    for champ, v, lo, hi in (("sphere", o.sphere, -30, 30), ("cylindre", o.cylindre, -10, 10), ("addition", o.addition, 0.5, 4.0)):
        if v is None:
            continue
        if not _pas_025(v):
            alertes.append(Alerte("bloquant", f"{nom}.{champ}", f"{v} n'est pas un multiple de 0,25 : lecture probablement fausse"))
        if not lo <= v <= hi:
            alertes.append(Alerte("bloquant", f"{nom}.{champ}", f"{v} hors plage plausible [{lo} ; {hi}]"))
    if o.cylindre not in (None, 0):
        if o.axe is None:
            alertes.append(Alerte("bloquant", f"{nom}.axe", "Cylindre présent sans axe"))
        elif not 0 <= o.axe <= 180:
            alertes.append(Alerte("bloquant", f"{nom}.axe", f"Axe {o.axe} hors 0-180"))
    if o.cylindre in (None, 0) and o.axe not in (None, 0):
        alertes.append(Alerte("a_verifier", f"{nom}.axe", "Axe sans cylindre"))


def valider(ordo: Ordonnance, aujourd_hui: Optional[date] = None) -> list[Alerte]:
    aujourd_hui = aujourd_hui or date.today()
    alertes: list[Alerte] = []

    for champ in ("patient_nom", "date_prescription", "prescripteur_nom"):
        if getattr(ordo, champ) is None:
            alertes.append(Alerte("bloquant", champ, "Champ obligatoire pour une prise en charge"))
    for champ in ordo.champs_illisibles:
        alertes.append(Alerte("a_verifier", champ, "Signalé illisible ou ambigu par l'extraction"))

    _controler_oeil("od", ordo.od, alertes)
    _controler_oeil("og", ordo.og, alertes)

    progressif = any(t in ordo.type_equipement for t in ("lunettes_progressifs", "lunettes_double_foyer", "lunettes_vp"))
    if progressif and ordo.od.addition is None and ordo.og.addition is None:
        alertes.append(Alerte("a_verifier", "addition", "Équipement de près ou progressif sans addition lue"))
    if ordo.od.addition is not None and ordo.og.addition is not None and ordo.od.addition != ordo.og.addition:
        alertes.append(Alerte("a_verifier", "addition", "Additions OD et OG différentes, cas rare"))
    if ordo.ecart_pupillaire_mm is not None and not 45 <= ordo.ecart_pupillaire_mm <= 80:
        alertes.append(Alerte("a_verifier", "ecart_pupillaire_mm", "Écart pupillaire hors 45-80 mm"))

    if ordo.date_prescription is not None:
        if ordo.date_prescription > aujourd_hui:
            alertes.append(Alerte("bloquant", "date_prescription", "Date dans le futur"))
        validite = duree_validite_ans(ordo)
        if validite is None:
            alertes.append(Alerte("a_verifier", "date_prescription", "Validité non calculable sans date de naissance"))
        else:
            try:
                fin = ordo.date_prescription.replace(year=ordo.date_prescription.year + validite)
            except ValueError:  # 29 février
                fin = ordo.date_prescription.replace(year=ordo.date_prescription.year + validite, day=28)
            if aujourd_hui > fin:
                alertes.append(Alerte("bloquant", "date_prescription", f"Ordonnance expirée le {fin:%d/%m/%Y} (validité {validite} an(s))"))

    if ordo.prescripteur_rpps and not (ordo.prescripteur_rpps.isdigit() and len(ordo.prescripteur_rpps) == 11):
        alertes.append(Alerte("a_verifier", "prescripteur_rpps", "Un RPPS compte 11 chiffres"))
    return alertes
