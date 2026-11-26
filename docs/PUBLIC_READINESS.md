# Voix du Niger : checklist de préparation à un usage public

**Statut actuel :** MVP adapté à un pilote contrôlé avec des participants informés. **Ne pas ouvrir au public général avant d'avoir traité les points marqués BLOQUANT.**

## 1. Données, consentement et droits (BLOQUANT)

- [ ] Remplacer l'ébauche de consentement par un texte relu juridiquement et compris par les participants.
- [ ] Identifier le responsable du corpus et donner un contact réel pour questions, retrait ou plainte.
- [ ] Expliquer séparément : enregistrement, entraînement de modèles, partage/publication du corpus, publication des modèles et usage commercial éventuel.
- [ ] Définir la durée de conservation et les personnes ayant accès aux données brutes.
- [x] Ajouter une action admin pour retirer les enregistrements et audios du stockage actif et un journal d’audit qui ne conserve pas le code participant.
- [ ] Définir, tester et documenter le retrait/effacement de bout en bout : sauvegardes, exports téléchargés, copies publiées et, selon la politique applicable, jeux et modèles dérivés. L’action intégrée ne traite que le stockage actif.
- [ ] Conserver la version du consentement acceptée, l'horodatage et la preuve d'information présentée ; ne pas réécrire ces éléments silencieusement.
- [ ] Vérifier la licence et la provenance de chaque source de phrases. Les importateurs rejettent maintenant les marqueurs temporaires de droits, mais une personne responsable doit toujours vérifier les conditions réellement applicables. Contacter les auteurs de Feriji avant une réutilisation dans le corpus TTS.
- [ ] Ne pas publier de noms, numéros, adresses ni données personnelles dans les métadonnées du corpus.

## 2. Sécurité et abus (BLOQUANT)

- [ ] Déployer derrière HTTPS/TLS, avec HSTS au niveau du reverse proxy et une configuration de sécurité vérifiée.
- [x] Ajouter des comptes d’équipe individuels, des rôles RBAC, des périmètres obligatoires langue/région pour les non-admins, des mots de passe hachés, des sessions expirantes et la révocation.
- [ ] Compléter la sécurité de l’authentification : limitation de débit, politique anti-brute-force, processus sûr de récupération de compte et MFA si possible. La clé partagée `ZARMA_ADMIN_TOKEN` reste un accès de secours à garder hors exposition publique.
- [ ] Protéger l'administration par contrôle d'accès réseau ou portail d'authentification ; réduire l'exposition publique des routes de documentation API.
- [ ] Ajouter une limitation de débit, des quotas de collecte et des limites de taille/durée au proxy et à l'application.
- [x] Vérification serveur du conteneur, du flux audio, de la durée réellement décodée et du décodage complet avec délais bornés implémentée.
- [ ] Tester le flux sur les appareils, navigateurs et formats audio du déploiement cible.
- [ ] Protéger contre les fichiers malformés, les répétitions massives et les tentatives d'épuisement du stockage.
- [ ] Vérifier les mises à jour et dépendances, garder les secrets hors du dépôt et limiter les permissions du processus/volume.
- [ ] Fermer ou restreindre `/docs` et `/redoc` si les endpoints ne doivent pas être publics.

## 3. Fiabilité opérationnelle (BLOQUANT avant campagne ouverte)

- [ ] Sauvegardes automatiques chiffrées de la base et des audios, avec exercice de restauration vérifié.
- [ ] Stockage persistant et surveillé ; seuils d'espace disque, erreurs et taux d'échec d'export alertés.
- [ ] File d'envoi robuste dans le navigateur (IndexedDB), avec reprise après coupure réseau/fermeture et statut de synchronisation confirmé par le serveur.
- [ ] Progression de collecte calculée côté serveur, pas seulement dans `localStorage` du navigateur.
- [ ] Réessais idempotents ou détection des doubles envois pour éviter plusieurs enregistrements après une réponse réseau perdue.
- [x] Ajouter le journal d’audit des imports, modifications de comptes, releases, providers et runs, plus l’historique des décisions de revue et suppressions.
- [ ] Ajouter alertes pour événements de sécurité, tentative de connexion échouée et accès refusé ; définir la rétention du journal et la surveillance de son intégrité.
- [ ] Plan de réponse en cas d'incident : accès non autorisé, demande de suppression, fichier corrompu, interruption de service.

## 4. Qualité linguistique et audio (BLOQUANT pour publier un corpus)

- [ ] Faire relire chaque phrase par une personne compétente dans la langue et sa variante ; documenter orthographe et variantes.
- [ ] Avoir des référents (ou un processus d’arbitrage) distincts pour les onze catégories de la Charte et les sous-corpus explicitement séparés (notamment Teda/Tedaga et Dazaga), avec ouverture progressive ; aucune langue ne doit être déclarée prête sur la seule base de sa présence dans le menu.
- [ ] Former les réviseurs avec les mêmes critères : texte intégral, intelligibilité, hésitations, coupures, bruit, voix multiples, langue/variante correcte.
- [x] À la réception, vérification du format/flux décodé, de la durée réelle et de l’intégrité de décodage. Le script de préparation signale aussi la durée anormale, le silence, le clipping et les doublons exacts.
- [ ] Tester les seuils et les formats sur de vrais appareils ; la détection technique ne prouve ni la qualité linguistique ni que l’audio correspond au texte.
- [ ] Conserver un historique de revue. Les cas rejetés et en attente doivent rester séparés des données approuvées et ne pas entrer accidentellement en entraînement.
- [ ] Faire des audits aléatoires par réviseur, locuteur, appareil et langue ; suivre le taux d'approbation et les causes de rejet.

## 5. Expérience participant et accessibilité (BLOQUANT avant ouverture générale)

- [ ] Faire tester le front par de vrais locuteurs sur Android bas/milieu de gamme et différents navigateurs.
- [ ] Ajouter l'explication localisée et validée par la communauté ; l'écran est actuellement principalement en français.
- [ ] Vérifier que les instructions sont compréhensibles même pour un participant peu à l'aise avec la lecture technique.
- [ ] Tester les permissions du microphone, la taille des fichiers, la reprise réseau et l'absence de perte lorsque l'onglet se ferme.
- [ ] Définir un identifiant de participation difficile à deviner ou un mécanisme de session/invitation pour éviter l'usurpation et les collisions.
- [ ] Ajouter un contact de support et un mécanisme clair pour signaler une phrase incorrecte ou demander de l'aide.

## 6. Passage pilote -> public

### Pilote fermé

Peut démarrer après finalisation du consentement, validation des prompts, HTTPS et test du flux. Limiter le nombre de participants et vérifier manuellement chaque prise. Ne pas promettre un corpus public tant que licences et droits ne sont pas tranchés.

### Bêta limitée

Passer en bêta quand l’authentification renforcée, les quotas, les sauvegardes/restauration, la validation audio à la réception, les erreurs de réseau et le suivi serveur sont testés. Les contrôles RBAC présents dans le MVP ne remplacent pas les tests d’exposition HTTPS et de résistance aux abus.

### Publication d'un dataset

Publier une documentation de dataset : langues/variantes, méthode d'enregistrement, durées, nombre de locuteurs, distribution pertinente et anonymisée, splits, règles de nettoyage, statut de revue, licences et limites. Le split par locuteur est nécessaire pour une évaluation honnête des modèles multi-speakers ; pour un objectif single-speaker, réserver plutôt des phrases de test non vues et l'indiquer clairement.
