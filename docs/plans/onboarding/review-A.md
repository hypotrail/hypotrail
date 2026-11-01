# Revue A : proposition v1 « de mon dataset à une étude lancée » (UX et produit)

Revue indépendante du 1er novembre 2026, faite sur `main` en lecture seule. **[C]** signale ce qui est constaté dans le dépôt, **[J]** un jugement.

## 1. Forces

- **[C]** Le diagnostic est exact. `launch.py` et `agent_files.py` remontent à la racine par `parents[2]` (le `pyproject.toml` le reconnaît : une roue non éditable ne fonctionne pas). Le script d'atelier est câblé sur Auto MPG. Aucune commande ne produit de brouillon de cas, et la fraction du test final n'est pas réglable.
- **[J]** La frontière « préparer, sceller, étudier » est le bon modèle mental, cohérent avec l'expérience E1.
- **[J]** `doctor`, `hypotrail new`, modèle Codespaces : peu coûteux, utiles.

## 2. Faiblesses

1. **La phase A en demande trop avant le scellement. [C]** La disponibilité d'une variable est déjà une *décision de l'étude*, qui peut différer du cas (CASE-CONTRACT, §Variables). La fiche du PO est déjà importée puis adoptée *dans* l'étude (`brief import`, `brief set`). **[J]** Exiger zéro `TODO` sur plus de 230 lignes de `case.yaml`, c'est une quarantaine de questions avant de commencer : l'utilisateur décrochera là. Or seuls quelques points déterminent le scellement : la cible, l'unité de ligne et les doublons, l'ordre temporel, les entités et l'exposition préalable. **[C]** Contrepartie : le cas est haché, et toute modification après `init` déclenche `sources_changed`, qui bloque l'étude. D'où un noyau figé et une couche descriptive modifiable, comme `case.l10n.yaml`.
2. **La clé `holdout` double un mécanisme existant. [C]** Le profil `review-v1` scelle déjà un test final futur ou à groupes disjoints, à partir de `analysis_contract.timing` et `dependencies` (`partition._assign_review`). **[J]** Demander `method: grouped` est trop technique. Il vaut mieux poser des questions de scénario et laisser le moteur *déduire* la méthode. Supprimer `seed` : il permet de retirer au sort jusqu'à un découpage favorable.
3. **Les vrais jeux de données bloqueront. [C]** Le contrat refuse aujourd'hui une colonne de temps de type date (`order.by` doit être numérique ou `line`), une cible manquante, des doublons sans `policy: group`, tout format autre que CSV et toute tâche autre que binaire ou régression. Hotel a demandé un `build_case.py` de 981 lignes. **[J]** `case new` doit proposer une transformation journalisée (tri, horloge numérique dérivée d'une date) ou un refus qui explique quoi faire.
4. **Le profilage regarde des lignes qui seront scellées. [C]** L'ADR 0006 exige la mise de côté avant tout regard, inspection structurelle comprise. **[J]** Le risque est faible, puisque ce ne sont que des comptes, mais il faut le déclarer. Surtout, celui qui arrive avec *son* fichier l'a presque toujours déjà ouvert : l'exposition préalable doit être la première question posée.
5. **Trop de commandes et de concepts [J]** avant la première question de l'étude.
6. **[C]** `hypotrail-runtime` est une dépendance par chemin : une publication sur PyPI suppose de publier deux paquets, et l'installation par `git+…#subdirectory=` reste à vérifier. Le hook n'existe que pour Copilot et ne fait que coopérer (clarification J0).

## 3. Rôle de l'agent

| Option | Pour | Contre |
|---|---|---|
| **A. Agent ou skill de préparation distinct** | Instructions ciblées | Deux agents dans le sélecteur ; contexte perdu au passage ; deux jeux d'instructions et deux hooks à maintenir |
| **B. Mode du même agent** (`preparing`, puis `seal`) | Un seul agent, un dossier, un rapport ; continuité avec `brief import` | Changement du moteur ; budget d'instructions presque épuisé (3 977 mots sur 4 000 [C]), d'où un skill chargé à la demande |
| **C. Assistant CLI interactif** | Déterministe, testable, utilisable sans Copilot | Ne lit pas la fiche ; terminal intimidant pour un junior |
| **D. Formulaire dans le panneau** | Visuel | Écriture hors de la liste blanche W4, W5, W7, W8, donc ADR 0002 et 0004 à amender [C] ; panneau optionnel |

**Recommandation [J] : B adossé à C.** La commande déterministe `hypotrail new … --data` porte la frontière. Elle pose les six questions de scellement, dans le terminal, par options ou par un fichier de réponses. L'agent d'étude, unique, pilote les mêmes commandes depuis le chat : il propose des réponses sourcées, et l'utilisateur tranche avec ses propres mots. Descriptions et disponibilités viennent **après** le scellement, comme décisions de l'étude.

## 4. Le `case.yaml`

**[J]** Il est trop technique pour un junior (triplets `value/status/source`, `row_key`, empreintes) et l'utilisateur ne devrait jamais avoir à l'éditer. Ce qu'il doit trancher lui-même :

- la cible, et le libellé positif ;
- ce que représente une ligne ;
- le moment de la prédiction, et si l'usage vise le futur ;
- les entités qui reviennent ;
- s'il a déjà exploré les données ;
- l'acceptation du test final, présenté en mots et en comptes (« les 20 % les plus récents, 1 840 lignes »).

Le reste revient à la machine et à l'agent, avec ses sources. Le cas se lit comme une fiche du rapport.

## 5. Windows natif, au premier rang

**[C] Ce qui bloque aujourd'hui :**

