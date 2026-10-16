"""Règles du magasin : ce que l'agent doit savoir du fonctionnement de la boutique pour poser moins de questions.

Texte libre écrit par l'opticien dans le panneau (ou ajouté par « retiens : … » sur Telegram, après
confirmation). Ajouté au prompt système à chaque demande. Jamais de donnée patient.
"""
from __future__ import annotations

from datetime import date

from .acces import dossier_donnees

MODELE = """# Le magasin
- Nom, adresse, horaires :
- Logiciel principal : MyEasyOptic (seule base des clients).

# Mutuelles fréquentes → portail à utiliser
- (ex.) Harmonie Mutuelle → Almerys
- (ex.) Mutuelle Générale → Viamedis

# Habitudes de saisie dans MyEasyOptic
- (ex.) Toujours renseigner le prescripteur et le RPPS.
- (ex.) Les dossiers sont créés au nom de l'assuré principal.

# Fournisseurs et équipements
- (ex.) Verres : fournisseur habituel …
- (ex.) Offre 100 % Santé proposée systématiquement.

# Qui valide quoi
- (ex.) Les devis au-dessus de 1 000 € sont validés par l'opticien gérant.

# Façon de répondre
- (ex.) Réponses courtes, sans formule de politesse.
"""


def _fichier():
    return dossier_donnees() / "regles.md"


def lire() -> str:
    f = _fichier()
    return f.read_text(encoding="utf-8") if f.exists() else ""


def ecrire(texte: str) -> None:
    _fichier().write_text(texte.strip()[:20000] + "\n", encoding="utf-8")


def ajouter(regle: str) -> str:
    regle = " ".join(regle.split())
    if not regle:
        return "Règle vide : rien n'est ajouté."
    texte = lire().rstrip()
    if "# Retenu sur Telegram" not in texte:
        texte += "\n\n# Retenu sur Telegram"
    ecrire(f"{texte}\n- {regle} ({date.today():%d/%m/%Y})")
    return f"Retenu : « {regle} ». L'opticien peut la modifier dans le panneau, rubrique Règles du magasin."
