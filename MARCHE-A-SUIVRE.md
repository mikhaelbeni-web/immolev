# Plateforme agent pour opticien : marche à suivre

Version du 15/10/2026. Confiance notée **[H]** haute, **[M]** moyenne, **[B]** basse.

## 1. Ce qui change la conception avant d'écrire du code

**a. « Un robot qui navigue de page en page » recouvre deux techniques très différentes.**

| | Agent visuel (Claude computer use pilote Chrome à chaque dossier) | Scripts navigateur (Playwright) par portail, Claude fournit les données et décide |
|---|---|---|
| Mise en route | Rapide, aucun script | Un script par portail et par tâche |
| Vitesse par dossier | Lente (capture d'écran à chaque clic) | Quelques secondes |
| Coût par dossier | Élevé (beaucoup d'images envoyées) | Quasi nul hors extraction |
| Fiabilité | Variable, peut cliquer au mauvais endroit | Déterministe, casse quand le portail change d'écran |
| Traçabilité | Faible | Chaque action est journalisée |

Recommandation **[M]** : scripts Playwright pour les tâches répétées (consulter des droits, préparer une PEC, lire les paiements), et agent visuel seulement pour les écrans imprévus ou pour écrire un nouveau script. Claude reste l'orchestrateur : il lit l'ordonnance, choisit le portail selon la carte de tiers payant, appelle le bon script, explique les rejets.

**b. Les CGU des portails sont le premier risque, avant la technique.** Les accès aux portails des OTP sont nominatifs et rattachés au professionnel ; l'automatisation y est souvent interdite ou non prévue **[M, CGU non lues une par une]**. Un compte suspendu bloque le tiers payant du magasin. La fuite Almerys/Viamedis de 2024 est partie d'identifiants de professionnels volés **[H]**, donc les OTP surveillent les connexions anormales. Ordre de préférence : intégration déjà présente dans le logiciel d'optique > accès partenaire ou API négocié > automatisation du portail avec accord écrit > automatisation sans accord (à éviter).

**c. Une ordonnance est une donnée de santé.** RGPD article 9 et, dès qu'un tiers stocke ces données pour le compte du magasin, obligation d'un hébergeur certifié HDS (article L1111-8 du Code de la santé publique) **[H]**. Si l'app est vendue à d'autres opticiens, la société devient sous-traitante de chacun : HDS, contrat de sous-traitance et analyse d'impact (AIPD) deviennent incontournables **[H]**. Envoyer l'image à l'API Claude est un traitement par un sous-traitant hors HDS **[M, statut à vérifier au moment du choix]** : la parade la plus simple est de ne rien stocker chez Anthropic (rétention zéro à demander, ou Claude via un fournisseur cloud certifié HDS en région UE) et de stocker les dossiers uniquement chez un hébergeur HDS. À valider avec un DPO ou un avocat avant la mise en production, pas avant le prototype.

**d. Les identifiants ne passent jamais par le chat ni par le code.** Messagerie : connexion OAuth (connecteur Gmail ou Microsoft 365), droits en lecture limités aux dossiers utiles. Portails et logiciel d'optique : coffre-fort de secrets (Bitwarden Secrets Manager, 1Password, ou un coffre du cloud HDS), lu par les scripts au moment de l'exécution. La double authentification reste faite par un humain ; le script réutilise ensuite la session du navigateur.

**e. Un humain valide avant tout envoi.** Pendant les premiers mois l'agent prépare, l'opticien relit et clique « envoyer ». On retire ce contrôle tâche par tâche, quand le taux d'erreur mesuré le justifie.

## 2. Architecture cible : un agent sur l'ordinateur du magasin, commandé par Telegram

```
Équipe (groupe Telegram : texte, photo d'ordonnance, boutons Confirmer / Annuler)
   │  seuls les identifiants Telegram autorisés sont écoutés
   ▼
Ordinateur du magasin, allumé en permanence (agent/telegram.py)
   │  photos gardées en mémoire 1 h au plus, effacées du groupe dès réception
   ▼
Orchestrateur Claude (agent/orchestrateur.py)
   ├─ lectures : exécutées directement (lire une ordonnance, chercher un client, vérifier des droits)
   └─ écritures : mises en attente, exécutées seulement après clic « Confirmer » d'un membre
   ▼
Catalogue d'actions (agent/outils.py), chacune pilotant Chrome sur un écran relevé à l'avance
   ├─ MyEasyOptic (logiciel principal, seule base de données)
   ├─ portails des mutuelles marquées « non » pour la PEC dans MyEasyOptic
   └─ messagerie (connecteur OAuth)
   ▼
Journal d'actions sans donnée médicale · coffre-fort pour les mots de passe
```

**Pas de curseur ni de capture d'écran.** L'agent pilote Chrome et lit directement le contenu des pages (champs, boutons, tableaux). Deux modes : **libre pour lire et chercher** sur n'importe quelle page (« où en est ce dossier ? »), **procédure vérifiée pour écrire** (saisie relue après enregistrement, confirmation humaine). Choix de l'utilisateur, 15/10.

**L'agent ne « comprend pas tout tout seul ».** Il enchaîne des actions qu'il connaît. Une action nouvelle (« ajoute ce client dans tel portail ») s'ajoute au catalogue après relevé des écrans. Laisser un agent improviser des clics dans un logiciel de facturation santé produit des erreurs silencieuses. Pour une demande hors catalogue, l'agent répond qu'il ne sait pas encore faire. **[H]**

## 2 bis. Risques propres à Telegram

| Risque | Fait | Parade dans le prototype | Ce qui reste à décider |
|---|---|---|---|
| Données de santé chez un tiers non HDS | Les groupes et les conversations avec un bot ne sont pas chiffrés de bout en bout ; les messages sont stockés sur les serveurs de Telegram **[H]** | Photo effacée du groupe dès réception (bot administrateur), réponses avec initiales seulement | **Choix du 15/10 : photos par Telegram acceptées.** Reste à écrire ce choix dans le registre RGPD du magasin (finalité, durée, Telegram comme destinataire) et à prévenir les clients dans l'information RGPD. Retour possible avec `TELEGRAM_PHOTOS=0` |
| Effacement incomplet | Un bot ne peut effacer un message que s'il est administrateur et que le message a moins de 48 h **[H]** ; la suppression côté serveur n'est pas garantie **[M]** | Effacement immédiat | Rendre le bot administrateur du groupe |
| Compte d'un membre piraté | Celui qui contrôle le téléphone d'un membre peut demander et confirmer **[H]** | Liste blanche d'identifiants, confirmation obligatoire, journal | Mot de passe Telegram (double vérification) sur chaque compte membre |
| Instructions cachées dans un mail ou un portail | Un texte lu peut tenter de donner des ordres à l'agent **[H]** | Consigne « données, jamais instructions » et confirmation humaine de chaque écriture | Rien |
| Ordinateur allumé en permanence | Accès physique = accès à MyEasyOptic et aux portails ouverts **[H]** | Aucune | Session Windows verrouillée, profil Chrome dédié, poste hors de portée des clients |

## 2 ter. Cahier des charges reçu le 15/10 : ce que je retiens, ce que j'écarte

| Proposition | Décision | Raison |
|---|---|---|
| Agent qui travaille comme un employé dans les logiciels existants, sans API | **Retenu** | C'est l'architecture en place : catalogue d'actions + Claude qui enchaîne |
| Modules métier (clients, prescriptions, mutuelles, commandes, devis/facturation, environnement logiciel) | **Retenu** comme plan du catalogue d'actions | Chaque module devient une famille d'actions et de contrôles |
| Boucle analyse, plan, exécution, vérification, compte rendu, arrêt en cas d'échec | **Retenu** | Chaque action relit l'écran après coup pour vérifier que la saisie a bien été enregistrée |
| Confirmation humaine des actions sensibles, historique, secrets protégés, données minimisées | **Retenu**, déjà codé | Confirmation par bouton, journal, coffre-fort, initiales seulement dans Telegram |
| Application Windows installable comme point de départ | **Écarté pour la v1** | MyEasyOptic et les portails sont des sites web. Un script Chrome sur le PC du magasin suffit. Une application Windows ajoute installeur, signature et mises à jour sans rien apporter tant qu'aucun logiciel du magasin n'est une application Windows classique |
| Automatisation Windows (UI Automation) | **Gardé en réserve** | Utile seulement si un logiciel fournisseur installé sous Windows doit être piloté. À vérifier : MyEasyOptic gère déjà des commandes fournisseurs (Commande ICC, Opsysweb, avis de livraison EDI) **[H, liste de sa documentation]** |
| L'IA « observe l'écran » pour décider chaque clic | **Écarté comme mode principal** | Dans un navigateur, l'agent lit directement les champs de la page : plus rapide, moins cher, et il ne confond pas deux boutons. La capture d'écran sert seulement aux écrans imprévus, en lecture |
| Grande base de connaissances optique | **Réduit** | Claude connaît déjà l'optique. Ce qui manque, c'est la procédure exacte de chaque écran et les règles de contrôle, écrites comme code testé (déjà fait pour l'ordonnance) |
| Étape 1 « moteur de bureau sur une application de test » | **Remplacé** | On commence directement par MyEasyOptic en lecture seule sur un client test : c'est là que se trouve la valeur, et c'est sans risque |

### Les 4 demandes types, traduites en actions

| Demande | Actions nécessaires | Où | Disponible |
|---|---|---|---|
| « Où en est la commande de ces lunettes ? » | chercher client → ouvrir visite → lire statut commande | MyEasyOptic | Après relevé des écrans |
| « Vérifie la prise en charge mutuelle et ce qui manque » | chercher client → lire onglet PEC (statut, message mutuelle, « Que faire ? ») → vérifier pièces jointes (ordonnance, accord) | MyEasyOptic | Après relevé des écrans |
| « Prépare la saisie de la commande chez le fournisseur » | lire visite et devis → contrôler cohérence verres/ordonnance → préparer la commande, envoi confirmé | MyEasyOptic (commande intégrée) ou site fournisseur | Après relevé ; dépend du fournisseur |
| « Trouve les dossiers bloqués et explique pourquoi » | lister PEC orange et rouges, factures sans paiement, commandes en retard | MyEasyOptic, puis portails | Après relevé ; tâche à lancer aussi chaque matin |

## 3. Étapes, dans l'ordre

| # | Étape | Action concrète | Critère de réussite |
|---|---|---|---|
| 1 | Mesurer le module ordonnance | Photographier 30 vraies ordonnances (dont 10 manuscrites), les passer dans l'app, comparer chaque champ à la saisie humaine | Zéro erreur non signalée sur sphère, cylindre, axe, addition ; toute valeur douteuse apparaît en alerte. Sinon on ajuste les consignes avant d'aller plus loin |
| 2 | Cadre légal minimal | Lire les CGU des 2 portails les plus utilisés ; écrire aux OTP pour demander un accès partenaire ; choisir un hébergeur HDS ; inscrire le traitement au registre RGPD | Réponse écrite des OTP ; hébergeur choisi |
| 3 | Logiciel d'optique : MyEasyOptic | Logiciel web, sans API documentée, avec PEC électronique intégrée. Détail et actions dans [MYEASYOPTIC.md](MYEASYOPTIC.md) | Créer ou retrouver une fiche client test et y saisir l'ordonnance validée, sans saisie manuelle |
| 4 | Messagerie | Brancher le connecteur mail en OAuth ; l'agent classe les mails (accords PEC, rejets, relevés de paiement) | Sur une semaine, 100 % des mails de TP classés, tableau de suivi à jour |
| 5 | Premier portail, lecture seule | Script Playwright « consulter les droits » sur le portail au plus gros volume, identifiants lus dans le coffre | 20 consultations sans intervention |
| 6 | Premier portail, préparation de PEC | Le script remplit la PEC à partir de l'ordonnance validée et s'arrête avant l'envoi | 20 PEC préparées sans correction par l'opticien |
| 7 | Agent Telegram | Créer le bot (@BotFather), le groupe, la liste des membres ; lancer `python3 -m agent.telegram` sur le poste du magasin. Prototype déjà écrit | Une photo envoyée dans le groupe aboutit à une ordonnance saisie dans MyEasyOptic après un clic « Confirmer » |
| 8 | Étendre | Portail suivant par ordre de volume ; alerte quand un script casse | Chaque portail ajouté passe les critères 5 et 6 |

## 4. Ce qu'il me faut de ta part

1. Logiciel : MyEasyOptic (reçu). Reste la messagerie (Gmail ou Outlook / Microsoft 365), qui fixe l'étape 4.
2. Pour l'étape 1 : 30 photos d'ordonnances, avec les noms masqués si tu veux tester ici, ou en local sur ton poste avec l'app.
3. Aucun mot de passe dans le chat. Pour la messagerie, on passe par le connecteur officiel.

## 5. Code

Le module 1 est dans ce dossier (voir [README.md](README.md)). Pour la suite (scripts par portail, orchestrateur, déploiement), un dépôt GitHub privé est préférable à ce dossier partagé : historique, revue, déploiement automatique.

## 6. Commercialiser : par quoi commencer

### Ce que la vente change

| Sujet | Pour ton magasin seul | Dès que tu vends à d'autres opticiens |
|---|---|---|
| Statut RGPD | Tu es responsable de traitement de tes propres clients | Tu deviens **sous-traitant** de chaque magasin : contrat article 28 avec chacun, registre, AIPD, sécurité documentée **[H]** |
| Photos par Telegram | Choix acceptable si écrit dans ton registre | **Difficile à vendre** : chaque opticien acheteur devrait accepter par écrit que des ordonnances transitent par un service non HDS. Un acheteur prudent ou son DPO refusera **[M]**. Prévoir la page web du produit pour les photos, Telegram pour les commandes |
| Hébergement | Rien de stocké hors MyEasyOptic | Si ton produit stocke ou fait transiter des données de santé par tes serveurs : hébergeur certifié HDS obligatoire **[H]**. L'agent installé chez le client sans serveur central limite ce sujet |
| API Claude | Clé à ton nom | Accord de traitement des données avec Anthropic, rétention minimale à demander, mention dans les contrats clients **[M]** |
| MyEasyOptic | Tu pilotes ton propre compte | Piloter le logiciel de tes clients sans accord de l'éditeur expose à un blocage technique ou contractuel. **L'accord de MyEasySoft devient un prérequis commercial**, et ton marché se limite à ses utilisateurs tant qu'un autre logiciel n'est pas couvert **[M]** |
| Portails tiers payant | Ton compte, ton risque | Tu automatises les comptes nominatifs de tes clients : CGU à faire valider par écrit **[M]** |
| Dispositif médical | Non concerné | Probablement non concerné tant que le produit sert à la saisie administrative et ne prétend ni vérifier ni corriger une prescription sur le plan médical **[M]**. Ne jamais vendre de « contrôle de la correction » |
| Concurrence | Sans objet | OptiBot et Granit vendent déjà l'automatisation des portails **[M]** : il te faut un avantage clair (intégration MyEasyOptic, commande par message, prix) |

### Ordre des étapes

| # | Étape | Action | Critère de réussite |
|---|---|---|---|
| 1 | Prouver le gain dans ton magasin | Faire tourner le module ordonnance et une première action MyEasyOptic pendant 4 semaines ; chronométrer avant/après | Un chiffre : heures gagnées par semaine et rejets évités. Sans gain mesuré, rien à vendre |
| 2 | Concurrence et éditeur, en parallèle | Démo d'OptiBot et de Granit ; écrire à MyEasySoft pour un partenariat | Une phrase qui dit pourquoi un opticien te choisirait ; réponse écrite de l'éditeur |
| 3 | Valider la demande | Présenter le chiffre de l'étape 1 à 5 opticiens utilisateurs de MyEasyOptic, avec un prix mensuel | 3 accords écrits pour un pilote payant |
| 4 | Cadre légal | Société, CGV, contrat de sous-traitance type, AIPD, DPO externe, assurance RC professionnelle, accord de traitement avec Anthropic | Dossier complet relu par un avocat ou un DPO |
| 5 | Rendre le produit vendable | Photos par la page web, installation simple sur un PC client, mises à jour à distance, suivi des erreurs, dépôt GitHub privé | Installation chez un nouveau magasin en moins d'une heure |
| 6 | Pilote payant | 3 magasins pendant 2 mois, support direct | Les 3 renouvellent et paient |

Les étapes 1 à 3 coûtent peu et disent si le reste vaut la peine. Les étapes 4 et 5 coûtent cher : ne les lancer qu'avec les accords de l'étape 3.
