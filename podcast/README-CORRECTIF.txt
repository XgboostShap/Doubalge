PODCAST PEDAGOGIQUE 0.1.1 — CORRECTIF ACCES REFUSE WINDOWS

1. Fermer la fenetre de lancement du programme (Lancer-Podcast.cmd).
2. Extraire PodcastPedago-Correctif-Windows.zip dans un dossier temporaire.
3. Copier app.py et storage.py dans le dossier de votre application, celui
   qui contient Lancer-Podcast.cmd. Accepter le remplacement des deux fichiers.
4. Relancer Lancer-Podcast.cmd puis cliquer sur Continuer jusqu'au script final.

Pas de reinstallation necessaire. Garder le dossier donnees et .venv :
vos PDF, projets, resultats et dependances restent a leur place.

Ce correctif coordonne les lectures et ecritures de JSON et reessaie les
verrouillages temporaires Windows 5, 32 et 33. Si l'enregistrement echoue
durablement, le fichier precedent est conserve et une erreur est affichee.

Verification : 19 tests automatises, dont erreurs Windows simulees,
lectures/ecritures concurrentes et reprise du worker apres une erreur.
La validation native sur votre PC Windows reste a confirmer.
