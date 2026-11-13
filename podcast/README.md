# Podcast pédagogique — version 0.4.0

Application locale Windows 10/11 pour transformer plusieurs PDF en un dialogue pédagogique en français, puis en **podcast MP3 avec les voix déjà créées dans VoiceStudio**. Ollama rédige le texte ; VoiceStudio réalise la synthèse vocale sur le même PC.

## Mettre à jour une installation existante

1. Fermer la fenêtre de lancement de PodcastPedago.
2. Extraire **tout** le ZIP correctif dans un dossier temporaire.
3. Ouvrir **Mettre-a-jour.cmd**, puis choisir le dossier contenant votre `Lancer-Podcast.cmd`.
4. Relancer l’application et vérifier **Version 0.4.0** en haut de la page.

Un projet déjà traité en 0.3.0 peut passer directement à la lecture audio : les contrôles scientifiques de cette version sont conservés, sans refaire les PDF. Pour un projet plus ancien, suivre **Améliorer les résumés existants**, attendre le réexamen puis **Continuer jusqu’au script final**. Les PDF et les projets sont conservés ; les résultats remplacés sont archivés.

L’outil de mise à jour vérifie les empreintes des 16 fichiers applicatifs, sauvegarde les fichiers remplacés et tente de les restaurer en cas d’échec. Il ne remplace ni `donnees`, ni `.venv`, ni `.runtime`. Si Windows refuse `Mettre-a-jour.cmd`, ouvrir PowerShell dans le dossier du correctif et lancer `powershell -NoProfile -ExecutionPolicy Bypass -File .\mettre-a-jour.ps1` ; choisir ensuite le dossier de l’installation.

L’ancienne application Streamlit V7, dont `app.py` appelle `podcast_interface.run()`, est une autre application. Ce correctif ne s’applique pas à son dossier : utiliser le ZIP complet dans un nouveau dossier, puis importer ses réglages et son dialogue comme indiqué ci-dessous. Ses données restent dans son dossier d’origine.

## Retrouver les voix de l’ancienne version et lire le dialogue révisé

Ce parcours permet de lire un texte déjà écrit, sans relancer Ollama ni analyser de PDF.

1. Ouvrir VoiceStudio sur le PC et garder son API locale en service.
2. Dans PodcastPedago, cliquer sur **Lire un dialogue TXT**.
3. Charger `dialogue_revise_20min.txt`, ou un autre dialogue au format `AnneSo: Une question` puis `Sophie: Une réponse`. Cliquer sur **Utiliser ce texte pour l’audio**.
4. Ouvrir **Récupérer mes anciens réglages VoiceStudio**, choisir l’ancien `podcast_interface.py` et cliquer sur **Importer mes réglages**.
5. Vérifier les deux associations avec **Écouter cette voix**, puis sélectionner **Essai d’environ 3 minutes** avant de générer.
6. Après contrôle, sélectionner **Podcast complet**, générer et utiliser le lecteur ou **Télécharger le MP3**.

L’import lit les valeurs initiales des champs de configuration dans le fichier Python, sans exécuter son code. Il récupère les références AnneSo/Sophie, l’adresse locale, les pauses et le volume. Il ne peut pas retrouver un changement effectué uniquement dans une ancienne session Streamlit : dans ce cas, choisir les profils dans **Charger mes voix VoiceStudio**. Un JSON avec les mêmes clés historiques (`voice_studio_url`, `vs_anneso`, `vs_sophie`, et éventuellement `pause_ms`, `normalize_audio`, `target_dbfs`) est aussi accepté. Aucun profil privé n’est inclus dans l’archive distribuée.

Le texte importé reste un texte fourni pour lecture : il ne reçoit pas une validation scientifique automatique. L’éditeur bloque la génération tant que les modifications du dialogue ne sont pas enregistrées. Les noms servent au choix des voix et ne sont pas prononcés. Les lignes qui continuent une réplique sont rattachées à cet intervenant ; les titres sans intervenant doivent être retirés avant import.

## Écouter le script d’un projet PDF

Dans **Voix et podcast MP3**, conserver **Script du projet (neuf étapes)**, puis importer les anciens réglages ou charger les profils existants. L’option **Reprendre AnneSo pour les questions et Sophie pour les explications** adapte les noms du projet : seules les étapes 8 et 9 sont à reconstruire si les intervenants changent. Les résumés et le plan sont conservés. Décocher cette option pour garder les noms actuels et affecter les références aux mêmes rôles ; un troisième intervenant demande sa propre association.

Pour charger les profils directement, vérifier l’adresse API (`http://127.0.0.1:3900` par défaut), cliquer sur **Charger mes voix VoiceStudio**, choisir une référence pour chaque intervenant et **Enregistrer les voix**. Aucun profil n’est recréé. Une référence absente est signalée.

Si **Préparer le MP3** apparaît, cliquer une fois pour utiliser FFmpeg déjà disponible ou télécharger `imageio-ffmpeg==0.6.0` dans l’environnement Python de l’application. Cette préparation demande Internet ; les générations suivantes sont locales. Utiliser ensuite un aperçu, un essai court ou le podcast complet.

