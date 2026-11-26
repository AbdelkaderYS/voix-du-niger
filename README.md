# Voix du Niger : collecte et préparation du corpus vocal

MVP national de collecte vocale pour les onze langues citées par la Charte de la Refondation 2025, avec le français et l’anglais référencés séparément comme langues de travail. Il propose deux modes (lecture guidée et parole spontanée) puis des validations et exports séparés pour la reconnaissance automatique de la parole (*Automatic Speech Recognition*, ASR) et la synthèse vocale (*Text-to-Speech*, TTS). Le catalogue national ne signifie pas que des phrases, des consignes ou un corpus validé existent déjà dans chaque langue : les variétés, graphies, sources et droits doivent être validés. L’application n’embarque pas encore de modèle ASR/TTS et n’effectue pas d’inférence vocale.

> **Statut : MVP pour pilote contrôlé, pas plateforme de production.** Le flux technique peut être testé localement. Avant une campagne publique, il faut compléter le consentement, la suppression de bout en bout (dont sauvegardes et copies), les sauvegardes/restauration, la sécurité du serveur et la validation linguistique.

## Ce que contient le dépôt

- **Interface de collecte mobile** : un parcours en quatre écrans (langue, activité, accord, code participant) puis l’enregistrement, avec un seul grand bouton, l’écoute avant envoi et la reprise. Seules les langues qui ont des textes approuvés sont proposées ; les autres sont listées comme bientôt disponibles. Un participant sans code peut en créer un sur place. Le texte d’accord est en langage simple (version `consent-v5-plain-language`).
- **Lecture guidée** : la transcription de référence vient de la phrase validée en base ; une prise peut être approuvée séparément pour l'ASR et le TTS.
- **Parole spontanée** : utilise uniquement des consignes importées et validées pour la langue sélectionnée ; l'audio doit être transcrit et vérifié par une personne compétente avant l'approbation ASR. Ce protocole ne rend pas la parole spontanée éligible au TTS.
- **API FastAPI** et SQLite, migration des anciens enregistrements, métadonnées de consentement par contribution et journal des décisions de revue.
- **Administration RBAC** : une section à la fois, choisie dans un menu filtré selon le rôle ; comptes d’équipe avec rôles et sessions expirantes, périmètres obligatoires de langues/régions, tableau de bord national, suivi des volontaires pseudonymes, audit et retrait des données du stockage actif.
- **Pipeline dataset et training ops** : releases ASR/TTS versionnées par langue/région, aperçu des manifests/rapport qualité préparés côté serveur, validation finale indépendante des droits/licences, registre de providers et suivi de jobs/métriques. Le registre ne soumet pas encore des jobs GPU distants automatiquement.
- **Exports distincts** : `task=asr` ne contient que les prises approuvées ASR avec transcription ; `task=tts` ne contient que les lectures approuvées TTS. Les fichiers sont convertis en WAV mono PCM 16 bits et accompagnés d'un `metadata.csv`. `task=all` demeure uniquement pour la compatibilité et n'est pas l'option recommandée pour l'entraînement.
- **Phrases initiales en zarma en attente de revue** : elles ne sont pas considérées comme validées. Le Hausa et le Tamajaq/Tamasheq sont activés comme pilotes ; chaque autre langue du catalogue national doit elle aussi disposer de phrases importées et vérifiées avant la collecte guidée.
- **Aucune consigne de parole spontanée linguistique n'est fournie comme si elle était validée.** Il faut préparer les consignes dans chaque langue, documenter leurs sources et leurs conditions d'utilisation, puis préciser le réviseur et la date. Le fichier `examples/elicitation_prompts_template.csv` est un modèle à compléter, et non un corpus prêt à importer.
- **Script de préparation ML** `scripts/prepare_dataset.py` : vérification technique des WAV, détection d'anomalies simples et doublons audio exacts, rééchantillonnage optionnel, séparation par groupes en train/validation/test.
- **Guide d'entraînement TTS** `TRAINING_GUIDE.md` et [guide ASR](docs/ASR_TRAINING_GUIDE.md) : préparation par tâche, FFT comme référence quand elle est faisable, LoRA/QLoRA en repli conditionnel, et évaluation humaine/automatique.
- **Catalogue de langues nationales** [`docs/NATIONAL_LANGUAGE_CATALOG.md`](docs/NATIONAL_LANGUAGE_CATALOG.md) : langues citées dans la Charte 2025, codes applicatifs, états initiaux et régions.
- **RBAC et opérations d’entraînement** [`docs/RBAC_TRAINING_OPERATIONS.md`](docs/RBAC_TRAINING_OPERATIONS.md) : permissions, bootstrap admin, validation indépendante, releases, providers et future intégration distante.
- **Benchmark des plateformes** [`docs/PLATFORM_BENCHMARK.md`](docs/PLATFORM_BENCHMARK.md) : Mozilla Common Voice, TWB Voice, Karya, HausaNLP/Shamsuddeen et Feriji.
- **Liste avant ouverture publique** [`docs/PUBLIC_READINESS.md`](docs/PUBLIC_READINESS.md) : sécurité, consentement, reprise réseau, contrôle qualité et publication.
- **Feuille de route modèles/matériel** [`docs/MODEL_ROADMAP_HARDWARE.md`](docs/MODEL_ROADMAP_HARDWARE.md) : candidats ASR/TTS/LLM/RAG, licences, VRAM/RAM/stockage et court/moyen/long terme.
- **Assistant vocal conversationnel** [`docs/VOICE_ASSISTANT_ROADMAP.md`](docs/VOICE_ASSISTANT_ROADMAP.md) : définition du produit, architecture, données distinctes, RAG et étapes vers le mode rural/faible connexion.
- **Schéma visuel de l’architecture Speech-to-Speech** [`docs/VOICE_ASSISTANT_ARCHITECTURE.png`](docs/VOICE_ASSISTANT_ARCHITECTURE.png) : vue d’ensemble de l’ASR → LLM/RAG → TTS, de la brique de collecte actuelle et de la feuille de route. L’agriculture est un exemple d’usage, pas la finalité exclusive.

