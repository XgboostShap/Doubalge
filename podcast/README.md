# Podcast pédagogique — version 0.1.10

Application locale pour transformer plusieurs PDF en un script de podcast
progressif, en français, avec Mistral via Ollama. Le programme produit le **texte
du dialogue** ; la synthèse audio n’est pas incluse dans cette version.

## Correctif 0.1.10 — plan pédagogique par lots

L’étape 5 ne transmet plus tous les thèmes dans une seule requête. Le fichier
signalé contenait 176 thèmes pour 181 idées ; ses aperçus représentaient environ
66 600 caractères avant les instructions. Augmenter le contexte n’est plus
nécessaire pour cette requête de plan.

Le programme prépare une vue d’ensemble à partir de titres répartis dans le
document, puis traite **tous** les thèmes par lots de six. Il rapproche les
thèmes dans de grands chapitres, choisit leur ordre, puis rédige une fiche par
chapitre. Chaque lot et chaque fiche sont sauvegardés en Markdown et JSON.
Une reprise conserve les fragments du plan déjà terminés.

Seules les métadonnées nécessaires sont envoyées au modèle : titres, aperçus
explicitement abrégés, nombres d’idées et acquis précédents. Les textes complets
de l’étape 4 et les consignes de public sont conservés. Le programme rétablit
les références et contrôle que chaque idée figure exactement une fois dans un
chapitre ou dans la liste motivée des exclusions.

Une proposition manquante ou mal formée produit un plan provisoire signalé à
relire. Les avertissements figurent dans `05.md`, les fragments et le rapport
final. Les pannes Ollama, les annulations et les erreurs disque restent des
arrêts explicites. La limite existante de 20 chapitres de 24 idées est conservée :
les idées qui dépasseraient cette capacité restent dans le dossier et sont
signalées hors podcast. La régression sur les 181 idées fournies n’en exclut
aucune.

Pour mettre à jour : fermer la fenêtre de lancement, extraire tout le ZIP,
ouvrir **Mettre-a-jour.cmd**, choisir le dossier contenant `Lancer-Podcast.cmd`,
vérifier **Version 0.1.10**, puis cliquer sur **Continuer**. L’étape 5 reprend ;
les quatre premières étapes, les PDF et les modèles restent conservés.
Il n’est pas nécessaire de refaire les résumés pour ce correctif.

Validation : plan complet du volume fourni à travers le client HTTP Ollama avec
réponses simulées et contexte de 8 192 tokens ; couverture exacte des références,
reprise des lots et chapitres, aperçus longs, avertissements et neuf étapes dans
Chromium. Les essais Mistral sont ciblés. La qualité pédagogique et scientifique
du plan, la génération complète avec Mistral et l’interface native Windows
restent à vérifier.

## Correctif 0.1.9 — texte commun et contrôle des idées

L’étape 4 ne demande plus au modèle de recopier les identifiants complets des
idées. Elle reçoit un paragraphe par référence courte ; le programme rétablit
les références du PDF dans l’ordre source. Cela corrige notamment le blocage
« Citer chaque idée attendue… PDF1-P2-I109 ». Une formulation manquante ou une
réponse invalide, répétitive ou tronquée laisse l’énoncé et son explication
sources dans le texte, avec un avertissement. Les références étrangères sont
ignorées. La même protection s’applique aux explications de l’étape 7.
L’énoncé précis reste affiché avant l’explication du modèle pour éviter qu’une
simple annonce du sujet remplace l’information essentielle.
Les avertissements restent dans les Markdown et dans `generation_warnings`
du JSON final. La conservation d’une référence ne valide pas le sens du texte.

Les nouveaux contrôles de l’étape 2 (`source-review-v2`) apportent :

- une reprise individuelle des décisions mal formées ou des citations rejetées,
  sans écarter les autres idées du même groupe ;
- le refus des citations constituées uniquement d’un en-tête, de colonnes de
  tableau ou d’une référence bibliographique, ainsi que des descriptions du
  seul plan du PDF ;
- une seconde lecture automatique qui vérifie si les citations appuient le sens,
  la causalité et la portée de l’affirmation ; les avis incertains ou
  contradictoires restent à vérifier et ne deviennent pas des faits acceptés ;
- la conservation des rubriques de tous les blocs résumés et une liste compacte
  des énoncés retenus, transmise à la compilation pour éviter d’omettre les
  notions des derniers blocs.

