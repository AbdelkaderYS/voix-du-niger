# Démarrage rapide

## Choisir une langue

Dans la page de collecte, choisis une langue du catalogue national. Les onze catégories mentionnées dans la Charte 2025 sont présentes, mais chaque langue reste en préparation ou en pilote jusqu’à ce que sa variété, ses textes et ses droits soient vérifiés. **Lire des phrases** sert potentiellement à l'ASR et au TTS après revue dédiée. **Parler librement** (parole spontanée) sert à l'ASR seulement après transcription vérifiée. Une langue n'apparaît comme choix qu'une fois au moins une phrase ou une consigne approuvée importée. L'application n'affiche que des phrases/consignes importées et approuvées pour la langue sélectionnée ; elle n'invente pas de contenu local.

CSV : `language_code,text_prompt,category,orthography_version,source,source_license,native_review_status,native_reviewed_by,native_reviewed_at` (le champ historique `text_zarma` reste accepté). Le champ `text_zarma` est conservé pour compatibilité technique, mais il contient le texte dans la langue indiquée par `language_code`.

## 1. Lancer l'application en local

Prérequis : Python 3.11+ et FFmpeg.

```bash
cd zarma-tts-mvp
python -m venv .venv
source .venv/bin/activate       # Windows : .venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
export ZARMA_ADMIN_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(40))')"
export ZARMA_BOOTSTRAP_ADMIN_USERNAME="admin-local"
export ZARMA_BOOTSTRAP_ADMIN_PASSWORD="remplacer-par-un-secret-unique-de-14-caracteres-minimum"
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Sous Windows PowerShell :

```powershell
$env:ZARMA_ADMIN_TOKEN = (python -c "import secrets; print(secrets.token_urlsafe(40))")
$env:ZARMA_BOOTSTRAP_ADMIN_USERNAME = "admin-local"
$env:ZARMA_BOOTSTRAP_ADMIN_PASSWORD = "remplacer-par-un-secret-unique-de-14-caracteres-minimum"
```

Ouvre <http://127.0.0.1:8000> pour collecter, puis <http://127.0.0.1:8000/admin> pour l’administration. Connecte-toi avec le nom et le mot de passe bootstrap. La clé `ZARMA_ADMIN_TOKEN` n’est qu’un accès d’urgence et sert aussi au script de préparation côté serveur ; garde-la hors des dépôts publics. HTTPS est obligatoire avant tout accès depuis un autre appareil.

## 2. Importer les textes de collecte

- Phrases lues : `examples/phrases_template.csv`.
- Consignes spontanées : `examples/elicitation_prompts_template.csv`.
- Exemples zarma en attente de revue : `examples/phrases_seed_DO_NOT_IMPORT_UNREVIEWED.csv`.

**Les dix exemples attendent une validation linguistique.** Confirme leur orthographe, leur sens, leur naturel et leur adéquation à la variante de zarma visée avec un locuteur compétent. Dans ce fichier, remplace `PENDING_NATIVE_REVIEW` par `APPROVED` uniquement pour les lignes approuvées. L'importateur refuse les lignes en attente.

Pour les phrases lues et les consignes spontanées, renseigne la source, des conditions d’utilisation réellement vérifiées, le statut de validation, le réviseur natif et la date. Les marqueurs provisoires comme `TO_VERIFY`, `TBD` et `PENDING_RIGHTS_REVIEW` sont refusés. Le mode reste indisponible si aucune consigne n'a été approuvée pour cette langue. Un fichier modèle n'est pas un prompt validé.

## 3. Faire un pilote

1. Complète les informations de consentement avant toute collecte formelle.
2. Importe seulement des phrases et consignes relues et approuvées.
3. Teste l'enregistrement, l'envoi et la révision sur au moins deux téléphones/navigateurs.
4. Pour la parole spontanée, un réviseur doit retranscrire les mots audibles avant l'approbation ASR.
5. Pour le TTS, n'approuve que les lectures dont la phrase exacte correspond à l'audio et dont la qualité/les droits sont acceptables.
6. Si une prise est marquée « À refaire », le participant recharge la page avec le même code pour retrouver cet élément en priorité.
7. Exporte ASR et TTS séparément.

Pour le téléphone, configure HTTPS. Le MVP dispose désormais de comptes internes, de rôles, de périmètres et d’un journal d’audit administratif ; les contrôles de production (anti-brute-force, sauvegardes chiffrées, suppression des exports et récupérations de compte) restent à finaliser avant une collecte publique.

## 4. Préparer les données avant le fine-tuning

```bash
python scripts/prepare_dataset.py \
  --input /chemin/vers/voix-du-niger-tts-approved.zip \
  --out-dir data/tts_prepared \
  --task tts \
  --language-code dje \
  --seed 42
```

Vérifie `quality_report.csv`, puis `train.csv`, `validation.csv` et `test.csv`. Pour ASR, utilise `--task asr`, l'export ASR et le [guide ASR](docs/ASR_TRAINING_GUIDE.md). Pour TTS, utilise `--task tts` et `TRAINING_GUIDE.md`. FFT est la référence si l'architecture et les ressources le permettent ; LoRA/QLoRA ne sont des solutions de repli que si la recette du modèle les supporte.

## 5. Tests automatisés

```bash
pip install -r requirements-dev.txt
pytest -q
```

La suite teste les routes principales, la migration, les contrôles d’import et de périmètre, l’éligibilité ASR/TTS, le RBAC et l’export avec des fichiers audio artificiels. Elle ne remplace pas les tests réels depuis un téléphone ni une validation par des locuteurs compétents pour chaque langue et variété.
