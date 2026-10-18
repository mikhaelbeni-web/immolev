# Métiers de l'immobilier et chaînes d'un dossier
Repères pour assister un gestionnaire de développement foncier. Confiance : [H] haute, [M] source secondaire, [V] à faire valider par le notaire, l'avocat, l'expert-comptable ou le syndic professionnel, qui priment toujours. Les seuils, délais et taux changent : donne-les avec leur date et la source officielle (legifrance.gouv.fr, service-public.fr, impots.gouv.fr).

## 1. Les acteurs
- **Développeur foncier** : trouve le terrain, vérifie qu'il est constructible, négocie avec le propriétaire, monte l'opération jusqu'à l'obtention du permis purgé. **[H]**
- **Promoteur** : maître d'ouvrage de l'opération, porte le risque financier, vend en VEFA ou en bloc. **[H]**
- **Notaire** : promesse, acte de vente, VEFA, purge des droits de préemption, règlement de copropriété et état descriptif de division. **[H]**
- **Maîtrise d'œuvre** : architecte (obligatoire au-delà de 150 m² de surface de plancher pour une personne physique, et pour toute personne morale [M]), bureaux d'études, OPC, contrôleur technique, coordinateur SPS. **[M]**
- **Syndic** : représente le syndicat des copropriétaires, exécute les décisions d'AG, tient les comptes. **Conseil syndical** : assiste et contrôle le syndic. **[H]**
- **Gestionnaire locatif / administrateur de biens** : baux, quittances, encaissements, révisions, régularisations de charges, travaux. **[H]**
- **Exploitant hôtelier** : direction, réception, revenue management, ménage, maintenance ; propriétaire des murs souvent distinct de l'exploitant (bail commercial ou contrat de gestion). **[M]**

## 2. Les chaînes d'un dossier, d'amont en aval
Règle de lecture : n'agis sur un maillon que si ses entrées sont présentes. Si une entrée manque, dis laquelle et à quel maillon elle se prépare.

### 2.1 Développement foncier et promotion
| # | Maillon | Besoin en amont | Sortie | Qui |
|---|---|---|---|---|
| 1 | Prospection | Secteur cible | Terrain repéré, propriétaire identifié (cadastre, fichiers fonciers) | Agent cherche, humain décide |
| 2 | Faisabilité | Parcelle | Règles du PLU (zone, hauteur, emprise, stationnement), servitudes, risques (Géorisques), surface constructible estimée | Agent prépare, architecte confirme |
| 3 | Bilan promoteur | Faisabilité, prix de sortie | Charge foncière admissible = recettes − (travaux + honoraires + frais financiers + frais commerciaux + marge) | Agent calcule, humain valide |
| 4 | Promesse de vente | Accord du propriétaire | Promesse sous conditions suspensives (permis purgé, financement, sol, pré-commercialisation) | Notaire, humain signe |
| 5 | Permis de construire | Dossier architecte | Dépôt, récépissé, demandes de pièces, arrêté | Architecte dépose, agent suit les délais |
| 6 | Purge | Arrêté affiché | Recours des tiers : 2 mois à compter de l'affichage continu sur le terrain [H] ; retrait par l'administration : 3 mois [H] | Huissier constate l'affichage |
| 7 | Financement et garanties | Pré-commercialisation | Crédit, garantie financière d'achèvement (obligatoire en VEFA) [H], assurance dommages-ouvrage (obligatoire) [H] | Banque, assureur |
| 8 | Acquisition du terrain | Conditions levées | Acte authentique | Notaire |
| 9 | Commercialisation | Prix, plans | Contrats de réservation, dépôts de garantie, actes VEFA | Commercialisateur, notaire |
| 10 | Chantier | Ordre de service | DROC, comptes rendus, situations de travaux, avenants | Maîtrise d'œuvre |
| 11 | Appels de fonds VEFA | Avancement constaté | Plafonds du prix cumulés : 35 % fondations achevées, 70 % mise hors d'eau, 95 % achèvement, solde à la livraison (art. R261-14 CCH) [H] | Agent prépare, humain valide |
| 12 | Livraison et réception | Travaux terminés | PV de réception avec réserves, DAACT | Humain |
| 13 | Garanties | Réception | Parfait achèvement 1 an, bon fonctionnement 2 ans, décennale 10 ans [H] | Agent suit les échéances |

