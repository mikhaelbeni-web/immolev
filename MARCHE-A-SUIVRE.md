# Immolev : marche à suivre

Version du 18/10/2026. Confiance : **[H]** haute, **[M]** moyenne.

## 1. Principes repris d'Optizien

- L'agent travaille dans les logiciels existants (pages web lues dans Chrome, messagerie, documents photographiés), sans API à négocier.
- Lecture libre, écriture sur confirmation : chaque enregistrement, envoi ou clic de bouton attend un « Confirmer » dans Telegram.
- Les mots de passe restent dans le coffre de Windows et ne passent jamais par l'IA.
- Rien n'est stocké sur un serveur : la passerelle Vercel relaie seulement les appels à Claude.

## 2. Ce qui change avec l'immobilier et la vie personnelle

| Sujet | Décision | Raison |
|---|---|---|
| Une entité par document | Chaque facture, appel de fonds ou avis est rattaché à une seule entité (société, SCI, copropriété, hôtel, opération, foyer) | Mélanger deux entités fausse la comptabilité et peut constituer un abus de biens sociaux **[H]** |
| Vie personnelle | Revenus, impôts, patrimoine seulement en conversation privée avec le gestionnaire | Un groupe Telegram partagé n'est pas un lieu pour son revenu fiscal de référence |
| Fraude au faux fournisseur | Un IBAN qui change par rapport au paiement précédent bloque la préparation du paiement jusqu'à vérification par téléphone ; IBAN à clé fausse = alerte bloquante | Fraude fréquente dans le BTP et la gestion immobilière **[M]** |
| Paiements, votes, dépôts | Jamais exécutés par l'agent sans confirmation explicite | Irréversibles |
| Telegram | Moins sensible qu'en optique (pas de données de santé), mais les données fiscales et bancaires restent sur les serveurs de Telegram **[H]** | Photos de documents acceptées ; `TELEGRAM_PHOTOS=0` pour les refuser |

## 3. Étapes, dans l'ordre

| # | Étape | Action concrète | Critère de réussite |
|---|---|---|---|
| 1 | Mesurer la lecture de documents | Passer 30 vrais documents (15 factures, 5 appels de fonds, 5 avis d'impôt ou de taxe foncière, 5 quittances) dans `app.py` et comparer champ par champ | Aucun montant, IBAN ou date faux sans alerte |
| 2 | Remplir le questionnaire | Panneau Immolev, carte Questionnaire : biens, logiciels, société, foyer, patrimoine | Toutes les questions répondues ou volontairement laissées vides |
| 3 | Brancher la messagerie | Gmail ou Outlook, pro et perso, depuis le panneau | L'agent retrouve un appel de fonds reçu par mail |
| 4 | Relever le premier logiciel | Logiciel le plus utilisé (copropriété, PMS ou comptabilité), en lecture seule : « analyse ce logiciel de A à Z » | Fiche du logiciel produite, procédures retenues |
| 5 | Premier connecteur d'écriture | Classer un document dans le logiciel de comptabilité, après confirmation | 20 documents classés sans correction |
| 6 | Routines | Rappels hebdomadaires (impayés, échéances) et mensuels (clôture hôtel, pièces au comptable) | Rappels reçus aux bonnes dates |

## 4. Ce qu'il faut de ta part

1. La liste de tes logiciels (copropriété, gestion locative, hôtel, comptabilité, banque).
2. Des documents réels pour l'étape 1, avec les noms de tiers masqués si tu veux.
3. Aucun mot de passe dans le chat : tout passe par le panneau.
