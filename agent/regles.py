"""Règles du gestionnaire : ce que l'agent doit savoir de sa façon de travailler pour poser moins de questions.

Texte libre écrit par le gestionnaire dans le panneau (ou ajouté par « retiens : … » sur Telegram, après
confirmation). Ajouté au prompt système à chaque demande. Jamais de donnée personnelle de tiers.
"""
from __future__ import annotations

from datetime import date

from .acces import dossier_donnees

MODELE = """# Le gestionnaire
- Fonction, employeur ou société :
- Logiciels principaux : (copropriété, gestion locative, hôtel, comptabilité)

# Opérations et biens suivis
- (ex.) Hôtel Le Parc : reporting hebdomadaire le lundi
- (ex.) Résidence Les Pins : copropriété, AG en mai

# Habitudes de traitement
- (ex.) Toute facture fournisseur est rattachée au bien et à l'opération avant d'être payée.
- (ex.) Les appels de fonds sont vérifiés contre le budget voté.

# Qui valide quoi
- (ex.) Les paiements au-dessus de 5 000 € sont validés par moi seul.

# Vie personnelle
- (ex.) Les sujets d'impôts et de patrimoine se traitent seulement en message privé.

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
    return f"Retenu : « {regle} ». Le gestionnaire peut la modifier dans le panneau, rubrique Règles du gestionnaire."