## 1. Prérequis

- Python 3.11 ou plus récent.
- FFmpeg installé sur le serveur qui exporte le corpus et, si nécessaire, dans l'environnement de préparation.
- Un navigateur récent autorisant le microphone.

```bash
python --version
ffmpeg -version
```

## 2. Installation locale

Depuis le dossier `zarma-tts-mvp` :

### Linux / macOS

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export ZARMA_ADMIN_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(40))')"
export ZARMA_BOOTSTRAP_ADMIN_USERNAME="admin-local"
export ZARMA_BOOTSTRAP_ADMIN_PASSWORD="remplacer-par-un-secret-unique-de-14-caracteres-minimum"
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:ZARMA_ADMIN_TOKEN = (python -c "import secrets; print(secrets.token_urlsafe(40))")
$env:ZARMA_BOOTSTRAP_ADMIN_USERNAME = "admin-local"
$env:ZARMA_BOOTSTRAP_ADMIN_PASSWORD = "remplacer-par-un-secret-unique-de-14-caracteres-minimum"
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Ouvre ensuite :

- Collecte : <http://127.0.0.1:8000>
- Administration : <http://127.0.0.1:8000/admin>
- Documentation API : <http://127.0.0.1:8000/docs>
- Santé du service : <http://127.0.0.1:8000/api/health>

Dans l’administration, connecte-toi avec le nom d’utilisateur et le mot de passe bootstrap. `ZARMA_ADMIN_TOKEN` est une clé de secours, conservée aussi pour les scripts opérés côté serveur ; elle ne doit jamais être publiée dans Git, un notebook partagé ou une capture d’écran.

Les données sont stockées dans `data/` par défaut. Pour utiliser un volume persistant ailleurs :

```bash
export ZARMA_DATA_DIR="/chemin/persistant/zarma-data"
```

Ne supprime pas ce dossier : il contient la base SQLite et les enregistrements originaux.

## 3. Préparer et importer les phrases

### Option A : commencer avec des phrases validées

1. Ouvre `examples/phrases_template.csv` pour le format minimal.
2. Prépare le texte dans la langue choisie avec un locuteur compétent et fixe la convention d’écriture (ponctuation, variantes, chiffres, noms propres).
3. Enregistre le CSV en UTF-8 avec `language_code`, `text_prompt`, `category`, `orthography_version`, `source`, `source_license`, `native_review_status`, `native_reviewed_by` et `native_reviewed_at`. Codes : `dje` = zarma, `ha` = hausa, `taq` = tamasheq. Les lignes approuvées doivent avoir une source et des droits réellement vérifiés ; `TO_VERIFY`, `TBD` et les marqueurs équivalents sont rejetés. Si `language_code` est absent, le système garde la compatibilité et considère la phrase comme du zarma (`dje`).
4. Dans `/admin`, importe ce CSV.

