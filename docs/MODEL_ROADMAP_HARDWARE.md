# Modèles à envisager et besoins matériels : Voix du Niger

Dernière révision : 2026-10-09

Ce document propose une feuille de route technique pour construire à terme un assistant vocal en zarma, hausa et tamasheq. Les besoins mémoire sont des **estimations de planification**, pas des minima garantis : ils changent selon les versions des bibliothèques, longueur de contexte, batch, précision, quantification, modèle audio, séquence et stratégie de fine-tuning. Mesurer le pic réel de VRAM/RAM sur un essai représentatif avant de payer un GPU.

## 1. Ne pas chercher un modèle unique pour tout

Le produit final comporte quatre briques séparées :

1. **ASR (Automatic Speech Recognition)** : parole de l'utilisateur → texte.
2. **LLM (modèle de langage)** : comprendre la demande et formuler une réponse, avec ou sans RAG.
3. **TTS (Text-to-Speech)** : réponse textuelle → voix.
4. **Application/orchestrateur** : enregistrement, transmission, langues, confidentialité, récupération des erreurs, lecture audio et éventuel fonctionnement hors connexion.

La plateforme collecte maintenant lecture guidée et parole spontanée. Les prises ne deviennent utilisables qu'après revue propre à la tâche. L'ASR exige une transcription fidèle et un ensemble d'évaluation séparé par locuteur ; le TTS exige des paires lecture/texte propres et autorisées pour la voix visée. Le MVP ne contient encore aucun modèle ASR/TTS ni inférence.

## 2. Candidats de modèles

### A. TTS : générer une réponse parlée

| Candidat | Ce que l'on sait | Décision proposée | Taille/RAM de planification |
|---|---|---|---|
| `facebook/mms-tts-hau` | VITS, checkpoint déclaré pour le hausa (`hau`), environ 36 M paramètres, licence CC BY-NC 4.0. | Baseline immédiate pour tester le hausa et son pipeline, pas le zarma. Vérifier le dialecte, l'écriture et la qualité avec des natifs. | Poids ~0,15 Go en FP32 à titre d'ordre de grandeur ; inférence CPU possible, prévoir 2–4 Go de RAM de processus pour un test simple. |
| `facebook/mms-tts-taq` | VITS, checkpoint déclaré pour le tamasheq (`taq`), environ 36 M paramètres, licence CC BY-NC 4.0. | Baseline immédiate pour le tamasheq, après vérification de la variante et du système d'écriture utilisés. | Ordre de grandeur identique à un modèle de ~36 M paramètres ; réserver 2–4 Go de RAM pour le test. |
| `facebook/mms-tts-ses` | VITS pour le songhay/koyraboro senni (`ses`), et non un checkpoint étiqueté zarma (`dje`). Licence CC BY-NC 4.0. | **Expérience exploratoire uniquement** pour le zarma : tester la tokenisation et faire écouter les résultats à des locuteurs. Ne pas le présenter comme un modèle zarma. Comparer avec une base VITS/Piper adaptée sur le corpus collecté. | Même ordre de grandeur que les autres petits checkpoints MMS-TTS ; vérifier les fichiers et les besoins exacts de la version retenue. |
| VITS/Piper adapté avec son propre corpus | VITS est une architecture TTS pouvant être adaptée et exportée pour l'inférence CPU/ONNX avec le pipeline Piper approprié. La disponibilité d'une voix dans Piper ne signifie pas que cette voix couvre une langue donnée. | **Candidat pratique pour un TTS léger hors ligne**, une fois la voix entraînée et la licence de code/poids vérifiée. Une recette Piper peut demander des ajustements au tokenizer, au phonémiseur et à l'orthographe. | Entraînement pilote : prévoir une GPU de 8–16 Go VRAM, 16–32 Go RAM système et ~40 Go libres sur disque comme budget confortable de travail, puis mesurer. L'inférence exportée peut fonctionner sur CPU sans GPU. |
| XTTS-v2 | Le modèle officiel liste 17 langues, dont ni le zarma, ni le hausa, ni le tamasheq. Licence Coqui Public Model License. | Ne pas en faire la base principale de ces langues. Une démonstration sur une langue prise en charge ne prouve pas le support du zarma. | Plus lourd que MMS-VITS ; ne pas dimensionner une infrastructure autour de lui avant un test de compatibilité. |
| F5-TTS | Code officiel MIT, mais les poids préentraînés publiés ont une licence CC BY-NC liée aux données Emilia selon le dépôt officiel. | Piste de recherche, pas premier choix pour une mise en production commerciale. Vérifier la langue, le tokenizer et les restrictions du checkpoint exact. | Évaluer la mémoire sur le checkpoint et la recette précise ; ne pas extrapoler la mémoire d'un modèle VITS de 36 M paramètres. |

