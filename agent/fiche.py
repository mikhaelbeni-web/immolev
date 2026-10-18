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
    ("identite", "Le gestionnaire", "Votre nom, fonction et employeur ou société", "Mikhael B., gestionnaire de développement foncier chez …"),
    ("perimetre", "Le gestionnaire", "Activités suivies : promotion, hôtels, copropriétés, gestion locative, transactions…", "2 programmes en VEFA, 1 hôtel, 6 copropriétés"),
    ("biens", "Le gestionnaire", "Biens et opérations gérés (nom court, adresse, rôle de chacun)", "Hôtel Le Parc (Nice, 42 chambres) ; Résidence Les Pins (copro 38 lots)"),
    ("equipe", "L'équipe", "Qui travaille avec vous, avec quel rôle ?", "Sarah : assistante ; cabinet X : comptable"),
    ("validation", "L'équipe", "Qui valide quoi (devis, paiements, appels de fonds, travaux) ?", "Paiements > 5 000 € validés par Mikhael"),
    ("logiciels", "Outils", "Logiciels utilisés et pour quoi (copropriété, gestion locative, hôtel, comptabilité, banque)", "Copro : … ; hôtel : PMS … ; compta : …"),
    ("deroule", "Façon de travailler", "Étapes d'un dossier type chez vous (opération, sinistre, travaux, clôture)", "Devis → validation → ordre de service → facture → paiement → classement"),
    ("prestataires", "Façon de travailler", "Prestataires et partenaires habituels (notaire, architecte, entreprises, syndic, banque)", "Notaire : Me … ; banque : …"),
    ("copro_habitudes", "Copropriétés", "Assemblées générales, appels de fonds, conseil syndical : vos habitudes et échéances", "AG en mai, appels trimestriels le 1er"),
    ("hotel_habitudes", "Hôtels", "Indicateurs suivis et rythme de reporting (TO, prix moyen, RevPAR…)", "Rapport hebdo le lundi"),
    ("mails", "Communication", "Adresses mail utilisées (pro, perso) et signature des mails", ""),
    ("ton", "Communication", "Comment l'agent doit-il vous répondre ?", "Court, tutoiement, sans formule de politesse"),
    ("societe", "Votre société", "Votre société : forme juridique, activité, date de clôture, régime de TVA et d'impôt", "SAS, holding, clôture 31/12, IS"),
    ("comptable", "Votre société", "Expert-comptable (cabinet, contact) et logiciel de comptabilité", "Cabinet …, envoi des pièces le 5 du mois"),
    ("remuneration", "Votre société", "Comment vous vous rémunérez (salaire, dividendes, honoraires) et à quel rythme", "Salaire mensuel + dividendes en juin"),
    ("charges", "Votre société", "Charges et échéances récurrentes (loyers, emprunts, URSSAF, assurances)", "Emprunt le 5, URSSAF le 15"),
    ("foyer", "Vie personnelle", "Foyer fiscal : situation, nombre de parts, personnes à charge", "Marié, 2 enfants, 3 parts"),
    ("revenus", "Vie personnelle", "Sources de revenus du foyer (salaires, dividendes, revenus fonciers, LMNP, SCI)", "Salaire, dividendes, 2 appartements en location nue"),
    ("patrimoine", "Vie personnelle", "Patrimoine immobilier et financier à suivre (SCI, biens, crédits, placements)", "SCI familiale (2 biens), résidence principale avec crédit"),
    ("echeances_perso", "Vie personnelle", "Échéances personnelles à rappeler (déclaration de revenus, taxe foncière, assurances)", "Déclaration en ligne en mai"),
    ("confidentiel", "Limites", "Qui peut voir les données sensibles (revenus, impôts, comptes, salaires) ?", "Seulement Mikhael, en message privé"),
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
