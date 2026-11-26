# Benchmark de plateformes de collecte vocale et implications pour Voix du Niger

Dernière révision : 9 octobre 2026.

Ce document résume des pratiques publiques documentées. Il ne prétend pas que ces plateformes ont toutes été conçues pour le TTS : certaines sont des plateformes de collecte générale ou orientées ASR, dont les pratiques de corpus sont néanmoins utiles.

## 1. Mozilla Common Voice

**Approche observée**

1. Constituer une banque de phrases lisibles dont les droits permettent une diffusion adaptée au projet.
2. Obtenir une couverture linguistique et phonétique variée, avec des phrases que des locuteurs de différents profils peuvent lire.
3. Recueillir les enregistrements des volontaires.
4. Faire valider les clips par d'autres contributeurs.
5. Publier des versions de corpus documentées et répéter le cycle pour combler les lacunes.

**À reprendre**

- Séparer clairement la préparation/validation du texte, la collecte audio et la validation du son.
- Ne pas accepter un texte source sans vérifier ses droits.
- Prévoir une méthode de contribution accessible et une mobilisation communautaire.
- Conserver des statuts de revue distincts plutôt que considérer chaque fichier reçu comme une donnée d'entraînement.

**Limite à retenir**

Common Voice est historiquement très utilisé pour la reconnaissance vocale (ASR). Son système de collecte est instructif, mais la meilleure recette de données pour un TTS dépend de l'objectif : une voix unique contrôlée, plusieurs voix, ou une couverture dialectale large.

Source : https://www.mozillafoundation.org/en/common-voice/platform-and-dataset/
Playbook pour les textes : https://common-voice.github.io/community-playbook/sub_pages/text.html

## 2. CLEAR Global / Translators without Borders : TWB Voice

C'est le benchmark opérationnel le plus proche du projet. CLEAR Global indique que TWB Voice prend en charge la collecte multilingue à grande échelle, l'assurance qualité avec validation communautaire, la gouvernance fondée sur le consentement et la gestion de plusieurs projets.

Dans le projet présenté pour le nord-est du Nigeria, CLEAR Global rapporte la collecte et la validation de plus de 111 heures de données ASR, ainsi que 20 heures de données TTS, avec 135 contributeurs. L'organisation indique avoir développé des modèles de transcription et de synthèse vocale en hausa et en kanuri.

Le playbook TWB Voice recommande notamment :

- définir la cible (langues, variantes, usage final) avant de collecter ;
- concevoir le corpus textuel en parallèle du recrutement ;
- établir des consignes de prise et des règles de validation avant le pilote ;
- utiliser une révision par d'autres contributeurs, avec des critères explicites ;
- séparer les jeux train/dev/test par locuteur pour les évaluations où l'on veut mesurer la généralisation à des voix non vues ;
- ne publier que les données qui satisfont les critères retenus de qualité et de consentement, ou publier les statuts distinctement en protégeant les données concernées ;
- avoir une procédure de retrait/effacement et des conditions d'accès aux jeux de données.

**À reprendre dans Voix du Niger**

- Une révision graduée : auto-écoute, révision par un contributeur formé, puis arbitrage par un référent linguistique pour les cas incertains.
- Des critères de validation reproductibles : texte prononcé intégral, intelligibilité, bruit, coupure, plusieurs voix, langue/variante correcte.
- Un audit de consentement et une procédure de suppression de bout en bout.
- Un split indépendant des locuteurs pour les corpus multi-speakers, en plus du split par phrase utile pour une première voix unique.
- Une publication documentée avec métadonnées minimales, sources, licences et rapport de qualité.

**Résultat TTS à regarder sans le surestimer**