## Compatibilité VoiceStudio et contrôles audio

La version 0.4.0 reprend le contrat API présent dans les anciens fichiers fournis : `GET /health`, `GET /v1/audio/voices` et `POST /v1/audio/speech`, avec l’en-tête `Authorization: Bearer local`. Le POST envoie exactement `model`, `input`, `voice` et `response_format`, avec `tts-1` et `wav` par défaut. La synthèse peut prendre jusqu’à 900 secondes par requête, contre 15 secondes pour les lectures de l’API. Le contrôle de santé accepte l’absence de `/health` (HTTP 404) pour les autres versions compatibles. La liste peut aussi provenir de `/profiles`.

Chaque réplique est synthétisée séparément, avec découpage des textes longs, cache et reprise après interruption. La vitesse est ajustée localement par FFmpeg. Les fichiers sont convertis dans un format commun, équilibrés vers le volume cible lorsque l’option est active, puis assemblés avec les pauses et encodés en MP3 à **192 kbit/s**. Le volume reste limité pour éviter la saturation numérique. Une réplique totalement silencieuse arrête la génération ; une durée très atypique produit un avertissement à réécouter, sans supprimer la réplique.

Les essais de 3 ou 5 minutes prennent le début du texte et conservent les répliques entières ; leur durée est approximative. Ils ont leurs propres MP3 et rapports, et ne remplacent pas le podcast complet. Le rapport CSV indique le nom, le nombre de mots, la durée et les avertissements de chaque réplique. Une durée plausible ne prouve pas que la synthèse a prononcé tous les mots.

Les références sont mémorisées dans le projet. Modifier le texte, les voix, les pauses ou le volume archive les anciens exports audio. Changer seulement la durée d’essai conserve les différents exports. Le cache reste dans le dossier privé du projet. La mise à jour du moteur audio renouvelle l’empreinte des exports 0.3.0 pour appliquer les nouveaux réglages.

## Première installation

1. Extraire `PodcastPedago-Windows.zip`, puis ouvrir `Installer-Windows.cmd` dans le dossier `PodcastPedago`.
2. Installer Ollama depuis <https://ollama.com/download/windows> si nécessaire.
3. Télécharger le modèle une fois : `ollama pull mistral`. S’il est déjà présent, garder son nom exact affiché par `ollama list`, par exemple `mistral:latest`.
4. Ouvrir `Lancer-Podcast.cmd`, créer un projet, ajouter les PDF et vérifier les modèles installés.
5. Choisir public, durée, deux ou trois intervenants et contexte, puis lancer les étapes.

Le serveur est accessible uniquement sur `127.0.0.1:8766`. Garder la fenêtre de lancement ouverte. Après installation et téléchargement du modèle, les PDF locaux peuvent être traités hors connexion. La carte NVIDIA peut accélérer Ollama ; elle n’est pas indispensable au fonctionnement.

## Les neuf étapes

| Étape | Résultat |
| --- | --- |
| 1 | Extraction du texte et découpage de chaque PDF en trois parties, avec pages conservées. Les pages sans texte extractible sont signalées. |
| 2 | Idées confrontées à leurs citations, seconde lecture de leur appui, classement éditorial et résumé extractif de chaque partie. Les passages incertains restent à vérifier. |
| 3 | Compilation extractive des trois parties pour chaque PDF, avec registre intégral des idées retenues. |
| 4 | Texte commun regroupant les passages de tous les PDF par rôle pédagogique, sans nouvelle reformulation des faits. |
| 5 | Thèmes cohérents, notions fondatrices avant les méthodes, et sélection selon la durée. Paramètres spécialisés et idées hors podcast restent au dossier avec leur motif. |
| 6 | Une phrase essentielle par idée sélectionnée, copiée depuis son énoncé source. |
| 7 | Énoncé et explication sources rassemblés, avec raccord entre chapitres. |
| 8 | Questions courtes proposées par le modèle ; réponses insérées depuis les sources, définitions issues du glossaire, mémoire de continuité bornée. |
| 9 | Contrôle de couverture et d’identité des réponses, durée estimée, rapport et exports. |

Chaque résultat terminé est sauvegardé en Markdown et JSON avant la suite. Le dialogue est enregistré par blocs de deux idées au maximum, puis par chapitre. **Continuer** réutilise les blocs terminés après une interruption. Une erreur réseau, une annulation ou un problème d’enregistrement reste un arrêt explicite.

## Corrections de contenu de la version 0.3.0

Le glossaire sépare les acronymes à casse mixte comme QoT : QAM et QoT ne sont plus fusionnés. Les développements sont contrôlés avant **et après** les sigles ; les sens inventés de DT, SDN et OMS observés dans l’export précédent sont refusés. Les traductions de `step-size` et de l’anticipation à deux actions, le périmètre d’une grille de fréquences et la distinction entre `colorless` et `contentionless` ont des contrôles ciblés. Les commentaires sur une diffusion restreinte ou sur la seule présence d’un tableau sont écartés du récit scientifique.