### Option B : préparer les consignes de parole spontanée ASR

1. Ouvre `examples/elicitation_prompts_template.csv`.
2. Fais rédiger et relire les consignes dans la langue cible. Elles doivent déclencher une réponse ouverte sans imposer les mots que le participant doit prononcer.
3. Remplis la source et la licence/les conditions d'utilisation, `native_reviewed_by`, `native_reviewed_at`, et passe à `APPROVED` uniquement après une revue réelle.
4. Dans `/admin`, importe le CSV. Une consigne ne sera proposée qu'à la langue correspondante. Si aucune consigne validée n'existe pour cette langue, le mode spontané reste bloqué.

### Option C : examiner les phrases de démarrage

Le fichier `examples/phrases_seed_DO_NOT_IMPORT_UNREVIEWED.csv` contient 10 phrases initiales référencées à un guide de Peace Corps/Niger. La transcription et la traduction française doivent être contrôlées par un locuteur natif ; le document date de 2006 et les conventions peuvent différer de l'usage actuel.

Après vérification, corrige le texte si nécessaire, donne à `orthography_version` le nom de la convention effectivement retenue (par exemple `zarma_orthography_v1`), puis remplace `PENDING_NATIVE_REVIEW` par `APPROVED` uniquement pour les lignes approuvées. L'importateur rejettera les lignes qui restent en attente. N'utilise pas ces lignes non relues pour entraîner un modèle.

