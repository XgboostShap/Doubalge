PODCAST PEDAGOGIQUE 0.1.2 — CORRECTIF PAGES ET ACCES WINDOWS

1. Fermer la fenetre de lancement du programme (Lancer-Podcast.cmd).
2. Extraire PodcastPedago-Correctif-0.1.2.zip dans un dossier temporaire.
3. Copier app.py, storage.py et pipeline.py dans le dossier de votre application,
   celui qui contient Lancer-Podcast.cmd. Accepter le remplacement des fichiers.
4. Relancer Lancer-Podcast.cmd puis cliquer sur Continuer jusqu'au script final.

Pas de reinstallation necessaire. Garder le dossier donnees et .venv :
vos PDF, projets, resultats et dependances restent a leur place.

Ce correctif attribue les pages sources depuis le lecteur PDF au lieu de
demander au modele de les produire. Chaque extrait analyse appartient a
une seule page connue. Les trois parties par PDF sont conservees.

Il coordonne aussi les lectures et ecritures de JSON et reessaie les
verrouillages temporaires Windows 5, 32 et 33. Si l'enregistrement echoue
durablement, le fichier precedent est conserve et une erreur est affichee.

Verification : 24 tests automatises, dont numeros de page absents ou faux
dans les reponses simulees du modele, erreurs Windows simulees,
lectures/ecritures concurrentes et reprise du worker apres une erreur.
La validation native sur votre PC Windows reste a confirmer.
