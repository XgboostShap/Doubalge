PODCAST PEDAGOGIQUE 0.5.2 — CORRECTIF REDACTION TROP LONGUE

1. Fermer la fenetre de lancement de PodcastPedago.
2. Extraire TOUT le ZIP correctif dans un dossier temporaire.
3. Ouvrir Mettre-a-jour.cmd et choisir le dossier INSTALLE contenant
   Lancer-Podcast.cmd et donnees. Ne pas choisir le dossier du correctif.
4. Relancer depuis le dossier installe et verifier Version 0.5.2.
5. Ouvrir le DERNIER PROJET puis Continuer jusqu’au script final.
   Les etapes 1 et 2 et les passages deja termines sont reutilises.
   Ne pas reimporter le PDF ni reexaminer l’etape 2 pour l’erreur
   de redaction « 5 a 85 mots » de l’etape 3.
6. Relire le dialogue puis essayer un audio court avec les voix existantes.

LES PDF, LEUR EXTRACTION, LES PROJETS ET LES VOIX SONT CONSERVES.
Les resultats remplaces sont archives. Aucun PDF n’est a reimporter.
Si aucune idee n’est retenue a l’etape 2, utiliser Reexaminer l’etape 2.
Pour un ancien controle signale par l’application, utiliser Ameliorer les
resumes existants avant de continuer.

La redaction vise un texte plus court. Si le brouillon est trop long,
une demande ciblee le reformule avec son compte de mots et ses sources.
Un depassement modere peut rester avec une note editoriale apres relecture
automatique favorable. Aucun texte n’est coupe pour atteindre 85 mots.
Les faits, nombres, unites et citations sont toujours controles.

Si Windows refuse Mettre-a-jour.cmd, ouvrir PowerShell dans le dossier du
correctif puis lancer :
powershell -NoProfile -ExecutionPolicy Bypass -File .\mettre-a-jour.ps1

Pour lire un dialogue TXT deja corrige : ouvrir VoiceStudio, puis Lire un
dialogue TXT dans l’application, enregistrer le texte et importer les anciens
reglages podcast_interface.py si necessaire. Aucune voix n’est recreee.

Si votre ancien app.py lance Streamlit V7, utiliser le ZIP complet dans un
nouveau dossier ; ce correctif vise PodcastPedago avec ses neuf etapes.
Consulter README.md pour les limites des controles, de Windows et des voix.
