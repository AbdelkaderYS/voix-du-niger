# Préparer et évaluer un corpus ASR : Voix du Niger

Ce guide s’applique aux langues et sous-corpus du catalogue national, dont le Zarma (`dje`), le Hausa (`ha`), le Tamajaq/Tamasheq (`taq`), le Teda/Tedaga (`tuq`) et le Dazaga (`dzg`). Les exemples utilisent les trois codes de pilote historiques, mais le traitement reste par langue et variété : ne mélange pas les sous-corpus pour entraîner un même modèle sans justification explicite. Le MVP collecte et prépare les données ; il n’entraîne ni n’exécute encore de modèle ASR.

## 1. Définir le jeu de données

Pour l'entraînement ASR, une ligne approuvée doit associer :

- un fichier audio décodable et contrôlé ;
- la transcription exacte de ce qui est audible, pas seulement le texte suggéré à l'écran ;
- le code de langue et, si disponible, la variante ;
- un identifiant pseudonyme stable de locuteur ;
- la provenance, les conditions de réutilisation et les métadonnées utiles à la traçabilité.

Les lectures de phrases et la parole spontanée peuvent toutes deux contribuer au corpus ASR si elles sont validées. Elles devraient rester identifiables dans `task_type` pour pouvoir évaluer les différences entre parole lue et parole naturelle. La parole spontanée ne doit pas être transcrite à partir de la consigne affichée : il faut écouter l'audio.

## 2. Exporter un corpus par tâche et par langue

Dans l'espace `/admin`, télécharger l'export ASR. Puis lancer le script séparément pour chaque langue :

```bash
python scripts/prepare_dataset.py \
  --input /chemin/voix-du-niger-asr-approved.zip \
  --out-dir data/asr_dje_prepared \
  --task asr \
  --language-code dje \
  --seed 42
```

Pour le Hausa, utiliser `--language-code ha` et un dossier séparé ; pour le Tamasheq, `--language-code taq`. Pour Teda/Tedaga et Dazaga, garder respectivement `tuq` et `dzg` dans des corpus séparés. La commande refuse d'enchaîner involontairement des langues mélangées. Par défaut le script regroupe les données par locuteur pour réduire les fuites entre entraînement, validation et test. Il faut suffisamment de locuteurs pour que ce split soit utile ; trois groupes est une limite technique minimale, pas une taille de corpus recommandée.

Le script crée les manifests `train.csv`, `validation.csv`, `test.csv`, le rapport technique et un résumé. Les durées et seuils par défaut sont seulement des filtres initiaux : écouter les fichiers signalés avant d'exclure définitivement les données.

## 3. Vérifier les transcriptions

Avant l'entraînement :

1. faire revoir les consignes, la transcription et les conventions d'écriture par des locuteurs compétents ;
2. définir comment annoter les hésitations, répétitions, mots incomplets, emprunts, noms propres, chiffres et segments inaudibles ;
3. conserver le texte brut révisé et créer la forme normalisée pour l'évaluation sans écraser la source ;
4. inspecter les cas qui semblent très courts, très longs, silencieux, coupés ou dupliqués ;
5. produire un test indépendant, représentatif des locuteurs et des situations d'utilisation visées.

N'applique pas une normalisation agressive spécifique au français. Les conventions doivent être définies pour chaque langue et utilisées de la même manière pour la référence et les prédictions.

## 4. Modèle de départ et entraînement

Comparer d'abord des modèles existants sur le test local, en vérifiant leurs langues déclarées, licences, tokenisation et qualité réelle. Un modèle multilingue peut échouer fortement sur une langue à faibles ressources ; la présence d'un code de langue ou d'une étiquette « multilingual » n'est pas une preuve de performance.

Établir un baseline sans fine-tuning. Ensuite, suivre prioritairement la recette officielle du modèle choisi. Tester le Full Fine-Tuning (FFT) comme référence si l'architecture, le volume de données et le matériel le permettent. Si la mémoire ou le coût rendent FFT impraticable, comparer LoRA, puis QLoRA uniquement si cette architecture et son code d'entraînement les supportent. Ne pas transposer automatiquement des paramètres d'un LLM texte à un encodeur-décodeur audio.

Ne fixer ni taux d'apprentissage, ni nombre d'époques, ni taille de batch universels. Utiliser la configuration de référence du checkpoint, puis une recherche limitée, avec arrêt fondé sur la métrique de validation et sauvegarde de la configuration complète.

## 5. Évaluation

Calculer au minimum :

- **WER** (Word Error Rate) lorsque la segmentation en mots est linguistiquement pertinente ;
- **CER** (Character Error Rate) comme mesure complémentaire, particulièrement si les conventions de segmentation ou d'écriture le justifient ;
- les scores séparés par langue, variante, type de parole et conditions d'enregistrement ;
- un audit qualitatif de noms propres, chiffres, négations, termes locaux et erreurs qui changeraient le sens.

Publier la version de normalisation, les partitions, la provenance du modèle, les licences, les métriques et les limites. Ne pas comparer deux WER calculés avec des conventions différentes.

## 6. Limites du MVP

La réception vérifie les signatures, la présence d'un flux audio, la durée décodée et un décodage FFmpeg complet avec délais bornés. Il reste à tester les formats réellement envoyés par les appareils ciblés. La file d'envoi hors ligne, les comptes individuels et la procédure intégrée de retrait restent à faire. Suivre `docs/PUBLIC_READINESS.md` avant toute campagne ouverte.