Un motif de seconde lecture qui recopie l’affirmation reste incertain : il
ne constitue pas une justification indépendante de son appui dans les citations.
Ces contrôles utilisent le même modèle local et restent imparfaits. Une citation
exacte et une seconde lecture automatique ne remplacent pas la vérification
scientifique. Les résumés peuvent être plus longs et l’étape 2 demande davantage
d’appels au modèle. Les erreurs de connexion, les annulations et les erreurs
disque arrêtent toujours le traitement ; elles ne sont pas traitées comme un
simple avis incertain.

Pour mettre à jour : fermer la fenêtre de lancement, extraire tout le ZIP
correctif, ouvrir **Mettre-a-jour.cmd**, choisir le dossier contenant
`Lancer-Podcast.cmd`, puis vérifier **Version 0.1.9**.

- **Continuer** reprend l’étape 4 interrompue avec les résumés déjà enregistrés.
- Pour réexaminer aussi le contenu d’un ancien `02.md`, choisir **Améliorer les
  résumés existants**, puis **Continuer**. Les résultats précédents sont archivés,
  les candidats disponibles et le texte extrait sont réutilisés. Cette relecture
  peut changer les idées retenues et relance les étapes suivantes.

Les PDF, projets et modèles sont conservés. Les tests couvrent la référence
signalée, les références manquantes ou étrangères, la reprise par groupe, les
preuves structurelles rejetées, la récupération individuelle, les avis de seconde
lecture et la conservation des blocs. La validation native Windows, la génération
intégrale des 147 pages et la fidélité scientifique restent à vérifier.

## Correctif 0.1.8 — synthèses, DT et reprise de l’étape 3

Le glossaire du PDF de test définit DT par « Digital twin » (page 27). Avec
cette définition source, le contrôle accepte aussi « digital twins »,
« jumeau numérique » et « double numérique », au singulier et au pluriel.
Ces variantes ne sont pas accordées à un autre sens de DT, par exemple
« Decision tree ». Les citations et les unités conservent leurs contrôles.

Une formulation de synthèse dont l’acronyme reste incertain est isolée dans
**Formulations de synthèse à vérifier**, avec son motif et le texte automatique
non retenu. Les autres rubriques et le registre d’idées sources sont conservés.
Si aucune rubrique n’est exploitable, les énoncés sources servent de résultat
provisoire. Cela ne confirme pas la formulation rejetée ni la fidélité scientifique.

L’étape 3 découpe les résumés longs, compile des blocs bornés puis rassemble
leurs synthèses. Chaque bloc est enregistré en Markdown et JSON avant le suivant.
Le modèle reçoit les résumés et les termes utiles du glossaire ; le registre
détaillé reste conservé séparément. Les appels ne cumulent pas un historique
de conversation. Si un format, une répétition ou une limite de sortie empêche
une compilation, les résumés concernés restent disponibles, avec une mention
**Compilation provisoire à relire**. Une réponse tronquée n’est pas acceptée.
Les pannes Ollama, les annulations et les erreurs disque restent signalées.

Les avertissements figurent dans les Markdown des étapes 2, 3 et 9 et dans le
JSON final sous `synthesis_warnings`. L’étape exacte est précisée dans les
erreurs du modèle qui arrêtent encore le traitement.

Pour mettre à jour depuis 0.1.7 : fermer la fenêtre de lancement, extraire tout
le ZIP correctif, ouvrir **Mettre-a-jour.cmd**, puis choisir le dossier contenant
`Lancer-Podcast.cmd`. Vérifier **Version 0.1.8** et cliquer sur **Continuer**.
Les PDF, les projets et les parties terminées restent conservés. Il n’est pas
nécessaire de réinstaller Mistral ni de changer le contexte 16/32/65 k.

Validation : régression DT, isolement des formulations, réponses incomplètes,
conservation des sources, découpage et reprise par bloc ; parcours Chromium avec
fournisseur simulé. L’essai Mistral sur les synthèses fournies est ciblé : il ne
constitue pas une nouvelle génération complète des 147 pages du PDF ni une
validation de l’interface native Windows.

## Correctif 0.1.7 — références des idées conservées par le programme

Le regroupement thématique (étape 4) et les phrases essentielles (étape 6)
n'exigent plus que le modèle recopie les identifiants complets du PDF. Chaque
requête utilise des repères courts I1, I2… avec un schéma JSON à une clé par
idée. Le programme rétablit ensuite les identifiants originaux et contrôle que
chaque idée source est présente exactement une fois. Les anciennes réponses
en listes, où un identifiant pouvait être oublié ou dupliqué, ne sont pas
réutilisées pour ces nouvelles requêtes.

