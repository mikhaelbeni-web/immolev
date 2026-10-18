# Plateforme agent Immolev : module 1, saisie d'ordonnance

Photo d'ordonnance optique → données structurées → contrôles automatiques → relecture et validation par l'opticien → envoi direct au logiciel principal d'optique. La plateforme ne stocke aucune donnée patient ; elle garde seulement un journal d'actions sans donnée médicale.

La marche à suivre complète est dans [MARCHE-A-SUIVRE.md](MARCHE-A-SUIVRE.md), l'analyse des 8 plateformes et l'enchaînement des tâches dans [PLATEFORMES-ET-TACHES.md](PLATEFORMES-ET-TACHES.md).

## Contenu

| Fichier | Rôle |
|---|---|
| `ordonnance/schema.py` | Schéma d'une ordonnance (patient, prescripteur, OD/OG, addition, EP, équipement) |
| `ordonnance/extract.py` | Appel à Claude (vision + sortie structurée validée par l'API) |
| `ordonnance/validation.py` | Contrôles déterministes : pas de 0,25, plages, axe obligatoire si cylindre, validité selon l'âge, champs obligatoires ; transposition en cylindre négatif |
| `ordonnance/destination.py` | Envoi au logiciel principal (connecteur à écrire quand le logiciel sera connu) et journal d'audit sans donnée médicale |
| `app.py` | Page web : prendre la photo, relire, corriger, valider puis envoyer. Une alerte bloquante empêche l'envoi |
| `agent/telegram.py` | Bot Telegram : membres autorisés seulement, photo effacée du groupe, boutons Confirmer / Annuler |
| `agent/orchestrateur.py` | Claude comprend la demande, exécute les lectures, met les écritures en attente de confirmation |
| `agent/navigateur.py` | Pilotage de Chrome sans curseur : l'agent lit les pages, suit les liens, remplit les champs ; tout clic de bouton attend la confirmation ; relevé des écrans (structure sans valeurs) dans `procedures/ecrans/` |
| `agent/connecteurs_mcp.py` | Connecteurs MCP (Outlook/Hotmail, Gmail, autres) : outils découverts automatiquement, lecture libre seulement si déclarée, tout le reste sur confirmation |
| `connecteurs/gmail_mcp.py` | Connecteur Gmail d'Immolev (serveur MCP) ; mode démonstration sans compte avec `GMAIL_FAUX=1` |
| `agent/outils.py` | Catalogue d'actions : lire et corriger une ordonnance, saisir dans MyEasyOptic ; recherche client et droits prévues mais pas encore branchées |
| `tests/` | 24 tests (contrôles, transposition, page web, orchestrateur, bot Telegram, pilotage d'un vrai Chrome sur un faux logiciel, connecteur MCP avec un faux serveur de messagerie) |

## Installer sur le PC du magasin (Windows)

1. Installer [Python 3.11 ou plus](https://www.python.org/downloads/) en cochant « Add python.exe to PATH », et Google Chrome.
2. Copier le dossier `plateforme-agent` sur le PC, double-cliquer `installer.bat`. Il installe tout, lance les tests (attendu : 24 passed), puis demande la clé API Claude, le jeton du bot et les identifiants Telegram autorisés. Ces secrets vont dans le coffre de Windows (Gestionnaire d'identification), jamais dans un fichier.
3. Double-cliquer `lancer.bat`. Une fenêtre Chrome s'ouvre : s'y connecter à MyEasyOptic et aux portails, une fois.
4. Laisser la fenêtre noire ouverte : c'est l'agent qui écoute le groupe Telegram.

## Lancer en local (développement)

```bash
python3 -m pip install -r requirements.txt
export ANTHROPIC_API_KEY=...        # clé créée sur console.anthropic.com, jamais collée dans un chat
python3 -m pytest tests             # doit afficher 24 passed
uvicorn app:app --host 0.0.0.0 --port 8000
```

Ouvrir `http://localhost:8000` (ou l'IP du poste depuis un téléphone du magasin) et photographier une ordonnance.
En ligne de commande : `python3 -m ordonnance photo.jpg` (code de sortie 1 s'il reste une alerte bloquante).

## Pilotage de Chrome

Au premier lancement, l'agent ouvre une fenêtre Chrome avec un profil dédié (`profil-chrome/`). Connecte-toi toi-même dans cette fenêtre à MyEasyOptic et aux portails, une seule fois : les sessions restent ouvertes. L'agent ne lit ni ne remplit jamais un mot de passe.

Ce que l'agent fait seul : lire une page (cadres/iframes compris), ouvrir une adresse, suivre un lien ou un onglet, remplir un champ (rien n'est enregistré), cliquer un bouton sans risque (Rechercher, Actualiser, Afficher, Filtrer, Suivant… liste `BOUTONS_SANS_RISQUE` dans `agent/navigateur.py`). Ce qui attend ton clic « Confirmer » dans Telegram : tout clic sur un bouton, avec l'aperçu des champs du formulaire.

Pour apprendre un écran, écris dans Telegram : « Ouvre la fiche du client test dans MyEasyOptic et relève l'écran sous le nom myeasyoptic_fiche_client ». La structure (libellés, types de champs, boutons, sans aucune valeur) est enregistrée dans `procedures/ecrans/`.

Limites connues : testé seulement sur une page imitant un logiciel, pas encore sur MyEasyOptic. Le contenu des pages lues, données patients comprises, est envoyé à l'API Claude.

## Connecteurs MCP (messagerie et autres logiciels)

L'agent se branche à n'importe quel serveur MCP déclaré dans `connecteurs.json` (modèle : `connecteurs.exemple.json`). Chaque outil du serveur devient disponible pour Claude. Un outil n'est utilisé sans confirmation que s'il est déclaré en lecture seule par le serveur ou listé dans `lecture` ; envoyer, supprimer, créer ou modifier passe toujours par « Confirmer ».

La messagerie est **au choix de l'opticien** : `installer.bat` (via `configurer.py`) demande Gmail, Outlook/Hotmail ou Microsoft 365 pro, lance la connexion et écrit `connecteurs.json`.

| Messagerie | Connecteur | Ce qu'il fait | Prérequis |
|---|---|---|---|
| Gmail | `connecteurs/gmail_mcp.py`, écrit pour Immolev (API Gmail officielle) | Chercher, lire (texte + noms des pièces jointes) sans confirmation ; brouillon et envoi sur confirmation | Un client OAuth « Application de bureau » dans Google Cloud, fichier `gmail_client_secret.json` à côté de l'agent. Jeton rangé dans le coffre Windows |
| Hotmail / Outlook.com | `@softeria/ms-365-mcp-server` (open source) | Mails, dossiers, pièces jointes, agenda ; écritures sur confirmation | Node.js sur le PC. Noms des outils en lecture à vérifier au premier lancement (confiance moyenne) |
| Microsoft 365 pro | Même connecteur, option `--org-mode` | Idem | Idem |

**Avant de vendre, côté Google :** lire et préparer des mails Gmail utilise des autorisations que Google classe « restreintes ». Pour des clients extérieurs à ta société, il faut faire vérifier l'application par Google et passer une évaluation de sécurité annuelle (CASA), payante et longue de plusieurs semaines **[M-H]**. En attendant, le connecteur fonctionne en mode test : chaque opticien doit être ajouté comme utilisateur test, et la connexion est à refaire régulièrement (Google limite la durée des jetons en mode test) **[M]**. Côté Microsoft, prévoir d'enregistrer ta propre application Azure pour la version commerciale **[M]**.

Ajouter un logiciel = ajouter un bloc dans `connecteurs.json` et relancer. Au démarrage, le journal affiche chaque connecteur avec son nombre d'outils, ou « HORS SERVICE » et la raison.

## Lancer l'agent Telegram

1. Sur Telegram, écrire à @BotFather, `/newbot`, récupérer le jeton. Le ranger dans le coffre de secrets, jamais dans un chat.
2. Créer le groupe du magasin, y ajouter le bot et le nommer administrateur (droit de supprimer les messages).
3. Récupérer l'identifiant numérique de chaque membre (par exemple avec @userinfobot).
4. Sur l'ordinateur du magasin :

```bash
export TELEGRAM_TOKEN=...  TELEGRAM_MEMBRES=111111111,222222222  ANTHROPIC_API_KEY=...
export CONNECTEURS=connecteurs.json   # facultatif
# TELEGRAM_PHOTOS=0 pour refuser les photos d'ordonnance dans le groupe (acceptées par défaut, choix du 15/10)
python3 -m agent.telegram   # ouvre aussi la fenêtre Chrome de l'agent
```

Test : envoyer une photo d'ordonnance dans le groupe. Attendu : la photo disparaît, l'agent répond avec les alertes puis un message « À confirmer » montrant OD/OG. Tant que le connecteur MyEasyOptic n'existe pas, « Confirmer » répond que le logiciel n'est pas configuré.

## Limites connues

- Pas encore testé sur de vraies ordonnances : la précision réelle est inconnue tant que l'étape 1 de la marche à suivre n'est pas faite.
- Règle de validité codée : verres 1 an avant 16 ans, 5 ans de 16 à 42 ans, 3 ans après ; lentilles 1 an avant 16 ans, 3 ans après (décret 2016-1381). Confiance moyenne sur la lecture exacte du texte : à faire confirmer avant de bloquer des dossiers en production.
- Le connecteur vers le logiciel principal n'existe pas encore : tant qu'il manque, la validation affiche « Non envoyée » et rien n'est perdu ni stocké.
- Coût estimé par ordonnance : de l'ordre de 0,05 à 0,10 $ avec Claude Opus 5.5 (estimation, à mesurer sur les vrais tests).
