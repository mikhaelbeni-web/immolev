# Les 8 plateformes : tâches et enchaînement par l'agent

Version du 15/10/2026. Confiance : **[H]** haute, **[M]** moyenne (source secondaire ou éditeur), **[B]** basse (déduction). Complète la [fiche comparative](../tiers-payant/fiche-comparative-tiers-payant.md).

## 1. Deux prémisses à corriger

**a. Sur les 8 noms, seuls 5 sont des portails où l'agent se connecte.** Almerys, Viamedis, SP Santé, iSanté et TP+ (Santéclair) ont un espace professionnel. Génération, Mercer et Ociane ne sont pas des portails de PEC pour l'opticien : ils renvoient vers un opérateur ou un réseau, indiqué sur la carte du client. Exemple trouvé : la carte Matmut affiche les codes **IS (iSanté)** et **KA (facturation Itelis)** **[M]**. L'agent doit donc lire la carte, puis choisir le portail. Il ne part jamais du nom de la mutuelle.

**b. « Pas besoin de stocker » est juste pour les données métier, faux pour la trace.** Le logiciel principal reste la seule base des clients, ordonnances, devis et factures : l'agent n'a pas besoin d'une base à lui, et le prototype n'écrit plus rien sur disque. En revanche il faut garder un **journal des actions de l'agent** (qui, quand, quel portail, quel n° de demande, quel résultat), sans données médicales. Sans ce journal, impossible de contester un rejet ou de prouver qu'un envoi a eu lieu. Les échanges via les espaces pros laissent une trace horodatée côté organisme **[M]**, mais tu n'y as accès que portail par portail.

**c. Ton logiciel principal fait peut-être déjà une partie du travail.** Les logiciels d'optique envoient souvent la demande de PEC directement depuis la fiche client (exemple : MyEasyOptic, écran PEC 100 % Santé / autre offre, bouton « récup taux ») **[H pour cet éditeur]**. Chaque portail déjà intégré dans ton logiciel ne doit pas être refait via Chrome. C'est la raison pour laquelle le nom du logiciel décide de la moitié du travail.

## 2. Les tâches communes à tous les portails

| # | Tâche | Entrée | Sortie à reporter dans le logiciel | Automatisable |
|---|---|---|---|---|
| T1 | Vérifier les droits du bénéficiaire | Carte TP (n° adhérent, bénéficiaire, date de naissance) | Droits ouverts oui/non, garanties optique | Oui, lecture seule |
| T2 | Simuler la prise en charge d'un devis | Devis (codes LPP, classe A/B, montants) | Montant estimé AMC, reste à charge | Oui |
| T3 | Demander la PEC | Bénéficiaire + ordonnance + équipement + devis | **N° de demande** | Oui, avec validation humaine avant envoi au début |
| T4 | Lire la réponse | N° de demande | Accord / accord partiel / pièce demandée / refus, **montant accordé** | Oui |
| T5 | Facturer la part AMC | Facture identique à l'accord + n° d'accord | Facture transmise | Oui, si la facture correspond exactement à l'accord |
| T6 | Rapprocher les paiements | Relevés de paiement (portail ou mail), virements groupés | Facture marquée payée / écart / impayée | Oui, c'est la tâche la plus rentable |
| T7 | Traiter les rejets | Motif du rejet | Correction et renvoi, ou dossier à traiter par un humain | Partiellement |