La fiche publique `TWB Voice Hausa Multi-Speaker TTS 1.0` décrit un modèle YourTTS/VITS entraîné à partir d'environ 30 heures de données hausa, sur trois voix. L'évaluation rapportée par les auteurs sur 30 phrases obtient une note moyenne de 2,52/5 pour la précision de prononciation et 2,93/5 pour le naturel. Cela illustre deux points : une plateforme et un volume de données conséquents ne garantissent pas une qualité parfaite ; il faut écouter et évaluer les sorties du modèle, pas uniquement suivre la loss.

Les jeux TWB Hausa sont soumis à une licence CC BY-NC 4.0 et à des conditions d'accès supplémentaires. Il faut vérifier ces conditions avant toute réutilisation, publication ou exploitation commerciale.

Sources :
- https://clearglobal.org/twbvoice/
- https://twbvoiceplaybook.clearglobal.org/3.-setting-up-a-project-to-collect-voice-data/3.1-designing-your-project
- https://twbvoiceplaybook.clearglobal.org/5.-recording-and-validation/5.2-guidelines-for-validation
- https://twbvoiceplaybook.clearglobal.org/7.-data-storage-compliance-and-ethical-issues/7.3-informed-consent
- https://mozilladatacollective.com/datasets/cmp74k47s02u2mp07zr9zwhpt
- https://huggingface.co/CLEAR-Global/TWB-Voice-Hausa-TTS-1.0

## 3. Karya : exemple Bhili

Karya décrit un système Bhili co-construit avec la communauté : plus de 400 contributeurs, sur 30 jours, plus de 30 000 paires de traduction, 120 heures de données vocales et 6 500 termes de glossaire. Le système a ensuite été intégré à des services utilisés dans le monde réel.

**À reprendre**

- Travailler avec des partenaires locaux (associations, éducateurs, institutions, radios ou collectifs linguistiques) qui peuvent mobiliser des locuteurs et vérifier les textes.
- Définir une application concrète pour motiver et orienter la collecte.
- Prévoir un budget et un processus terrain plutôt que compter exclusivement sur des contributions spontanées.
- Inclure un glossaire et un inventaire des termes/difficultés propres à chaque langue.

**Différence avec notre MVP**

Karya ne se limite pas à une interface : la mobilisation, la collecte de ressources textuelles, la validation communautaire et le déploiement d'un service final sont au cœur du projet. Voix du Niger doit construire ces partenariats en parallèle de la technique.

Source : https://www.karya.in/case-studies/bhili-tribal-language-voice-assistant/

## 4. HausaNLP et Shamsuddeen Hassan Muhammad

Le nom probablement visé par « Shamsou » est Shamsuddeen Hassan Muhammad, co-auteur de l'article *HausaNLP: Current Status, Challenges and Future Directions for Hausa Natural Language Processing* (AfricaNLP 2025). L'article présente un catalogue de jeux de données, outils et travaux HausaNLP, et insiste notamment sur la rareté de ressources ouvertes, les différences dialectales, la tokenisation et la nécessité de collaboration communautaire.

HausaNLP est surtout un point d'entrée pour trouver les ressources, les chercheurs et les lacunes autour du hausa ; ce n'est pas en soi une plateforme de collecte TTS équivalente à TWB Voice.

**À reprendre**

- Cartographier les corpus existants avant de collecter des doublons inutiles.
- Demander des retours à des linguistes et chercheurs du hausa.
- Documenter les variantes et l'orthographe retenue.
- Partager, quand les droits le permettent, des jeux de données versionnés et une description honnête de leurs limites.

Sources :
- https://aclanthology.org/2025.africanlp-1.27/
- https://catalog.hausanlp.org/

## 5. Feriji (Zarma–français)

Feriji est un corpus parallèle textuel destiné à la traduction automatique et à la recherche linguistique. Son dépôt indique 61 085 lignes zarma, 42 789 lignes françaises et un glossaire de 4 062 entrées. C'est une ressource possible pour proposer ou catégoriser des phrases en zarma, à condition de vérifier leur naturel oral, leur orthographe et leurs droits.

**Ce que Feriji peut apporter**

