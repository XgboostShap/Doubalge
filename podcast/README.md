# Podcast pédagogique — version 0.2.0

Application locale Windows 10/11 pour transformer plusieurs PDF en un **script de podcast en français**, avec Ollama. Les PDF et les résultats restent sur le PC. La génération des voix audio reste une étape ultérieure.

## Mettre à jour une installation existante

1. Fermer la fenêtre de lancement de PodcastPedago.
2. Extraire **tout** le ZIP correctif dans un dossier temporaire.
3. Ouvrir **Mettre-a-jour.cmd**, puis choisir le dossier contenant votre `Lancer-Podcast.cmd`.
4. Relancer l’application et vérifier **Version 0.2.0** en haut de la page.
5. Ouvrir l’ancien projet et cliquer sur **Améliorer les résumés existants**. Attendre la fin du réexamen de l’étape 2.
6. Cliquer sur **Continuer jusqu’au script final** pour reconstruire les étapes 3 à 9.

Ce réexamen est nécessaire : les anciens contrôles pouvaient conserver un bon identifiant associé au mauvais contenu. L’application empêche de reprendre directement l’ancien plan ou dialogue. Elle archive les résultats remplacés ; le texte extrait, les candidats disponibles, les PDF, les projets et les modèles sont conservés. Il n’est pas nécessaire de réinstaller Mistral ni d’augmenter le contexte pour appliquer cette mise à jour.

L’outil de mise à jour vérifie les empreintes des 14 fichiers applicatifs, sauvegarde les fichiers remplacés et tente de les restaurer en cas d’échec. Il ne remplace ni `donnees` ni `.venv`. Si Windows refuse `Mettre-a-jour.cmd`, ouvrir PowerShell dans le dossier du correctif et lancer `powershell -NoProfile -ExecutionPolicy Bypass -File .\mettre-a-jour.ps1` ; choisir ensuite le dossier de l’installation.

## Première installation

1. Extraire `PodcastPedago-Windows.zip`, puis ouvrir `Installer-Windows.cmd` dans le dossier `PodcastPedago`.
2. Installer Ollama depuis <https://ollama.com/download/windows> si nécessaire.
3. Télécharger le modèle une fois : `ollama pull mistral`. S’il est déjà présent, garder son nom exact affiché par `ollama list`, par exemple `mistral:latest`.
4. Ouvrir `Lancer-Podcast.cmd`, créer un projet, ajouter les PDF et vérifier les modèles installés.
5. Choisir public, durée, deux ou trois intervenants et contexte, puis lancer les étapes.

Le serveur est accessible uniquement sur `127.0.0.1:8766`. Garder la fenêtre de lancement ouverte. Après installation et téléchargement du modèle, les PDF locaux peuvent être traités hors connexion. La carte NVIDIA peut accélérer Ollama ; elle n’est pas indispensable au fonctionnement.

## Les neuf étapes

| Étape | Résultat |
| --- | --- |
| 1 | Extraction du texte et découpage de chaque PDF en trois parties, avec pages conservées. Les pages sans texte extractible sont signalées. |
| 2 | Idées confrontées à leurs citations, seconde lecture de leur appui, classement éditorial et résumé extractif de chaque partie. Les passages incertains restent à vérifier. |
| 3 | Compilation extractive des trois parties pour chaque PDF, avec registre intégral des idées retenues. |
| 4 | Texte commun regroupant les passages de tous les PDF par rôle pédagogique, sans nouvelle reformulation des faits. |
| 5 | Fil conducteur neutre, titres et sélection selon le budget de durée : notions, problème, méthode, résultats, applications et limites. Chaque idée hors podcast reste au dossier avec un motif. |
| 6 | Une phrase essentielle par idée sélectionnée, copiée depuis son énoncé source. |
| 7 | Énoncé et explication sources rassemblés, avec raccord entre chapitres. |
| 8 | Questions courtes proposées par le modèle ; réponses insérées depuis les sources, définitions issues du glossaire, mémoire de continuité bornée. |
| 9 | Contrôle de couverture et d’identité des réponses, durée estimée, rapport et exports. |

