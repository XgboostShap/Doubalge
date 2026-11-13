PODCAST PEDAGOGIQUE 0.4.0 — RETROUVER LES VOIX DE L’ANCIENNE VERSION

1. Fermer la fenetre de lancement de PodcastPedago.
2. Extraire tout le ZIP correctif dans un dossier temporaire.
3. Ouvrir Mettre-a-jour.cmd et choisir le dossier contenant Lancer-Podcast.cmd.
4. Verifier Version 0.4.0 en haut de l’application.

Si votre ancien app.py appelle podcast_interface.run() (Streamlit V7),
utiliser le ZIP complet dans un nouveau dossier. Ce correctif concerne
l’application PodcastPedago avec ses neuf etapes et son interface locale.

POUR LIRE LE DIALOGUE CORRIGE AVEC ANNESO ET SOPHIE
- Ouvrir VoiceStudio sur le PC.
- Dans PodcastPedago, cliquer sur Lire un dialogue TXT.
- Charger dialogue_revise_20min.txt, puis Utiliser ce texte pour l’audio.
- Ouvrir Recuperer mes anciens reglages VoiceStudio.
- Choisir l’ancien podcast_interface.py, puis Importer mes reglages.
- Si propose, cliquer une fois sur Preparer le MP3 (telechargement initial).
- Ecouter chaque voix, puis generer un essai d’environ 3 minutes.
- Apres verification, choisir Podcast complet et generer le MP3.
- Utiliser le lecteur ou Telecharger le MP3 ; le rapport CSV est disponible.

Les references sont recuperees dans votre fichier, sans executer son code.
Aucune nouvelle voix n’est creee. Les essais ont des fichiers distincts.
Les repliques terminees sont conservees pour une reprise apres interruption.

Pour un script PDF deja genere en 0.3.0, inutile de refaire les PDF.
Pour un projet plus ancien, suivre Ameliorer les resumes existants, puis Continuer.
Changer les noms des intervenants via l’import ne refait que les etapes 8 et 9.
Les PDF, projets, modeles et anciens reglages restent dans votre installation.

Si Windows refuse Mettre-a-jour.cmd, ouvrir PowerShell dans le dossier du
correctif et lancer :
powershell -NoProfile -ExecutionPolicy Bypass -File .\mettre-a-jour.ps1
Choisir le dossier de votre installation, pas celui du correctif.

Le texte fourni pour lecture n’est pas automatiquement valide scientifiquement.
Le connecteur est teste avec une API simulee et un vrai encodage MP3.
Les voix reelles et Windows natif restent a essayer sur votre PC.
Voir README.md pour les details et les limites des controles audio.