Le classement distingue thèmes, notions fondatrices, raisonnement principal et détails. Le plan regroupe les idées d’un même thème et place les bases avant les méthodes. Les scénarios numérotés restent des détails dans le dossier. Chaque raccord reprend un fait du chapitre précédent. Une introduction et une conclusion avec points à retenir sont ajoutées à partir des formulations sources, avec leurs références conservées.

Les répétitions exactes et certaines explications qui ne font que reformuler le constat sont détectées. La révision finale vérifie à nouveau les acronymes et les formulations techniques ; elle conserve aussi le registre des sources et le glossaire dans le JSON exporté pour faciliter une relecture indépendante.

## Conservation des sources

Les références sont désormais liées au texte, à l’explication, aux citations et aux pages par une empreinte. Le modèle ne réécrit plus librement le fait aux étapes 3 à 9 : une idée de modulation ne peut pas devenir une idée d’amplification sous le même identifiant. Une modification des sources ou du glossaire impose de reconstruire le plan.

Les contrôles de source distinguent notamment le dispositif cité du dispositif affirmé, les valeurs et unités (`mW` et `MW`), et un résultat expérimental d’une garantie générale. Ils restent des contrôles partiels, complétés par une seconde lecture du modèle. Une citation exacte ne prouve pas à elle seule que toute l’explication est juste.

Le plan ne force plus toutes les idées dans la durée demandée. Il compte les passages sources, questions, définitions, raccords et conclusion, conserve les exclusions motivées et limite chaque chapitre à cinq idées. La durée finale est calculée à 145 mots par minute, sans compter les noms des intervenants ; un écart important est signalé. L’application ne remplit pas artificiellement un podcast trop court.

À l’étape 8, le modèle propose uniquement les questions. Une question absente ou manifestement mal associée est reprise pour l’idée concernée, puis remplacée si nécessaire par une relance neutre signalée. Les questions identiques récentes sont variées. Le programme insère lui-même chaque réponse avec la bonne source. Le contrôle « toutes les idées affectées à ce chapitre » reste actif, y compris à la révision finale.

La mémoire conserve les idées déjà expliquées et les définitions sources, avec un aperçu limité pour le prochain appel. Les acronymes sont définis au premier emploi à partir du glossaire du document, avec une traduction reconnue lorsqu’elle est disponible. Les appels ne cumulent pas un historique complet de conversation.

## Résultats et relecture

Les exports comprennent `podcast.md`, `podcast.txt`, `podcast.json` et, après génération audio, `podcast.mp3` accompagné de ses rapports `audio.json` et `rapport_audio.csv` ; les essais ont des noms distincts. Le dossier du projet contient aussi les neuf étapes, les fragments, les citations, les motifs d’incertitude et les archives des anciens résultats. Le JSON final indique les idées couvertes, les exclusions, les avertissements et la durée estimée.

**Une relecture humaine reste nécessaire avant l’enregistrement.** Les formulations retenues à l’étape 2 peuvent encore comporter une mauvaise traduction ou une interprétation incomplète ; les conserver ensuite empêche une dérive supplémentaire mais ne les rend pas automatiquement exactes. La sélection éditoriale peut omettre un prérequis important. Les figures, équations, tableaux complexes et PDF scannés ne sont pas interprétés visuellement ; cette version n’intègre pas d’OCR. Les contradictions entre PDF ne sont pas arbitrées automatiquement.

## Vérification et sources

Les tests couvrent les erreurs relevées dans l’export précédent, les associations de contenu, la couverture des idées, les reprises, les archives et la migration. Le parcours navigateur utilise des API simulées : profils vocaux, aperçu, lecture et téléchargement sont vérifiés avec un **MP3 réellement encodé**. Les tests audio contrôlent l’authentification historique, les quatre champs du POST, l’import sans exécution, la lecture TXT sans PDF, les essais distincts, le volume, le silence, l’affectation des voix, les pauses, la reprise et l’annulation d’une requête HTTP en cours. Le paquet MP3 est préparé avec le gestionnaire uv de l’installation lorsqu’aucun pip n’est présent.

La vérification sur le podcast fourni porte sur sept erreurs identifiées et sur le glossaire du PDF. Les essais Mistral sont ciblés ; ils ne constituent pas une nouvelle génération scientifique complète des 147 pages. Les voix réelles de votre VoiceStudio, leur qualité sonore et l’interface native Windows doivent être essayées sur votre PC. Le cloud de développement ne peut pas joindre un service installé sur ce PC à travers son adresse `127.0.0.1`.

Pour les tests : `python -m unittest discover -s tests -q`. Pour construire les ZIP : `python build_release.py`. Le fichier `SOURCE-COMPLET.md` rassemble tous les sources de la version ; les archives de distribution excluent les PDF, projets, modèles, caches et secrets.