Chaque résultat terminé est sauvegardé en Markdown et JSON avant la suite. Le dialogue est enregistré par blocs de deux idées au maximum, puis par chapitre. **Continuer** réutilise les blocs terminés après une interruption. Une erreur réseau, une annulation ou un problème d’enregistrement reste un arrêt explicite.

## Ce que corrige la version 0.2.0

Les références sont désormais liées au texte, à l’explication, aux citations et aux pages par une empreinte. Le modèle ne réécrit plus librement le fait aux étapes 3 à 9 : une idée de modulation ne peut pas devenir une idée d’amplification sous le même identifiant. Une modification des sources ou du glossaire impose de reconstruire le plan.

Les contrôles de source distinguent notamment le dispositif cité du dispositif affirmé, les valeurs et unités (`mW` et `MW`), et un résultat expérimental d’une garantie générale. Ils restent des contrôles partiels, complétés par une seconde lecture du modèle. Une citation exacte ne prouve pas à elle seule que toute l’explication est juste.

Le plan ne force plus toutes les idées dans la durée demandée. Il compte les passages sources, questions, définitions et raccords, conserve les exclusions motivées et limite chaque chapitre à cinq idées. La durée finale est calculée à 145 mots par minute, sans compter les noms des intervenants ; un écart important est signalé. L’application ne remplit pas artificiellement un podcast trop court.

À l’étape 8, le modèle propose uniquement les questions. Une question absente ou manifestement mal associée est reprise pour l’idée concernée, puis remplacée si nécessaire par une relance neutre signalée. Les questions identiques récentes sont variées. Le programme insère lui-même chaque réponse avec la bonne source. Le contrôle « toutes les idées affectées à ce chapitre » reste actif, y compris à la révision finale.

La mémoire conserve les idées déjà expliquées et les définitions sources, avec un aperçu limité pour le prochain appel. Les acronymes sont définis au premier emploi à partir du glossaire du document, avec une traduction reconnue lorsqu’elle est disponible. Les appels ne cumulent pas un historique complet de conversation.

## Résultats et relecture

Les exports comprennent `podcast.md`, `podcast.txt` et `podcast.json`. Le dossier du projet contient aussi les neuf étapes, les fragments, les citations, les motifs d’incertitude et les archives des anciens résultats. Le JSON final indique les idées couvertes, les exclusions, les avertissements et la durée estimée.

**Une relecture humaine reste nécessaire avant l’enregistrement.** Les formulations retenues à l’étape 2 peuvent encore comporter une mauvaise traduction ou une interprétation incomplète ; les conserver ensuite empêche une dérive supplémentaire mais ne les rend pas automatiquement exactes. La sélection éditoriale peut omettre un prérequis important. Les figures, équations, tableaux complexes et PDF scannés ne sont pas interprétés visuellement ; cette version n’intègre pas d’OCR. Les contradictions entre PDF ne sont pas arbitrées automatiquement.

## Vérification et sources

Les tests couvrent les associations de contenu, la couverture des idées, les citations, les unités, les acronymes, les réponses manquantes, les reprises, les archives et la migration. Le parcours navigateur est testé avec un fournisseur simulé. Des essais Mistral ciblés utilisent le PDF de test et ses candidats déjà extraits ; ils ne constituent pas une nouvelle extraction intégrale des 147 pages ni une validation scientifique complète. L’interface native de Windows doit encore être vérifiée sur un PC Windows.

Pour les tests : `python -m unittest discover -s tests -q`. Pour construire les ZIP : `python build_release.py`. Le fichier `SOURCE-COMPLET.md` rassemble tous les sources de la version ; les archives de distribution excluent les PDF, projets, modèles, caches et secrets.
