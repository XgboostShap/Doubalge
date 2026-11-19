PODCAST PEDAGOGIQUE 0.6.0 — REPRISE ET VERIFICATION DES SOURCES

1. Fermer l application et sa fenetre de lancement.
2. Extraire TOUT le ZIP correctif dans un dossier temporaire.
3. Ouvrir Mettre-a-jour.cmd et choisir le dossier INSTALLE contenant
   Lancer-Podcast.cmd et donnees. Ne pas choisir le dossier du correctif.
4. Relancer depuis le dossier installe et verifier Version 0.6.0.
5. Rouvrir le DERNIER PROJET puis Continuer. Ne pas reimporter les PDF.
6. Si Verifications regroupees apparait : ouvrir la page du PDF, corriger
   l idee et ses citations, ou ecarter l idee avec un motif. Traiter le
   groupe puis Continuer. La correction sert aux etapes suivantes.
7. Relire le dialogue puis essayer un audio court avec les voix existantes.

LES PDF, PROJETS, REFERENCES VOCALES ET UNITES COMPATIBLES SONT CONSERVES.
Les resultats remplaces sont archives. Les refus persistants n empechent
plus d enregistrer les autres passages de l etape. Une etape incomplete
ne produit pas un script final declare valide.

Le mode normal est local. L application refuse les adresses Ollama et
VoiceStudio distantes et les alias Ollama cloud. Un telechargement du
moteur MP3 absent demande une autorisation separee, apres explication.
Docling est facultatif, avec modeles deja en cache ; aucun telechargement
automatique. Il ne garantit pas la restauration des formules.

Si Windows refuse Mettre-a-jour.cmd, ouvrir PowerShell dans le dossier du
correctif puis lancer :
powershell -NoProfile -ExecutionPolicy Bypass -File .\mettre-a-jour.ps1

Cette mise a jour ne remplace ni VoiceStudio ni les profils vocaux existants.
Les validations scientifiques, Windows natif et vos voix reelles restent a
controler sur votre PC. Voir README.md et SOURCE-COMPLET.md.
