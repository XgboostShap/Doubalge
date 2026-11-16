PODCAST PEDAGOGIQUE 0.5.3 — CORRECTIF DEVELOPPEMENTS DE SIGLES

1. Fermer la fenetre de lancement de PodcastPedago.
2. Extraire TOUT le ZIP correctif dans un dossier temporaire.
3. Ouvrir Mettre-a-jour.cmd et choisir le dossier INSTALLE contenant
   Lancer-Podcast.cmd et donnees. Ne pas choisir le dossier du correctif.
4. Relancer depuis le dossier installe et verifier Version 0.5.3.
5. Ouvrir le DERNIER PROJET puis Continuer jusqu’au script final.
   Les etapes 1 et 2 et les passages deja termines sont reutilises.
   Ne pas reimporter le PDF ni reexaminer l’etape 2 pour l’erreur
   de redaction « Developpement non confirme de PM » ou « 5 a 85 mots ».
6. Relire le dialogue puis essayer un audio court avec les voix existantes.

LES PDF, LEUR EXTRACTION, LES PROJETS ET LES VOIX SONT CONSERVES.
Les resultats remplaces sont archives. Aucun PDF n’est a reimporter.
Si aucune idee n’est retenue a l’etape 2, utiliser Reexaminer l’etape 2.
Pour un ancien controle signale par l’application, utiliser Ameliorer les
resumes existants avant de continuer.

Quand PM signifie Predictive Maintenance dans le PDF, la redaction propose
maintenance predictive. Maintenance previsionnelle et entretien predictif
sont aussi reconnus. Un autre sens de PM ne recoit pas ces traductions.
Une correction ciblee recoit le libelle refuse et les definitions autorisees.
Le resultat est relu contre les citations ; les faits et unites restent controles.

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
