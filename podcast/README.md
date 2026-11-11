# Podcast pédagogique — version 0.1.1

Application locale pour transformer plusieurs PDF en un script de podcast
progressif, en français, avec Mistral via Ollama. Le programme produit le **texte
du dialogue** ; la synthèse audio n’est pas incluse dans cette version.

## Correctif Windows 0.1.1

Cette version corrige les accès concurrents au fichier `tache.json`. Les lectures
et écritures partagent un verrou ; les erreurs temporaires Windows 5, 32 et 33
font l’objet de nouvelles tentatives, pendant quelques secondes. Le fichier
précédent reste en place tant que le remplacement n’a pas réussi. Une erreur
persistante d’enregistrement est affichée sans arrêter le worker.

Pour une installation existante, fermer la fenêtre de lancement puis remplacer
uniquement `app.py` et `storage.py` avec le ZIP correctif. Conserver le dossier
`donnees` et l’environnement `.venv`. Relancer `Lancer-Podcast.cmd`, puis cliquer
sur « Continuer jusqu’au script final ». Voir `README-CORRECTIF.txt`.

Les cas de verrouillage ont été testés par simulation des erreurs Windows et
par lectures/écritures concurrentes. La validation native sur le PC Windows
reste nécessaire. Un refus de permission permanent n’est pas contourné.

## Utilisation sous Windows 10/11 x64

1. Extraire le ZIP dans un dossier personnel, par exemple Documents.
2. Ouvrir **Installer-Windows.cmd** une première fois. Python 3.12 et pypdf sont
   installés dans ce dossier, sans modifier le Python global.
3. Installer et ouvrir [Ollama](https://ollama.com/download/windows), puis lancer
   `ollama pull mistral` dans un terminal pour télécharger le modèle.
4. Ouvrir **Lancer-Podcast.cmd**. L’interface s’ouvre dans le navigateur.
5. Créer un projet, sélectionner les PDF et renseigner le public, la durée et
   deux ou trois intervenants.
6. Dans « Mistral et Ollama », vérifier les modèles installés et choisir leur nom
   exact. L’adresse habituelle est `http://127.0.0.1:11434`.
7. Exécuter une étape à la fois, ou continuer jusqu’au script final.

La première installation et le téléchargement du modèle nécessitent Internet.
Le modèle peut occuper plusieurs Go. Ensuite, le traitement de PDF locaux se
fait sur ce PC, y compris hors connexion. Ollama utilise NVIDIA lorsqu’il peut
le faire ; le programme ne modifie pas le pilote et ne garantit pas la vitesse
sur une carte donnée. Garder les fenêtres Ollama et de lancement ouvertes.

## Les neuf étapes

1. Extraction et découpage de chaque PDF en trois parties équilibrées.
2. Résumé de chaque partie avec définitions, causes, conséquences et pages sources.
3. Compilation des trois résumés en une synthèse par PDF, avec registre des idées.
4. Texte commun par thèmes, avec toutes les idées extraites référencées.
5. Plan pédagogique : question centrale, acquis, nouveautés et transitions.
6. Une phrase par idée importante de chaque chapitre.
7. Explication continue de chaque chapitre, avant la mise en dialogue.
8. Dialogue chapitre par chapitre, avec mémoire des acquis, définitions, exemples,
   questions ouvertes et dernières répliques.
9. Révision des chapitres avec contrôle de continuité et export TXT, MD et JSON.

Le registre des idées reste disponible même si une synthèse narrative est plus
concise. Le plan déclare explicitement les idées laissées hors podcast. La
présence des identifiants dans les réponses aide le contrôle, mais ne prouve pas
la fidélité scientifique : relire les textes et leurs références.

Les PDF scannés doivent être passés en OCR auparavant. Les pages sans texte
extractible sont signalées. La durée finale est estimée à 145 mots/minute et un
écart important à la durée visée est signalé. Aucun texte trop long pour le
contexte n’est tronqué silencieusement : le programme demande d’augmenter le
contexte ou de réduire le projet.

## Reprise et sauvegardes

Les projets sont stockés dans **donnees/projets**. Chaque étape possède un JSON
et un Markdown ; chaque chapitre dialogué enregistre aussi sa mémoire. Un
traitement annulé conserve les étapes terminées et les réponses valides en cache.
« Continuer » reprend à la première étape absente. « Refaire cette étape »
archive ses anciens résultats et ceux qui en dépendent.

Changer la durée conserve les étapes 1 à 4 et reprend au plan. Changer uniquement
les intervenants conserve les étapes 1 à 7. Les anciens résultats sont placés
dans `versions`. Le dossier complet téléchargeable contient les PDF d’origine,
les étapes courantes, les mémoires et les exports ; les anciennes versions sont
conservées sur disque. Sauvegarder le dossier `donnees` pour conserver les projets.

Le serveur écoute uniquement sur `127.0.0.1`. Les PDF sont envoyés au serveur
Ollama local, pas à une API distante. Aucun jeton Hugging Face n’est nécessaire.
Les projets et résultats ne sont pas publiés automatiquement.

## Autres systèmes / développement

Python 3.12 conseillé :

```sh
python -m venv .venv
# Linux/macOS : source .venv/bin/activate
# Windows : .venv\Scripts\activate
python -m pip install -r requirements.txt
python app.py
```

Le port habituel est 8766 ; un autre port libre est choisi si nécessaire.
Options : `--data CHEMIN`, `--port NUMERO`, `--no-browser`.

## Vérification

```sh
python -m unittest discover -s tests -v
```

Les 19 tests utilisent de vrais PDF générés pour l’essai et un fournisseur simulé
pour vérifier les contrats JSON, les neuf étapes et la mémoire sans télécharger
Mistral. Le test navigateur `tests/browser_check.py` nécessite Playwright et un
Chromium installé. Il teste aussi les appels HTTP à un Ollama simulé, les exports,
les archives et l’annulation.

Ces tests ne mesurent pas la qualité des réponses d’un vrai modèle Mistral.
L’installation native Windows et la vitesse NVIDIA restent à vérifier sur le PC
cible. L’application fonctionne ici sous Linux ; aucune exécution Windows ne doit
être déduite de ce résultat.

## Sources

`pdfs.py` extrait et découpe ; `llm.py` appelle Ollama et gère le cache ;
`pipeline.py` contient les neuf traitements et leurs consignes ; `storage.py`
gère les sauvegardes ; `app.py` fournit le serveur et la file de traitements ;
`web/` contient l’interface. Le fichier **SOURCE-COMPLET.md** regroupe les sources
pour faciliter une reprise dans une autre discussion.

Fermer l’application avant de supprimer son dossier pour la désinstaller.
Ne pas déplacer un environnement Python déjà installé : pour changer de dossier,
réextraire le ZIP, réinstaller puis recopier `donnees`.
