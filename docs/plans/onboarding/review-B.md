# Revue B : rigueur méthodologique et faisabilité (proposition v1)

Dépôt `main` @ fabab9c. Essais faits dans `tmpB/` ; aucun fichier du dépôt n'a été modifié.

## 1. Constats vérifiés

1. **[Constaté] Le diagnostic d'empaquetage de la v1 est en partie faux.** La wheel construite par `uv build` s'installe avec `uv tool install` (657 Mo, avec `--find-links` pour le runtime). Hors du checkout, `init`, `render`, `data` et `marimo export` du notebook généré fonctionnent sur un cas synthétique. Les gabarits d'agent sont déjà dans le paquet (`agent_files.py:55,60`). `launch.py:48` ne lit pas les notebooks : il cherche un `.venv` et se rabat sur `sys.executable`. Ce qui casse réellement :
   - `hypotrail-runtime` est une dépendance de chemin (`pyproject.toml:23,44`) et n'est pas sur PyPI (404, comme `hypotrail`). Une installation par pip/pipx ou PyPI échoue, et ces deux noms peuvent être squattés.
   - En wheel, `agent.json` reçoit `env PYTHONPATH=<site-packages> python -m mlkit.study.cli` (`agent_files.py:231-240`). Cette commande ne marche pas sous Windows et ne correspond pas au motif du hook (`pretool.py:56-58`).
   - `understanding/snapshot.py:49` lit `parents[3]/uv.lock`, absent en wheel : le verrou de dépendances disparaît du snapshot sans signal.
2. **[Constaté] Le holdout temporel ou groupé existe déjà** dans le profil `review-v1` (`partition.py:341-452`), via `analysis_contract.timing` et `dependencies.kind`. Essai sur une copie du cas MPG (`kind: temporal`, horloge `model_year`) : test final pour `model_year >= 80`, 89 lignes, fraction effective 0,224 à cause des ex-aequo. La clé `holdout` de la v1 ferait doublon.
3. **[Constaté]** « A case never records a human decision » (CASE-CONTRACT l.12), et l'ADR 0006 fait du holdout un défaut de protocole. Or la v1 dit à la fois « l'humain tranche le schéma » et « clé du cas » : c'est contradictoire.
4. **[Constaté]** Les horloges et `order.by` doivent être numériques. Une colonne de temps de type date et une cible manquante sont `unsupported_capability`. Une strate d'une seule ligne peut laisser une classe absente du test final.
5. **[Constaté]** L'ADR 0006 veut une mise à l'écart avant « the first look, including the structural inspection ». `init` n'inspecte que les lignes de développement, alors que `case new` inspecterait toutes les lignes.
6. **[Constaté]** `init` crée un lien `data/` vers les données du cas (`launch.py`, `install_readme`). Le hook refuse seulement les commandes qui contiennent le nom du fichier (`pretool.py:64-67`) et se dit lui-même « not a security boundary ». Un script ou un `glob` le contourne.
7. **[Constaté]** Dans E1, le bras B n'a fait aucun calcul hors du CLI (l.96) ; le bras A a exploré en cachette (l.179). L'argument plaide pour des commandes déterministes, pas pour un hook.

## 2. Problèmes classés

- **Bloquant P1** : une clé `holdout` dans le cas contredit le contrat et double `analysis_contract`. Cela ferait deux chemins de partition à garantir.
- **Bloquant P2** : des `holdout --preview` répétés qui affichent les proportions par strate permettent de **choisir le holdout qui arrange**.
- **Bloquant P3** : le hook n'interdit rien. De plus, `cp ~/churn.csv .` place le fichier brut dans l'espace de travail, donc dans l'index du chat (`@workspace`) sans aucun appel d'outil.
- **Majeur P4** : rien n'est prévu pour les dates, la cible manquante, les CSV multilignes (la clé `L<ligne>` suppose une ligne physique par enregistrement) ni les petits jeux.
- **Majeur P5** : le runtime fait échouer l'installation par git ou PyPI, et `agent.json` n'est pas portable.
- **Majeur P6** : Windows natif est refusé (§6) et l'empaquetage du panneau exige Node (§7).

