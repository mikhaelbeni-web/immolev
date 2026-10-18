# Immolev : l'agent IA du gestionnaire immobilier

Copie d'Optizien, même architecture, adaptée à un gestionnaire de développement foncier : promotion immobilière, gestion hôtelière, copropriétés, gestion locative, comptabilité, et sa vie personnelle (sa société, son foyer fiscal, son revenu fiscal de référence, son patrimoine).

L'agent tourne sur le PC du gestionnaire, reçoit les demandes par Telegram, lit les documents, navigue dans Chrome et la messagerie, et attend un clic « Confirmer » avant toute écriture. Rien n'est stocké sur un serveur : les données restent dans `%LOCALAPPDATA%\Immolev` et les secrets dans le coffre Windows (service `immolev`), séparés de ceux d'Optizien.

La marche à suivre est dans [MARCHE-A-SUIVRE.md](MARCHE-A-SUIVRE.md).

## Contenu

| Fichier | Rôle |
|---|---|
| `document/schema.py` | Schéma d'un document : facture, devis, appel de fonds (copropriété, VEFA), quittance, avis d'impôt sur le revenu, de taxe foncière ou de CFE, relevé, bulletin de paie |
| `document/extract.py` | Appel à Claude (vision + sortie structurée validée par l'API) |
| `document/validation.py` | Contrôles déterministes : HT + TVA = TTC, taux de TVA, lignes de TVA, clé IBAN, clé SIRET/SIREN, dates et échéances, numéro de facture, RFR et nombre de parts |
| `document/destination.py` | Envoi au logiciel de comptabilité (connecteur à écrire quand le logiciel sera connu) et journal d'audit sans nom ni montant |
| `app.py` | Page web : photographier un document, relire, corriger, valider puis envoyer. Une alerte bloquante empêche l'envoi |
| `agent/orchestrateur.py` | Prompt système (pro + perso), boucle Claude, lectures directes, écritures en attente de confirmation |
| `agent/connaissances/` | Base de connaissances chargée à chaque demande : métiers et chaînes de dossier (promotion, copropriété, gestion locative, hôtellerie, transaction), fiscalité immobilière, société du gestionnaire, vie personnelle |
| `agent/fiche.py` | Questionnaire du gestionnaire (biens, logiciels, société, foyer fiscal, patrimoine…) |
| `agent/outils.py` | Actions : lire, corriger et classer un document ; recherche dans les logiciels de gestion prévue mais pas encore branchée |
| `agent/telegram.py`, `agent/navigateur.py`, `agent/connecteurs_mcp.py`, `connecteurs/`, `panneau/` | Repris d'Optizien sans changement d'architecture |
| `site/` | Site Vercel : page publique, espace client, passerelle Claude `/api/ia` |
| `tests/` | 67 tests |

## Installer sur le PC (Windows)

1. Installer [Python 3.11 ou plus](https://www.python.org/downloads/) en cochant « Add python.exe to PATH », et Google Chrome.
2. Double-cliquer `installer.bat`. Il installe tout, lance les tests, puis demande la clé API Claude, le jeton du bot et les identifiants Telegram autorisés, rangés dans le coffre de Windows.
3. Double-cliquer `lancer.bat`. Une fenêtre Chrome s'ouvre : s'y connecter une fois aux logiciels de gestion, à la banque et à impots.gouv.

## Lancer en local (développement)

```bash
python3 -m pip install -r requirements.txt
export ANTHROPIC_API_KEY=...        # jamais collée dans un chat
python3 -m pytest tests             # doit afficher 67 passed
uvicorn app:app --host 0.0.0.0 --port 8000
```

En ligne de commande : `python3 -m document photo.jpg` (code de sortie 1 s'il reste une alerte bloquante).

## Site et passerelle (Vercel)

Projet Vercel séparé de celui d'Optizien, racine `site/`. Variables à créer dans Vercel :

| Variable | Contenu |
|---|---|
| `ANTHROPIC_API_KEY` | Clé de l'API Claude |
| `IMMOLEV_COMPTES` | `identifiant:sha256(identifiant:motdepasse);…` |
| `IMMOLEV_SECRET` | Chaîne aléatoire pour signer les sessions de l'espace client |

L'adresse de la passerelle est dans `agent/passerelle.py` (`https://immolev.vercel.app/api/ia`) : à changer si le domaine Vercel diffère.

## Limites connues

- Pas encore testé sur de vrais documents : la précision réelle de l'extraction est inconnue.
- Aucun connecteur de logiciel de copropriété, de gestion locative, de PMS hôtelier ni de comptabilité : la recherche répond « pas encore branché » et le classement « Non envoyé », sans rien perdre.
- Les repères fiscaux et juridiques de `agent/connaissances/` sont datés de 2026 ; ceux marqués [V] sont à faire valider par l'expert-comptable ou le notaire avant de s'y fier.
- Les données personnelles et fiscales lues par l'agent sont envoyées à l'API Claude.
