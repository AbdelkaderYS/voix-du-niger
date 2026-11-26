# Guide d'entraînement : du corpus Zarma TTS au modèle évalué


> **Corpus multilingue :** ne mélange pas automatiquement les trois langues dans un même fine-tuning monolingue. Lance le script de préparation séparément avec `--language-code dje`, `--language-code ha` ou `--language-code taq`. Un modèle multilingue partagé peut être évalué plus tard, mais il nécessite une conception et une évaluation explicitement multilingues.

Ce guide décrit le chemin complet entre l'export audio du MVP et une première évaluation d'un modèle de synthèse vocale en zarma. Il distingue les contrôles indépendants de l'architecture des décisions qui dépendent du modèle choisi.

> **Stratégie retenue pour Voix du Niger :** commencer par le *Full Fine-Tuning* (FFT), c’est-à-dire mettre à jour tous les paramètres que la recette du modèle autorise à entraîner. C’est notre référence expérimentale, pas une garantie de meilleure qualité. Si la mémoire GPU, le temps ou le coût rendent ce protocole impraticable, tester ensuite LoRA, puis QLoRA uniquement si l’architecture le prend réellement en charge. Les modèles vocaux n’acceptent pas tous PEFT ou la quantification 4 bits.

## 0. Définir le résultat recherché

La première cible raisonnable est une **voix de référence unique** : un locuteur, une convention d'écriture, un jeu de phrases bien vérifiées et une prononciation cohérente. Plusieurs voix pourront être ajoutées après ce premier essai.

Il faut séparer trois objectifs :

1. **Faire fonctionner la chaîne** : texte → prétraitement → entraînement → audio généré.
2. **Obtenir une voix intelligible** : les mots sont-ils reconnaissables et fidèles au texte ?
3. **Améliorer la qualité** : naturel, prosodie, rythme, cohérence de la voix et latence.

Un modèle qui termine l'entraînement n'est pas nécessairement un bon modèle. Un `loss` qui baisse ne prouve pas, à lui seul, que la prononciation en zarma s'améliore.

## 1. Choisir et tester la base TTS avant de collecter beaucoup plus

Le choix de l'architecture conditionne le jeu de caractères, le prétraitement, les pertes et la possibilité d'utiliser LoRA/QLoRA. Avant de lancer un gros entraînement, crée un petit test technique sur 20 à 50 phrases vérifiées.

Pour chaque modèle candidat, vérifie :

- **Langue et écriture** : comment le modèle transforme le texte en unités ? Les lettres, graphèmes et diacritiques utiles au zarma sont-ils conservés ? Quel est le taux d'unités inconnues (`UNK`) ? Peut-on utiliser des caractères, des phonèmes ou un lexique/G2P ?
- **Base de données d'entraînement** : est-ce un modèle TTS vraiment pré-entraîné, un modèle multilingue, un modèle de clonage de voix, ou seulement un modèle de reconnaissance vocale ?
- **Recette de fine-tuning** : le dépôt fournit-il du code et des formats compatibles avec tes fichiers et le modèle ?
- **Licence** : autorise-t-elle l'usage visé, notamment publication ou commercialisation ? Vérifie séparément la licence des poids, du code et des données.
- **Résultat de référence** : peux-tu générer un audio compréhensible avant l'entraînement sur des phrases zarma ? Sauvegarde ces exemples comme baseline.

### Pistes à examiner, sans les considérer comme des solutions garanties