**Point licences :** CC BY-NC 4.0 n'est pas compatible avec une utilisation commerciale ordinaire sans autorisation supplémentaire. Pour une voie commerciale, privilégier une architecture/code dont la licence convient et des données dont les contributeurs ont autorisé les usages prévus. Les licences de code, de poids, de données et les droits sur les voix sont des sujets distincts.

Liens officiels :
- MMS-TTS Hausa : https://huggingface.co/facebook/mms-tts-hau
- MMS-TTS Tamasheq : https://huggingface.co/facebook/mms-tts-taq
- MMS-TTS Songhay/Koyraboro Senni : https://huggingface.co/facebook/mms-tts-ses
- XTTS-v2 : https://huggingface.co/coqui/XTTS-v2
- F5-TTS : https://github.com/SWivid/F5-TTS
- Piper : https://github.com/OHF-Voice/piper1-gpl

### B. ASR : comprendre la parole du paysan

| Candidat | Couverture vérifiée dans la fiche/liste | Usage proposé | Besoin indicatif |
|---|---|---|---|
| `facebook/mms-1b-all` | Modèle ASR de 1 milliard de paramètres ; la liste publique inclut `hau` et `taq`, mais pas le code `dje`. Le fichier de poids principal affiché fait environ 3,86 Go et la licence est CC BY-NC 4.0. | Baseline ASR pour hausa/tamasheq ; ne pas supposer que l'absence de `dje` puisse se résoudre en sélectionnant un code de langue. Collecter et évaluer le zarma séparément. | Prévoir ~8–12 Go VRAM pour une inférence confortable à confirmer, ou 8–16 Go RAM pour des essais CPU ; le fine-tuning réclame davantage. Ce sont des marges de planification. |
| Whisper / faster-whisper | La liste de langue de Whisper comporte le hausa (`ha`), mais ne comporte pas le zarma ni le tamasheq comme langues dédiées. Une langue non prise en charge peut produire une transcription plausible mais incorrecte. | Benchmark de secours pour le hausa et le français ; n'est pas l'ASR zarma. Mesurer le WER/CER sur des enregistrements locaux avant tout usage. | Selon checkpoint : 2–4 Go VRAM pour des modèles plus petits/quantifiés ; 6–12 Go ou plus pour des checkpoints larges selon précision et contexte. Tester réellement le pic mémoire. |
| ASR affiné sur les données Voix du Niger | Pas encore disponible : le mode collecte existe, mais le corpus doit être rempli de données approuvées, transcrites et évaluées. | Trajectoire à moyen terme pour le zarma. Un modèle multilingue peut servir de point de départ si la licence, la tokenisation et les résultats le permettent. | 16–24 Go VRAM sont une cible pratique pour les expériences d'adaptation d'un modèle de taille importante ; 32 Go RAM et 100 Go libres de stockage constituent un point de départ plus confortable. |

Liens :
- MMS-1B-All : https://huggingface.co/facebook/mms-1b-all
- Whisper : https://github.com/openai/whisper
- Ressources voix hausa de CLEAR Global : https://clearglobal.org/resources/hausa-synthetic-voice-dataset-tts-models-asr-models/

**À noter :** la disponibilité d'un code de langue dans une liste n'est pas une garantie de précision pour le dialecte, le bruit de terrain, l'accent, les noms de cultures ou le vocabulaire agricole. Évaluer avec des tests enregistrés au Niger.

