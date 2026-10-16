"""Fiche du magasin (questionnaire rempli dans le panneau ou complété sur Telegram) et procédures retenues.

<données>/fiche-magasin.json : {"id_question": "réponse"} ; <données>/procedures.json : {"nom": "étapes"}.
Les deux sont ajoutés au prompt système. Jamais de donnée patient.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .acces import dossier_donnees

CONNAISSANCES = Path(__file__).with_name("connaissances")

# (identifiant, thème, question, exemple de réponse)
QUESTIONS = [
    ("magasin", "Le magasin", "Nom du magasin, adresse et téléphone", "Optizien Eyewear, 12 rue …, 75011 Paris, 01 …"),
    ("enseigne", "Le magasin", "Enseigne, groupement ou centrale d'achat (ou indépendant)", "Indépendant, adhérent à …"),
    ("finess", "Le magasin", "N° FINESS et SIRET (utiles pour les portails)", ""),
    ("horaires", "Le magasin", "Horaires d'ouverture", "Mardi-samedi 10h-19h"),
    ("equipe", "L'équipe", "Qui travaille au magasin, avec quel rôle ?", "Mikhael : opticien gérant ; Sarah : opticienne"),
    ("validation", "L'équipe", "Qui valide quoi (devis, PEC, commandes, remises) ?", "Les devis > 800 € sont validés par Mikhael"),
    ("reseaux", "Tiers payant", "Réseaux de soins partenaires du magasin", "Kalivia, Santéclair, Itelis…"),
    ("portails", "Tiers payant", "Quel opérateur ou réseau sur la carte → quel portail ?", "Almerys → portail Almerys ; Viamedis → portail Viamedis"),
    ("pec_habitudes", "Tiers payant", "Comment faites-vous les prises en charge ? (MyEasyOptic ou portail, qui relance, quand)", ""),
    ("deroule", "Façon de travailler", "Étapes d'un dossier chez vous, de l'ordonnance à la livraison", "Ordonnance → fiche client → devis → PEC → commande → livraison → facture"),
    ("saisie", "Façon de travailler", "Habitudes de saisie dans MyEasyOptic", "Toujours renseigner le prescripteur et le RPPS"),
    ("fournisseurs", "Fournisseurs", "Laboratoires de verres et fournisseurs principaux, délais habituels", "Verres : … (5 jours)"),
    ("tarifs", "Commerce", "Offres et politique tarifaire (2e paire, remises, 100 % Santé)", ""),
    ("mails", "Communication", "Adresse mail du magasin et signature des mails", ""),
    ("ton", "Communication", "Comment l'agent doit-il répondre à l'équipe ?", "Court, tutoiement, sans formule de politesse"),
    ("interdits", "Limites", "Ce que l'agent ne doit jamais faire", ""),
]
IDS = {q[0] for q in QUESTIONS}


def _lire(nom: str) -> dict:
    f = dossier_donnees() / nom
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    except ValueError:
        return {}


def _ecrire(nom: str, d: dict) -> None:
    f = dossier_donnees() / nom
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def lire() -> dict:
    return {k: v for k, v in _lire("fiche-magasin.json").items() if k in IDS and str(v).strip()}


def ecrire(reponses: dict) -> None:
    _ecrire("fiche-magasin.json", {k: " ".join(str(v).split())[:1500] for k, v in reponses.items() if k in IDS and str(v).strip()})


def completer(question: str, reponse: str) -> str:
    """Outil de l'agent (après confirmation) : question = identifiant du questionnaire."""
    if question not in IDS:
        return f"Question inconnue : {question}. Identifiants possibles : {', '.join(sorted(IDS))}."
    reponse = " ".join(reponse.split())
    if not reponse:
        return "Réponse vide : rien n'est enregistré."
    d = lire()
    d[question] = f"{d[question]} ; {reponse}" if d.get(question) else reponse
    ecrire(d)
    return f"Fiche du magasin complétée ({question}). L'opticien peut la modifier dans le panneau, carte Questionnaire."


def procedures() -> dict:
    return _lire("procedures.json")


def retenir_procedure(nom: str, etapes: str) -> str:
    nom, etapes = " ".join(nom.split())[:80], etapes.strip()[:3000]
    if not nom or not etapes:
        return "Nom ou étapes vides : rien n'est retenu."
    d = procedures()
    d[nom] = f"{etapes}\n(retenue le {date.today():%d/%m/%Y})"
    _ecrire("procedures.json", d)
    return f"Procédure « {nom} » retenue : je la suivrai la prochaine fois."


def supprimer_procedure(nom: str) -> None:
    d = procedures()
    d.pop(nom, None)
    _ecrire("procedures.json", d)


def connaissances() -> str:
    return "\n\n".join(f.read_text(encoding="utf-8").strip() for f in sorted(CONNAISSANCES.glob("*.md")))


def texte_prompt() -> str:
    d = lire()
    lignes = [f"- {q} : {d[i]}" for i, _, q, _ in QUESTIONS if i in d]
    manque = [i for i, *_ in QUESTIONS if i not in d]
    parties = ["# Fiche du magasin (questionnaire rempli par l'opticien)\n" + ("\n".join(lignes) if lignes else "(vide)")]
    if manque:
        parties.append("Questions encore sans réponse (identifiants) : " + ", ".join(manque) + ".\nSi l'une d'elles t'empêche "
                       "de bien faire une tâche, pose la question à l'équipe en une ligne, puis propose completer_fiche avec "
                       "la réponse. Ne pose pas plus d'une question de ce type par demande.")
    p = procedures()
    if p:
        parties.append("# Procédures retenues dans ce magasin (suis-les en priorité)\n" +
                       "\n\n".join(f"## {n}\n{e}" for n, e in p.items()))
    parties.append("Quand tu as mené à bien une tâche sur un site en cherchant ton chemin, propose retenir_procedure avec les "
                   "étapes exactes (écrans, champs, boutons), sans aucune donnée de client.")
    return "\n\n".join(parties)