Procédure T3 commune **[M]** : choisir l'organisme d'après la carte, identifier le **bénéficiaire** (pas l'ouvrant droit, première cause de rejet **[M]**), saisir date d'ordonnance, prescripteur et corrections, décrire l'équipement (verres, monture, LPP, classe), envoyer, noter le n° de demande. Ne jamais renvoyer une demande en double : chercher d'abord si elle existe.

Délai pour facturer chez Almerys et Viamedis : 12 mois après la date de soins ; certaines mutuelles accordent moins **[M, source éditeur]**. L'agent doit donc traiter les retours chaque semaine.

## 3. Plateforme par plateforme

| Plateforme | Nature | Où l'agent agit | Tâches connues | Particularités pour l'agent | Confiance |
|---|---|---|---|---|---|
| **Almerys** | OTP | Portail pro Almerys | T1, T3, T4, T6 ; « tiers payant étendu » couvrant les devis optiques | Gros volume ; cible prioritaire des connexions suspectes depuis la fuite de 2024 | [M] |
| **Viamedis** | OTP | viamedispro.com | T1, T3, T4, T6, traitement des factures en anomalie ; paiements regroupés tous organismes confondus | Le relevé groupé oblige à pointer facture par facture : T6 indispensable | [M] |
| **SP Santé** | OTP (Cetip) | Espace pro SP Santé | Convention, tables de convention et de regroupement, demandes de remboursement et de PEC optiques | Conventionnement préalable du magasin (formulaire, RIB, convention signée) | [M] |
| **iSanté** | OTP (Cetip) | Espace pro iSanté | T1, T3, T4 probables | Utilisé par la Matmut (code IS sur la carte) | [M] pour Matmut, [B] pour le détail |
| **TP+** | Tiers payant de Santéclair pour opticiens non partenaires | tpplus.fr | T3, T4, T5 aux conditions du réseau | Si le magasin est partenaire Santéclair, passer par le circuit réseau, pas par TP+ | [M] |
| **Génération** | Gestionnaire | Le réseau inscrit sur la carte : Santéclair, Kalixia, Itelis, Sévéane ou Carte Blanche | T2 : simulation sur le site Génération pour les équipements hors 100 % Santé | Router d'abord vers le bon réseau ; sans réseau, le client avance les frais | [M] |
| **Mercer** | Gestionnaire | Selon la carte | Tiers payant partiel documenté en 2025, optique non citée | Vérifier carte par carte si l'optique est en tiers payant | [B] |
| **Ociane (Matmut)** | Mutuelle | iSanté ou réseau Itelis selon le code de la carte | Selon le portail cible | Lire les codes IS / KA sur la carte | [M] |

Ce tableau vient de sources publiques. **Les écrans réels, les champs exacts et les boutons ne sont visibles qu'une fois connecté.** L'étape suivante (section 5) sert à les relever.

## 4. Enchaînement d'un dossier par l'agent

```
1. Photo ordonnance        → module 1 (fait) → données validées par l'opticien
2. Photo carte TP          → lecture : AMC, OTP, réseau, bénéficiaires
3. Routage                 → portail cible (règles section 3)
4. T1 droits               → Chrome, portail cible, lecture seule
5. Logiciel principal      → retrouver ou créer le client, saisir l'ordonnance, préparer le devis
6. T2 / T3 PEC             → depuis le logiciel si le portail y est intégré, sinon Chrome
                             l'agent remplit, l'opticien clique « envoyer » (phase 1)
7. T4 réponse              → n° d'accord + montant reportés dans le logiciel
8. T5 facture              → depuis le logiciel, contrôlée contre l'accord
Chaque semaine :
9. T6 paiements            → relevés (mail + portails) → pointage dans le logiciel
10. T7 rejets              → liste des dossiers à corriger, avec motif
```

L'agent pilote Chrome sur le poste du magasin : il réutilise les sessions déjà ouvertes par l'opticien (double authentification faite par un humain). Les mots de passe restent dans le gestionnaire de mots de passe du navigateur ou dans un coffre, jamais dans le chat.

## 5. Ce qui débloque la suite

1. **Logiciel principal : MyEasyOptic.** Il fait déjà les PEC électroniques pour les mutuelles marquées `opt` ou `opt/len` : voir [MYEASYOPTIC.md](MYEASYOPTIC.md). Les portails via Chrome ne servent qu'aux mutuelles marquées `non` et au suivi des paiements.
2. **Un relevé des écrans, portail par portail.** Ce fil est relié à ton ordinateur : tu te connectes toi-même à un portail, puis je parcours les écrans en lecture seule (T1, liste des PEC, relevés) et je note champs et boutons. Aucun envoi, aucun mot de passe transmis. Critère : pour chaque portail, une fiche écran par tâche.
3. **Comparer avec l'existant avant de tout construire.** Des outils vendus aux opticiens automatisent déjà la soumission multi-portails et le suivi (OptiBot, Granit) **[M, affirmations des éditeurs]**. Une démo de 30 minutes chacun dit si tu construis tout, ou seulement ce qu'ils ne couvrent pas.

## Sources

- [Matmut, carte mutuelle](https://www.matmut.fr/mutuelle/services/carte-mutuelle) (codes IS iSanté, KA Itelis)
- [Coover, SP Santé](https://www.coover.fr/mutuelle/sp-sante) (fonctions de l'espace pro, conventionnement)
- [Génération, parcours optique](https://aide.generation.fr/parcours-optique-vos-questions-frequentes/) (réseaux, simulation)
- [Granit, portails de tiers payant](https://www.getgranit.ai/ressources/portails-tiers-payant) (procédure PEC, rejets, rapprochement)
- [OptiBot, questions fréquentes tiers payant](https://optibot.fr/blog/questions-frequentes-tiers-payant-optique) (délais 12 mois, première cause de rejet ; source éditeur)
- [MyEasyOptic, écran tiers payant](https://www.myeasyoptic.com/wp-content/uploads/2021/05/MEO-modification-TP.pdf) (PEC depuis le logiciel)
- [Viamedis, espace professionnels de santé](https://www.viamedispro.com/)
