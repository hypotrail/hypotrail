# Atelier Auto MPG dans GitHub Codespaces : guide de l'organisateur

Ce guide prépare l'atelier « Déléguer une étude ML » (binômes : une personne junior en ML avec un ou une data engineer ou PM) dans GitHub Codespaces : le chat Copilot avec l'agent Hypotrail, le panneau d'étude (étape v3), le rapport HTML, les notebooks Marimo, et la démonstration de l'export Azure ML en fin de matinée (plan seulement, aucun job Azure).

Fichiers concernés :

| Fichier | Rôle |
|---|---|
| `.devcontainer/devcontainer.json` | Image Python 3.13, Node 22, extensions Copilot, Copilot Chat et Python, drapeau du panneau à `v3`, ports Marimo |
| `.devcontainer/post-create.sh` | Installe uv (version fixée), synchronise `framework/.venv` (groupes `dev` et `azureml`), empaquette le panneau en VSIX |
| `scripts/workshop/install-panel.sh` | Empaquette (`@vscode/vsce` fixé, via `npx`) et installe le panneau dans le VS Code du codespace |
| `scripts/workshop/new-mpg-study.sh` | Crée l'étude Auto MPG en français d'un binôme dans `studies/<nom>` (ignoré par git) et affiche la suite |

Le panneau n'est pas publié : `--extensionDevelopmentPath` n'existe pas dans Codespaces, donc `post-create.sh` en fait un VSIX (dans `.workshop-cache/`, ignoré par git) à partir d'une copie de `extension.js`, `package.json`, `README.md`, `lib/` et `media/`, sans modifier ses sources. L'installation a lieu quand VS Code s'attache au codespace (`postAttachCommand`), puis le script d'étude la vérifie de nouveau depuis le terminal intégré.

## 1. Prérequis

- **Comptes GitHub** : un par participant, avec accès en lecture au dépôt `chadlis/hypotrail` (dépôt privé : inviter les comptes ou une équipe de l'organisation).
- **Licences Copilot** : indispensables, le chat est le cœur de l'atelier. Copilot Business ou Enterprise attribué à chaque compte (ou Copilot individuel). Dans les politiques Copilot de l'organisation, vérifier que Copilot Chat dans l'IDE et le mode agent sont autorisés ; si les agents personnalisés (`.github/agents/*.agent.md`) n'apparaissent pas, vérifier aussi la politique des fonctionnalités en préversion de l'éditeur.
- **Codespaces activé** pour l'organisation : *Organization settings > Codespaces > General* : autoriser les membres concernés (tous, ou une sélection), et choisir qui paie (*Billing* : l'organisation, avec une limite de dépense supérieure à 0 ; sinon chaque compte personnel paie sur son quota gratuit).
- **Un poste par binôme** : un navigateur récent suffit (VS Code pour le Web) ; VS Code de bureau avec l'extension GitHub Codespaces fonctionne aussi.
- Une version récente de VS Code (1.109 ou plus) pour l'outil `vscode/askQuestions` (le sélecteur de réponse de l'agent). Codespaces dans le navigateur est toujours à jour.

## 2. Prébuilds (fortement recommandé)

Sans prébuild, la création d'un codespace télécharge l'image, installe uv, synchronise l'environnement du moteur (scikit-learn, Marimo, InterpretML, MLflow, etc.) et empaquette le panneau : compter 4 à 6 minutes. Avec un prébuild, ce travail est déjà fait : environ 1 minute.

1. Dépôt > *Settings > Codespaces > Set up prebuild*.
2. Branche : `claude/codespaces-mpg-workshop` (ou `main` une fois la branche fusionnée).
3. Configuration : `.devcontainer/devcontainer.json`.
4. Région : celle des participants (Europe West).
5. Déclenchement : *On configuration change* (ou *Every push* si la branche bouge encore ce soir).
6. Type de machine : 4 cœurs.
7. Attendre que le prébuild soit *Ready* (onglet *Actions*, workflow « Codespaces Prebuilds », quelques minutes).

`post-create.sh` est lancé par `updateContentCommand`, qui s'exécute aussi pendant le prébuild. Seule l'installation du panneau dans VS Code attend la première connexion (`postAttachCommand`, quelques secondes).

## 3. Ouvrir un codespace sur la branche

- Interface : page du dépôt > *Code > Codespaces > … > New with options* : branche `claude/codespaces-mpg-workshop` (ou `main` après fusion), région, machine **4-core**, *Create codespace*.
- Ligne de commande : `gh codespace create -R chadlis/hypotrail -b claude/codespaces-mpg-workshop -m standardLinux32gb` puis `gh codespace code` (bureau) ou ouverture depuis github.com/codespaces.

Chaque binôme a son propre codespace : les études restent dans ce codespace (`/workspaces/hypotrail/studies/`).

## 4. Démarrage d'un binôme en 3 minutes

