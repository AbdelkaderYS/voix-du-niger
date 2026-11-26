# Catalogue linguistique national : Voix du Niger

Dernière révision : 9 octobre 2026.

## Périmètre de départ

L’article 12 de la Charte de la Refondation promulguée en mars 2025 cite les onze langues parlées au Niger suivantes :

| Nom dans l’interface | Code applicatif | Référence ISO 639-3 | État initial dans le produit |
|---|---|---|---|
| Arabe | `ara` | `ara` | Setup : variété et script à préciser |
| Buduma | `bdm` | `bdm` | Setup : validation native requise |
| Fulfuldé | `ful` | `ful` | Setup : variété locale à préciser |
| Gourmanchéma / Gulmancema | `gux` | `gux` | Setup : graphie à valider |
| Hausa | `ha` | `hau` | Pilote configuré, pas de corpus réputé validé par défaut |
| Kanuri | `kau` | `kau` | Setup : variété locale à préciser |
| Tamajaq / Tamasheq | `taq` | `taq` | Pilote configuré, variante et orthographe à préciser |
| Tagdal | `tda` | `tda` | Setup : validation native requise |
| Tassawaq | `twq` | `twq` | Setup : validation native requise |
| Tubu / Toubou (point de départ Teda/Tedaga) | `tuq` | `tuq` | Setup : `tuq` désigne Teda/Tedaga, pas automatiquement toutes les variétés Tubu |
| Zarma-Sonraï | `dje` | `dje` | Pilote configuré ; les phrases de démarrage sont encore à relire |

L’application conserve `ha` pour rester compatible avec le code historique du projet ; la référence ISO 639-3 correspondante est `hau`. Le code `taq` est utilisé comme identifiant projet pour Tamajaq/Tamasheq et doit être accompagné de métadonnées de variété.

### Sous-corpus supplémentaire : Dazaga

Le texte de la Charte utilise la catégorie « Tubu ». Sur le plan des données vocales, Teda/Tedaga (`tuq`) et Dazaga (`dzg`) doivent être séparés pour éviter de mélanger deux sous-corpus linguistiques distincts. L’interface inclut donc `dzg` en plus des onze catégories de la Charte ; ce n’est pas une douzième catégorie juridique, mais une séparation technique au sein du groupe Tubu/Toubou. Les consignes et l’orthographe de Dazaga restent à valider localement avant toute collecte.

La Charte indique également que le hausa est la langue nationale et que le français et l’anglais sont des langues de travail. Ceux-ci figurent au catalogue comme `fr` et `en` avec la portée `work`, et ne sont pas comptés comme langues parlées dans le tableau de couverture nationale.

**Interprétation importante :** cette liste reprend les onze langues citées dans la Charte ; elle ne prétend pas cataloguer toutes les variétés, langues de migration ou communautés linguistiques effectivement présentes. Le catalogue technique n’équivaut pas à une validation linguistique et n’indique pas qu’un jeu audio existe déjà. Le statut `setup` signifie que la langue ou le sous-corpus est enregistré mais que la collecte ne devrait commencer qu’après validation de la variété, de l’orthographe, des consignes et des droits.

## Codes de région du produit

| Code | Région / statut |
|---|---|
| `AGD` | Agadez |
| `DIF` | Diffa |
| `DOS` | Dosso |
| `MAR` | Maradi |
| `NIA` | Niamey |
| `TAH` | Tahoua |
| `TIL` | Tillabéri |
| `ZIN` | Zinder |
| `UNK` | Région non renseignée : à corriger dans la mesure du possible |

Ces codes sont des identifiants internes stables, pas des codes ISO de subdivisions. Une release nationale (`ALL`) est réservée à l’administration système ; les autres comptes doivent créer ou traiter des releases sur les régions qui leur sont explicitement attribuées.

## Contrôles avant d’ouvrir une langue

1. Nommer un référent linguistique et au moins un second relecteur compétent.
2. Décider de la variété locale, du système d’écriture et d’une version de convention orthographique.
3. Faire vérifier les phrases et les consignes, en indiquant source, droits/licence, réviseur et date.
4. Tester la sélection de langue, l’enregistrement, la transcription et les exports avec des locuteurs réels.
5. Ne déclarer la langue prête qu’après examen d’un premier jeu de données et des métriques de qualité.

## Sources publiques

- **Charte de la Refondation du Niger, 26 mars 2025**, article 12 (version PDF publiée en ligne) : https://niger.dk/wp-content/uploads/2025/05/Charte-Refondation-26Mars2025.pdf
- Présidence du Niger, portail institutionnel : https://www.presidence.ne/pages/refondation
- ISO 639-3 / SIL International, référence pour les codes linguistiques : https://iso639-3.sil.org/