## 3. Corrections

- **[Jugement] Pas de clé `holdout`.** Le cas déclare des **faits** avec leur statut : usage, horloges, groupes. Le moteur **déduit** la méthode comme le fait `review-v1`. L'humain répond à des questions factuelles (« un client revient-il ? », « quand l'issue est-elle connue ? »), jamais à « quelle méthode voulez-vous ? ». La fraction et la graine restent des défauts de protocole. Une éventuelle dérogation bornée (`init --final-fraction`) serait journalisée comme paramètre de protocole, ce qui demande un amendement de l'ADR 0006.
- **Remplacer `holdout --preview` par `case check --feasibility`.** La commande donne des comptes sans la cible (lignes, période, ex-aequo, groupes) et un simple réussi/échoué sur le minimum d'événements, sans afficher les proportions.
- **Les données restent hors de l'espace de travail du chat** : `cases/<id>/data/` avec `files.exclude`/`search.exclude`. Les nouvelles études n'ont plus de lien `data/`.
- **Tracer l'inspection** : `prior_exposure: {value: "inspection structurelle univariée de toutes les lignes avant scellement", status: observed}`, reprise dans le rapport.
- **Si l'utilisateur a déjà exploré** : une exploration partielle connue va dans `prior_exposed_rows`. Si tout le fichier a été exploré avec la cible, `permitted_claims` exclut la preuve indépendante et le rapport le dit. Mieux encore : attendre des données postérieures.

## 4. Règles de holdout recommandées

Déduction, dans l'ordre :
1. `future_prediction` avec deux horloges documentées → temporel, avec purge des labels tardifs.
2. Groupes répétés → `grouped`, ou `grouped_temporal` s'il y a aussi une horloge.
3. Dépendance temporelle supposée → temporel.
4. Sinon → stratifié sur la cible ou sur ses quantiles.
5. `unknown` → stratifié, avec des affirmations plafonnées.

Garde-fous :
- fraction de 0,2 ; la fraction effective (ex-aequo) est rapportée et refusée hors de [0,1 ; 0,35] ;
- au moins 100 lignes et au moins 30 événements minoritaires dans le test (seuils à calibrer), sinon refus motivé, sans repli silencieux ;
- dates : pas de conversion implicite. Soit le moteur accepte une horloge `date` avec un format explicite, soit on suit le modèle Hotel (copie triée, `order: line`, statut `observed`, vérification, sha et provenance) ;
- cible manquante : copie dérivée tracée, jamais d'exclusion silencieuse ;
- doublons : `duplicates: group`.

## 5. `case new` : quelles inférences

- **Fiables [Jugement]** : sha256, lignes physiques, en-tête, séparateur (nombre de champs constant), UTF-8 strict, manquants, cardinalité, doublons exacts, détection des champs multilignes (refus).
- **Dangereuses, à proposer seulement en `unknown`** :
  - types : codes postaux, zéros de tête, codes entiers catégoriels (`origin` de MPG), virgule décimale ;
  - sentinelles : à ne jamais mettre dans `na_values`, qui change le parsing ;
  - clés : un identifiant unique peut porter le temps ;
  - dates : ambiguïté jour/mois.
- **Jamais inférés** : groupes, disponibilité, cible.
- **Format** : `case.draft.yaml` avec une liste `todo:`. `case.yaml` n'est écrit qu'après un `case check` réussi, parce que le chargeur refuse les clés inconnues.
- **Affichage** : agrégats seulement. Pour la cible, les labels et le nombre de manquants.

## 6. Windows natif