- Une source de candidats de phrases en zarma, plutôt que de rédiger tous les prompts à partir de zéro.
- Des paires zarma-français pour aider les équipes à vérifier le sens et organiser les catégories.
- Un glossaire pour repérer le vocabulaire, puis le contrôler avec des locuteurs.
- Des textes que l'équipe peut transformer en tâches de lecture après validation linguistique et juridique.

**Ce que Feriji n'apporte pas**

- Pas d'audio humain aligné aux phrases : ce n'est donc pas, à lui seul, un corpus TTS supervisé.
- Pas une garantie que les phrases sont toutes naturelles à l'oral, adaptées à une voix TTS ou représentatives des variantes actuelles.
- Pas d'autorisation automatique de réutiliser les textes dans tous les corpus ou modèles.

Le dépôt donne une licence CC BY-NC-SA 4.0, décrit le corpus comme un travail en cours destiné à la recherche et au développement de traduction automatique, et demande aux entités souhaitant accéder/utiliser le dataset de contacter les auteurs. **Avant d'utiliser les lignes Feriji comme prompts enregistrés, demander l'autorisation aux auteurs et clarifier l'usage prévu, notamment la publication du corpus vocal et l'éventuel usage commercial.**

Source : https://github.com/27-GROUP/Feriji
Licence et conditions : https://github.com/27-GROUP/Feriji/blob/main/LICENSE.md

## 6. Comparaison synthétique avec Voix du Niger

| Dimension | MVP actuel | Pratique à viser inspirée des références |
|---|---|---|
| Préparation du texte | Import CSV, approbation obligatoire | Sources documentées, licence explicite, validation de plusieurs locuteurs compétents |
| Collecte | Téléphone/navigateur, une phrase par prise | Ajouter file d'envoi hors-ligne, instructions localisées, test de microphone et suivi de session |
| Revue | Un réviseur peut approuver/refaire/rejeter | Critères communs, formation des réviseurs, double revue/arbritrage des cas difficiles |
| Qualité audio | Contrôles techniques après export + revue humaine | Contrôle technique dès réception, revue humaine, statistiques par langue/locuteur/appareil |
| Langues | Zarma, Hausa et Tamasheq structurés dans les métadonnées | Orthographe, variantes et personnes référentes définies séparément par langue |
| Train/validation/test | Script split par phrase par défaut, option speaker | Split par phrase pour une voix unique ; split speaker-disjoint pour la généralisation multi-speaker |
| Consentement/droits | Ébauche, non suffisante pour le public | Consentement versionné, usages/licences clairs, procédure de retrait et de suppression des copies dérivées |
| Publication | Export WAV/CSV | Card dataset, licence, méthode de collecte, statistiques, splits, limites et procédure de mise à jour |
| Robustesse modèle | Non encore évaluée sur un corpus réel | Évaluation humaine et automatique séparée sur des phrases inédites, suivi par dialecte, locuteur et type de phrase |

## 7. Plan concret pour Voix du Niger

1. **Pilote fermé** avec une seule langue active au début, 2–3 téléphones et peu de participants.
2. **Comité linguistique léger** : au moins un référent par langue, convention orthographique, relecture de chaque prompt et arbitrage des cas douteux.
3. **Banc de phrases autorisées** : source et licence conservées par ligne ; ne pas importer directement Feriji en supposant que le droit de réutilisation est acquis.
4. **Validation graduée** : auto-écoute par le participant, revue communautaire formée, revue experte des désaccords et audits aléatoires.
5. **Gouvernance avant publication** : conditions de contribution, consentement, statut de chaque audio, règles de retrait/suppression, licence du corpus et licence du modèle envisagé.
6. **Évaluation modèle** : ne pas prétendre qu'un modèle est robuste sur la base de `train_loss`/`eval_loss` uniquement. Garder des phrases de test, mesurer la compréhension et faire évaluer le naturel et la prononciation par des locuteurs natifs.
