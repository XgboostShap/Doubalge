# Podcast pédagogique — version 0.5.1

Application locale Windows 10/11 pour transformer plusieurs PDF en un dialogue pédagogique en français, puis en **podcast MP3 avec les voix déjà créées dans VoiceStudio**. Ollama rédige le texte ; VoiceStudio réalise la synthèse vocale sur le même PC.

## Mettre à jour une installation existante

1. Fermer la fenêtre de lancement de PodcastPedago.
2. Extraire **tout** le ZIP correctif dans un dossier temporaire.
3. Ouvrir **Mettre-a-jour.cmd**, puis choisir le dossier contenant votre `Lancer-Podcast.cmd`.
4. Relancer l’application et vérifier **Version 0.5.1** en haut de la page.

Si le projet indique **Aucune idée explicative retenue**, ouvrir le dernier projet puis cliquer sur **Réexaminer l’étape 2**. Les idées candidates déjà extraites sont réexaminées avec le nouveau protocole. Après la fin du traitement, consulter le nombre d’idées confirmées puis cliquer sur **Continuer jusqu’au script final**. Aucun PDF n’est à réimporter : l’extraction de l’étape 1, les références vocales et les archives sont conservées.

Un projet 0.5.0 dont les idées et le dialogue sont déjà confirmés peut continuer normalement. Pour une version plus ancienne signalée par le programme, utiliser **Améliorer les résumés existants**, puis Continuer.

L’outil de mise à jour vérifie les empreintes des **19 fichiers applicatifs**, sauvegarde les fichiers remplacés et tente de les restaurer en cas d’échec. Il ne remplace ni `donnees`, ni `.venv`, ni `.runtime`. Si Windows refuse `Mettre-a-jour.cmd`, ouvrir PowerShell dans le dossier du correctif et lancer `powershell -NoProfile -ExecutionPolicy Bypass -File .\mettre-a-jour.ps1` ; choisir ensuite le dossier de l’installation.

Pour lancer après mise à jour, utiliser **Lancer-Podcast.cmd dans l’ancien dossier installé**, pas dans le ZIP téléchargé. Le bouton Windows « Extraire tout » et la colonne « Taille compressée » indiquent que l’on se trouve encore dans une archive.

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

La connexion reprend le contrat API présent dans les anciens fichiers fournis : `GET /health`, `GET /v1/audio/voices` et `POST /v1/audio/speech`, avec l’en-tête `Authorization: Bearer local`. Le POST envoie exactement `model`, `input`, `voice` et `response_format`, avec `tts-1` et `wav` par défaut. La synthèse peut prendre jusqu’à 900 secondes par requête, contre 15 secondes pour les lectures de l’API. Le contrôle de santé accepte l’absence de `/health` (HTTP 404) pour les autres versions compatibles. La liste peut aussi provenir de `/profiles`.

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
| 3 | Synthèses rédigées des parties de chaque PDF, avec réécriture et relecture contre les citations. Le registre intégral reste séparé. |
| 4 | Texte commun réunissant les idées sous forme de phrases réécrites et vérifiées, classées par rôle pédagogique ; registre complet conservé. |
| 5 | Notions et problème avant méthodes, résultats, applications et limites. Question directrice et titres proposés à partir des sources. Détails et idées hors durée restent au dossier avec leur motif. |
| 6 | Une phrase centrale réécrite par idée, 35 mots maximum, puis vérification du sens contre la source. |
| 7 | Une explication orale de 85 mots maximum par idée, relue séparément ; contexte court pour éviter les redites. |
| 8 | Questions courtes et réponses issues de la rédaction vérifiée ; définitions intégrées à la même réplique, mémoire bornée et rappels entre chapitres. |
| 9 | Vérification des sources et empreintes, vraie seconde relecture du dialogue, correction locale si possible, puis rapport et exports. Un passage non confirmé arrête explicitement la révision. |

Chaque résultat terminé est sauvegardé en Markdown et JSON avant la suite. Le dialogue est enregistré par blocs de deux idées au maximum, puis par chapitre. **Continuer** réutilise les blocs terminés après une interruption. Une erreur réseau, une annulation ou un problème d’enregistrement reste un arrêt explicite.

