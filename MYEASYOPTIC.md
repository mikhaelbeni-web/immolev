# MyEasyOptic, cible d'intégration

Version du 15/10/2026. Confiance : **[H]** documentation de l'éditeur, **[M]** source secondaire, **[B]** déduction.

## Ce que l'on sait

| Point | Constat | Conséquence pour l'agent |
|---|---|---|
| Éditeur | MyEasySoft **[M]** ; contact@myeasyoptic.com, 0 820 888 195 **[H]** | Interlocuteur pour une demande d'accès API ou partenaire |
| Technologie | Logiciel **web**, utilisé dans un navigateur, mises à jour automatiques **[H]** | L'agent écrit dans MyEasyOptic via Chrome, exactement comme sur les portails. Une seule technique pour tout |
| Hébergement | Cloud chez un hébergeur certifié HDS en France **[M]** | Les données restent dans MyEasyOptic : la plateforme n'a rien à stocker, ce qui règle l'essentiel du sujet HDS côté stockage |
| API | Aucune API ni import documentés ; un export de listes de clients existe (Statistiques > Mailing) **[H]** | Écriture uniquement par l'interface web, sauf si l'éditeur ouvre un accès |
| Interfaces existantes | Une quinzaine de partenaires intégrés (Easyplug, Megaconnect, Opsysweb, Zerosix, Activisu…) **[H]** | L'éditeur sait intégrer des tiers : une demande de partenariat a une chance réelle |
| PEC électronique | Intégrée, via le concentrateur **AreaSanté** (Groupe Reflex). Dans la liste des mutuelles, une colonne « PEC » vaut `opt/len`, `opt` ou `non` **[H]** | **Toute mutuelle marquée `opt` ou `opt/len` se traite dans MyEasyOptic, pas sur le portail.** Chrome sur les portails sert seulement aux mutuelles marquées `non` et au suivi des paiements |
| Réponse PEC | Verte : n° de PEC, date et montant par équipement remplis automatiquement. Rouge : « Message plateforme » ou « Message mutuelle » avec la colonne « Que faire ? ». Orange : 48 à 72 h, bouton « Actualiser la prise en charge » **[H]** | L'agent relance les PEC orange, lit les refus et propose la correction |
| Prérequis PEC | Option PEC activée, crédits PEC, FINESS renseigné, consentement imprimé et case « Consentement imprimé » cochée **[H]** | Le consentement reste une étape humaine avec le client |
| Facturation (TP Cash / Sicorfé) | Document « Ordonnance » joint à la visite obligatoire ; en cas d'accord, document « Accord PEC » joint et n° de PEC saisi ; rejet traité par avoir, duplication de la visite, correction et renvoi **[H]** | La photo de l'ordonnance prise dans le module 1 doit être jointe à la visite par l'agent |

## Enchaînement révisé d'un dossier

```
1. Photo ordonnance → module 1 → données validées par l'opticien
2. MyEasyOptic (Chrome) : retrouver ou créer la fiche client, créer la visite,
   saisir la correction OD/OG, joindre la photo comme document « Ordonnance »
3. Devis normalisé dans MyEasyOptic (fait par l'opticien : choix des verres et montures)
4. Mutuelle RC1 : colonne PEC = opt ou opt/len ?
     oui → onglet PEC de MyEasyOptic (consentement signé par le client, puis l'agent lance et relance)
     non → portail de l'organisme via Chrome, puis report du n° et du montant dans l'onglet PEC
5. Facturation dans MyEasyOptic, contrôlée contre l'accord
6. Chaque semaine : PEC orange relancées, refus listés avec le « Que faire ? », paiements pointés
```

## Actions, dans l'ordre

1. **Exporter ou photographier la liste des mutuelles de MyEasyOptic avec la colonne PEC** (Paramètres > Mutuelles & SS > Mutuelles). Critère : pour chacune des 8 plateformes, on sait si la PEC part de MyEasyOptic ou exige le portail.
2. **Écrire à MyEasySoft** (contact@myeasyoptic.com) : demander s'il existe une API ou un accès partenaire pour créer clients, visites et ordonnances, et si l'automatisation de l'interface par un agent est autorisée par leurs conditions. Critère : réponse écrite.
3. **Relever les écrans MyEasyOptic sur un client test** (fiche client, visite, saisie de la correction, pièces jointes, onglet PEC), en lecture seule, avec toi connecté sur ton ordinateur. Critère : chaque champ du schéma d'ordonnance a son emplacement à l'écran.
4. **Écrire le connecteur** qui remplit ces écrans à partir de l'ordonnance validée (remplace `LogicielNonConfigure` dans `ordonnance/destination.py`). Critère : 10 ordonnances test saisies dans MyEasyOptic sans correction.

## Sources

- [MyEasyOptic, Débuter avec le logiciel (2024)](https://www.myeasyoptic.com/wp-content/uploads/2024/06/MEO-Debuter-avec-MyEasyOptic-18062024.pdf)
- [MyEasyOptic, Demande de prise en charge électronique (2025)](https://www.myeasyoptic.com/wp-content/uploads/2025/06/MEO-Demande-de-prise-en-charge-electronique.pdf)
- [MyEasyOptic, Utilisation de TP Cash (2025)](https://www.myeasyoptic.com/wp-content/uploads/2025/01/MEO-Utilisation-de-TP-Cash.pdf)
- [MyEasyOptic, Export de données](http://www.myeasyoptic.com/wp-content/uploads/2018/05/MEO-Export-de-données.pdf)
- [MyEasyOptic, Documentations](https://www.myeasyoptic.com/documentations/)
- [LeBonLogiciel, fiche MyEasyOptic](https://lebonlogiciel.com/organisation-facturation-et-planification-gestion-commerciale-erp-gpao/myeasyoptic/2460)