### C. LLM : comprendre et répondre en zarma

| Candidat | Atouts | Réserves | Cible matérielle indicative |
|---|---|---|---|
| Qwen3-4B Instruct | Modèle dense de 4 milliards de paramètres ; fiche sous licence Apache 2.0 ; annonce plus de 100 langues/dialectes. Bon candidat de départ pour comparer les capacités de réponse, puis tester LoRA/QLoRA. | La prise en charge de plus de 100 langues n'est pas une garantie que la génération en zarma soit fiable. Il faut évaluer la compréhension, la grammaire, la cohérence et les hallucinations avec des locuteurs. | Inférence quantifiée 4 bits : environ 4–8 Go VRAM disponibles ; QLoRA : viser 12–16 Go VRAM et 32 Go RAM système pour un essai prudent à séquences courtes. |
| Qwen3-8B Instruct | Même famille, plus grande capacité potentielle ; fiche sous Apache 2.0. | Le gain en zarma doit être mesuré ; ne pas supposer qu'il double la qualité. Plus coûteux en temps et mémoire. | Inférence 4 bits : environ 6–10 Go VRAM ; QLoRA : viser 16–24 Go VRAM et 32–64 Go RAM système. Une carte 16 Go peut être serrée selon contexte/configuration. |
| Gemma 3 4B | Famille compacte et multilingue, annoncée par Google comme couvrant plus de 140 langues. Intéressante comme modèle comparatif. | Vérifier la licence Gemma et la liste réelle des langues utiles avant le déploiement. Aucun support zarma n'est garanti par le nombre global de langues. | Inférence quantifiée : prévoir 4–8 Go VRAM ; entraînement LoRA/QLoRA : viser 12–16 Go VRAM ou plus selon le contexte. |
| Modèle spécialisé entraîné à partir de zéro | Contrôle total des données et du tokenizer. | Très coûteux en données et en GPU ; disproportionné pour la première version. | Ne pas planifier un préentraînement LLM from scratch à court terme. Utiliser un modèle préentraîné, puis RAG et adaptation légère. |

Liens :
- Qwen3-4B : https://huggingface.co/Qwen/Qwen3-4B
- Qwen3-8B : https://huggingface.co/Qwen/Qwen3-8B
- Famille Gemma 3 : https://deepmind.google/models/gemma/gemma-3/

**Politique d’entraînement de Voix du Niger :** prendre le Full Fine-Tuning (FFT) comme référence expérimentale lorsque la recette du modèle et la mémoire le permettent. Si le coût/VRAM rend le FFT impraticable, tester LoRA, puis QLoRA uniquement pour les composants compatibles. Pour les modèles TTS VITS, utiliser d’abord la recette native : PEFT/QLoRA ne s’applique pas automatiquement. Pour les LLM texte, LoRA/QLoRA peuvent être des solutions de repli efficaces en mémoire, mais ne résolvent ni le manque de données ni une couverture linguistique insuffisante.

### D. Modèle de recherche RAG (pas une brique vocale)

Pour un dictionnaire et des documents agricoles, commencer par une recherche lexicale forte (SQLite FTS/BM25 ou PostgreSQL full-text), puis comparer avec une recherche hybride. Tester des embeddings multilingues tels que BGE-M3 ou multilingual-e5 comme candidats seulement ; les performances en zarma/tamasheq doivent être mesurées sur des questions réellement formulées dans ces langues.

Le RAG ne réentraîne pas le LLM : il recherche des éléments dans une base de connaissance au moment de la question et les ajoute au contexte de réponse. Un glossaire peut améliorer la terminologie, mais il ne suffit pas à apprendre à converser.

## 3. Besoins matériels, du court au long terme

### Infrastructure de collecte et de stockage