1. Ouvrir le codespace ; attendre la fin de la configuration (le terminal « Configuring codespace » se termine, `docs/workshop/CODESPACES.md` s'ouvre).
2. Vérifier que Copilot est connecté (icône Copilot dans la barre d'état, sans avertissement).
3. Dans le terminal :

   ```sh
   scripts/workshop/new-mpg-study.sh binome-03 --open
   ```

   Le script crée l'étude, active le panneau à l'étape v3 dans `studies/binome-03/.vscode/settings.json`, vérifie que le panneau est installé, affiche la suite, puis rouvre la fenêtre sur le dossier de l'étude (`code -r`). Sans `--open`, faire *File > Open Folder…* > `/workspaces/hypotrail/studies/binome-03`. **Le dossier ouvert doit être l'étude** : Copilot lit `.github/agents/` et `.github/copilot-instructions.md` à la racine du dossier ouvert.
4. Si VS Code le demande, faire confiance au dossier (le panneau exige un espace de travail approuvé).
5. Palette (`Ctrl+Shift+P`) : **Hypotrail: open the study panel**. À l'étape v3, on voit les onglets Overview, Decisions, Data & EDA, Evidence, What if? et Learn & hand off.
6. Chat Copilot (`Ctrl+Alt+I`) : choisir l'agent **Hypotrail** dans la liste des agents ; dans l'icône des outils (*Configure Tools*), vérifier que `vscode/askQuestions` est coché.
7. Écrire **On commence**. L'agent lance des commandes `uv run --project /workspaces/hypotrail/framework hypotrail …` dans le terminal : les autoriser (« Allow », ou l'autorisation pour la session).

Le rapport HTML est dans `studies/<nom>/reports/study.html` dès le premier rendu ; le panneau l'ouvre (« Your deliverables »), ainsi que les notebooks Marimo (« Open in Marimo »). Marimo démarre sur le port 2718, puis 2719, 2720… : ouvrir le lien affiché dans le terminal (`Ctrl+clic`), il contient le jeton d'accès ; l'onglet *Ports* liste les ports transférés.

## 5. Commandes de démonstration (organisateur)

Mode automatique (il n'existe qu'avec le moteur de la branche de fonctionnalités `claude/zealous-franklin-gywbya` ; sur un `main` qui ne l'a pas encore, le script refuse avec un message clair) :

```sh
scripts/workshop/new-mpg-study.sh demo-orga --automation until_final_test --open
```

Puis, dans le chat avec l'agent Hypotrail : « On commence ». L'agent lance `automation run --progress` : sept décisions enregistrées comme automatiques, 22 calculs, environ 30 secondes ; il s'arrête avant le test final, qui reste scellé. Chaque décision automatique reste à relire et à adopter ou changer avec ses propres mots : l'étude n'est pas défendable avant. La variante `full_demo` ouvre aussi le test final automatiquement ; l'étude est alors marquée comme démonstration, définitivement.

Sans le chat (secours, même résultat) :

```sh
uv run --project /workspaces/hypotrail/framework hypotrail automation run --progress \
  --request-id demo-1 --expected-revision 1 --study /workspaces/hypotrail/studies/demo-orga
```

Partir de la fiche du PO (PDF, R68) : `--from-pdf [FICHIER]` (par défaut `use-cases/auto-mpg/po/fiche-cas-usage-mpg.pdf`) crée l'étude avec `init --brief-pdf`, qui copie le PDF dans `studies/<nom>/brief/` et l'importe. L'étape 1 du panneau n'affiche pas la fiche du cas d'usage par défaut : elle annonce la fiche du PO importée, jusqu'à ce que le junior adopte dans le chat la fiche rédigée par l'agent (chaque champ avec ses pages, marquée « tirée du PDF »).

```sh
scripts/workshop/new-mpg-study.sh demo-pdf --from-pdf --open
```

Puis, dans le chat avec l'agent Hypotrail : « Prépare l'étude à partir de la fiche du PO ». Sans le script : `uv run --project framework hypotrail init --case use-cases/auto-mpg --study DOSSIER --lang fr --brief-pdf use-cases/auto-mpg/po/fiche-cas-usage-mpg.pdf`.

Fin d'atelier, plan d'export Azure ML (n'écrit rien, ne lance aucun job Azure ; utile une fois un modèle choisi) :

```sh
scripts/workshop/new-mpg-study.sh --azureml-plan demo-orga
```

Il liste les fichiers du projet Azure ML qui serait généré, leur statut et les champs manquants du profil de destination.

## 6. Dépannage

**Le panneau est absent** (la commande « Hypotrail: open the study panel » n'existe pas) :

```sh
scripts/workshop/install-panel.sh
```

puis *Developer: Reload Window*. Sinon : vue Extensions > *…* > *Install from VSIX…* > `/workspaces/hypotrail/.workshop-cache/hypotrail-companion-0.1.0.vsix`. Si le VSIX manque : `scripts/workshop/install-panel.sh --force` le reconstruit (Node est installé dans l'image).

**« Companion disabled (feature flag) »** : le dossier ouvert n'est pas une étude créée par le script, ou les réglages manquent. Vérifier `studies/<nom>/.vscode/settings.json` (`"hypotrail.companion.enabled": true`, `"hypotrail.companion.stage": "v3"`) ; `echo $HYPOTRAIL_COMPANION_STAGE` dans le terminal doit afficher `v3`.

**Le panneau ne trouve pas l'étude** : ouvrir le dossier de l'étude (ou le dépôt : les études sont cherchées jusqu'à deux niveaux sous le dossier ouvert). Ne pas renommer ni déplacer une étude : le CLI refuse une étude déplacée ; en créer une nouvelle.

**L'agent Hypotrail n'apparaît pas dans le chat** :
- le dossier ouvert doit être l'étude (`.github/agents/hypotrail.agent.md` à sa racine) ; *Developer: Reload Window* ;
- Copilot Chat à jour et connecté ; politique de l'organisation (mode agent, fonctionnalités en préversion) ;
- secours : mode Agent par défaut et écrire « Suis les instructions de .github/agents/hypotrail.agent.md. On commence. » (les instructions de `.github/copilot-instructions.md` sont chargées de toute façon).

**Pas de sélecteur de réponse** : `vscode/askQuestions` décoché ou VS Code trop ancien ; l'agent pose alors la question en texte, l'atelier continue.

**Copilot refuse** (pas de licence, non connecté) : se connecter avec le compte qui a la licence (icône Comptes, en bas à gauche).

**`uv` introuvable ou environnement absent** : `bash .devcontainer/post-create.sh` (idempotent).

**Marimo demande un jeton** : ouvrir le lien complet affiché dans le terminal, pas l'adresse du port seule.

**Codespace lent** : vérifier la machine (4 cœurs) ; *Codespaces: Change Machine Type*.

Le panneau reste optionnel : le chat, le rapport HTML et le notebook suffisent à l'atelier.

## 7. Coûts et délai d'inactivité

Tarifs publics GitHub (à vérifier sur la page de facturation Codespaces) : environ 0,36 $ par heure pour une machine 4 cœurs, et 0,07 $ par Go et par mois de stockage. Exemple : 12 binômes × 4 heures ≈ 17 $ de calcul, plus quelques dollars de stockage (codespaces et prébuild). Les comptes personnels ont un quota gratuit mensuel (120 heures-cœur, soit 30 heures en 4 cœurs).

- Délai d'inactivité : 30 minutes par défaut ; le codespace s'arrête, les fichiers restent. Pour l'atelier, le passer à 60 minutes (paramètres personnels *Codespaces > Default idle timeout*, ou politique d'organisation *Maximum idle timeout*).
- Durée de conservation : régler une rétention courte (par exemple 7 jours) et supprimer les codespaces après l'atelier : `gh codespace list` puis `gh codespace delete -c <nom>`.
- Supprimer ou désactiver le prébuild après l'atelier (son stockage est facturé).

## 8. Répétition de ce soir

- [ ] Fusionner la branche `claude/codespaces-mpg-workshop` dans `main` (PR), ou garder la branche pour demain.
- [ ] Activer Codespaces pour l'organisation, la facturation et une limite de dépense ; vérifier l'accès au dépôt et la licence Copilot de chaque participant.
- [ ] Créer le prébuild (section 2) et attendre *Ready*.
- [ ] Créer un codespace neuf en 4 cœurs et chronométrer le démarrage.
- [ ] Dans le terminal : `uv --version`, `ls framework/.venv/bin/hypotrail`, `echo $HYPOTRAIL_COMPANION_STAGE` (v3), `code --list-extensions | grep hypotrail` (`hypotrail-local.hypotrail-companion`).
- [ ] `scripts/workshop/new-mpg-study.sh essai --open` ; faire confiance au dossier ; ouvrir le panneau : les six onglets de v3 s'affichent. C'est le premier passage du panneau dans un vrai VS Code (`clients/vscode-companion/MANUAL-TEST.md`) : noter toute anomalie, et garder le plan B sans panneau.
- [ ] Chat : agent Hypotrail visible, `vscode/askQuestions` coché, « On commence » : la fiche des données, puis la première pause avec le sélecteur (adopter, changer, expliquer).
- [ ] Depuis le panneau, « Open in Marimo (read) » : le port 2718 est transféré et le notebook s'affiche.
- [ ] Démo : `scripts/workshop/new-mpg-study.sh demo-orga --automation until_final_test --open`, « On commence », puis `scripts/workshop/new-mpg-study.sh --azureml-plan demo-orga`.
- [ ] Préparer la liste des binômes et leurs noms d'étude (`binome-01`, `binome-02`, …).
- [ ] Supprimer le codespace d'essai (garder celui de la démo si on le souhaite).
- [ ] Plan B : VS Code de bureau avec l'extension Dev Containers sur le même `.devcontainer/` (Docker requis), ou l'organisateur qui projette son codespace.