### 2.2 Copropriété (loi du 10 juillet 1965, décret du 17 mars 1967) **[H]**
| # | Maillon | Besoin en amont | Sortie |
|---|---|---|---|
| 1 | Budget prévisionnel | Dépenses de l'exercice précédent, contrats | Budget à voter en AG |
| 2 | Assemblée générale | Convocation au moins 21 jours avant [H], ordre du jour, annexes | Procès-verbal ; majorités de l'article 24 (présents et représentés), 25 (tous les copropriétaires), 26 (double majorité) [H] |
| 3 | Notification du PV | PV signé | Délai de contestation : 2 mois après notification pour les opposants et défaillants [H] |
| 4 | Appels de fonds | Budget voté, tantièmes | Provisions exigibles le 1er jour de chaque trimestre, un quart du budget, sauf autre décision de l'AG [H] ; cotisation au fonds de travaux (au moins 5 % du budget [M]) |
| 5 | Encaissements, relances | Appels émis | Impayés par lot, relances, mise en demeure, recouvrement |
| 6 | Dépenses et travaux | Vote, devis, contrats | Ordres de service, factures contrôlées et payées |
| 7 | Clôture des comptes | Exercice terminé | Comptes annuels, annexes comptables, répartition des charges réelles par lot |
| 8 | Suivi réglementaire | Immeuble | Immatriculation au registre national, carnet d'entretien, plan pluriannuel de travaux, DPE collectif selon l'âge et la taille de l'immeuble [M, V] |

### 2.3 Gestion locative
- **Habitation** (loi du 6 juillet 1989) : dépôt de garantie plafonné à 1 mois de loyer hors charges en location nue, 2 mois en meublé [H] ; révision annuelle selon l'IRL si le bail le prévoit [H] ; régularisation annuelle des charges sur justificatifs [H] ; logements classés G interdits à la nouvelle location depuis 2025, F en 2028, E en 2034 [H, calendrier à revérifier].
- **Commercial** : bail 3-6-9, indexation ILC ou ILAT selon l'activité, plafonnement du loyer au renouvellement sauf exceptions, état des lieux et inventaire des charges obligatoires [M, V].
- Chaîne : bail signé → quittancement mensuel → encaissement et rapprochement → relance des impayés → révision annuelle → régularisation des charges → sortie (état des lieux, restitution du dépôt de garantie dans 1 mois si conforme, 2 mois sinon [H]).

### 2.4 Hôtellerie
- Indicateurs : taux d'occupation = chambres vendues ÷ chambres disponibles ; prix moyen (ADR) = CA hébergement ÷ chambres vendues ; RevPAR = CA hébergement ÷ chambres disponibles = TO × ADR [H] ; GOP (résultat brut d'exploitation) ; coût de distribution (commissions des plateformes de réservation). **[H]**
- Outils : PMS (logiciel de gestion hôtelière), channel manager, moteur de réservation, plateformes de réservation, terminal de paiement, comptabilité. **[M]**
- Obligations : collecte et reversement de la taxe de séjour à la commune [H] ; fiche individuelle de police pour les clients étrangers [H] ; affichage des prix ; sécurité incendie des établissements recevant du public (commission de sécurité) [M] ; classement en étoiles valable 5 ans [M].
- Chaîne d'un mois : réservations → séjours → facturation et encaissements → rapprochement PMS / banque / plateformes → reporting (TO, ADR, RevPAR, GOP) → taxe de séjour → charges et paie → clôture mensuelle.

### 2.5 Transaction
Mandat → estimation → diagnostics obligatoires (DPE, amiante, plomb, électricité, gaz, termites selon zone, ERP) [H] → offre → compromis ou promesse → délai de rétractation de 10 jours pour l'acquéreur non professionnel d'un logement [H] → conditions suspensives (prêt) → acte authentique → honoraires.

## 3. Contrôles avant toute écriture ou tout paiement (signale, ne corrige pas seul)
1. La facture correspond à un devis validé ou à un contrat, et à la bonne entité (société, SCI, copropriété, hôtel, foyer).
2. Montants cohérents : HT + TVA = TTC, taux de TVA plausible, retenue de garantie de 5 % sur les marchés de travaux si prévue [M].
3. Pas de doublon : même fournisseur, même numéro ou même montant à la même date.
4. IBAN identique aux paiements précédents ; sinon, vérification par téléphone avant tout paiement.
5. Échéance : échue, proche ou lointaine ; pénalités de retard possibles.
6. Pour un appel de fonds de copropriété : budget voté, tantièmes du lot, travaux votés.
7. Pour un appel de fonds VEFA : avancement attesté par le maître d'œuvre, plafond de l'étape respecté.

## 4. Ce que l'agent ne fait pas seul
- Payer, signer, voter, déposer une déclaration ou un permis, former un recours.
- Engager une dépense, accepter un devis, donner un ordre de service.
- Envoyer une mise en demeure, résilier un bail ou un contrat.
- Contacter un notaire, une banque, l'administration ou un locataire sans confirmation.
- Garder un identifiant ou un mot de passe en mémoire de conversation.
