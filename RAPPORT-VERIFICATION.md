# Vérification de DoublageBasic — 8 novembre 2026

## Statut

Archive de validation, avec installateur et application locale reconstitués.
**Pas de validation native Windows/NVIDIA et pas de validation complète de
l'analyse ou de la séparation sur un vrai extrait de film.** Ces limites ne
permettent pas de présenter cette version comme une livraison finale certifiée.

## Sources réellement retrouvées

Le dossier `/workspace/Doubalge` était propre, sur la branche `work`, au commit
`02aeae552e8f9c7c13c0831cc40704f1ebee330a`. Il ne contenait que les huit modules
Python historiques. Une sauvegarde intégrale de ce dossier a précédé les changements.

Sur le dépôt public `https://github.com/XgboostShap/Doubalge` :

- `main` : même commit initial et mêmes huit fichiers.
- `video-controle-20261028-6c04ef`, commit
  `66c781c452fdf3d3990e983942353b32f9132335` : huit modules et médias/HTML publiés.
- `studio-edition-compacte`, commit
  `592feeee01271dc92cab2b749f63e16cf3234a49` : éditeur complet, composants
  d'exports, préparation locale et tests. Le sous-dossier `studio` a été récupéré
  depuis cette branche, sans remplacer silencieusement les fichiers locaux.

Absents du dossier récupéré et des sources des trois branches : `app_local.py`,
`local_pipeline.py`, `verifier-installation.py`, `requirements-local.txt`,
`installation-windows.ps1`, `Installer-Windows.cmd`, `Lancer-DoublageBasic.cmd`,
`LIRE-MOI-WINDOWS.txt`, `local_web/index.html`, `local_web/style.css`,
`local_web/app.js`, `edition.py`, `duo.py`, `onde.py`, `timeline_editor.html`,
`impro_player.html`, `sources.json`, `requirements-duo.txt` et
`requirements-youtube.txt`. Les anciens tests Python au nombre annoncé de 42
n'ont pas été retrouvés. Ils ne sont pas présentés comme repassés.

Les fichiers du nouveau serveur, du worker, de l'installateur et de l'interface
ont été réécrits. `edition.py`, `duo.py` et `rendu_local.py` couvrent les nouvelles
corrections et exports ; la forme d'onde est produite par `local_pipeline.py`.
Les anciens noms HTML ne sont pas indispensables : leurs fonctions sont
fournies par les gabarits récupérés de `studio/templates` et le nouvel export.
Aucun extrait OSS n'est recodé en dur et aucun JSON OSS n'est appliqué à une
empreinte différente. Le fichier OSS original n'était pas une pièce jointe
accessible dans ce fil.

## Contrôles effectués dans cet environnement

- Syntaxe Python et JavaScript des nouveaux composants : valide.
- 37 tests Python des composants `studio` : réussis.
- 11 tests Python du nouveau parcours local : réussis. Contrôles Host/Origin/jeton
  de session ; chemins refusés ; lecture Range 206/416 ; import lié au SHA256 et
  à l'analyse ; préservation de `reviewed` et de `cuts` absent ; `cuts: []`
  explicite ; conflit de révisions ; ajout/renommage des identifiants de voix ;
  sauvegardes ; jeton en mémoire et masquage ; annulation d'une tâche en attente ;
  arrêt réel d'un processus et de son enfant sous Linux ; refus d'un second
  serveur sur le même dossier ; règle des chevauchements audio.
- Rendus réels FFmpeg des trois modes audio sur trois secondes synthétiques,
  à partir de pistes distinctes synthétiques de dialogue et de fond : les MP4
  produits se décodent. Ce test n'appelle pas le modèle Demucs.
- Chromium réel : création depuis une vidéo et un JSON synthétiques, écoute de
  l'original, recherche, édition des bornes, sauvegarde sur disque, ajout et
  renommage d'une voix, export MP4 intégré à un HTML, lecture du HTML avec le
  réseau désactivé, réouverture et conservation des corrections. Aucune erreur
  JavaScript observée. L'ouverture `file://` est bloquée par une politique du
  Chromium de cet environnement ; le HTML a été chargé dans une page hors ligne.
- Import effectif de PyTorch, TorchAudio, Pyannote, OpenCV, Demucs et des autres
  bibliothèques dans l'environnement Linux ; diagnostic FFmpeg réussi sur CPU.
- Résolution des dépendances pour Python 3.12 / Windows x86-64 : réussie.
  Simulation d'installation avec `uv 0.9.7` et cible Windows : réussie. Ce n'est
  pas une installation de ces bibliothèques sous Windows.
- Parsing du PowerShell par PowerShell 7.5.4 : réussi. Test de passage des arguments
  à la fonction d'exécution : réussi. Les CMD et PowerShell Windows 5.1 ne sont
  pas exécutables nativement ici.
- Distribution officielle `uv 0.9.7` : empreinte Windows récupérée ; options
  `python install`, `venv --seed`, `pip install/check`, `--no-progress` et
  `--reinstall` vérifiées avec le binaire officiel Linux de cette même version.
- Empreinte de Node 24.11.0 LTS Windows x64 vérifiée dans le manifeste officiel.
  Les deux empreintes sont figées dans l'installateur.
- Archive finale : construction par liste de fichiers sources, contrôle CRC,
  recherche de jetons potentiels et refus des caches, vidéos, `.venv`, `.git`,
  données utilisateur et liens symboliques.

## Limites encore ouvertes

1. Installation et lancement natifs sur Windows 10/11, chemins avec accents ou
   espaces, pilote NVIDIA, consommation mémoire et repli CPU sur ce PC réel.
2. L'appel réel à `speaker-diarization-3.1` a été tenté. Hugging Face n'a pas
   fourni le pipeline avec l'accès de cet environnement ; le chargement renvoie
   une erreur d'autorisation/conditions. Aucune qualité de diarisation n'est
   revendiquée. Le compte utilisé sur le PC doit disposer des accès requis.
3. Demucs `htdemucs` a été tenté. Le téléchargement officiel sur
   `dl.fbaipublicfiles.com` échoue dans cet environnement par tunnel proxy 403.
   Aucun contournement n'a été tenté. La séparation réelle et la réutilisation
   du cache hors connexion restent à vérifier après téléchargement sur le PC.
4. Le téléchargement YouTube sur le réseau personnel n'a pas été testé. Node
   est installé localement et transmis à yt-dlp ; un échec de réseau reste visible.
5. Le JSON OSS et sa vidéo originale doivent être réunis pour vérifier les
   35 intervalles, 30 plans et états `reviewed` précis du cas décrit.
6. Le lecteur HTML exporté intègre une vidéo finale avec ses repères ; il ne
   propose pas de changer les voix après export. Pour changer de mode, réexporter
   depuis le projet local. L'éditeur reste accessible dans l'application.

## Reproduire les tests

Après installation des dépendances :

```text
python -m unittest discover -s tests -v
python -m unittest discover -s studio/tests -p "test_*.py"
```

Les tests synthétiques n'exigent ni jeton, ni modèle téléchargé, ni GPU.
Le script navigateur de vérification est fourni dans `tests/browser-local.cjs`.
Il attend un serveur de test, Playwright et Chromium ; ses chemins se configurent
par les variables documentées dans son en-tête. Il ne fait pas partie du lancement
normal de l'application.