- [MMS-TTS pour Songhay/Koyraboro Senni (`facebook/mms-tts-ses`)](https://huggingface.co/facebook/mms-tts-ses) : c'est un checkpoint VITS annoncé pour **Songhay, Koyraboro Senni (`ses`)**, et non un modèle déclaré zarma. La proximité linguistique peut justifier un test exploratoire, mais il faut vérifier l'écriture, la phonétique, l'architecture de fine-tuning et la qualité obtenue. Sa licence affichée est **CC-BY-NC 4.0** : ne pas l'utiliser dans un produit commercial sans autre autorisation/licence adaptée.
- [XTTS-v2](https://docs.coqui.ai/en/latest/models/xtts.html) : la documentation énumère 16 langues, sans le zarma. La recette de fine-tuning documentée porte sur son GPT encoder ; ce n'est pas une recette universelle LoRA/QLoRA, et le modèle est soumis à la Coqui Public Model License. Ne suppose pas qu'une voix zarma sera bien prononcée parce que le modèle accepte plusieurs langues.
- [SpeechT5 : guide de fine-tuning TTS de Hugging Face](https://huggingface.co/docs/transformers/tasks/text-to-speech) : la procédure officielle explique le traitement des textes, des audios et l'évaluation d'un modèle pré-entraîné. Le guide utilise une base initialement entraînée en anglais et la fine-tune sur du néerlandais ; cela ne garantit ni la prise en charge du zarma ni un fine-tuning LoRA prêt à l'emploi.

**Décision obligatoire après le test :** sélectionner une base et sa recette spécifique. Si aucun modèle ne produit un audio raisonnable avec des phrases zarma, améliorer d'abord l'interface texte/phonèmes ou tester une autre base. Ajouter des adapters ne compense pas une couverture linguistique insuffisante.

## 2. Quantité de données : objectifs de planification

Les volumes ci-dessous sont des jalons de projet, pas des seuils universels de réussite. Le besoin réel dépend fortement du modèle, de son adéquation au zarma, de la qualité de la transcription et de la diversité phonétique.

| Phase | Objectif indicatif | But |
|---|---:|---|
| Test technique | 20–50 phrases | Vérifier le flux complet et les problèmes d'écriture/texte |
| Petit overfit de débogage | 50–200 phrases | Vérifier que la perte bouge et que la chaîne génère du son exploitable ; ce n'est pas une évaluation finale |
| Pilote de données | 30–60 minutes validées | Inspecter la qualité réelle des fichiers et affiner le protocole |
| Première expérience de transfert | Environ 3–5 heures propres | Évaluer si une base pré-entraînée peut apprendre une voix de référence |
| Extension | 5–10 heures ou davantage, selon les résultats | Augmenter la couverture des sons, mots, longueurs et structures grammaticales |

Avant de multiplier les heures, mesure les erreurs. Une heure de données avec de mauvais textes est moins utile qu'une heure bien contrôlée. Le modèle ne peut pas apprendre de façon fiable à partir de texte qui ne correspond pas à ce qui est prononcé.

## 3. Prétraitement des données, étape par étape

### Étape 1 : préserver l'export source

Garde le ZIP original du MVP intact, ainsi qu'une copie de la liste des phrases validées et de la version du protocole de collecte. Travaille sur une copie. Ne partage pas publiquement les enregistrements bruts sans autorisation explicite.

Le ZIP contient `metadata.csv` et les WAV validés. Le champ `phrase_id` aide à tracer la phrase source. Pour le split, le script regroupe par transcription normalisée (Unicode, casse, espaces et ponctuation) afin que des imports équivalents ne se retrouvent pas dans des splits différents même si leurs `phrase_id` divergent.

### Étape 2 : écouter et vérifier la correspondance texte/audio

Pour toutes les prises, au minimum pendant le pilote :

- écoute le fichier en entier ;
- vérifie qu'il commence et finit sans tronquer la parole ;
- compare chaque mot au texte enregistré ;
- vérifie les répétitions, mots omis, hésitations, autres voix et bruits ;
- demande une nouvelle prise si une erreur modifie le texte prononcé.

L'automatisation ne peut pas confirmer la justesse du zarma sans modèle de reconnaissance adapté et fiable. Utilise une revue humaine, avec une seconde écoute pour les cas ambigus.

### Étape 3 : vérifier les propriétés techniques

Contrôle :

- le fichier est lisible et non vide ;
- la fréquence d'échantillonnage correspond à celle exigée par la base TTS ;
- le nombre de canaux, la profondeur de bits et l'encodage sont acceptés par la recette ;
- la durée est plausible pour une phrase ;
- le signal n'est pas presque silencieux ni fortement écrêté (*clipping*) ;
- les fichiers ne sont pas des doublons exacts.

L'export MVP produit normalement du WAV mono PCM 16 bits à 22 050 Hz. Cela ne veut pas dire que tous les modèles attendent 22 050 Hz. Si la base demande 16 kHz, 24 kHz ou une autre fréquence, convertis avec le taux exact de la recette. Ne change pas la fréquence en réétiquetant simplement le fichier : il faut réellement rééchantillonner.

### Étape 4 : inspecter les drapeaux automatiques

Lance :

```bash
python scripts/prepare_dataset.py \
  --input data/zarma-tts-approved.zip \
  --out-dir data/tts_prepared \
  --group-by phrase \
  --seed 42
```

Le dossier cible doit être vide ou ne pas encore exister. Consulte en priorité :

- `quality_report.csv` pour les durées, le volume RMS, le clipping, les hashes et les raisons d'exclusion ;
- `excluded_errors.csv` s'il existe ;
- `dataset_summary.json` pour les comptes par split.

Les drapeaux `too_short`, `too_long`, `very_quiet_or_silent` et `possible_clipping` sont des **heuristiques**. Ils peuvent signaler des problèmes réels, mais aussi certains cas acceptables. Écoute les fichiers signalés avant de les refaire, de les corriger ou de les exclure. Les doublons exacts sont exclus par défaut des manifestes ; les fichiers originaux sont conservés dans le dossier de sortie pour audit.

Pour rééchantillonner vers 16 kHz, seulement si le modèle le demande :

```bash
python scripts/prepare_dataset.py \
  --input data/zarma-tts-approved.zip \
  --out-dir data/tts_prepared_16k \
  --target-sample-rate 16000 \
  --group-by phrase
```

N'utilise `--include-flagged` qu'après avoir écouté les prises signalées. N'utilise `--keep-exact-duplicates` que si tu as une raison documentée de conserver des fichiers audio identiques.

### Étape 5 : normaliser le texte sans effacer des distinctions linguistiques

Crée une règle écrite et versionnée que tous les textes suivent. Vérifie notamment :

- orthographe et variante/dialecte retenus ;
- majuscules/minuscules, espaces et ponctuation ;
- représentation des chiffres, montants, dates, heures et abréviations ;
- graphèmes spéciaux, apostrophes, diacritiques et combinaisons de caractères ;
- prononciation des noms propres et mots empruntés.

Ne supprime pas automatiquement les signes diacritiques ou la ponctuation sans vérifier si cela change la prononciation ou l'interprétation. Ne transforme pas les chiffres en mots à l'aveugle. Si le modèle attend un front-end phonémique, fixe une convention de phonèmes/graphèmes, puis teste-la avec un locuteur.

Le manifeste du script garde le texte tel qu'il est fourni dans le corpus, sauf suppression des espaces de bord pour le traitement technique. Le prétraitement spécifique au modèle (tokenisation, conversion phonémique, extraction de spectrogrammes ou embeddings de locuteur) vient ensuite.

### Étape 6 : segmenter et aligner

Le MVP recommande une phrase par enregistrement. Évite de fusionner plusieurs phrases dans un seul fichier ou de couper une phrase au milieu. Si un fichier doit être coupé, il faut réviser les timestamps et les transcriptions pour chaque segment.

Ne déplace pas les mots d'un segment à l'autre pour corriger un enregistrement. Refais la prise ou corrige ses métadonnées après écoute et validation humaine.

### Étape 7 : séparer train/validation/test sans fuite de texte

Le script crée `train.csv`, `validation.csv` et `test.csv` avec une graine fixe. Par défaut, les enregistrements ayant la même transcription après normalisation sont placés ensemble, même si leurs `phrase_id` diffèrent. Les proportions visées sont approximativement 80/10/10 ; avec peu de phrases, les proportions réelles varient.

- **Train** : met à jour les poids ou l'adapter.
- **Validation** : choisit les hyperparamètres et le meilleur checkpoint. Elle ne sert pas au gradient d'entraînement.
- **Test** : évaluation finale, à consulter après le choix du modèle ; ne l'utilise pas pour ajuster en permanence les hyperparamètres.

Avec plusieurs locuteurs, `--group-by speaker` place un locuteur dans un seul split. Cela répond à une question différente : généraliser à une voix non vue. Avec une seule voix cible, `--group-by phrase` est le bon point de départ.

### Étape 8 : adapter le format au modèle choisi

Les CSV préparés sont génériques. Le modèle retenu peut demander un JSONL, un TSV avec `audio|text`, un `datasets.Dataset` Hugging Face, ou des métadonnées spécifiques. Écris un petit adaptateur qui convertit le manifeste sans changer le sens du texte ni les chemins audio.

Avant l'entraînement complet, vérifie manuellement 10 lignes tirées au hasard : texte, fichier présent, échantillonnage, durée et identifiant correspondent.

### Étape 9 : inspecter la couverture du texte

Vérifie que toutes les lettres, caractères, graphèmes et phonèmes de la convention zarma sont pris en charge par le tokenizer ou le front-end du modèle. Compte les unités inconnues et les caractères supprimés. Si le modèle utilise des phonèmes, vérifie un échantillon de conversion grapheme-to-phoneme avec un locuteur compétent.

Évalue aussi la couverture des sons et des structures : questions, négations, phrases courtes et longues, mots fréquents, nombres et noms propres. La liste des dix phrases de démonstration n'est pas un corpus d'entraînement suffisant.

## 4. Stratégie d’entraînement : FFT d’abord, LoRA/QLoRA si nécessaire

### 4.1 Approche de référence : Full Fine-Tuning (FFT)

Le premier protocole doit suivre la recette officielle du modèle sélectionné et entraîner tous les paramètres que cette recette déclare entraînables. Avant de lancer un entraînement complet, vérifier que la mémoire disponible suffit à stocker les poids, gradients, états de l’optimiseur et activations. Pour un modèle vocal petit (par exemple une architecture VITS), le FFT peut être réaliste sur un GPU modeste ; pour un gros Transformer ASR ou un LLM, il peut demander beaucoup plus de VRAM ou plusieurs GPU.

Le terme FFT ne signifie pas nécessairement que chaque paramètre est toujours dégelé : certains modèles comportent des composants gelés par conception dans leur recette officielle. Consigner précisément quels paramètres sont entraînés.

### 4.2 Hyperparamètres : protocole initial

Les valeurs ci-dessous sont des plages de départ pour concevoir un pilote, et non des paramètres universels. **La recette officielle du checkpoint retenu prime toujours**, en particulier pour le TTS. Choisir le learning rate, le scheduler, le batch et la définition de la loss en fonction de l’architecture.

| Paramètre | Point de départ à tester | Règle de décision |
|---|---|---|
| Méthode | FFT | Référence si mémoire et recette le permettent |
| Epochs | ASR : 3–5 pour le premier pilote ; TTS : suivre la recette du modèle et piloter par steps/validation | Ne pas fixer le nombre final sans regarder la courbe de validation ; le TTS peut nécessiter un nombre de steps très différent selon l’architecture |
| Learning rate | Ne pas imposer une valeur unique ; reprendre la recette officielle. Pour une première recherche, tester un ordre de grandeur plus prudent puis ajuster | Faire une petite recherche contrôlée ; un taux trop élevé peut dégrader la voix ou faire diverger la perte |
| Optimiseur | Celui recommandé par le checkpoint (souvent AdamW pour des modèles Transformer ; les recettes TTS peuvent différer) | Ne pas remplacer sans raison la recette publiée |
| Scheduler / warmup | Valeurs de la recette officielle ; warmup en fraction des steps si recommandé | Conserver les mêmes règles entre les essais comparés |
| Batch effectif | Le plus grand batch stable ; si nécessaire utiliser l’accumulation de gradients | Consigner batch GPU et batch effectif séparément |
| Précision | FP32, FP16 ou BF16 selon support matériel et recette | Vérifier stabilité numérique et consommation mémoire |
| Validation | À intervalles réguliers, avec données jamais utilisées pour les gradients | Sauvegarder le meilleur checkpoint de validation, pas seulement le dernier |
| Early stopping | Si la validation se dégrade durablement et que les exemples audio stagnent | Ne pas choisir un modèle uniquement parce que la train loss baisse |

Pour le TTS, éviter d’imposer arbitrairement « 100 epochs » à toutes les architectures : certaines recettes documentent des steps, un nombre d’itérations ou une durée de formation. Pour l’ASR, 3–5 epochs constituent seulement un pilote initial ; prolonger si la validation progresse, arrêter ou réduire le learning rate si elle stagne ou se dégrade.

### 4.3 Quand passer à LoRA ou QLoRA ?

### LoRA, en bref

LoRA gèle une partie des poids pré-entraînés et apprend de petites matrices adaptatrices sur des couches sélectionnées. Cela réduit le nombre de paramètres entraînables et peut diminuer la mémoire nécessaire, si l'architecture et les modules ciblés s'y prêtent. L'adapter doit être enregistré avec l'identifiant exact et la révision du modèle de base.

### QLoRA, en bref

QLoRA ajoute LoRA à un modèle compatible chargé en précision réduite (souvent quantification 4 bits). Cela réduit encore la mémoire du composant quantifié, mais ne garantit pas une meilleure qualité, une accélération ou la compatibilité avec toutes les couches acoustiques. La quantification peut affecter le résultat et les bibliothèques ont des exigences matérielles.

### Arbre de décision pratique

1. **Le checkpoint dispose-t-il d’une recette officielle ?** La suivre pour commencer, sur un petit sous-ensemble qui permet de vérifier le chargement, le forward, le backward, la sauvegarde et la génération/transcription.
2. **Le FFT tient-il en mémoire et dans le budget ?** Si oui, lancer le pilote FFT et mesurer VRAM maximale, durée, qualité et validation. Si non, essayer d’abord les leviers pris en charge par la recette : batch plus petit, accumulation de gradients, précision mixte, gradient checkpointing ou entraînement sélectif documenté.
3. **Le FFT reste-t-il impraticable ?** Évaluer LoRA si les modules et l’architecture sont compatibles avec PEFT. Vérifier que les adaptateurs reçoivent bien des gradients.
4. **La VRAM reste-t-elle insuffisante ?** Évaluer QLoRA seulement si le composant concerné peut réellement être quantifié et entraîné avec la stack utilisée. Les convolutions, modules de synthèse et vocodeurs ne sont pas automatiquement compatibles avec les exemples QLoRA ciblant les couches linéaires de Transformer.
5. **Le modèle est-il VITS ou une autre architecture acoustique spécifique ?** Utiliser son pipeline natif. Ne pas supposer que `get_peft_model()` remplace la recette du modèle.

### Squelette LoRA : non exécutable avant inspection du modèle

Ce fragment illustre la forme générale d'une configuration PEFT ; `target_modules` doit être remplacé par les noms exacts vérifiés sur l'architecture choisie et la boucle d'entraînement doit suivre sa recette TTS :

```python
from peft import LoraConfig, get_peft_model

lora_config = LoraConfig(
    r=8,
    lora_alpha=16,
    lora_dropout=0.05,
    bias="none",
    target_modules=["REMPLACER_PAR_DES_MODULES_REELS"],
)

model = get_peft_model(model, lora_config)
model.print_trainable_parameters()
```

Inspecte les couches linéaires disponibles avant de définir `target_modules` :

```python
import torch

for name, module in model.named_modules():
    if isinstance(module, torch.nn.Linear):
        print(name)
```

**Ce n'est pas une recette complète de fine-tuning TTS.** Elle ne définit pas le chargement du modèle, le lecteur audio, la préparation du lot, les pertes, l'alignement, le décodeur/vocodeur ou l'inférence. Ces éléments dépendent de la base.

### Paramètres LoRA : uniquement pour l’expérience de repli

| Paramètre | Valeur initiale illustrative | Comment l’ajuster |
|---|---:|---|
| LoRA rank `r` | 8 | Comparer 4 ou 16 si le budget le permet |
| `lora_alpha` | 16 | Suivre les recommandations du modèle/framework |
| `lora_dropout` | 0,05 | Ajuster selon la taille du corpus et le surapprentissage |
| Learning rate adapter | Selon la recette compatible ; `1e-4` ou `5e-5` ne sont que des essais possibles, pas des valeurs prescrites | Ne pas transposer automatiquement les valeurs d’un LLM causal à un modèle audio |
| Batch effectif | Le plus grand stable | Utiliser accumulation si la recette le permet |
| Warmup / scheduler | Selon la recette du modèle | Garder les réglages comparables entre essais |
| Sélection du checkpoint | Validation et écoute d’exemples fixes | Choisir le meilleur compromis de qualité, pas automatiquement le dernier checkpoint |

Ces valeurs ne remplacent pas les hyperparamètres du FFT de référence et ne sont pas garanties pour le zarma.

### Exemple de configuration QLoRA : seulement si prise en charge

Pour un composant Transformer compatible avec Transformers + PEFT + bitsandbytes, la documentation PEFT décrit typiquement une quantification 4 bits `nf4`, une quantification imbriquée et un type de calcul adapté au GPU. Le schéma ci-dessous n'est **pas applicable automatiquement à tous les modèles TTS** :

```python
import torch
from transformers import BitsAndBytesConfig
from peft import prepare_model_for_kbit_training

compute_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
quant_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_use_double_quant=True,
    bnb_4bit_compute_dtype=compute_dtype,
)

# À n'utiliser que si from_pretrained et le composant du TTS
# acceptent cette configuration de quantification.
# model = ModelClass.from_pretrained(checkpoint, quantization_config=quant_config)
# model = prepare_model_for_kbit_training(model)
```

Avant toute vraie session, affiche la configuration matérielle, les paramètres entraînables, la mémoire GPU consommée et assure-toi que le backward pass passe sur un petit batch. N'ajoute pas de bibliothèques `bitsandbytes`/PEFT en espérant qu'elles rendront quantifiable chaque partie d'un modèle audio.

## 5. Protocole d'entraînement

### Phase A : baseline

1. Fixe une liste de 20–50 phrases de validation non utilisées pour les gradients.
2. Génère l'audio avec la base avant fine-tuning, si elle peut traiter ces textes.
3. Écoute et conserve les WAV, les textes, la seed et les paramètres de génération.
4. Si possible, fais noter les enregistrements par des locuteurs compétents sur intelligibilité, prononciation et naturel.

Si la base ne peut pas traiter correctement la convention d'écriture du zarma, note ce résultat et corrige le front-end avant de la fine-tuner.

### Phase B : test de surapprentissage contrôlé

Utilise un sous-ensemble très petit (par exemple 50–200 énoncés) pour vérifier toute la chaîne : chargement, batch, forward, pertes, gradients, sauvegarde et génération. Il est acceptable que ce mini-run surapprenne ; il sert à détecter des bugs. S'il ne peut pas apprendre ces exemples, n'engage pas encore un long entraînement.

### Phase C : entraînement principal

- Utilise le jeu train et évalue périodiquement sur validation.
- Sauvegarde les checkpoints et le meilleur checkpoint selon la métrique de validation choisie.
- Garde une graine fixe et une liste fixe de textes pour comparer les versions.
- Note les versions des bibliothèques, le modèle de base et sa révision, la configuration, la commande et le matériel utilisé.
- Reprends un checkpoint après interruption plutôt que de perdre les résultats, si la recette le permet.

Un GPU T4 peut permettre des expérimentations modestes, mais la possibilité et la vitesse dépendront fortement de l'architecture, de la taille du modèle, des séquences audio, du batch et de la précision. Démarre avec le batch le plus petit que la recette supporte, puis augmente progressivement.

## 6. Métriques à suivre pendant l'entraînement

### Métriques générales

| Métrique | À quoi elle sert | Signal de problème |
|---|---|---|
| `train_loss` / perte d'entraînement | Mesure l'objectif sur train | NaN/Inf, valeurs instables, ou aucune évolution malgré des gradients |
| `eval_loss` / perte validation | Suit la généralisation sur validation | Train baisse continuellement mais validation monte durablement : surapprentissage probable |
| Pertes par composant | Aide à trouver la partie du modèle qui bloque | Un composant explose ou reste anormal alors que les autres semblent normaux |
| Learning rate | Explique le comportement des mises à jour | Trop élevé peut produire des oscillations/divergence |
| Norme des gradients | Aide à surveiller la stabilité | Valeurs extrêmes, NaN/Inf ou gradients nuls inattendus |
| Paramètres entraînables et gradients des adapters | Vérifie que LoRA apprend réellement | Zéro paramètre trainable, ou aucun gradient sur l'adapter ciblé |
| Temps par step, mémoire GPU et erreurs OOM | Planifie les runs et diagnostique la capacité | OOM, fragmentation mémoire, très forte baisse de débit |
| Checkpoint / step / seed | Rend les comparaisons reproductibles | Impossible de relier un audio à une configuration précise |

### Pertes spécifiques selon l'architecture

Il n'existe pas de nomenclature universelle. Un modèle peut publier seulement un `loss` total ; un autre peut exposer plusieurs composants. Pour une architecture VITS ou GAN, les noms peuvent inclure par exemple :

- **mel/spectrogram reconstruction loss** : écart entre les représentations spectrales prédites et la référence ;
- **KL loss** : terme de régularisation latent dans les modèles qui en utilisent un ;
- **generator adversarial loss** et **discriminator loss** : termes de l'entraînement adversarial ;
- **feature matching loss** : comparaison de représentations internes de discriminateurs ;
- **duration/alignment loss** : objectif pour la durée ou l'alignement, lorsque la recette le prévoit.

Logue les pertes que la recette fournit et lis leur définition dans le code du modèle. Les valeurs absolues ne se comparent pas directement entre architectures ou configurations différentes. N'invente pas de métrique si le modèle ne l'expose pas.

### Fréquence de suivi recommandée

Pour une première expérience, journalise les métriques toutes les 10–50 steps et lance une évaluation audio toutes les quelques centaines de steps ou à chaque fraction d'époque, selon le temps disponible. Cette fréquence est un point de départ à adapter au volume et à la vitesse de l'entraînement.

À chaque évaluation, génère toujours les mêmes phrases de validation. Garde le même réglage de génération et, si le modèle est stochastique, la même seed pour une comparaison aussi contrôlée que possible.

### Comment interpréter les courbes

- **Train loss et validation loss diminuent, les audios s'améliorent** : poursuis et sauvegarde le meilleur checkpoint.
- **Train loss diminue, validation loss remonte et l'audio de validation se détériore** : probablement surapprentissage ; arrêter plus tôt, augmenter les données ou régulariser.
- **Pertes NaN/Inf ou audio non fini/silencieux** : vérifier learning rate, précision, échelle des entrées, batch, gradients et compatibilité de la recette.
- **Loss s'améliore, mais prononciation reste incorrecte** : vérifier les transcriptions, la couverture des graphèmes/phonèmes, le modèle de base et le split ; la perte seule n'est pas un critère suffisant.
- **Audio répétitif ou qui coupe la phrase** : inspecter longueur du texte, limites du modèle, segmentations, alignement et paramètres de génération.

## 7. Évaluation après entraînement

Ne considère pas le dernier checkpoint comme automatiquement le meilleur. Sélectionne le checkpoint sur validation, puis évalue une seule fois le jeu test final après les décisions principales.

### Évaluation humaine obligatoire

Prépare un jeu figé de 30–100 phrases de test, si la taille du corpus le permet, couvrant différents types : mots fréquents, questions, négation, phrases courtes et longues, nombres, noms propres et combinaisons de sons moins fréquentes. Fais écouter les sorties à un ou plusieurs locuteurs compétents, idéalement sans préciser quelle version est utilisée.

Pour chaque audio, note sur une échelle simple de 1 à 5 :

1. **Intelligibilité** : les mots prononcés sont-ils reconnaissables ?
2. **Exactitude de la prononciation** : l'audio correspond-il au texte ?
3. **Naturel/prosodie** : débit, pauses, intonation et rythme sont-ils plausibles ?
4. **Cohérence vocale** : la voix reste-t-elle stable d'une phrase à l'autre ?
5. **Artefacts** : craquements, coupures, répétitions, silence ou sons non linguistiques ?

Fais aussi transcrire à l'aveugle un échantillon par deux locuteurs. Si les conventions de transcription sont cohérentes, calcule un WER/CER exploratoire entre le texte de référence et les transcriptions humaines. Ce n'est pas la même chose que le WER automatique d'un ASR, et les résultats seront sensibles à l'orthographe et aux variantes dialectales.

### Métriques automatiques possibles, à interpréter avec prudence

- **WER/CER** : utile seulement si une transcription de référence fiable et des conventions de normalisation cohérentes existent. Un ASR médiocre pour le zarma faussera la mesure.
- **MOS (Mean Opinion Score)** : évaluation perceptuelle de 1 à 5 ; exige des consignes constantes et un nombre suffisant de juges pour des conclusions robustes.
- **Mel-cepstral distortion (MCD)** : possible si les références et sorties sont alignées et si l'implémentation est adaptée ; dépend de l'alignement et n'explique pas à lui seul l'intelligibilité.
- **F0 RMSE / corrélation de pitch** : seulement si la comparaison du pitch est appropriée à la recette et que les alignements sont crédibles.
- **Real-time factor (RTF)** : temps de génération divisé par la durée de l'audio généré ; RTF inférieur à 1 signifie que l'audio est généré plus vite que sa lecture. Mesure aussi le temps de latence par phrase sur la machine visée.

PESQ/STOI et des métriques provenant de la reconnaissance vocale ne sont pas automatiquement fiables pour un corpus zarma à faible ressource. Elles ne remplacent pas l'écoute humaine, surtout lorsqu'il n'y a pas d'ASR reconnu dans la langue.

### Comparaison baseline vs modèle fine-tuné

Compare les deux versions sur le même jeu de phrases, avec les mêmes paramètres de génération. La conclusion utile est : le fine-tuning a-t-il augmenté la prononciation et l'intelligibilité sans dégrader la naturalité ou la cohérence vocale ? Si l'amélioration est faible ou incertaine, collecte davantage de données ou revois la base/normalisation avant de conclure que LoRA ou QLoRA a échoué.

## 8. À quoi s'attendre après le premier entraînement

Le premier modèle risque de présenter encore :

- certaines lettres ou combinaisons de sons mal prononcées ;
- une prosodie plate ou irrégulière ;
- des erreurs sur les nombres, noms propres ou textes longs ;
- des mots omis/répétés si la segmentation ou l'alignement pose problème ;
- une voix moins stable sur les phrases jamais entendues.

Ces symptômes ne se règlent pas tous par plus de steps. Utilise le type d'erreur pour choisir la prochaine action : correction de texte, couverture phonétique, plus de données, adaptation du tokenizer/front-end, choix d'une meilleure base, réduction du learning rate, changement du checkpoint ou de la stratégie d'entraînement.

Un résultat initial réussi devrait au minimum : (a) générer un WAV valide pour chaque phrase de test ; (b) ne pas produire majoritairement de silences ou de répétitions ; (c) avoir une intelligibilité jugée utile par des locuteurs ; (d) surpasser ou justifier la comparaison avec la baseline ; et (e) documenter ses limites. Le but du pilote est de mesurer ces critères, pas de promettre une qualité de production dès le premier run.

## 9. Sauvegarder et documenter le modèle final

Conserve :

- le checkpoint sélectionné, l'adapter LoRA si utilisé et la base exacte qui lui correspond ;
- le tokenizer, le processor, la configuration audio et le front-end texte/phonèmes ;
- la configuration d'entraînement, les logs, les courbes et la graine ;
- les scores et les audios de validation/test générés ;
- la provenance et la version du corpus, le protocole de consentement et la licence ;
- la fiche modèle : langues/variantes visées, limite connue, licence, usage autorisé et avertissement que le modèle peut faire des erreurs.

Si tu ne sauvegardes qu'un adapter LoRA, il ne constitue pas à lui seul le modèle complet : il doit être rechargé sur la même base et avec les bons modules/configurations. Sauvegarde aussi le processor/tokenizer et les réglages d'inférence nécessaires.

Ne publie les voix, les WAV, les embeddings de locuteur ou les poids entraînés que si le consentement, les licences de la base et les droits sur le corpus autorisent explicitement cet usage.

## 10. Ressources techniques

### Documentation principale

- [Hugging Face Audio Course : prétraitement d'un corpus audio](https://huggingface.co/learn/audio-course/chapter1/preprocessing) : resampling, filtrage et formatage selon le modèle.
- [Hugging Face Transformers : Text-to-Speech](https://huggingface.co/docs/transformers/tasks/text-to-speech) : traitement des textes/audios, entraînement et génération SpeechT5 ; utile comme exemple de pipeline complet, pas comme garantie zarma.
- [Hugging Face PEFT : quantification et QLoRA](https://huggingface.co/docs/peft/developer_guides/quantization) : configuration 4 bits et restrictions de compatibilité.
- [Hugging Face PEFT : configuration LoRA](https://huggingface.co/docs/peft/package_reference/lora) : rang, dropout et couches ciblées.
- [Coqui TTS : fine-tuning](https://coqui-tts.readthedocs.io/en/latest/training/finetuning.html) : format du dataset et fine-tuning de modèles Coqui ; la méthode dépend du modèle.
- [MMS-TTS Songhay/Koyraboro Senni](https://huggingface.co/facebook/mms-tts-ses) : source exacte de la base `ses` mentionnée plus haut ; ce checkpoint n'est pas étiqueté zarma et sa licence est non commerciale.

### Ressources d'apprentissage complémentaires

- [DataCamp : Prétraitement pour le Machine Learning en Python](https://www.datacamp.com/fr/courses/preprocessing-for-machine-learning-in-python) : bases sur nettoyage, formats, données manquantes et split train/test. Cours généraliste, pas spécialement consacré aux données vocales.
- [freeCodeCamp : Speech Recognition in Python](https://www.freecodecamp.org/news/speech-recognition-in-python) : notions pratiques d'enregistrement audio, lecture de WAV et bases du traitement de la parole. Le sujet principal est la reconnaissance vocale, pas le fine-tuning TTS.
- [freeCodeCamp : détection des attaques audio avec librosa](https://www.freecodecamp.org/news/use-python-to-detect-music-onsets) : exemple de manipulation de formes d'onde avec Python/librosa ; utile pour apprendre les outils, mais ce n'est pas une recette de nettoyage des enregistrements de parole.
- [Peace Corps/Niger : An Introduction to the Zarma Language (PDF)](https://files.peacecorps.gov/multimedia/audio/languagelessons/niger/NE_Zarma_Language_Lessons.pdf) : support linguistique de départ pour la validation des dix phrases. Il ne dispense pas d'une révision par un locuteur actuel.

## 11. Checklist de décision avant un entraînement long

- [ ] Consentement et licences couvrent l'entraînement et l'usage du modèle envisagé.
- [ ] Les transcriptions de l'ensemble d'entraînement ont été vérifiées par un locuteur compétent.
- [ ] L'orthographe et la convention des nombres/ponctuation sont versionnées.
- [ ] Les WAV ont les propriétés exigées par la recette TTS.
- [ ] `quality_report.csv` a été examiné et les doublons/anomalies traités.
- [ ] Les transcriptions équivalentes sont séparées par groupe entre train, validation et test (pas de fuite de texte).
- [ ] Le tokenizer/front-end gère les graphèmes du zarma, ou un plan explicite est en place.
- [ ] Une baseline audio a été conservée.
- [ ] Un mini-run complète forward, gradients, sauvegarde et génération audio.
- [ ] La compatibilité LoRA/QLoRA a été vérifiée sur cette architecture, et non présumée.
- [ ] Les métriques de validation et les sorties audio sont suivies pendant l'entraînement.
- [ ] Le test final reste hors des décisions d'hyperparamètres.


## Corpus multilingue : Zarma, Hausa et Tamasheq

L’application enregistre maintenant `language_code` : `dje` (zarma), `ha` (hausa) et `taq` (tamasheq). Cette étiquette doit être conservée de l’enregistrement jusqu’à l’export et à l’entraînement. Il ne faut pas mélanger les langues sans le décider explicitement.

Pour la première expérience, entraînez et évaluez **un modèle par langue** si le volume disponible le permet, ou choisissez un modèle TTS multilingue dont l’architecture prend réellement en charge les langues/scripts concernés. Si vous entraînez un modèle commun, fournissez un conditionnement explicite de langue (et de locuteur si nécessaire) et rapportez les résultats séparément pour chaque langue. Ne laissez pas une langue avec plus d’heures dominer les autres sans mesurer cet effet.

Les conventions orthographiques doivent être définies séparément par langue et stockées dans `orthography_version`. Pour le tamasheq, consignez explicitement le système d’écriture choisi ; ne mélangez pas les scripts ou conventions sans normalisation linguistique documentée.

Feriji peut fournir des **textes candidats en zarma**, mais ne contient pas les enregistrements alignés nécessaires au TTS. Les phrases doivent être relues, autorisées et enregistrées. Le dépôt Hugging Face indique CC-BY-NC-4.0 : vérifiez la licence et l’accès aux fichiers avant toute redistribution ou usage commercial.