- le moteur refuse Windows natif (`study/lock.py:44`, `platform_unsupported`), et `fcntl` est aussi utilisé ailleurs (`pilot.py`, `classical.py`, `mapie_uncertainty.py`) ;
- les scripts sont tous en bash ;
- l'interpréteur est cherché dans `.venv/bin/python` (sous Windows, il est dans `.venv\Scripts\python.exe`) ;
- la commande de secours passe par `env PYTHONPATH=…`, qui n'existe pas sous Windows ;
- le hook reconnaît les commandes par une regex POSIX, refuse `$` et `&` et suppose des chemins POSIX.

**[J] Les risques en entreprise :**

- les guillemets de `--user-words` sous PowerShell, avec les apostrophes du français ;
- les espaces dans les chemins, OneDrive, la limite de 260 caractères ;
- un antivirus qui verrouille le fichier au moment de `os.replace` ;
- la politique d'exécution, qui bloque l'installateur d'uv ;
- un proxy qui inspecte le TLS ;
- un VS Code installé pour tous les utilisateurs, ou en version portable, sans `code` dans le PATH.

**[J] Ce qu'il faut changer :**

1. Un verrou multiplateforme (`msvcrt` ou `filelock`) et une CI sur `windows-latest`.
2. Aucun script shell dans le parcours : `new`, `setup vscode` et `doctor` passent tous par la CLI Python, et le hook devient `hypotrail hook`, qui analyse des argv.
3. `pathlib` partout, un interpréteur résolu selon l'OS, des argv seulement dans `agent.json`.
4. Des textes libres passés par fichier (`--user-words-file`), jamais par l'échappement d'un shell.
5. Un `doctor` qui vérifie la politique d'exécution, la longueur des chemins, OneDrive, `code`, le proxy et les certificats, et affiche la commande PowerShell correctrice.
6. Une documentation PowerShell d'abord (`winget install astral-sh.uv`).
7. Comme critère de sortie, une acceptation chronométrée sur un poste d'entreprise sans droits d'administrateur.

## 6. Panneau sans Node

**[C]** Node ne sert qu'à `vsce package`. Le panneau est du JavaScript sans compilation ni dépendance : son VSIX peut être produit une fois pour toutes en CI.

| Option | Pour | Contre |
|---|---|---|
| VSIX en release GitHub, installé à la main | Pas de Node | Quatre clics ; téléchargement d'un `.vsix` parfois filtré par le proxy |
| `hypotrail setup vscode`, avec le VSIX embarqué dans le paquet Python | Une commande, hors ligne, passe le même proxy qu'uv ; version liée au moteur ; repli code-server déjà écrit pour Codespaces et WSL | Il faut trouver `code` (sous Windows : `%LOCALAPPDATA%\Programs\Microsoft VS Code\bin\code.cmd`) ; une liste blanche d'extensions le bloque aussi |
| Marketplace ou Open VSX | Un clic, mises à jour automatiques | Éditeur public à créer et à vérifier ; une mise à jour peut dépasser la version du moteur ; un éditeur inconnu est souvent bloqué en entreprise |

**[J]** Pour un participant, y compris sous Windows, le plus simple est **`hypotrail setup vscode`**, lancé automatiquement par `hypotrail new` quand `code` est trouvé, avec la release comme secours. Le Marketplace viendra plus tard, une fois le panneau sorti du drapeau : avec un éditeur vérifié, c'est la seule voie qu'une DSI acceptera d'ajouter à sa liste blanche.

## 7. Manques et superflu

**Manques.** Les dates comme horloge. L'arrivée d'un nouvel extrait de données. Un argument de confidentialité : seuls des comptes parviennent à l'agent. Les formats Excel et Parquet, à convertir avec journal.

**Superflu.** Le `seed` réglable, `case set` présenté comme une interface, et un hook présenté comme une protection.

## 8. Parcours cible révisé

1. **Installer.** Soit Codespaces (modèle `study-template`), soit `uv tool install hypotrail` puis `hypotrail doctor`, sous Windows, macOS ou Linux.
2. **Créer l'étude.** `hypotrail new churn --data churn.csv [--brief fiche.pdf] --open` copie les données, calcule l'empreinte et un profil en comptes, puis installe l'agent, le panneau et le hook.
3. **Préparer dans le chat.** L'utilisateur écrit « Prépare l'étude ». L'agent lit la fiche et pose les six questions une par une ; la CLI enregistre les réponses avec les mots de l'utilisateur.
4. **Valider le test final.** L'aperçu est donné en mots et en comptes ; l'utilisateur adopte ou corrige, puis lance `seal`. Le chapitre 0 du rapport explique comment le test a été mis de côté.
5. **Mener l'étude.** Elle se déroule comme aujourd'hui ; descriptions et disponibilités deviennent des décisions de l'étude.

## 9. Ordre de livraison

1. **Lot 0, portabilité :** ressources de paquet, verrou, interpréteur et argv, CI Windows, publication de `hypotrail-runtime`.
2. **Lot 1 :** `hypotrail new --data`, qui intègre `doctor`, `setup vscode` (avec le VSIX embarqué) et le hook en Python, plus le modèle Codespaces.
3. **Lot 2 :** les six questions, traduites en `order`, `duplicates` et `analysis_contract`, l'aperçu, la commande `seal` et le chapitre 0.
4. **Lot 3 :** horloge dérivée d'une date, conversions de format.
5. **Lot 4 :** séparation entre noyau scellé et couche descriptive.
6. **Validation :** un cas inédit, préparé par une personne extérieure sous Windows natif et sous Codespaces, chronométré.
