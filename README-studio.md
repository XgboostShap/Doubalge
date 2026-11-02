# Doubalge — application locale

Doubalge regroupe désormais la préparation, l’éditeur de scène, la sauvegarde des
corrections et l’export MP4 dans **une seule fenêtre Windows**. Les visuels de
l’éditeur et les vignettes du lecteur sont conservés. Le spectacle reste un export
HTML autonome. Les huit modules Python historiques ne sont pas modifiés.

## Mettre à jour une installation existante

1. Enregistrer le dernier JSON corrigé depuis l’ancien onglet avant de le fermer.
2. Extraire le ZIP GitHub puis copier **tout `studio` et `Lancer-studio.cmd`** dans
   le dossier existant. Conserver `.venv`, `.venv-detection`, `.cache`, `resultats`
   et `token_hf.txt`.
3. Ouvrir **Lancer-studio.cmd**. Au premier lancement, il installe uniquement
   `pywebview` et ses dépendances de fenêtre si nécessaire. Cette étape demande
   Internet ; les modèles existants et les environnements IA sont conservés.
4. Dans la fenêtre Doubalge, choisir **Importer une ancienne scène HTML**, ouvrir
   son `OSS-editeur.html` et choisir où conserver le nouveau projet. L’ancien HTML
   reste intact ; aucune analyse ni séparation n’est relancée.
5. Dans l’éditeur, utiliser **Importer** pour reprendre le dernier JSON corrigé
   s’il n’était pas déjà intégré à l’ancien HTML. Les brouillons de l’ancien
   navigateur ne peuvent pas être récupérés automatiquement.