## Correctif 0.5.1 — projet sans idée retenue

L’ancien contrôle pouvait écarter toutes les idées d’un PDF lisible parce que le modèle ne recopiait pas exactement les citations ou parce que son motif ressemblait à l’énoncé. Le nouveau protocole numérote les passages originaux : le modèle choisit leurs références et le programme insère les citations exactes. La seconde lecture sélectionne aussi des références pour l’énoncé et l’explication. Un motif reformulé n’est plus rejeté pour cette seule raison lorsqu’une preuve source valide a été sélectionnée.

Les contrôles du sens, des unités, des dispositifs, des traductions et du périmètre des résultats restent actifs. Les définitions de sigles écrites dans le corps d’un article court sont aussi reprises lorsque leurs initiales correspondent ; elles ne sont pas inventées à partir du sigle seul. Un identifiant inconnu ou une idée non confirmée ne sont pas acceptés automatiquement. Les passages d’une même page coupée entre deux parties peuvent servir ensemble à la vérification, quand la page tient dans le budget ; les citations gardent leur numéro de page.

Les numéros de preuve restent dans les références et ne doivent pas entrer dans le récit. Les annotations connues comme « (E1) » sont retirées des énoncés avec une correction enregistrée ; les citations restent inchangées et le sens est toujours contrôlé ensuite. Les listes simples de jeux de données doivent correspondre au nombre annoncé et leurs noms doivent figurer dans les citations. Le qualificatif « public » nécessite aussi un appui dans la source : un jeu mentionné dans un article n’est pas nécessairement public. Une notation ambiguë observée dans l’extraction d’un exposant est refusée : le modèle doit expliquer la complexité sans inventer la formule manquante. Ces contrôles ciblés s’appliquent dès l’examen des idées et pendant leur réécriture.

Si aucune idée n’est confirmée, un diagnostic affiche les motifs et propose de réexaminer l’étape 2. La suite ne génère plus de synthèses vides présentées comme terminées. Un examen limité à l’étape 2 conserve son rapport avec l’état « à réexaminer » ; une génération complète s’arrête à ce point. Les anciennes réponses négatives en cache ne sont pas réutilisées par le nouveau protocole de sélection des sources.

Les projets et les idées déjà correctement confirmés en 0.5.0 restent utilisables. Ce correctif résout une difficulté de format et de reprise ; il ne transforme pas chaque avis du modèle en preuve scientifique.

## Corrections de rédaction de la version 0.5.0

Cette version répond à l’audit des étapes 01 à 09 fourni le 15 novembre. Les traductions « pouvoir » dans une égalisation de puissance, le mélange émetteur/récepteur, les fautes techniques observées et les commentaires de production ont des contrôles ciblés. Les notices de diffusion, même présentées comme des propriétés du réseau, et les remarques sur les publications de doctorat sont écartées du contenu explicatif. Une citation composée d’un titre et de « Proprietary – Restricted Distribution » est refusée comme preuve.

La seconde lecture de l’étape 2 sélectionne désormais les références des passages exacts qui appuient l’énoncé et l’explication ; le programme les recopie. Elle travaille sur deux idées maximum à la fois. L’absence de preuve garde le passage parmi les éléments à vérifier. Une correction terminologique limitée peut préparer la demande du modèle pour éviter la recopie d’un mauvais résumé ; elle ne change ni les nombres, ni les unités, ni le rôle des équipements.

Le registre de faits reste inchangé pendant la rédaction, mais les phrases du podcast peuvent être reformulées. Chaque réécriture reçoit son empreinte, les sources de l’idée et un verdict de relecture avec citation. Les contrôles vérifient notamment les acronymes, les dispositifs, les nombres et leurs unités. Il n’y a pas de retour silencieux à un ancien texte non validé.

La révision finale prend aussi en compte les deux réponses précédentes pour repérer les redites. Elle peut demander une correction locale, vérifier cette correction à nouveau et enregistrer les versions avant/après. Une correction refusée ne produit pas un script automatiquement déclaré prêt pour le MP3. Les questions restent produites par petits blocs et les réponses viennent des explications réécrites et vérifiées ; il ne s’agit pas d’un dialogue libre sans contraintes factuelles.

