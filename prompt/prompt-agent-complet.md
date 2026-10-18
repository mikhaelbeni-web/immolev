# Prompt complet de l'agent Immolev

Version 1 du 18/10/2026. Le prompt envoyé à Claude à chaque demande est assemblé par `agent/orchestrateur.py`, fonction `systeme()` :

1. **Partie A : prompt système** (`SYSTEME` dans `agent/orchestrateur.py`). Identité, mission pro et perso, ordre de travail (dont l'identification de l'entité concernée), règles d'action, méthode d'analyse d'un logiciel, blocages et reprise, mémoire, style.
2. **Partie B : base de connaissances** (`agent/connaissances/*.md`, chargés dans l'ordre alphabétique) :
   - `fiscalite-immobiliere.md` : TVA immobilière, structures de détention, revenus fonciers, plus-values, impôts locaux.
   - `immobilier-metier.md` : acteurs, chaînes d'un dossier (promotion, copropriété, gestion locative, hôtellerie, transaction), contrôles avant paiement, limites de l'agent.
   - `societe-du-gestionnaire.md` : comptabilité, TVA, paie, trésorerie, obligations et calendrier de sa société.
   - `vie-personnelle.md` : foyer fiscal, revenu fiscal de référence, calendrier déclaratif, rémunération du dirigeant, patrimoine.
3. **Partie C : ce que le gestionnaire a appris à l'agent** : fiche du questionnaire, notes techniques par site, procédures retenues, règles écrites dans le panneau ou sur Telegram (elles priment sur la partie B).

Légende de confiance dans la partie B : **[H]** haute, **[M]** moyenne (source secondaire), **[V]** à faire valider par l'expert-comptable, le notaire ou l'avocat. Rien de ce qui est marqué [V] ne doit être affirmé sans vérification.

Pour modifier le comportement : la partie A dans le code, la partie B dans les fichiers `.md`, la partie C dans le panneau.