Le moteur de fenêtre Windows est **Microsoft Edge WebView2**, qui doit être installé
sur le PC (il est présent sur de nombreuses installations Windows 10/11). Si le
lancement signale son absence, installer le runtime Evergreen depuis la page
[Microsoft WebView2](https://developer.microsoft.com/microsoft-edge/webview2/).
Cette livraison reste une application Python lancée par le CMD ; elle n’est pas
encore empaquetée en un exécutable Windows indépendant.

## Parcours dans la fenêtre unique

- **Nouvelle scène** : vidéo locale ou URL YouTube, timeline/corrections facultatives,
  choix de la détection, nombre de voix et séparation audio. Le journal et
  l’annulation restent dans la fenêtre. Après préparation, **Éditer la scène préparée**.
- **Ouvrir un projet** : sélectionner son fichier `projet.doubalge`.
- L’éditeur conserve la vidéo, les blocs, les plans, la forme d’onde et annuler/rétablir.
  Les modifications sont enregistrées sur disque après chaque changement. Le bouton
  **Enregistrer le projet** force une sauvegarde ; **Copie JSON** crée une sauvegarde
  indépendante. Le retour aux projets et la fermeture attendent la sauvegarde.
- **Exporter un MP4** : choisir les voix et l’ambiance, la qualité, puis **Créer le MP4**.
  Un dialogue demande le fichier de destination. Le MP4 est directement écrit sur
  le PC, avec les vignettes clignotantes et le prochain plan. Progression et annulation
  restent disponibles ; aucun téléchargement depuis un navigateur n’est nécessaire.
- **Exporter pour le spectacle** : crée le spectacle HTML autonome avec les
  corrections actuelles. Le lecteur impro autonome reste également exportable.

La fenêtre communique directement avec Python. Elle n’ouvre ni navigateur externe,
ni serveur HTTP, ni adresse `127.0.0.1`. L’HTML/JavaScript est seulement utilisé à
l’intérieur de la fenêtre pour conserver les visuels existants. L’usage local
n’exige pas de cloud. Internet est nécessaire aux installations initiales, aux
premiers modèles et au téléchargement d’une nouvelle vidéo YouTube.

## Contenu d’un projet

Chaque scène occupe un dossier distinct, contenant :

- `projet.doubalge` : le fichier à ouvrir dans l’application ;
- `document.json` : la scène et ses médias intégrés ;
- `corrections.json` : le dernier état enregistré ;
- `corrections-precedentes.json` : la version précédant la dernière sauvegarde ;
- `preparation/` : les résultats intermédiaires, pour les nouvelles préparations.

Pour déplacer ou sauvegarder un projet, copier **tout son dossier**, pas seulement
`projet.doubalge`. Les écritures des corrections sont atomiques. Une sauvegarde
illisible est signalée au lieu d’être remplacée par l’analyse initiale. Une autre
fenêtre ne peut pas ouvrir le même projet en écriture. Les médias et données de
projet sont privés : ne pas les publier dans le dépôt GitHub.

## Validation de l’application de bureau

Les tests couvrent la sauvegarde/réouverture, la conservation de l’analyse de départ,
les erreurs de disque, les corrections d’une autre source, le verrouillage entre
fenêtres, l’import d’un ancien HTML sans exécuter ses scripts, la préparation avec
JSON et l’annulation sans écraser un ancien MP4.

Un test réel pywebview/Qt sous Linux vérifie le pont Python, la lecture vidéo, les
corrections enregistrées, le MP4 H.264/AAC, l’export spectacle, la fermeture sauvegardée
et l’absence de serveur HTTP. Qt Linux n’inclut pas les codecs H.264 : la lecture de
l’interface y est testée avec une copie VP8/Opus synthétique ; les médias du rendu
MP4 et les MP4 produits restent en H.264/AAC. **Le moteur Edge WebView2, la lecture
H.264 dans la fenêtre Windows et les dialogues natifs restent à valider sur le PC
Windows réel.** Les modèles IA ne sont pas relancés pour ces tests d’interface.

```bash
python -m unittest discover -s studio/tests -p 'test_*.py' -v
# Test de fenêtre explicite, avec pywebview et un moteur GUI installés :
python studio/tests/test_desktop_native.py
```

## Fonctions et parcours HTML historiques

Les sections suivantes décrivent aussi les exports autonomes et les commandes
historiques, toujours disponibles. Leur formulaire navigateur/serveur local est un
parcours de compatibilité ; **Lancer-studio.cmd ouvre désormais l’application**.

## Installation sur le PC Windows

Placer `studio`, `Installer-studio.cmd` et `Lancer-studio.cmd` dans le dossier
principal, à côté de `projet` si les huit modules sont dans ce sous-dossier.
Le dépôt GitHub fonctionne aussi directement avec ses huit modules à la racine.

1. Installer Python 3.12 64 bits et un pilote NVIDIA récent.
2. Lancer `Installer-studio.cmd`. L’environnement `.venv` existant est réutilisé.
   L’installation principale prévoit PyTorch CUDA 12.8 pour une carte NVIDIA.
   Pour une installation CPU : `Installer-studio.cmd cpu` dans un terminal.
3. Créer `token_hf.txt` à côté de `Lancer-studio.cmd`, contenant uniquement
   la clé Hugging Face complète sur une ligne, sans guillemets, en UTF-8.
   Ce fichier privé est ignoré par Git. Ne pas l’inclure dans une archive partagée.
4. Ouvrir `Lancer-studio.cmd`, puis **Nouvelle scène** pour choisir une vidéo ou
   coller son URL YouTube. **Ouvrir un projet** reprend une scène déjà importée.
   Une timeline.json déjà calculée peut être choisie pour réutiliser l’analyse.
   Dans « Corrections manuelles », choisir le JSON corrigé de l’éditeur : ses voix,
   ses bornes, ses plans et ses validations sont prioritaires, sans nouvelle attribution IA.
   Un JSON corrigé peut aussi être placé dans le champ Timeline ; il est reconnu automatiquement.
   Garder « Préparer le choix des voix et de l’ambiance » coché pour créer les pistes audio.

La nouvelle détection utilise **[pyannote Community-1](https://huggingface.co/pyannote/speaker-diarization-community-1)**.
La clé doit permettre l’accès à ce modèle ; accepter ses conditions sur Hugging Face
si ce n’est pas déjà fait. Le modèle classique reste disponible et nécessite l’accès
à speaker-diarization-3.1 et segmentation-3.0. Les modèles sont téléchargés lors de
la première analyse, puis conservés sur le PC.
Internet reste nécessaire pour les premiers modèles et les vidéos YouTube.
Le contrôle d’accès du service YouTube peut refuser certains téléchargements.

Le traitement se fait sur le PC. La diarisation et la séparation voix/fond utilisent
la carte NVIDIA si CUDA est disponible ; les exports vidéo utilisent le CPU. Le périphérique est affiché
dans la console. Le mode hors ligne Hugging Face est désactivé pour ce lanceur.
Le lancement utilise UTF-8 pour éviter les erreurs d’écriture de rapport Windows.

## Détection des prises de parole

Pour activer l’amélioration sur une installation existante, copier `studio` et
`Installer-studio.cmd` depuis la nouvelle version, puis relancer **Installer-studio.cmd**
une seule fois. Il conserve `.venv` et prépare un environnement de détection séparé
`.venv-detection` avec pyannote 4. Cela conserve la compatibilité du traitement
audio existant. CUDA 12.8 est utilisé pour la RTX 5060 Ti ; l’option `cpu` du script
reste disponible.

Dans **Lancer-studio.cmd**, la liste **Détection des voix** propose Community-1
quand l’installation est prête et le modèle classique 3.1. Community-1 améliore
généralement la séparation et le comptage des locuteurs sur les évaluations publiées,
mais ne garantit pas une identification parfaite des personnages d’un film.
Indiquer le **nombre de voix attendu** si on le connaît aide à limiter les groupes
superflus. Les numéros Voix 1, Voix 2… restent des groupes acoustiques à vérifier.

Les deux modes conservent maintenant les petites pauses : l’ancienne fusion
automatique jusqu’à 0,3 seconde a été supprimée. Seules les plages qui se
chevauchent pour une même voix sont réunies, et les voix simultanées sont conservées.
Community-1 utilise sa sortie standard, pas sa sortie exclusive qui imposerait
une seule voix à la fois.

**Un JSON existant est toujours prioritaire.** Un JSON corrigé ne déclenche aucune
nouvelle attribution IA, même si Community-1 est sélectionné. Pour tester une
nouvelle détection, choisir la vidéo sans JSON et garder les anciens résultats à
part. Les corrections ne sont pas utilisées pour réentraîner automatiquement le modèle.

Le traitement reste local ; la télémétrie pyannote est désactivée. Le modèle est
chargé directement depuis son cache complet, sans requête réseau quand les fichiers
sont déjà présents. L’audio est chargé en mémoire pour éviter de dépendre des DLL
de décodage FFmpeg sur Windows.
Le processus de détection libère son GPU avant la séparation audio. Le modèle,
sa révision et le périphérique sont enregistrés dans `timeline.json` pour identifier
la détection réellement utilisée. Une erreur du modèle avancé est signalée, sans
substitution silencieuse par l’ancien modèle.

## Corriger la scène

L’éditeur `OSS-editeur.html` s’ouvre après préparation. Il conserve ensemble la
vidéo, la timeline, le panneau de parole et le panneau des changements de plan.
La vidéo se trouve à gauche, avec les voix et les deux panneaux de correction
à sa droite. La liste complète et l’aide sont dans des fenêtres séparées.

Pour une vidéo longue, la timeline affiche **trois minutes à la fois** par défaut.
La barre **Défiler** sous les pistes, ses flèches et la barre horizontale permettent
de parcourir le reste ; les noms des voix restent visibles à gauche. Le réglage
**Vue** propose aussi 1 minute, 30 secondes et la vue entière. Le défilement manuel
ne change ni l’image courante ni les corrections et désactive **Suivre la lecture**.
**Au curseur** retrouve la position de lecture ; recocher **Suivre la lecture**
permet à la timeline d’accompagner la vidéo.

La forme d’onde est affichée plus haut, avec un gain visuel ×2. Le bouton
**Forme d’onde** permet de choisir la hauteur et un gain de ×1 à ×8 pour repérer
les passages faibles. Ce gain ne change pas le son. La hauteur s’adapte à la place
disponible pour garder toutes les pistes à l’écran.

- Cliquer un bloc de parole, puis glisser son centre pour le déplacer ou ses
  poignées pour ajuster ses bornes. Déplacer un bloc sur une autre ligne change sa voix.
- Utiliser les champs Début / Fin ou le choix de voix pour une correction précise.
- Cliquer un losange de plan, puis le déplacer, saisir son instant ou utiliser
  −1 / +1 image. « Au curseur » place la coupe à l’image affichée.
- Maj + glisser crée une parole ; Scinder et Fusionner ajustent le découpage.
- Annuler / Rétablir conservent l’historique de la session.
- « Voir l’analyse initiale » affiche les propositions d’origine en transparence.
  Les données automatiques sont conservées ; les corrections sont prioritaires.
- « Enregistrer les corrections » télécharge un JSON. « Importer » le recharge
  dans le même projet, avec vérification de la vidéo et de l’identifiant d’analyse.
- « Exporter le lecteur impro » génère un nouveau HTML reprenant les corrections
  présentes. Les repères de voix anticipent de 1,5 seconde, les plans de 0,5 seconde.
- « Options du lecteur » permet de cocher plusieurs voix à retirer et de choisir
  indépendamment de conserver ou non l’ambiance/musique. Ces choix sont conservés
  dans le JSON et dans le lecteur exporté. Le lecteur permet aussi de les changer
  pendant la lecture. Par défaut, toutes les voix et l’ambiance sont conservées.

Le bas de l’éditeur indique le nombre de passages ajoutés, modifiés et supprimés
par rapport à l’analyse initiale, ou au point de départ si elle n’est pas disponible.
Les exports JSON et impro portent la date et
l’heure dans leur nom ; le lecteur affiche aussi ce récapitulatif et sa date
d’export. **Ctrl + J** ouvre les téléchargements du navigateur : ouvrir le fichier
`version-impro-…-date-heure.html` qui vient d’être créé. L’ancien `OSS.html` produit
pendant la préparation ne change pas lorsqu’on corrige la scène dans le navigateur.
Le message « Téléchargement demandé » ne garantit pas que le navigateur a enregistré
le fichier : vérifier sa présence dans les téléchargements.
Après l’export, **Voir ce lecteur** ouvre exactement les données qui viennent
d’être préparées. Le lien disparaît dès qu’une nouvelle modification rend cet
export ancien ; exporter à nouveau pour vérifier le dernier état. La vidéo de
l’éditeur se met en pause à l’ouverture du lecteur.

Espace : lire/pause ; flèches : image précédente/suivante ; S : scinder ; P :
ajouter un plan ; Suppr : supprimer la sélection ; Ctrl+Z / Ctrl+Y : historique.

Le dossier `resultats/edition-…` contient les deux HTML, la timeline d’analyse,
les corrections initiales et un dossier `travail` utilisé pour les médias.
Les HTML intègrent leurs médias et se partagent seuls. Leur taille dépend de la vidéo.
Une erreur d’export conserve la timeline déjà calculée : elle peut être réutilisée.
Le fond « hors champ / inconnu » n’est pas un personnage supplémentaire.
Les identités acoustiques restent des propositions à vérifier.

### Mettre à jour un éditeur déjà créé

Inutile de refaire l’analyse d’une vidéo de huit minutes pour changer l’interface :

1. Dans l’ancien éditeur, **Enregistrer les corrections** pour télécharger le JSON
   contenant le dernier brouillon.
2. Copier le dossier `studio` mis à jour et **Actualiser-editeur.cmd** dans le
   dossier principal du projet, à côté de la `.venv` existante.
3. Lancer **Actualiser-editeur.cmd**, choisir l’ancien `OSS-editeur.html`, puis le
   JSON de corrections enregistré. Le JSON est facultatif si les repères intégrés
   au HTML suffisent.
4. Cliquer **Créer le nouvel éditeur**. Un HTML `…-actualise.html` est créé à côté
   de l’original et s’ouvre dans le navigateur. Les médias, les propositions initiales,
   les corrections importées et leurs validations sont conservés. L’original reste
   intact ; aucun modèle, téléchargement ou nouveau traitement audio n’est nécessaire.

En ligne de commande :

```powershell
.\.venv\Scripts\python.exe -X utf8 studio\actualiser_editeur.py "D:\Resultats\OSS-editeur.html" --corrections "D:\Resultats\timeline-corrigee.json"
```

## Envoyer une vidéo d’entraînement MP4

### Mettre à jour le projet existant

Enregistrer d’abord les corrections JSON depuis l’ancien onglet. Extraire le ZIP
GitHub de cette version, puis copier **tout le dossier `studio`** et les lanceurs
à côté de l’installation existante (ou de `projet`). Conserver `.venv`,
`.venv-detection`, `.cache`, `token_hf.txt` et `resultats` ; ne pas déplacer ni
supprimer les anciens résultats. Cette fonction utilise les dépendances déjà
prévues, dont `imageio-ffmpeg==0.7.0` et NumPy ; aucune réinstallation de modèle
n’est nécessaire si le studio fonctionne déjà.

1. Ouvrir **Lancer-studio.cmd**, puis **Ouvrir un projet** ou **Importer une ancienne scène HTML**.
2. Importer le dernier JSON corrigé si nécessaire. Les modifications suivantes sont
   automatiquement enregistrées dans le projet.
3. Dans **Exporter un MP4 → Choisir les voix et l’ambiance**, cocher une ou deux
   voix à retirer et régler l’ambiance et les paroles non attribuées.
4. Revenir à **Exporter un MP4**, choisir **Compact** ou **Standard**, puis
   **Créer le MP4** et choisir sa destination. Les corrections sont figées à ce clic.
5. Attendre la fin, vérifier la vidéo et le son, puis partager le fichier soi-même.
   Aucun envoi de message n’est effectué. Le destinataire n’installe ni Python ni IA.

Le fichier est encodé en **MP4 H.264, yuv420p, audio AAC stéréo 48 kHz**, avec les
métadonnées de lecture en début de fichier (`faststart`). Le profil Compact vise
360p à environ **4 Mo/minute** et Standard 720p à environ **14 Mo/minute**, selon
le rapport d’image et le contenu. La taille annoncée est indicative ; les limites
varient selon la messagerie. Si nécessaire, envoyer comme document ou utiliser
un lien de partage. Cette version exporte toute la scène.

Le MP4 conserve les vignettes du lecteur impro : portraits lorsqu’ils sont présents,
sinon symboles V1, V2… avec les couleurs et noms corrigés. Toutes les voix sont
visibles à droite, avec « Film » ou « À vous » selon les rôles choisis. Les cartes
restent atténuées à 35 % au repos, clignotent toutes les 0,25 seconde dès 1,5 seconde
avant la parole, puis restent allumées pendant la réplique. Les photos sont empilées
et les symboles sans photo sont alignés horizontalement, comme dans le lecteur.
La vignette en bas à gauche montre une image du prochain plan corrigé, clignote
0,5 seconde avant la coupe et reste allumée 0,25 seconde après. Les paroles non
attribuées conservent leur avertissement. La vidéo reste cadrée dans une scène 16:9.
Les repères suivent les corrections actuelles, sans nouvelle analyse IA. Le mixage
reprend les règles du lecteur : l’ambiance est indépendante, mais retirer une voix
coupe aussi les autres dialogues pendant un chevauchement. Des résidus vocaux
peuvent rester dans le fond sonore.

Le service écoute uniquement sur le PC (`127.0.0.1`). Le lanceur affiche l’adresse
simple de l’éditeur, sans clé dans l’URL. Les commandes d’export restent protégées
par une clé propre à la session. Si le port 8765 est occupé, un autre port libre
est choisi automatiquement ; ouvrir l’adresse affichée pour cette scène.
Sous Windows, les sessions ne peuvent plus partager le même port. Une ancienne
adresse avec clé propose de revenir à la page de la session courante.
L’encodage et les médias restent sur le PC, sans besoin d’Internet.
Les fichiers temporaires sont nettoyés à l’arrêt
normal du lanceur. Les corrections restent à sauvegarder avec **Enregistrer les
corrections** ; le service ne réécrit pas le HTML d’origine.

### Vérifications de l’export MP4

Les tests sous Linux/Chromium couvrent l’export depuis l’interface, le téléchargement,
les codecs réellement produits, les repères incrustés, les corrections réattribuées,
le refus d’une autre source, la progression et l’annulation. Les tests mesurent le
signal **après décodage du MP4 AAC**, pour une et deux voix retirées, avec et sans
ambiance, y compris un chevauchement. Le rendu utilise OpenCV et Pillow (déjà installés avec le studio), puis FFmpeg
pour le H.264/AAC. Son exécution sur Windows et la réception effective
dans WhatsApp/iOS/Android restent à vérifier sur les appareils réels.

```bash
python -m unittest discover -s studio/tests -p 'test_*.py' -v
python studio/tests/make_fixture.py /chemin/resultat-test
node studio/tests/test_mp4.cjs /chemin/resultat-test/OSS-editeur.html
node studio/tests/test_mp4_visuals.cjs /chemin/resultat-test/OSS.html
```

Le test navigateur utilise Playwright, Chromium et FFprobe. La variable `PYTHON`
peut sélectionner l’interpréteur installé pour le studio ; `CHROMIUM` sélectionne
le navigateur de test. FFprobe sert uniquement à la validation en développement.

## Spectacle : improvisateurs, public et plusieurs scènes

Le fichier **Spectacle.html** à la racine est une application autonome : l’ouvrir
dans Chrome ou Edge sur le PC du spectacle. Aucune installation ni connexion
Internet n’est nécessaire pour jouer les scènes déjà préparées.

1. Dans chaque éditeur, terminer les corrections, puis **Exporter le lecteur impro**.
   Le bouton **Mode spectacle** exporte aussi un spectacle contenant directement
   cette scène avec les corrections courantes. Les nouveaux dossiers de résultat
   contiennent un fichier Spectacle.html préchargé avec leur scène initiale.
2. Dans le mode spectacle, cliquer **Ajouter des scènes** et sélectionner plusieurs
   lecteurs HTML exportés. Les anciennes versions des lecteurs sont compatibles.
   Un MP4 brut ou un JSON de corrections ne contient pas tous les repères/pistes :
   il faut préparer ce fichier dans l’éditeur puis exporter son lecteur.
3. Ordonner les scènes avec les flèches ↑ / ↓, changer leurs titres si nécessaire,
   puis **Préparer** la scène choisie. Les voix retirées, l’ambiance et les noms
   des improvisateurs sont mémorisés séparément pour chaque scène.
4. **Enregistrer le spectacle** télécharge un HTML contenant l’ensemble du programme,
   ses vidéos, ses pistes audio et ses réglages. Ce fichier peut être rouvert seul,
   hors connexion, ou chargé avec **Charger un spectacle**. Le programme contient
   les médias : sa taille augmente avec le nombre et la durée des vidéos.

### Installer les deux écrans

Sur Windows : **Win + P → Étendre**. Dans le mode spectacle, cliquer **Ouvrir
l’écran public**, déplacer la nouvelle fenêtre sur le deuxième écran puis cliquer
sur **Plein écran public**. Un double-clic dans cette fenêtre permet aussi de
changer le plein écran. Autoriser les fenêtres du navigateur si celui-ci bloque
l’ouverture demandée par le bouton.

L’écran improvisateurs conserve la vidéo, les vignettes de voix avec le nom de
l’improvisateur, les annonces de parole et l’aperçu du prochain plan. Cocher
« Je joue Voix N » retire cette voix du film ; les choix se cumulent. Les voix
conservées sont marquées « Film » pour éviter de les confondre avec les rôles joués.
Le plein écran impro affiche seulement cette vue de scène ; les raccourcis restent actifs.

L’écran public affiche **la vidéo seule**, sans noms ni repères. Sa vidéo est
toujours muette : le son est produit **une seule fois par la fenêtre de commande**,
avec le mixage choisi. Sélectionner la sortie de la sono dans les réglages audio
Windows ; le programme ne change pas automatiquement les périphériques audio.
Le microphone des improvisateurs reste géré par la sono, hors de cette application.

Les deux lectures suivent la même position et les mêmes pauses. Entre deux scènes,
la sortie public reste noire pendant la préparation. Par défaut, le passage se
fait avec **Suivante**, puis **Lire**. Cocher **Enchaînement automatique** pour
lancer la suivante après la fin. Le bouton **Noir / arrêt** coupe la lecture et
remet au début. La fermeture de la fenêtre public arrête la lecture ; la fermeture
de la commande remet la sortie public au noir.

Raccourcis de spectacle : **Espace** lire/pause, **N** suivante, **P** précédente,
**B** noir et arrêt. Ils sont désactivés pendant la saisie d’un nom.
Vérifier l’ensemble sur les deux écrans réels avant le spectacle : la sortie vidéo,
le plein écran et la latence dépendent aussi du PC, des écrans et du navigateur.

Importer directement un fichier éditeur réutilise les corrections intégrées à ce
fichier, pas les brouillons de son ancien navigateur. Pour garder les dernières
modifications, exporter le lecteur ou le spectacle depuis l’éditeur ouvert.

## Sélection des voix et ambiance

L’éditeur conserve le son original pour vérifier les attributions. Le traitement
prépare deux pistes : tous les dialogues d’un côté, le fond sonore de l’autre.
Le modèle officiel TorchAudio `HDEMUCS_HIGH_MUSDB_PLUS` est téléchargé une seule
fois (environ 320 Mo), puis conservé dans `.cache/torch`. Aucun paquet supplémentaire
ni token supplémentaire n’est nécessaire pour ce modèle.

Dans le lecteur, chaque case « Retirer Voix N » coupe la piste de dialogue sur
les plages attribuées à cette voix par les corrections. Plusieurs cases peuvent
être cochées. L’ambiance est indépendante ; la case « Conserver les paroles non
attribuées » décide du son de dialogue hors des zones connues. « Retirer toutes
les voix » coupe aussi ces passages inconnus ; décocher ensuite l’ambiance rend
le lecteur entièrement muet. « Tout conserver » rétablit l’ensemble du son.

La séparation est expérimentale : le modèle a été entraîné sur la musique et
peut laisser des restes de voix dans le fond. Il ne sépare pas les personnes
qui parlent simultanément : retirer une voix coupe le dialogue de toutes les
voix sur ce chevauchement. La qualité dépend aussi de l’exactitude des plages
de parole ; les corrections humaines ne sont jamais remplacées par une nouvelle
diarisation quand un JSON corrigé est fourni.

Le nombre de voix attendu peut être indiqué lors d’une nouvelle analyse pour
limiter les groupes superflus ; ce n’est pas une garantie d’identification juste.
Les passages non validés restent signalés dans l’éditeur et le lecteur.

Pour une préparation rapide sans séparation : décocher l’option dans le formulaire
ou utiliser `--sans-audio-separe`. Le lecteur conserve alors le son original et
explique que les choix de voix demandent de recréer le projet avec les pistes.
Les anciens HTML muets doivent être recréés une fois depuis la vidéo et son JSON
corrigé : les pistes audio manquantes ne peuvent pas être ajoutées par un simple import JSON.
Le code ne clone aucune voix, ne traduit pas les dialogues et n’enregistre pas le micro.

Les médias et corrections des exemples de l’autre discussion ne sont pas
codés en dur dans le générateur. Chaque vidéo produit ses propres données.

## Ligne de commande

```powershell
.\.venv\Scripts\python.exe -X utf8 studio\lancer_studio.py --video "D:\Videos\scene.mp4"
.\.venv\Scripts\python.exe -X utf8 studio\lancer_studio.py --video "D:\Videos\scene.mp4" --detection community-1 --personnages 3
.\.venv\Scripts\python.exe -X utf8 studio\lancer_studio.py --video "D:\Videos\scene.mp4" --timeline "D:\Resultats\timeline.json"
.\.venv\Scripts\python.exe -X utf8 studio\lancer_studio.py --video "D:\Videos\scene.mp4" --corrections "D:\Resultats\timeline-corrigee.json"
```

Le deuxième exemple réutilise la diarisation existante, après vérification de
la source et de la durée. Une ancienne timeline sans empreinte doit avoir le
même chemin ou la même URL source. Le troisième exemple réutilise directement
les corrections et leurs validations, avec vérification de l’empreinte de la vidéo.
Il suffit du même fichier vidéo et du JSON ; l’ancienne attribution automatique
n’est pas nécessaire. Une nouvelle copie vidéo réencodée ne possède pas la même empreinte.

## Vérifications et limites

Les tests de détection vérifient les pauses courtes, les chevauchements, l’ordre
d’apparition des voix, les installations incomplètes et la réutilisation exacte
des corrections sans appel IA. Community-1 est également essayé sur une vidéo
réelle, sur CPU. Les performances et la qualité d’attribution sur le PC Windows
et sur chaque nouvel extrait restent à contrôler ; aucun taux d’erreur garanti
n’est annoncé pour les scènes de film.

Le test local génère une vidéo synthétique, effectue de vrais glissements et
exports dans Chromium, puis lit le lecteur exporté. Les écrans 1280×720,
1366×768 et 1920×1080 sont couverts avec quatre voix et une piste inconnue.
Un très grand nombre de voix peut nécessiter une fenêtre plus grande.
Une vidéo synthétique de 8 min 24 vérifie la vue de trois minutes, le défilement,
les noms de voix fixes, les déplacements et poignées après défilement, la fin de
vidéo, les différentes échelles et le maintien de la position au redimensionnement.
Les fichiers CMD et CUDA restent à exécuter sur le PC Windows ; le moteur et
les interfaces sont vérifiés dans l’environnement Linux de développement.

Les tests audio rendent les 64 combinaisons de quatre voix, de l’ambiance et
des passages inconnus dans WebAudio, puis mesurent les signaux pour vérifier
les coupures et l’indépendance du fond. La lecture, la pause, les recherches,
la vitesse et le cumul de cases sont aussi exercés dans Chromium. Une séparation
réelle HDemucs et une génération complète depuis un JSON corrigé ont été vérifiées
sur un court extrait, sur CPU. Cela ne garantit pas l’absence de résidus vocaux
sur toutes les vidéos.

Les essais du mode spectacle ouvrent deux fenêtres Chromium, vérifient les pauses,
recherches et transitions, la sortie public sans repères et muette, les réglages
par scène, la sauvegarde autonome et la lecture hors connexion. La synchronisation
est contrôlée sur les horloges vidéo du navigateur ; l’installation physique
Windows sur deux moniteurs reste à vérifier sur le PC du spectacle.

Les gabarits proviennent des HTML fournis par l’utilisateur et de la branche
`video-controle-20261028-6c04ef`, notamment pour retrouver les corrections OSS.
Le travail porte sur la disposition compacte, les contrôles d’image et de plan,
la génération depuis une nouvelle vidéo et les lanceurs PC.

### Si l’ancien navigateur affiche « Accès refusé »

La préparation peut être terminée même si l’éditeur local ne s’est pas ouvert.
Quand la console affiche `[terminé] Éditeur : …`, conserver ce dossier de résultats.
Après mise à jour de `studio` et de `Lancer-studio.cmd`, fermer les anciennes consoles,
relancer `Lancer-studio.cmd`, choisir **Importer une ancienne scène HTML** et le **OSS-editeur.html**
indiqué par ce message. Aucune détection ni séparation n’est relancée. Importer
le dernier JSON corrigé si des modifications avaient déjà été enregistrées.
L’application de bureau n’utilise plus cette adresse locale. Pour le parcours
historique en ligne de commande, utiliser l’adresse simple affichée par sa console.