Si une affectation manque ou est inexploitable, les idées correspondantes sont
conservées dans un **groupe provisoire** marqué « classement à revoir ». Une
référence étrangère n'ajoute aucune idée et ne remplace pas une référence source.
Si une phrase manque, son **énoncé source** est conservé avec un avertissement.
Après une erreur persistante de format ou de répétition dans ces tâches, le
programme applique ces mêmes reprises explicites. Les erreurs réseau, 404,
annulations et sauvegardes disque restent signalées normalement.

Les classements et formulations provisoires sont listés dans les Markdown des
étapes 4 et 6 et dans le rapport de l'étape 9 ; le JSON final contient
`generation_warnings`. Ce mécanisme garantit la conservation des références,
pas la justesse scientifique des idées ni celle de leur reformulation.

Pour mettre à jour : fermer la fenêtre de lancement, extraire le ZIP correctif,
ouvrir **Mettre-a-jour.cmd** et sélectionner le dossier contenant
`Lancer-Podcast.cmd`. Vérifier **Version 0.1.7**, puis cliquer sur **Continuer**.
Le traitement reprend l'étape interrompue, sans refaire les étapes précédentes.
Les projets, PDF et modèles sont conservés. Pour demander une nouvelle proposition
à la place d'un classement provisoire déjà terminé, utiliser **Refaire cette étape**.

Les tests reproduisent la liste de douze identifiants signalée, les références
omises et étrangères, les formats invalides, les reprises et un parcours complet
avec des réponses incomplètes. Le parcours navigateur avec fournisseur simulé
reste également vérifié. Le PDF complet et l'interface native Windows restent
à valider.

## Correctif 0.1.6 — acronymes et traductions françaises

Le contrôle n'impose plus le libellé anglais exact pour les traductions usuelles
reconnues. Par exemple, si le PDF définit AI par « Artificial intelligence »,
« intelligence artificielle (AI) » est autorisé. La traduction est activée par
la définition présente dans le glossaire, jamais par les lettres de l'acronyme
seules : un autre sens de AI ne reçoit pas automatiquement cette traduction.
Les accents, tirets, articles et certaines variantes usuelles sont pris en
compte pour comparer les libellés. Les citations exactes et les unités physiques
restent contrôlées avec leur casse : mW et MW ne sont pas confondus.

Le correctif inclut des traductions courantes en IA et réseaux optiques, sans
prétendre traduire automatiquement tous les acronymes d'un PDF. Un libellé non
reconnu reste à vérifier. « White Space Spectrum » pour WSS et « sélecteur
optique à fibres dopées » pour SOA restent refusés avec le glossaire du test.

Pour mettre à jour : fermer la fenêtre de lancement, extraire le ZIP correctif,
ouvrir **Mettre-a-jour.cmd**, puis choisir le dossier contenant
`Lancer-Podcast.cmd`. Vérifier **Version 0.1.6**, puis cliquer sur **Continuer**
pour reprendre la synthèse bloquée. Les parties déjà terminées sont conservées.
Il n'est pas nécessaire de forcer une nouvelle extraction. Pour réexaminer aussi
d'anciennes exclusions d'une étape 2 déjà terminée, utiliser **Améliorer les
résumés existants**. Le résultat reste une aide à la relecture scientifique.

## Mise à jour 0.1.5 — synthèses structurées et appui aux sources

Pour améliorer un projet existant : fermer le programme, extraire le ZIP
correctif et lancer **Mettre-a-jour.cmd**. Choisir le dossier contenant
`Lancer-Podcast.cmd`. Vérifier **Version 0.1.5**, puis cliquer sur
**Améliorer les résumés existants**. L'ancien résultat et les étapes suivantes
sont archivés ; les candidats de l'étape 2 sont copiés dans `reprises/02.json`.
Ils sont confrontés au PDF pour préparer de nouveaux résumés, sans recommencer
leur extraction lorsqu'ils sont réutilisables. Cette vérification demande quand
même des appels au modèle. Une fois l'étape 2 terminée, **Continuer** reprend à
l'étape 3. Si l'amélioration s'arrête, **Continuer** conserve les sous-parties
valides et reprend l'étape 2. Aucun modèle ni paquet supplémentaire n'est requis.

