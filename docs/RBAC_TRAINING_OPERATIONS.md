# RBAC, administration nationale et opérations d’entraînement

Dernière révision : 9 octobre 2026.

Ce guide décrit ce que l’interface admin sait faire dans le MVP actuel, et ce qui requiert encore une intégration côté serveur. La présence d’un bouton, d’un provider ou d’un statut ne prouve pas qu’une machine distante a été contactée.

## 1. Comptes et rôles

Les contributions des volontaires et les comptes de l’équipe sont distincts. Une personne peut fournir des enregistrements avec un code pseudonyme et le consentement requis ; elle n’a pas besoin d’un compte interne d’administration. L’application ne demande pas le nom ou le téléphone pour identifier une contribution.

| Rôle | Autorisations principales | Ne peut pas faire |
|---|---|---|
| Volontaire / participant | Enregistrer des contributions publiques selon le parcours et le consentement | Se connecter à l’administration, examiner d’autres contributions |
| `transcriber` | Saisir/corriger une transcription en attente | Approuver un corpus ou valider le TTS |
| `reviewer` | Examiner l’audio, corriger/transcrire et approuver pour l’ASR si habilité | Approuver l’usage TTS ou valider une release finale |
| `validator` | Revue indépendante, approbation TTS sur lecture, validation finale de dataset et confirmation des droits/licences | Gérer les comptes système ou les secrets de providers |
| `language_lead` | Importer du contenu linguistique validé, arbitrer langue/orthographe | Approuver une release finale ou gérer des comptes |
| `dataset_manager` | Créer les releases, lancer la préparation côté serveur, inscrire le rapport et exporter dans son périmètre | Marquer les droits comme vérifiés ou approuver seul la release finale |
| `training_operator` | Voir les datasets autorisés, créer/suivre des runs et enregistrer des métriques/identifiants distants | Lancer automatiquement un serveur distant depuis le navigateur ; approuver la release finale |
| `provider_manager` | Répertorier les serveurs/providers, modifier leur statut après vérification | Stocker des clés dans la base ou approuver les jeux de données |
| `privacy_officer` | Traiter un retrait/effacement du stockage actif et consulter le journal de retrait | Utiliser les fonctions de préparation ou d’entraînement par défaut |
| `admin` | Comptes, rôles, périmètres et opérations système | Aucune restriction de rôle |

Les rôles sont appliqués côté API, pas uniquement en masquant des panneaux dans l’interface.

### Périmètre minimal obligatoire

Tout compte non-admin doit recevoir explicitement au moins une langue et une région. Les champs vides ne donnent aucun accès : ils ne signifient pas « toutes ». Il faut attribuer toutes les valeurs nécessaires explicitement à une personne qui a un mandat national. La création d’une release `ALL` (nationale) est réservée à l’administration ; un gestionnaire régional prépare une release distincte pour une région attribuée.

Régions disponibles : `AGD`, `DIF`, `DOS`, `MAR`, `NIA`, `TAH`, `TIL`, `ZIN`, `UNK`. Les codes de langues et les statuts initiaux figurent dans [NATIONAL_LANGUAGE_CATALOG.md](NATIONAL_LANGUAGE_CATALOG.md).

## 2. Bootstrap et connexion

Configuration recommandée avant le premier démarrage :

