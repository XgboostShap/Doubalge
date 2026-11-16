PODCAST PEDAGOGIQUE 0.5.1 — CORRECTIF AUCUNE IDEE RETENUE

1. Fermer la fenetre de lancement de PodcastPedago.
2. Extraire TOUT le ZIP correctif dans un dossier temporaire.
3. Ouvrir Mettre-a-jour.cmd et choisir le dossier INSTALLE contenant
   Lancer-Podcast.cmd et donnees. Ne pas choisir le dossier du correctif.
4. Relancer depuis le dossier installe et verifier Version 0.5.1.
5. Ouvrir le DERNIER PROJET, puis Reexaminer l’etape 2 si aucune idee
   n’a ete retenue. Attendre la fin et lire le nombre d’idees confirmees.
6. Cliquer sur Continuer jusqu’au script final, puis relire et essayer
   un audio court avec les voix existantes.

LES PDF, LEUR EXTRACTION, LES PROJETS ET LES VOIX SONT CONSERVES.
Les resultats remplaces sont archives. Aucun PDF n’est a reimporter.
Un projet 0.5.0 deja confirme peut continuer normalement.
Pour un ancien controle signale par l’application, utiliser Ameliorer les
resumes existants avant de continuer.

Le modele selectionne maintenant des numeros de passages : le programme
recopie les citations exactes. Les references inconnues et les affirmations
non confirmees restent refusees. Un diagnostic explique un resultat vide,
sans produire trois syntheses vides presentees comme terminees.

Si Windows refuse Mettre-a-jour.cmd, ouvrir PowerShell dans le dossier du
correctif puis lancer :
powershell -NoProfile -ExecutionPolicy Bypass -File .\mettre-a-jour.ps1

Pour lire un dialogue TXT deja corrige : ouvrir VoiceStudio, puis Lire un
dialogue TXT dans l’application, enregistrer le texte et importer les anciens
reglages podcast_interface.py si necessaire. Aucune voix n’est recreee.

Si votre ancien app.py lance Streamlit V7, utiliser le ZIP complet dans un
nouveau dossier ; ce correctif vise PodcastPedago avec ses neuf etapes.
Consulter README.md pour les limites des controles, de Windows et des voix.