Sources des exemples : [Peace Corps/Niger : An Introduction to the Zarma Language (PDF)](https://files.peacecorps.gov/multimedia/audio/languagelessons/niger/NE_Zarma_Language_Lessons.pdf), en particulier les leçons 2 à 5. Le fait qu'une phrase soit transcrite dans le guide ne remplace pas la validation de son adéquation au corpus actuel.

## 4. Pilote terrain

1. Complète le consentement et définis une personne responsable du corpus ainsi qu'un réviseur linguistique.
2. Attribue des codes pseudonymes comme `ZRM-001`. N'utilise pas de nom, de numéro de téléphone ou d'information personnelle comme identifiant.
3. Teste sur au moins deux téléphones/navigateurs avec 5 phrases.
4. Fais enregistrer une seule phrase par fichier. Les personnes peuvent écouter et recommencer avant l'envoi.
5. Dans `/admin`, écoute chaque prise et compare l'audio à la phrase affichée.
6. Pour chaque lecture, vérifie la fidélité au texte et décide de l'éligibilité ASR, TTS ou des deux. Pour la parole spontanée, corrige ou transcris les mots prononcés puis approuve uniquement pour l'ASR. Les décisions « À refaire » et « Rejeter » exigent un commentaire.
7. Si une prise est marquée **À refaire**, le participant doit recharger ou rouvrir la page avec le même code ; cette phrase sera prioritaire.
8. Quand les prises sont validées, télécharge le ZIP du corpus.

### Accès depuis un téléphone

L'enregistrement par navigateur nécessite généralement un contexte sécurisé (**HTTPS**), sauf exceptions telles que `localhost`. Pour le pilote sur téléphone, déploie l'application sur une adresse HTTPS et vérifie que le serveur utilise un volume persistant. Ne rends pas l'application publique en conservant des paramètres de démonstration.

## 5. Préparer un export pour la suite ML

Après l'export de l'administration, commence par inspecter les fichiers et faire relire un échantillon. Puis prépare un dossier de travail :

```bash
# Après avoir téléchargé l'export ASR depuis /admin
python scripts/prepare_dataset.py \
  --input /chemin/vers/voix-du-niger-asr-approved.zip \
  --out-dir data/asr_dje_prepared \
  --task asr \
  --language-code dje \
  --seed 42

# Après avoir téléchargé l'export TTS depuis /admin
python scripts/prepare_dataset.py \
  --input /chemin/vers/voix-du-niger-tts-approved.zip \
  --out-dir data/tts_dje_prepared \
  --task tts \
  --language-code dje \
  --seed 42
```

Exécute le script séparément pour chaque langue. Pour le hausa, utilise `--language-code ha` et un dossier de sortie différent ; pour le tamasheq, utilise `--language-code taq`. Si le ZIP contient plusieurs langues et que cette option est omise, le script s'arrête au lieu de les mélanger.

Le dossier cible doit être absent ou vide. Si plusieurs langues sont présentes, donne toujours `--language-code dje`, `--language-code ha` ou `--language-code taq`. Le manifeste inclut la langue, la catégorie et la version orthographique. Le script crée :

```text
data/tts_prepared/
├── audio/                 # WAV normalisés
├── train.csv              # manifeste générique
├── validation.csv
├── test.csv
├── quality_report.csv     # durée, volume RMS, clipping, hash, drapeaux
├── excluded_errors.csv    # créé uniquement si des entrées sont invalides
└── dataset_summary.json
```

Le script vérifie les WAV mono PCM 16 bits, la durée, le silence/volume faible, le clipping et les doublons audio exacts. Les prises techniquement suspectes sont exclues des trois manifestes par défaut et signalées dans `quality_report.csv`, mais elles restent dans le dossier `audio/` pour inspection. Ce sont des heuristiques : écoute les cas signalés avant de décider de les conserver ou de les refaire.

Si le modèle exige une fréquence différente de celle de l'export, vérifie d'abord sa documentation, puis rééchantillonne, par exemple :

```bash
python scripts/prepare_dataset.py \
  --input /chemin/vers/voix-du-niger-tts-approved.zip \
  --out-dir data/tts_dje_prepared_16k \
  --task tts \
  --language-code dje \
  --target-sample-rate 16000
```

N'impose pas 16 kHz ou 22,05 kHz arbitrairement : la fréquence doit correspondre au modèle et à sa recette d'entraînement. La valeur par défaut de l'application est 22 050 Hz, configurable via `ZARMA_EXPORT_SAMPLE_RATE`.

Par défaut, `--task asr` sépare par locuteur (`--group-by speaker`) afin qu'une même voix ne soit pas à la fois en entraînement et en test. Il faut au moins trois groupes de locuteurs ; un petit pilote peut ne pas suffire à produire une évaluation fiable. `--task tts` utilise `--group-by phrase` par défaut afin de réserver des phrases non vues. `--group-by phrase` regroupe les textes après normalisation Unicode, casse, espaces et ponctuation. N'interprétez pas les métriques avant d'avoir vérifié les transcriptions et les splits.

**Important :** les colonnes CSV sont génériques. Un modèle TTS peut exiger un format spécifique (par exemple `audio_file|text` pour une recette donnée, ou un objet `datasets` avec une colonne audio). Convertis les manifestes à ce format après avoir choisi le modèle ; ne modifie pas le texte sans règle linguistique explicite.

## 6. Après la préparation : fine-tuning

Consulte [TRAINING_GUIDE.md](TRAINING_GUIDE.md), qui explique :

- comment examiner le corpus et normaliser le texte et l'audio étape par étape ;
- comment sélectionner et tester un modèle pré-entraîné avant tout entraînement ;
- comment établir un protocole FFT de référence et quand envisager LoRA/QLoRA ;
- quelles pertes, métriques, courbes et évaluations humaines suivre ;
- comment sélectionner le meilleur checkpoint et évaluer les audios générés.

Ne pars pas du principe que n'importe quel modèle TTS peut être fine-tuné avec PEFT/QLoRA. Le support dépend de l'architecture et de la recette d'entraînement ; le guide détaille cette décision.

## 7. Limites et protection des données

- Le texte de consentement est une **ébauche pour pilote**. Avant la collecte formelle, préciser le responsable, le partage, l'entraînement de modèles, la publication, l'usage commercial éventuel, la durée de conservation, l'accès et le retrait/effacement, y compris la gestion des exports et sauvegardes.
- Le MVP possède des comptes d’équipe et un contrôle d’accès par rôles et périmètres, mais il manque encore plusieurs protections de production : limitation des tentatives de connexion, procédure de réinitialisation/autorisations de support pleinement opérationnelle, file d’envoi hors ligne persistante, sauvegardes chiffrées et suppression automatisée des sauvegardes/exports/copies ou des modèles dérivés. L’effacement du MVP ne supprime que le stockage actif. Il ne doit pas être ouvert au public avant traitement des bloqueurs de `docs/PUBLIC_READINESS.md`.
- Le registre des providers et des runs conserve la configuration et le suivi ; il ne se connecte pas encore à SSH/Slurm/notebook/cloud GPU et ne soumet pas de jobs distants. Voir `docs/RBAC_TRAINING_OPERATIONS.md` avant de le présenter comme une orchestration de training intégrée.
- Le serveur vérifie la signature puis exécute ffprobe et un décodage FFmpeg complet avec délais bornés ; la durée stockée provient du fichier décodé, pas du navigateur. Vérifier cette chaîne sur l'environnement cible et sur les formats réellement envoyés par les téléphones avant l'ouverture du service.
- Le catalogue contient les onze catégories linguistiques citées par la Charte de la Refondation 2025, avec Dazaga disponible comme sous-corpus distinct sous la catégorie Tubu/Toubou, plus le français et l’anglais comme langues de travail. Leur présence dans l’interface n’indique pas qu’un corpus est prêt : chaque langue et variété doit être activée après préparation des consignes, validation humaine et vérification des droits. Une validation native reste obligatoire. Les exports conservent `language_code` et l’approbation par tâche ; ne redistribue pas de données sans consentement et droits vérifiés.
- Le fichier final ne doit contenir que des enregistrements validés dont les usages sont autorisés.
- Sauvegarde la base SQLite et les audios ensemble ; teste régulièrement la restauration. N'expose pas les fichiers bruts ou la base sur le web.
- Le modèle `facebook/mms-tts-ses` est entraîné pour le Songhay/Koyraboro Senni, pas pour le zarma, et sa licence est CC-BY-NC 4.0. Il peut servir d'expérience de transfert uniquement après vérification technique et juridique ; il ne faut pas le présenter comme un modèle zarma prêt à l'emploi.

## Feriji : comment l’utiliser dans ce projet

Feriji est un corpus **textuel français–zarma**, et non un corpus audio. Il contient environ 61 085 phrases en zarma, 42 789 en français et un glossaire de 4 062 entrées. Il peut aider à créer une banque de phrases de collecte, diversifier le vocabulaire, construire des catégories et relier des exemples à leur traduction française. Il ne peut pas entraîner directement un TTS sans audio correspondant à chaque phrase.

Flux recommandé : sélectionner des phrases candidates → vérifier leur provenance et leurs droits → faire valider l’orthographe et le naturel par un locuteur natif → enregistrer ces phrases via l’application → conserver source et version d’orthographe dans les métadonnées. Ne pas traduire automatiquement les phrases Feriji en hausa ou en tamasheq et considérer ces traductions comme validées.

Le dépôt Hugging Face indique la licence **CC-BY-NC-4.0** et demande d’accepter des conditions d’accès aux fichiers. Conserver l’attribution et ne pas présumer que le corpus ou ses dérivés peuvent être redistribués ou exploités commercialement ; vérifier les conditions avant usage.

- [Feriji sur Hugging Face](https://huggingface.co/datasets/27Group/Feriji)
- [Dépôt GitHub Feriji](https://github.com/27-GROUP/Feriji)
- [Article ACL 2024](https://aclanthology.org/2024.acl-srw.1/)

## 8. Structure

```text
zarma-tts-mvp/
├── app/
│   ├── main.py
│   └── static/                 # interface participant et admin
├── examples/
│   ├── phrases_template.csv
│   ├── elicitation_prompts_template.csv
│   └── phrases_seed_DO_NOT_IMPORT_UNREVIEWED.csv
├── scripts/
│   └── prepare_dataset.py
├── tests/
├── TRAINING_GUIDE.md
├── docs/ASR_TRAINING_GUIDE.md
├── START_HERE.md
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## 9. Tests

Installer les dépendances de l'application, puis :

```bash
pip install pytest
pytest -q
```

Les tests couvrent les principales routes du MVP, le catalogue linguistique, les permissions RBAC, la portée régionale des releases et la préparation d’un corpus artificiel. Ils ne remplacent pas une vérification réelle sur téléphone, la revue juridique du consentement ou les tests linguistiques par des locuteurs de chaque langue concernée.