Le tri repère les sections explicites : couverture et pages liminaires,
remerciements, sommaire, listes de figures/tableaux, glossaire et bibliographie.
Elles restent dans le PDF et sont signalées dans les rapports. Le résumé/abstract
scientifique et le corps du texte sont analysés. Une section non reconnue est
conservée pour analyse ; le classement est indicatif, à vérifier sur un document
dont la présentation est inhabituelle. Les acronymes sont lus dans le glossaire
du PDF et transmis aux contrôles concernés ; aucune définition propre au PDF
de test n'est inscrite dans le code. Une expansion entre parenthèses ou une
définition explicite qui ne reprend pas un libellé connu est refusée. Par
prudence, une traduction française légitime mais absente du lexique peut donc
être signalée : employer l'acronyme seul ou son libellé source exact. Le lexique
original et ses pages sont affichés à la fin de l'étape 2 pour faciliter la
relecture. Ce garde-fou ne reconnaît pas toutes les erreurs terminologiques.

Chaque idée candidate est relue avec son passage source. Le modèle doit la
conserver, proposer une correction ou l'écarter avec un motif. Pour une idée
retenue, il doit fournir une explication et une citation exacte présente dans
le texte envoyé. Le programme contrôle cette présence et la couverture des
identifiants. Les explications réduites à une référence ou à quelques mots sont
refusées. Le format JSON est aussi imposé à la génération pour les tâches de
contrôle et de synthèse. Les corrections et exclusions sont consultables dans
les Markdown et JSON. Seuls les doublons strictement identiques sont fusionnés
dans le registre ; leurs pages et citations sont regroupées.

Les énoncés dont le sujet est indéterminé (« ces techniques », « cette approche »…)
sont signalés à vérifier, car une correction peut conserver une attribution
causale erronée. Un contrôle de structure ou de citation qui échoue après sa
reprise devient aussi une incertitude explicite, sans transformer sa réponse
invalide en fait accepté. Les erreurs réseau, 404, annulations et écritures disque
restent des erreurs de traitement. Les idées incertaines sont écartées du script
provisoire, conservées avec leur motif dans l'étape 2, comptées dans l'interface
et reprises dans le rapport JSON final. Un modèle plus adapté peut être choisi
pour les réexaminer ; le changement de paramètres conserve les candidats déjà
extraits avant l'archivage. Aucun contrôle ne garantit que toutes les ambiguïtés
ou erreurs sémantiques sont repérées.

**Ce contrôle n'est pas une preuve automatique de vérité scientifique.** Une
citation correcte peut accompagner une interprétation erronée : vérifier les
relations causales, les chiffres et les corrections proposées avec le PDF.
Le schéma impose une décision unique par identifiant. La casse des citations
et des doublons est conservée, notamment pour distinguer mW et MW.

Les résumés de pages ne sont plus simplement collés. Une synthèse est construite
pour chaque partie sous cinq rubriques : problème posé, notions essentielles,
méthodes, résultats, limites. Elle est en français, sans longueur minimale et
avec un plafond de 950 mots (consigne : 900). Une rubrique non documentée reste
vide. Les longs registres sont traités par petits lots puis regroupés, avec
sauvegarde des sous-synthèses en Markdown. Toutes les idées retenues restent dans
le registre détaillé, même si la synthèse est plus courte. L'étape 3 reçoit les
trois synthèses, sans recevoir à nouveau le registre complet.

Le classement thématique est également réalisé par lots d'au plus 12 idées.
Le plan utilise des groupes et leurs aperçus abrégés, puis le logiciel rétablit
les identifiants d'idées. Chaque groupe est affecté ou explicitement exclu, avec
un motif conservé pour chacune de ses idées. Un chapitre est limité à 24 idées ;
les longs documents/podcasts peuvent demander plusieurs projets. Les sources
complètes restent dans le dossier ; les aperçus du plan ne remplacent pas le
registre. Les explications et dialogues reçoivent les idées de leur chapitre,
sans charger à nouveau toutes les citations archivées.

La génération intégrale de la thèse de 147 pages n'est pas validée. Les tests
automatisés contrôlent le tri, les citations, la couverture d'un registre de
250 idées, la reprise, l'amélioration d'un ancien projet et le parcours navigateur.
La vitesse et la validation native Windows restent à vérifier sur le PC cible.

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
`pipeline.py` contient les neuf traitements et leurs consignes ; `quality.py`
gère le tri, le lexique et les contrôles de synthèse ; `storage.py`
gère les sauvegardes ; `app.py` fournit le serveur et la file de traitements ;
`web/` contient l’interface. Le fichier **SOURCE-COMPLET.md** regroupe les sources
pour faciliter une reprise dans une autre discussion.

Fermer l’application avant de supprimer son dossier pour la désinstaller.
Ne pas déplacer un environnement Python déjà installé : pour changer de dossier,
réextraire le ZIP, réinstaller puis recopier `donnees`.
