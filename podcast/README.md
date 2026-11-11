# Podcast pédagogique — version 0.1.4

Application locale pour transformer plusieurs PDF en un script de podcast
progressif, en français, avec Mistral via Ollama. Le programme produit le **texte
du dialogue** ; la synthèse audio n’est pas incluse dans cette version.

## Mise à jour 0.1.4 — parties Markdown et mémoire courte

Chaque partie de PDF terminée à l'étape 2 est enregistrée immédiatement dans
`etapes/parties/02-PDF1-P1.md` (et son JSON de reprise). Les synthèses par PDF,
textes par thème, phrases clés, explications, dialogues et révisions sont
également enregistrés par document, thème ou chapitre, avant de passer au suivant.
Les liens **Parties déjà enregistrées en Markdown** donnent accès à ces textes
même si l'étape entière n'est pas encore terminée.

Après un arrêt, **Continuer** reprend les unités manquantes. Les empreintes des
données et paramètres empêchent de reprendre une partie devenue périmée.
**Refaire cette étape** archive les parties et force une nouvelle génération.
Les réponses valides par page restent aussi en cache : une partie de PDF
inachevée ne doit pas faire relire ses pages déjà traitées à paramètres identiques.

Chaque appel Ollama est une nouvelle conversation : aucun dialogue complet
n'est accumulé dans l'historique. Le chapitre suivant reçoit uniquement son
contenu, le sommaire du plan et une fiche de continuité bornée (derniers acquis,
définitions récentes ou pertinentes, exemples, questions et deux dernières
répliques abrégées). La mémoire complète reste dans `memoire/C1.json`, etc.
Les sources et idées du chapitre courant ne sont pas tronquées. La fiche courte
est un aide-mémoire ; elle ne garantit pas à elle seule l'absence de répétitions.
Les poids du modèle peuvent rester chargés dans Ollama pour éviter de les
recharger à chaque chapitre : cela n'ajoute pas un historique de conversation.

L'erreur **prediction aborted, token repeat limit reached** indique une boucle
de génération, pas un manque de contexte. Le programme fait une seule reprise
spécifique, sans réinjecter la réponse avortée, en demandant une réponse concise
avec une pénalité de répétition modérée. Si l'extraction d'une page boucle encore,
le texte est partagé en deux et relu sans perdre de caractères ni changer sa
page source (trois niveaux maximum). Les erreurs réseau, 404, annulations ou
réponses tronquées ne sont pas assimilées à une répétition. Seuls les résultats
complets et validés sont enregistrés. Un échec persistant garde l'erreur exacte
et permet d'essayer un autre modèle déjà installé. Aucun réglage ne garantit
qu'un modèle donné ne bouclera jamais.

Pour mettre à jour : fermer la fenêtre de lancement, extraire le ZIP correctif,
ouvrir **Mettre-a-jour.cmd**, choisir le dossier contenant `Lancer-Podcast.cmd`,
puis vérifier **Version 0.1.4** et cliquer sur **Continuer**. Les PDF, projets,
modèles et dépendances restent conservés.

## Mise à jour 0.1.3 — version visible et remplacement automatique

La version chargée est affichée en haut de l'interface. « Version et dossier du
programme » dans la barre latérale permet d'identifier le dossier réellement
utilisé. Une interface mise à jour connectée à une ancienne instance demande de
fermer et relancer le programme ; un mélange avec un ancien `pipeline.py` est
signalé avant de lancer les traitements.
Un échec conservé depuis une version précédente est identifié comme ancien,
sans effacer son détail ; « Continuer » lance une nouvelle tentative.

Pour une installation existante : fermer la fenêtre de lancement, extraire le
ZIP correctif puis ouvrir **Mettre-a-jour.cmd**. Choisir le dossier contenant
`Lancer-Podcast.cmd`. L'outil vérifie les empreintes, sauvegarde les anciens
fichiers de code dans `mises-a-jour`, remplace les fichiers et rouvre le programme.
Les PDF, projets et `.venv` sont conservés. La version **0.1.3** doit apparaître
à l'écran ; cliquer ensuite sur « Continuer jusqu'au script final ».

L'outil de mise à jour Windows reste à vérifier nativement sur le PC cible.

## Correctif 0.1.2 — références de pages

Le modèle n'a plus à produire lui-même les numéros de page des idées. Pendant
l'extraction, chaque requête porte sur le texte d'une seule page connue ; le
programme rattache ensuite les idées à cette page issue du lecteur PDF. Les trois
parties de chaque document et les neuf étapes restent conservées. La compilation
relie ensuite les pages et les parties. Cette lecture peut demander davantage
d'appels au modèle sur les longs documents.

Les extraits sans idée retenue sont signalés dans le résumé pour vérification.
Une couverture ou une bibliographie n'impose pas d'inventer un point explicatif.

Le correctif actuel est cumulatif et inclut celui des verrouillages Windows.
Voir `README-CORRECTIF.txt` pour la mise à jour automatique.

Les pages indiquent la provenance du texte envoyé au modèle. Elles ne remplacent
pas une vérification de la fidélité de chaque affirmation aux sources.

## Correctif Windows inclus depuis 0.1.1

Cette version corrige les accès concurrents au fichier `tache.json`. Les lectures
et écritures partagent un verrou ; les erreurs temporaires Windows 5, 32 et 33
font l’objet de nouvelles tentatives, pendant quelques secondes. Le fichier
précédent reste en place tant que le remplacement n’a pas réussi. Une erreur
persistante d’enregistrement est affichée sans arrêter le worker.

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

Les tests automatisés utilisent de vrais PDF générés pour l’essai et un fournisseur simulé
pour vérifier les contrats JSON, les neuf étapes, la mémoire courte, les reprises
après répétition et les sauvegardes partielles sans télécharger Mistral. Le test navigateur `tests/browser_check.py` nécessite Playwright et un
Chromium installé. Il teste aussi les appels HTTP à un Ollama simulé, les exports,
les archives et l’annulation.

Les erreurs de répétition et de verrouillage sont reproduites par simulation.
Un essai réel précédent de Mistral a traité les pages 14, 77 et 106 du PDF
utilisateur (147 pages) : 16 idées avec leur provenance issue du PDF. Ce résultat
ne valide pas le podcast intégral des 147 pages. Les documents et résultats
utilisateurs sont privés et exclus des archives distribuées.
Ces tests ne mesurent pas la qualité pédagogique du podcast complet.
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