| Horizon | Objectif | CPU/RAM | GPU | Stockage conseillé |
|---|---|---|---|---|
| Court terme : 0–3 mois | Pilote, 2–20 locuteurs, tests des flux et premiers essais de modèles | Serveur web : 2–4 vCPU et 8 Go RAM ; machine de préparation : 16–32 Go RAM | Aucun GPU pour l'application de collecte. Kaggle/Colab T4 16 Go ou L4 24 Go convient pour préparer les données et tester de petites recettes vocales ; le FFT doit être vérifié sur le checkpoint exact avant de conclure que la VRAM suffit. | 100 Go SSD/NVMe pour le pilote, plus une sauvegarde séparée. |
| Moyen terme : 3–12 mois | Corpus contrôlé pour 1–3 langues, adaptation ASR/TTS, essai RAG/LLM | 8 vCPU et 32–64 Go RAM pour les traitements ; 16 Go RAM minimum au serveur de collecte si le volume croît | 24 Go VRAM recommandés pour plus de marge ; T4 16 Go reste utile pour certains modèles VITS compacts ; un FFT plus lourd peut demander une réduction de batch ou un GPU plus grand. A100 40/80 Go si expérimentation plus lourde et budget disponible. | 500 Go–1 To NVMe ou stockage objet persistant, snapshots et sauvegardes chiffrées. |
| Long terme : 12–36 mois | Plusieurs dialectes/voix, service utilisé au quotidien, évaluation et mises à jour | 16+ vCPU, 64–128 Go RAM selon concurrence et traitements | Un serveur L4/A10/A100 selon latence et volume ; 40–80 Go VRAM n'est utile que si les tâches/modèles retenus le justifient. Plusieurs serveurs peuvent être préférables à une grande GPU unique pour séparer ASR, LLM et TTS. | 2–5 To d'object storage/NVMe selon le nombre d'heures, versions et répliques ; politique de conservation et sauvegarde testée. |

### Stockage audio : ordre de grandeur vérifiable

Le WAV PCM mono 16 bits à 22 050 Hz utilisé par défaut représente environ 158,8 Mo par heure (hors métadonnées et sauvegardes). À 16 kHz il représente environ 115,2 Mo par heure.

| Corpus | Un seul jeu normalisé en 22,05 kHz | Avec originaux, versions de travail et sauvegardes (budget x3 indicatif) |
|---|---:|---:|
| 10 heures par langue × 3 langues = 30 h | ~4,8 Go | ~14,3 Go |
| 100 heures par langue × 3 langues = 300 h | ~47,6 Go | ~143 Go |
| 500 heures par langue × 3 langues = 1 500 h | ~238 Go | ~714 Go |

Ces nombres ne couvrent pas tous les poids des modèles et checkpoints, les journaux, les fichiers d'export et les documents. Les voix originales sont des données sensibles : chiffrement au repos, accès selon rôle, sauvegarde séparée et procédure de retrait sont nécessaires.

### VRAM : règles de planification

| Travail | VRAM de départ à essayer | Commentaire |
|---|---:|---|
| Inference MMS-TTS VITS (~36 M paramètres) | 2–4 Go, ou CPU | Très petit modèle ; le preprocessing et les dépendances peuvent peser autant que le réseau. |
| Fine-tuning d'une voix VITS/Piper | 8–16 Go | Ajuster batch, segments, précision et gradient accumulation ; conserver des checkpoints hors du disque temporaire. |
| Inférence ASR MMS-1B-All | 8–12 Go à confirmer | Les poids affichés font ~3,86 Go ; runtime, buffers et longueur audio utilisent de la mémoire supplémentaire. |
| LLM 4B quantifié pour l'inférence | 4–8 Go | Les poids quantifiés ne représentent pas l'ensemble de la mémoire : KV cache et runtime s'ajoutent. |
| QLoRA LLM 4B | 12–16 Go cible | Séquences courtes, batch 1, gradient checkpointing et quantification sont souvent nécessaires. |
| LLM 7–8B quantifié en inférence | 6–10 Go | La mémoire dépend surtout du contexte et du runtime. |
| QLoRA LLM 7–8B | 16–24 Go cible | 16 Go peut fonctionner avec contraintes ; 24 Go est plus confortable, sans garantie pour toutes configurations. |
| Fine-tuning complet d'un LLM 7–8B | 80 Go ou multi-GPU comme ordre de grandeur prudent | Optimiseur, gradients et activations coûtent plusieurs fois les poids. À éviter pour ce projet au début. |

