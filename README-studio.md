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

La clé doit permettre l’accès aux modèles pyannote speaker-diarization-3.1 et
segmentation-3.0. Les modèles sont téléchargés lors de la première analyse.
Internet reste nécessaire pour les premiers modèles et les vidéos YouTube.
Le contrôle d’accès du service YouTube peut refuser certains téléchargements.

Le traitement se fait sur le PC. La diarisation utilise la carte NVIDIA si CUDA
est disponible ; les exports vidéo utilisent le CPU. Le périphérique est affiché
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

Espace : lire/pause ; flèches : image précédente/suivante ; S : scinder ; P :
ajouter un plan ; Suppr : supprimer la sélection ; Ctrl+Z / Ctrl+Y : historique.

Le dossier `resultats/edition-…` contient les deux HTML, la timeline d’analyse,
les corrections initiales et un dossier `travail` utilisé pour les médias.
Les HTML intègrent leurs médias et se partagent seuls. Leur taille dépend de la vidéo.
Une erreur d’export conserve la timeline déjà calculée : elle peut être réutilisée.
Le fond « hors champ / inconnu » n’est pas un personnage supplémentaire.
Les identités acoustiques restent des propositions à vérifier.

## Périmètre de cette première version

L’éditeur a le son original. Le lecteur généré par défaut est muet pour l’impro.
La séparation voix/ambiance ne fait pas partie du traitement par défaut demandé.
Les gabarits conservent la compatibilité des pistes séparées déjà présentes
dans les exemples OSS, mais ne fabriquent pas de nouvelles pistes séparées.
Le code ne clone aucune voix, ne traduit pas les dialogues et n’enregistre pas le micro.

Les médias et corrections des exemples de l’autre discussion ne sont pas
codés en dur dans le générateur. Chaque vidéo produit ses propres données.

## Ligne de commande

```powershell
.\.venv\Scripts\python.exe -X utf8 studio\lancer_studio.py --video "D:\Videos\scene.mp4"
.\.venv\Scripts\python.exe -X utf8 studio\lancer_studio.py --video "D:\Videos\scene.mp4" --timeline "D:\Resultats\timeline.json"
```

Le deuxième exemple réutilise la diarisation existante, après vérification de
la source et de la durée. Une ancienne timeline sans empreinte doit avoir le
même chemin ou la même URL source. Un JSON de corrections s’importe dans l’éditeur ;
il ne remplace pas la timeline brute dans ce formulaire.

## Vérifications et limites

Le test local génère une vidéo synthétique, effectue de vrais glissements et
exports dans Chromium, puis lit le lecteur exporté. Les écrans 1280×720,
1366×768 et 1920×1080 sont couverts avec quatre voix et une piste inconnue.
Un très grand nombre de voix peut nécessiter une fenêtre plus grande.
Les fichiers CMD et CUDA restent à exécuter sur le PC Windows ; le moteur et
les interfaces sont vérifiés dans l’environnement Linux de développement.

Les gabarits proviennent des HTML fournis par l’utilisateur et de la branche
`video-controle-20261028-6c04ef`, notamment pour retrouver les corrections OSS.
Le travail porte sur la disposition compacte, les contrôles d’image et de plan,
la génération depuis une nouvelle vidéo et les lanceurs PC.