```bash
export ZARMA_ADMIN_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(40))')"
export ZARMA_BOOTSTRAP_ADMIN_USERNAME="admin-local"
export ZARMA_BOOTSTRAP_ADMIN_PASSWORD="remplacer-par-un-secret-long-unique"
export ZARMA_SESSION_HOURS=12
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Le mot de passe bootstrap doit contenir au moins 14 caractères. Le compte bootstrap est créé uniquement si les deux variables username/password sont définies et qu’aucun compte de ce nom n’existe déjà. Le mot de passe n’est pas affiché par l’application. Les sessions sont des jetons aléatoires expirants ; le hash du jeton est stocké dans SQLite. Les mots de passe sont hachés avec PBKDF2-HMAC-SHA256.

La clé `ZARMA_ADMIN_TOKEN` reste disponible comme accès d’urgence (`break-glass`) et pour le script CLI de préparation. Ne la mets pas dans le code HTML, une capture d’écran, un dépôt Git, une variable JavaScript ou un notebook partagé. En exploitation quotidienne, utilise un compte nominatif par membre, affecté au moindre périmètre possible. Configure HTTPS avant tout accès autre que localhost.

## 3. Workflow recommandé de revue et de release

1. Le référent linguistique importe uniquement les phrases/consignes dont la source, les droits, la graphie et la validation humaine sont documentés.
2. Les volontaires enregistrent. Les audios arrivent en attente et n’entrent pas automatiquement dans le corpus entraînable.
3. Le transcriber corrige les transcriptions. Le reviewer approuve l’usage ASR après écoute. Le validator approuve le TTS uniquement pour les lectures dont le texte correspond exactement à la phrase de référence et dont le consentement TTS est présent.
4. Le dataset manager crée une release pour une tâche (`asr` ou `tts`), une langue et une région. Les releases TTS utilisent uniquement des lectures guidées ; la parole spontanée est ici réservée à l’ASR.
5. Sur le serveur de l’application, le dataset manager lance la préparation. Exemple :

   ```bash
   export ZARMA_ADMIN_TOKEN='la-cle-est-dans-l-environnement-du-serveur'
   python scripts/prepare_release.py --release-id UUID-DE-LA-RELEASE
   ```

   Le script exporte les seules prises autorisées pour la tâche/langue/région, vérifie l’archive, exécute `scripts/prepare_dataset.py`, puis inscrit le résumé, les manifests train/validation/test et le rapport technique de qualité dans `data/prepared_datasets/<release_id>/`.

6. Dans le tableau admin, ouvrir « Inspecter le corpus préparé » et consulter `dataset_summary.json`, la liste des fichiers et un aperçu limité de `quality_report.csv`. Le rapport est une aide technique : il ne remplace pas l’écoute ni l’examen linguistique.
7. Si des corrections sont nécessaires, le validator choisit « Demander une correction » et décrit les problèmes. Le gestionnaire corrige les sources ou le script sur le serveur, puis relance `scripts/prepare_release.py --release-id UUID --output-suffix rev2` pour conserver l’ancienne préparation et créer une nouvelle révision. Une release déjà approuvée doit être versionnée plutôt que modifiée en place.
8. Un validator distinct vérifie la provenance et les droits d’utilisation, la transcription, la variété de langue, les exclusions automatiques et la stratégie train/validation/test. Il marque les droits comme vérifiés au moment d’approuver la release ; une release non préparée ou avec droits non vérifiés ne peut pas être approuvée.
9. Seul un dataset approuvé est sélectionnable pour le suivi d’un run d’entraînement.

Toute modification majeure du corpus approuvé doit donner lieu à une nouvelle release et un nouveau hash, pas à la réécriture silencieuse d’un dataset déjà utilisé.

## 4. Datasets préparés : quoi inspecter ?

Le serveur maintient sous `ZARMA_DATA_DIR/prepared_datasets/` les dossiers générés par le pipeline. Chaque release enregistrée référence un sous-dossier. Les noms et tailles des fichiers connus sont affichés ; l’API d’aperçu n’autorise pas la lecture d’un chemin absolu arbitraire. Le résumé et le rapport qualité sont limités à un échantillon côté interface pour garder la page réactive.

Le contrôle humain doit inclure au minimum :

- concordance audio–texte (échantillon aléatoire, puis toutes les prises pendant le petit pilote) ;
- langue/variété et règle d’orthographe ;
- fichiers manquants, durée, silence, clipping et doublons signalés ;
- sources et droits sur textes et audio ;
- séparation pertinente des splits : ASR multi-locuteurs généralement par locuteur ; TTS multi-voix selon le but de généralisation ;
- protection des voix, autorisations de publication et procédure de retrait.

## 5. Providers, opérateurs et suivi de runs

L’interface comprend un registre de providers : GPU local, serveur SSH, Slurm/HPC, notebook, cloud GPU ou API gérée. Il conserve le type, endpoint, localisation, contact opérationnel/notes et **le nom d’une variable d’environnement** qui détient éventuellement le secret. Il ne stocke pas la clé API ni le mot de passe SSH. Une URL contenant username/password, query string ou fragment est refusée.

Un provider ne doit être marqué `active` qu’après test réel par son responsable. Le run contient la release approuvée, la tâche, la langue, le modèle de base, la méthode, l’état, l’identifiant du job distant, les métriques et un résumé du log.

**Limite actuelle :** le MVP fait le registre et le suivi ; il ne se connecte pas encore à SSH/Slurm/Kaggle/cloud et ne soumet pas une commande GPU depuis le formulaire. Après avoir créé le run dans l’interface, l’opérateur doit lancer l’entraînement dans l’environnement choisi puis reporter le `remote_job_id`, l’état, les métriques et les observations. Cette limite est volontaire : exécuter des commandes arbitraires envoyées par un navigateur sur un serveur GPU serait dangereux.

### Contrat conseillé pour un futur adaptateur de provider

Avant toute soumission automatique, développer un adaptateur côté serveur (pas dans le navigateur) ayant un contrat commun :

- `health_check(provider_id)` : vérifier l’authentification et l’accès, sans lancer de GPU ;
- `stage_dataset(release_id, manifest_sha256)` : transférer uniquement une release approuvée, vérifier le hash côté cible ;
- `submit_job(job_id, approved_config)` : configuration signée/validée, liste blanche de scripts et chemins, aucun shell arbitraire provenant de l’utilisateur ;
- `get_status(remote_job_id)` et `cancel_job(remote_job_id)` ;
- `collect_metrics(remote_job_id)` : loss train/val, métriques de tâche (WER/CER ASR; intelligibilité/naturalness TTS), durée, coût, GPU, version code/config et identifiant du checkpoint ;
- journal d’audit, délais, reprise, permissions par provider et réconciliation après coupure réseau.

Pour SSH/Slurm, les clés doivent être installées côté serveur dans un secret manager ou une identité système au moindre privilège. Pour les API cloud, mettre les tokens dans le gestionnaire de secrets du déploiement. Ne jamais accepter une commande libre ou un chemin de fichier arbitraire depuis le web.

## 6. Méthode de fine-tuning et traçabilité

Le choix par défaut dans l’interface est **Full Fine-Tuning (FFT)**. LoRA/QLoRA ne doivent être retenus que si la mémoire GPU, le coût, la recette du modèle ou les contraintes de déploiement le justifient. Le modèle ASR et le modèle TTS ont des architectures, pertes, lots et métriques différents : créer des expériences séparées. Il n’y a pas encore de modèle ASR/TTS livré dans l’application et le registre ne lance pas lui-même d’entraînement.

Pour chaque run, consigner :

- release ID, tâche, langue, région et SHA-256 du résumé/manifeste ;
- nom/révision du modèle, licence, méthode FFT/LoRA/QLoRA, code commit et configuration ;
- GPU, VRAM, durée, coûts estimés, seeds, logs et checkpoint retenu ;
- métriques sur un test qui n’a pas servi au réglage ; pour l’ASR, WER/CER avec normalisation documentée ; pour le TTS, évaluation humaine aveugle de l’intelligibilité, la prononciation et le naturel, plus mesures automatisées pertinentes.

## 7. Exigences avant l’échelle nationale

Le MVP n’est pas un système de production simplement parce que ses tests passent. Avant le recrutement massif : déployer derrière HTTPS, désactiver l’accès public à la clé de secours, limiter les tentatives de connexion, configurer sauvegardes chiffrées/restauration, surveillance et alertes, stockage audio avec droits système stricts, procédure de retrait couvrant sauvegardes/exports/copies et politique de durée de conservation. Prévoir une migration vers PostgreSQL et stockage objet si plusieurs instances ou forte concurrence apparaissent. Tester toutes les langues sur des vrais appareils et réseau faible avant d’annoncer leur disponibilité.
