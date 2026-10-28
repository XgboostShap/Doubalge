# OSS — fichiers HTML sans installation

**[Télécharger le lecteur OSS (ZIP, 3,5 Mo)](OSS-lecteur.zip?raw=1)**

1. Extraire le ZIP et ouvrir **OSS.html** dans Chrome ou Edge.
2. Écouter les repères **Voix 1…4**, choisir **Voix que je joue**, puis **Lire / Pause**.
3. Utiliser **Plein écran**. Le film conserve les autres dialogues attribués.

Le mode inverse conserve une voix du film et vous laisse improviser les autres.
La vidéo et le son sont intégrés : le lecteur fonctionne hors connexion après
le téléchargement, sans installation ni microphone. Les repères clignotent
1,5 seconde avant la parole puis restent éclairés pendant ; le plan suivant est
annoncé 0,5 seconde avant la coupe.

**[Télécharger l’éditeur OSS (ZIP, 7 Mo)](OSS-editeur.zip?raw=1)** pour corriger
les paroles et les plans avec le son original et la forme d’onde. Ouvrir
**OSS-editeur.html**, ajuster la timeline, puis télécharger le JSON des corrections
pour le transmettre dans le chat, ou générer une nouvelle version impro en HTML.

Les versions légères utilisent des pistes séparées AAC mono, avec synchronisation
vérifiée dans Chromium. Le lecteur direct est aussi disponible en [OSS.html](OSS.html?raw=1)
et l’éditeur en [OSS-editeur.html](OSS-editeur.html?raw=1) ; enregistrer ces HTML
puis les ouvrir localement, car l’aperçu GitHub n’exécute pas le lecteur.

## Repères à vérifier

Les corrections transmises dans le chat sont intégrées : **35 intervalles de
parole et 30 changements de plan**, dont 7 plans ajoutés. Toutes les répliques
ont une voix attribuée dans ce fichier. Les états de validation sont préservés :
9 intervalles et 7 plans sont validés ; 26 intervalles et 23 plans restent
à vérifier. La diarisation brute et les propositions automatiques restent intactes.

Les quatre repères sont acoustiques et aucune association voix/visage n’est
confirmée : les cartes affichent donc V1…V4.

Le fond séparé reste continu ; les voix inconnues et les chevauchements avec une
voix remplacée sont retirés de la piste de dialogue. Les chevauchements entre
deux voix conservées restent audibles. La séparation est expérimentale : des
restes de voix, des timbres modifiés ou des bruitages atténués peuvent subsister.

Vérifications : 42 tests Python ; essais Chromium des quatre rôles, du mode
inverse, des repères vocaux, de la pause, des recherches, de l’export JSON et du
plein écran. Aucune requête réseau depuis les lecteurs. Les pistes AAC décodées
par le navigateur ont un décalage mesuré nul par rapport aux pistes de référence
sur l’échantillon vérifié. Le lecteur Django a également été revérifié.