Les définitions du lexique sont intégrées à la réplique de réponse ; les 14 prises de parole isolées « Dans ce document… » de l’exemple ne sont plus nécessaires. Les rappels utilisent les nouvelles phrases courtes, sans modifier la casse des unités. Le texte destiné à VoiceStudio est préparé séparément : retrait des références numériques de publications, lecture française d’unités courantes et de certaines lettres grecques, conservation des valeurs. Le rapport CSV contient le **texte réellement envoyé à la synthèse**. Les crochets numériques d’un dialogue TXT fourni manuellement sont conservés pour éviter de supprimer une valeur ou un intervalle. Ce préparateur n’est pas un lecteur universel de LaTeX ou de formules mathématiques.

## Petites requêtes et reprise

Chaque passage est enregistré en Markdown et JSON avant la suite. Les réécritures portent sur une idée, la seconde lecture des faits sur deux idées, et les questions sur deux idées. Les appels utilisent de nouvelles conversations, avec seulement un contexte court ; l’historique complet reste dans les fichiers. La révision et les corrections ont également leurs points de reprise.

Le contexte 8 192 tokens reste pris en charge pour les petits passages. Une page ou une citation démesurée peut demander un découpage supplémentaire ; aucune entrée n’est coupée silencieusement pour contourner le budget. Le nombre d’idées d’un long PDF peut entraîner de nombreux appels. La vitesse dépend du modèle et du PC ; la mise à jour n’exige pas une nouvelle carte graphique.

La durée est une cible, pas du remplissage obligatoire : le programme indique la durée estimée et les écarts, puis la durée réelle du MP3. Une source insuffisante ne justifie pas l’invention de contenu pour atteindre 20 minutes.

## Conservation des sources et limites

Le registre, les citations, les pages, les décisions incertaines et les anciens résultats restent au dossier du projet. Modifier une source ou un glossaire invalide les résultats qui en dépendent. Les champs de l’export distinguent le registre conservé, les réponses réécrites et les corrections de la révision.

**Les relectures du modèle restent faillibles.** Une citation exacte ne suffit pas à prouver une interprétation correcte, et deux appels au même modèle ne sont pas deux experts indépendants. Un petit modèle peut encore refuser une correction ou confirmer une mauvaise lecture. Les nouveaux contrôles corrigent des défaillances observées et rendent les refus visibles ; ils ne constituent pas une certification scientifique. Relire le nouveau dialogue et essayer un court audio avec les voix réelles avant de produire le podcast complet.

Les figures, équations et tableaux complexes ne sont pas interprétés visuellement. Les pages scannées nécessitent un OCR externe. Les contradictions ou ambiguïtés du PDF peuvent demander une vérification humaine ; la simple copie d’une phrase du PDF ne les résout pas.

## Vérification et distribution

Les tests couvrent les exemples de l’audit, les reformulations liées à leurs sources, le refus d’un texte non confirmé, une correction effective à l’étape 9, les empreintes, les unités sensibles à la casse, la reprise et la migration. Le parcours Chromium utilise des API simulées et un MP3 réellement encodé : neuf étapes, ancien projet, import VoiceStudio/TXT, aperçu, lecture, téléchargement, essais séparés et rapport CSV. Les vérifications PowerShell portent sur les fichiers de mise à jour et la conservation des données, pas sur l’interface native Windows.

Les essais avec le vrai Mistral sont ciblés sur des extraits ; ils ne constituent pas une nouvelle validation complète des 147 pages. Les voix réelles et leur prosodie restent à essayer dans VoiceStudio sur le PC : le cloud ne peut pas joindre ce service via l’adresse locale de ce PC.

Pour les tests : `python -m unittest discover -s tests -q`. Pour construire les ZIP : `python build_release.py`. `SOURCE-COMPLET.md` rassemble les sources de la version. Les archives distribuées ne contiennent ni PDF utilisateur, ni dialogue, ni voix privées, ni modèle, ni cache, ni secret.
