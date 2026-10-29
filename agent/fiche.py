"""Fiche du gestionnaire (questionnaire rempli dans le panneau ou complété sur Telegram) et procédures retenues.

<données>/fiche-gestionnaire.json : {"id_question": "réponse"} ; <données>/procedures.json : {"nom": "étapes"}.
Les deux sont ajoutés au prompt système. Jamais de donnée personnelle.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .acces import dossier_donnees

CONNAISSANCES = Path(__file__).with_name("connaissances")

# (identifiant, thème, question, exemple de réponse)
QUESTIONS = [
    # Questionnaire sur mesure : seulement ce que les « Règles du gestionnaire » ne disent pas encore.
    ("contacts_equipe", "Contacts", "Coordonnées (mail ou téléphone) de Paolo, Zack et Thomas, et d'Even Gestion (David, Waren, Saul)", "Paolo : 06… ; Even Gestion : contact@…"),
    ("contact_dan", "Contacts", "Adresse mail de Dan Penia (comptable de vos sociétés) et de Béatrice Robin", "dan@…"),
    ("mails_vip", "Mails", "Expéditeurs ou sujets toujours urgents, à vous signaler tout de suite (en plus des fuites)", "Sacha Levy, syndics, mises en demeure, huissiers"),
    ("signature", "Mails", "Signature à mettre en bas des mails, et vouvoiement ou tutoiement selon les destinataires", "Mikhael Benichou – Milev Invest ; vouvoiement sauf équipe"),
    ("hotels_suivi", "Hôtels", "Chiffres à préparer pour le rendez-vous avec Zack et Thomas (taux d'occupation, prix moyen, avis, ménage…) et sur quelle période", "Semaine écoulée : TO, prix moyen, CA, avis < 4"),
    ("gestion_directe", "Gestion directe", "Appartements et commerces en gestion directe (81 rue de Sèvres, Saint-Marc, Washington, Ozoir) : avec quel outil faites-vous quittances, relances et suivi des loyers ?", "Tableau Excel ; quittances Rentila…"),
    ("prestataires_externes", "Gestion directe", "Que contrôler chez Check My Guest, Majesti et Laforêt (sociétés de gestion), et à quel rythme ?", "Reversement mensuel avant le 10"),
    ("facturation_milev", "Vos sociétés", "Facturation de milev invest à Sacha Levy : rythme, montant ou mode de calcul, outil de facturation", "Facture mensuelle le 1er, forfait"),
    ("banques", "Vos sociétés", "Banque de mikalevinvest et de milev invest (le CIC tient LM Invest)", "Qonto pour milev invest"),
    ("echeances", "Vos sociétés", "Échéances à rappeler : clôtures d'exercice, TVA, CFE, déclaration de revenus, taxes foncières", "Clôture 31/12, TVA trimestrielle"),
    ("foyer", "Vie personnelle", "Foyer fiscal (situation, nombre de parts) et revenus à suivre pour votre revenu fiscal de référence", "Marié, 2 enfants, 3 parts"),
    ("interdits", "Limites", "Ce que l'agent ne doit jamais faire, même si on le lui demande", "Ne jamais payer, ne jamais écrire à un locataire sans accord"),
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
    return {k: v for k, v in _lire("fiche-gestionnaire.json").items() if k in IDS and str(v).strip()}


def ecrire(reponses: dict) -> None:
    _ecrire("fiche-gestionnaire.json", {k: " ".join(str(v).split())[:1500] for k, v in reponses.items() if k in IDS and str(v).strip()})


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
    return f"Fiche du gestionnaire complétée ({question}). Le gestionnaire peut la modifier dans le panneau, carte Questionnaire."


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


def notes_sites() -> dict:
    return _lire("notes-sites.json")


def noter_site(site: str, note: str) -> str:
    """Mémoire technique d'un site : méthode de connexion qui marche, erreur rencontrée, solution, étape humaine."""
    site, note = " ".join(site.split())[:60], " ".join(note.split())[:300]
    if not site or not note:
        return "Site ou note vide : rien n'est noté."
    d = notes_sites()
    liste = [n for n in d.get(site, []) if n.split(" (")[0] != note]
    liste.append(f"{note} ({date.today():%d/%m/%Y})")
    d[site] = liste[-8:]
    _ecrire("notes-sites.json", d)
    return f"Noté pour {site}."


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
    parties = ["# Fiche du gestionnaire (questionnaire rempli par le gestionnaire)\n" + ("\n".join(lignes) if lignes else "(vide)")]
    if manque:
        parties.append("Questions encore sans réponse (identifiants) : " + ", ".join(manque) + ".\nSi l'une d'elles t'empêche "
                       "de bien faire une tâche, pose la question à l'équipe en une ligne, puis propose completer_fiche avec "
                       "la réponse. Ne pose pas plus d'une question de ce type par demande.")
    ns = notes_sites()
    if ns:
        parties.append("# Notes techniques par site (méthodes qui marchent, erreurs déjà vues)\n" +
                       "\n".join(f"- {site} : " + " | ".join(n) for site, n in ns.items()))
    p = procedures()
    if p:
        parties.append("# Procédures retenues chez ce gestionnaire (suis-les en priorité)\n" +
                       "\n\n".join(f"## {n}\n{e}" for n, e in p.items()))
    parties.append("Quand tu as mené à bien une tâche sur un site en cherchant ton chemin, propose retenir_procedure avec les "
                   "étapes exactes (écrans, champs, boutons), sans aucune donnée de client.")
    return "\n\n".join(parties)
