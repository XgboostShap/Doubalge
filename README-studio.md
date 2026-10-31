# Éditeur local Doubalge

Cette version reprend les interfaces des fichiers OSS fournis, avec l’édition
des paroles et des plans sur un seul écran. Les huit modules Python historiques
restent inchangés. Le lecteur HTML et son éditeur sont autonomes : la vidéo est
intégrée aux fichiers, sans serveur ni téléchargement au moment de leur lecture.

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
4. Ouvrir `Lancer-studio.cmd`, choisir une vidéo ou coller son URL YouTube.
   Une timeline.json déjà calculée peut être choisie pour réutiliser l’analyse.
   Dans « Corrections manuelles », choisir le JSON corrigé de l’éditeur : ses voix,
   ses bornes, ses plans et ses validations sont prioritaires, sans nouvelle attribution IA.
   Un JSON corrigé peut aussi être placé dans le champ Timeline ; il est reconnu automatiquement.
   Garder « Préparer le choix des voix et de l’ambiance » coché pour créer les pistes audio.

La clé doit permettre l’accès aux modèles pyannote speaker-diarization-3.1 et
segmentation-3.0. Les modèles sont téléchargés lors de la première analyse.
Internet reste nécessaire pour les premiers modèles et les vidéos YouTube.
Le contrôle d’accès du service YouTube peut refuser certains téléchargements.

Le traitement se fait sur le PC. La diarisation et la séparation voix/fond utilisent
la carte NVIDIA si CUDA est disponible ; les exports vidéo utilisent le CPU. Le périphérique est affiché
dans la console. Le mode hors ligne Hugging Face est désactivé pour ce lanceur.
Le lancement utilise UTF-8 pour éviter les erreurs d’écriture de rapport Windows.

## Corriger la scène

L’éditeur `OSS-editeur.html` s’ouvre après préparation. Il conserve ensemble la
vidéo, la timeline, le panneau de parole et le panneau des changements de plan.
La liste complète et l’aide sont dans des fenêtres séparées.

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

Espace : lire/pause ; flèches : image précédente/suivante ; S : scinder ; P :
ajouter un plan ; Suppr : supprimer la sélection ; Ctrl+Z / Ctrl+Y : historique.

Le dossier `resultats/edition-…` contient les deux HTML, la timeline d’analyse,
les corrections initiales et un dossier `travail` utilisé pour les médias.
Les HTML intègrent leurs médias et se partagent seuls. Leur taille dépend de la vidéo.
Une erreur d’export conserve la timeline déjà calculée : elle peut être réutilisée.
Le fond « hors champ / inconnu » n’est pas un personnage supplémentaire.
Les identités acoustiques restent des propositions à vérifier.

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

Le test local génère une vidéo synthétique, effectue de vrais glissements et
exports dans Chromium, puis lit le lecteur exporté. Les écrans 1280×720,
1366×768 et 1920×1080 sont couverts avec quatre voix et une piste inconnue.
Un très grand nombre de voix peut nécessiter une fenêtre plus grande.
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