- **[Constaté]** `require_posix()` (`lock.py:42`) bloque `init` (`commands.py:2309`) et `store.create` (`store.py:222`) ; il vient de `fcntl.flock` (verrou d'écriture et baux d'exécution).
- **Verrous** : `msvcrt.locking` ou `portalocker`. Ces verrous sont **obligatoires** sur leur plage, or `_read_holder` et `read_lease` lisent les fichiers verrouillés (`lock.py:109,227,236`). Il faut verrouiller un octet hors du contenu et revérifier la détection des baux orphelins.
- **`os.replace`** échoue si un autre processus garde le fichier ouvert (panneau, Marimo, antivirus) : il faut des réessais bornés (`store.py:85`, `render_notebook.py:375`).
- **Encodage** : `ensure_ascii=False` (`cli.py:480`) vers un tube produit du cp1252, donc du mojibake côté Node. Il faut `sys.stdout.reconfigure(encoding='utf-8')` et `encoding=` partout (`lock.py:109`).
- **Commandes** : un argv vers `hypotrail.exe` plutôt que `env …`. L'affichage doit utiliser `list2cmdline` ou une forme PowerShell, pas `shlex.join` (`launch.py:222`, `agent_files.py:240`). Le panneau lance par `execFile` sans shell (`cli.js:212`), ce qui marche avec un `.exe` mais pas avec `env` ni avec un `.cmd`.
- **Hook** : livré dans le paquet (`hypotrail hook pretool`), avec un motif déduit de `agent.json`.
- **Scripts bash** : à remplacer par `hypotrail new` et `hypotrail setup`.
- **Lien `data/`** : à supprimer, ce qui règle aussi la question du mode développeur.
- **Test** : il n'y a pas de CI aujourd'hui. Il faut une matrice GitHub Actions `ubuntu`/`windows`/`macos-latest` avec uv et la suite `framework/tests/study`, plus deux tests de concurrence (deux processus qui se disputent le verrou ; un `os.replace` pendant qu'un lecteur garde le fichier ouvert), puis un essai manuel VS Code et Copilot.
- **Effort [Jugement]** : 6 à 10 jours. Risque principal : une régression silencieuse des baux, d'où les tests avant de lever `require_posix`.

## 7. Panneau sans Node

- **[Constaté]** J'ai construit un VSIX en Python pur (`tmpB/mkvsix.py`, avec `zipfile`). Il a les mêmes 105 entrées que celui de vsce 3.9.2, un `[Content_Types].xml` identique et un `extension/*` identique octet pour octet. L'installation par `code` n'a pas été testée ici.
- **Recommandation [Jugement]** :
  - la CI construit le VSIX avec vsce, l'attache à la release et l'embarque dans la wheel ; `hypotrail setup vscode` lance `code --install-extension` (`code.cmd` sous Windows, trouvé par `shutil.which`) ;
  - le générateur Python sert de plan B et de test de parité ;
  - Marketplace et Open VSX plus tard : il faut un vrai éditeur (aujourd'hui `hypotrail-local`, `UNLICENSED`), et `extensions.allowed` bloque de toute façon un éditeur inconnu en entreprise.
- **Effort** : 1 à 2 jours.

## 8. Plan par lots

0. **Socle (3-4 j)** : runtime publié ou fusionné dans la wheel, `cli_command` portable, `uv.lock` embarqué, CI. D'abord `uv tool install git+…#subdirectory=framework`, PyPI ensuite (réserver les deux noms dès maintenant).
1. **Démarrage (3-4 j)** : `hypotrail new` et `setup vscode` (VSIX embarqué), hook livré dans le paquet, `doctor`, `review-v1` par défaut, plus de lien `data/`.
2. **Préparation (6-8 j)** : `case new` (brouillon), `case check --feasibility`, skill `hypotrail-case`, données hors de l'espace de travail, exposition tracée.
3. **Holdout (3-5 j)** : règles du §4 sur `analysis_contract`, garde-fous de taille, amendement de l'ADR 0006, rapport. Les dates ensuite (2-4 j).
4. **Windows natif (6-10 j)**, après les tests de concurrence.
5. **Validation** : un cas non vu, préparé par une personne extérieure, sous Linux et sous Windows.