### Recommandation GPU immédiate

- **Commencer avec une T4 de 16 Go** pour préparer les données, benchmarker l’ASR et tester un FFT vocal compact si la recette tient en mémoire. Pour un LLM 3–4B, envisager LoRA/QLoRA si le FFT est trop coûteux.
- **Passer à 24 Go VRAM** si les mesures montrent que le FFT vocal ou les batchs choisis dépassent les capacités de la T4 ; pour les LLM 7–8B, LoRA/QLoRA restent des options à tester avant le FFT complet.
- **Ne pas acheter de GPU long terme avant le benchmark** : mesurer secondes par minute audio, latence, mémoire pic, coût par heure audio et qualité d'une voix validée.

## 4. Combien de données faut-il viser ?

Ce sont des jalons de programme, pas des seuils universels :

| Brique | Court terme | Moyen terme | Long terme |
|---|---|---|---|
| TTS, une voix cible | 3–5 h propres pour prouver la chaîne, puis viser 10–20 h pour le premier modèle utile | 20–50 h par voix/langue si possible, avec couverture phonétique vérifiée | Davantage de voix et de styles, ou corpus multi-locuteurs si le produit en a besoin ; évaluer séparément chaque voix. |
| ASR | 5–10 h de parole transcrite pour le pipeline et le premier benchmark, avec prudence sur les conclusions | Viser 20–100 h diversifiées par langue, selon les transferts et la qualité obtenue | Plusieurs centaines d'heures si le volume, la diversité et le budget justifient une spécialisation plus robuste. |
| LLM conversationnel | Petit jeu de questions/réponses validées pour évaluer les modèles sans fine-tuning | Construire un jeu supervisé relu par des locuteurs et experts du domaine, puis essayer LoRA/QLoRA | Enrichir par domaines, variantes dialectales, conversations multi-tours, tests adversariaux et corrections réelles des utilisateurs. |
| RAG | 50–200 documents/entrées contrôlés comme banc de test de retrieval | Documents structurés, index lexical + dense hybride, tests de rappel et de fidélité | Gouvernance des sources, dates, versions, qualité et fraîcheur par domaine/langue. |

Pour TTS, une voix cohérente et une transcription exacte sont souvent plus utiles qu'un grand nombre de prises bruitées. Pour ASR, varier les locuteurs, les âges adultes, accents, vitesses, conditions d'enregistrement et parole spontanée est essentiel. Obtenir un consentement explicite pour chaque tâche et usage.

## 5. Licence et commercialisation

Vérifier séparément : (1) licence des données vocales, (2) droit d'utiliser/redistribuer les transcriptions et dictionnaires, (3) licence du checkpoint, (4) licence de code, (5) consentement des personnes à entraîner et diffuser une voix. Une licence du code dite open source ne rend pas automatiquement les poids, données ou voix librement commercialisables.

Ne faire aucune mise en production commerciale sur un checkpoint CC BY-NC sans autorisation ou changement de base légalement compatible.

## 6. Références de départ

- MMS-TTS (Hausa) : https://huggingface.co/facebook/mms-tts-hau
- MMS-TTS (Tamasheq) : https://huggingface.co/facebook/mms-tts-taq
- MMS-TTS (Songhay/Koyraboro Senni) : https://huggingface.co/facebook/mms-tts-ses
- MMS ASR 1B : https://huggingface.co/facebook/mms-1b-all
- Whisper : https://github.com/openai/whisper
- Qwen3-4B : https://huggingface.co/Qwen/Qwen3-4B
- Qwen3-8B : https://huggingface.co/Qwen/Qwen3-8B
- Gemma 3 : https://deepmind.google/models/gemma/gemma-3/
- Piper / Open Home Foundation : https://github.com/OHF-Voice/piper1-gpl
- F5-TTS : https://github.com/SWivid/F5-TTS
- TWB Voice (CLEAR Global) : https://clearglobal.org/twbvoice/
- Ressources vocales hausa (CLEAR Global) : https://clearglobal.org/resources/hausa-synthetic-voice-dataset-tts-models-asr-models/
