# Atelier Hypotrail : installation et démarrage (participants)

Cette page s'adresse aux participants de l'atelier « Découvrir le développement ML assisté par agents ». **L'installation se fait au début de l'atelier**, pendant le premier pas guidé. En Codespaces, lancez la création du codespace **dès votre arrivée** : elle prend 4 à 6 minutes.

Dépôt : [https://github.com/hypotrail/hypotrail](https://github.com/hypotrail/hypotrail). Version mise en page (même contenu) : [ouvrir dans le navigateur](https://htmlpreview.github.io/?https://github.com/hypotrail/hypotrail/blob/main/docs/workshop/README.html), ou le fichier [README.html](README.html).

Il y a deux façons de travailler :

- **Option 1, recommandée : GitHub Codespaces.** VS Code tourne dans le navigateur, et rien n'est à installer sur votre poste.
- **Option 2 : en local.** Sur votre machine, sous Linux, macOS ou Windows, avec `uv tool install` et sans Node.

Un seul poste qui fonctionne par binôme suffit.

**Dans les deux cas, il vous faut :**

- un compte GitHub (le dépôt [hypotrail/hypotrail](https://github.com/hypotrail/hypotrail) est public) ;
- **GitHub Copilot** (licence de l'entreprise ou individuelle) avec le chat et le **mode Agent** ;
- VS Code 1.109 ou plus récent, pour le sélecteur de réponses de l'agent. Le VS Code de Codespaces est toujours à jour.

## Option 1 : GitHub Codespaces (recommandée)

### 1. Forker le dépôt

Sur la page du dépôt, [https://github.com/hypotrail/hypotrail](https://github.com/hypotrail/hypotrail), cliquez sur **Fork** puis **Create fork** (lien direct : [https://github.com/hypotrail/hypotrail/fork](https://github.com/hypotrail/hypotrail/fork)), sous votre compte personnel. Gardez « Copy the `main` branch only » coché.

Le fork vous donne votre propre copie : vos études et vos essais n'y touchent pas le dépôt d'origine, et le codespace est rattaché à votre compte.

> Le codespace d'un fork personnel utilise **le quota gratuit de votre compte** : 120 heures-cœur par mois, soit 30 heures sur une machine à 4 cœurs, largement assez pour l'atelier.

### 2. Créer le codespace (dès votre arrivée)

Sur la page de **votre fork**, cliquez sur **Code**, puis **Codespaces** et **…**, puis **New with options**. Choisissez :

- la branche `main` ;
- la région la plus proche (Europe West) ;
- une machine **4-core**.

Cliquez ensuite sur *Create codespace*.

La première création prend **4 à 6 minutes**. Elle installe l'environnement du moteur et le panneau d'étude, et le terminal « Configuring codespace » doit se terminer sans erreur.

Pour l'atelier, passez le délai d'inactivité à 60 minutes : [github.com/settings/codespaces](https://github.com/settings/codespaces), *Default idle timeout*.

### 3. Créer votre étude

Dans le terminal du codespace :

```sh
bash scripts/workshop/new-mpg-study.sh binome-XX --from-pdf --open
```

Remplacez `XX` par votre numéro de binôme, puis passez à [Ouvrir l'étude](#ouvrir-létude).

## Option 2 : en local

Sur votre poste, le moteur s'installe comme un outil, `hypotrail`, avec **uv**. Node n'est pas nécessaire.

### 1. Prérequis

- **uv**, qui installe lui-même Python 3.13 s'il manque.

  Windows (PowerShell) :

  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```

  macOS et Linux :

  ```sh
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

  Ou bien `brew install uv` sous macOS. Rouvrez ensuite le terminal.
- **git**, pour récupérer le cas de l'atelier (Auto MPG).
- **VS Code** et sa commande `code`. Sous macOS : palette, puis *Shell Command: Install 'code' command in PATH*. Sous Windows, l'installeur l'ajoute.

**Derrière un proxy d'entreprise :** définissez `HTTPS_PROXY` et `UV_SYSTEM_CERTS=1` avant les commandes `uv` (PowerShell : `$env:UV_SYSTEM_CERTS = "1"`), ainsi que `UV_DEFAULT_INDEX` si l'entreprise a un miroir PyPI.

### 2. Installer l'outil et le panneau

Les mêmes commandes sous PowerShell, macOS et Linux :

```sh
uv tool install "git+https://github.com/hypotrail/hypotrail#subdirectory=framework"
hypotrail setup vscode
hypotrail doctor
```

- `uv tool install` installe le moteur et ses dépendances (environ 650 Mo : pandas, scikit-learn, SciPy, Marimo, InterpretML…). Faites cette étape sur un bon réseau. Si `hypotrail` n'est pas trouvé ensuite : `uv tool update-shell`, puis rouvrez le terminal.
- `hypotrail setup vscode` installe le panneau d'étude dans VS Code, sans Node. Faites ensuite *Developer: Reload Window*. Sans commande `code`, `hypotrail setup vscode --vsix-out panneau.vsix` écrit le fichier : vue *Extensions*, menu **…**, puis *Install from VSIX…*.
- `hypotrail doctor` vérifie le poste (Python, uv, VS Code, Copilot, panneau, proxy, dossier OneDrive, chemins longs sous Windows) et affiche la commande qui corrige chaque point.

> **Windows :** tant que `hypotrail doctor` signale `platform` en échec, le moteur ne peut pas écrire d'étude sous Windows natif : passez par **WSL2** (Ubuntu, extension VS Code **WSL**, toutes les commandes dans WSL) ou par l'option 1.

> Si l'installation du panneau est refusée (« extension not allowed »), c'est que la politique de l'entreprise filtre les extensions. Le panneau est optionnel : le chat et le rapport suffisent. Prévenez l'organisateur.

Pour mettre à jour : `uv tool install --force "git+https://github.com/hypotrail/hypotrail#subdirectory=framework"`, puis `hypotrail setup vscode`.

### 3. Créer votre étude

Récupérez le cas de l'atelier, dans un chemin **sans espaces**, puis créez l'étude depuis le **terminal intégré de VS Code** :

```sh
git clone https://github.com/hypotrail/hypotrail.git hypotrail
hypotrail new binome-XX --case hypotrail/use-cases/auto-mpg --brief hypotrail/use-cases/auto-mpg/po/fiche-cas-usage-mpg.pdf --lang fr --dir studies --open
```

Remplacez `XX` par votre numéro de binôme, puis passez à [Ouvrir l'étude](#ouvrir-létude). L'étude est créée dans `studies/binome-XX` ; les données restent dans le dossier du cas, hors du dossier de l'étude.

## Ouvrir l'étude

1. La fenêtre VS Code se rouvre sur le dossier `studies/binome-XX` (sinon : `code -r studies/binome-XX`). Si VS Code le demande, **faites confiance au dossier**.
2. Ouvrez la palette (`Ctrl+Shift+P`, ou `Cmd+Shift+P` sur Mac) et lancez **Hypotrail: open the study panel**. Le panneau s'affiche.
3. Ouvrez le chat Copilot (`Ctrl+Alt+I`) :
   - passez en mode **Agent** ;
   - choisissez l'agent **hypotrail** ;
   - dans *Configure Tools*, vérifiez que `vscode/askQuestions` est coché.
4. Écrivez **« Prépare l'étude à partir de la fiche du PO »**. L'agent lit le PDF, rédige la fiche du besoin et lance des commandes `hypotrail` (en Codespaces : `uv run … hypotrail`).


### Les autorisations de l'agent : une règle visible

`hypotrail new` installe dans l'étude une **règle de l'atelier**, un « hook » Copilot écrit dans `.github/hooks/hypotrail.json` (il lance `hypotrail hook pretool`). Avant chaque action de l'agent, elle s'applique ainsi :

- **autorisé sans demande** : une commande simple du moteur, exactement celle que l'étude a enregistrée (`uv run … hypotrail …` en Codespaces, l'exécutable `hypotrail` en local). Vous n'avez pas à valider chaque étape de l'étude ;
- **refusé** : toute lecture directe du fichier de données brut (`auto-mpg.data`). Ce fichier contient aussi les lignes du test final, mises de côté et scellées. On regarde les données par le panneau, `hypotrail data` ou les notebooks, et l'étude compte ces regards ;
- **demandé, comme d'habitude** : tout le reste.

Chaque décision de la règle est notée dans `.github/hooks/hypotrail-hook.log`, que l'on regardera ensemble.

Les hooks sont une fonction **en préversion** de VS Code. Si VS Code vous demande quand même d'autoriser une commande du moteur `hypotrail`, lisez-la, puis choisissez **Allow in this Session**. N'utilisez pas « Allow all », qui autoriserait toutes les actions de l'agent, y compris les modifications de fichiers.

## Dépannage

| Symptôme | À faire |
|---|---|
| La commande « Hypotrail: open the study panel » n'existe pas | `hypotrail setup vscode` (en Codespaces : `bash scripts/workshop/install-panel.sh`), puis *Developer: Reload Window* |
| « Companion disabled (feature flag) » | Le dossier ouvert n'est pas une étude créée par `hypotrail new` : rouvrez `studies/<nom>` |
| Quelque chose ne marche pas sur le poste | `hypotrail doctor` : il indique la commande qui corrige chaque point |
| L'agent hypotrail n'apparaît pas | Le dossier ouvert doit être l'étude elle-même. Faites *Reload Window*. En secours : mode Agent par défaut, puis « Suis les instructions de .github/agents/hypotrail.agent.md. On commence. » |
| Pas de sélecteur de réponses | VS Code trop ancien ou `vscode/askQuestions` décoché : l'agent pose ses questions en texte, on continue |
| `platform_unsupported` | Vous êtes sous Windows natif : passez par WSL2 ou Codespaces |
| `uv tool install` échoue (réseau, certificat) | Proxy : voir les prérequis de l'option 2 (`UV_SYSTEM_CERTS=1`). Sinon, prenez Codespaces |
| Marimo demande un jeton | Ouvrez le lien complet affiché dans le terminal |

Le panneau reste optionnel : le chat, le rapport HTML (`studies/<nom>/reports/study.html`) et le notebook suffisent.

Guide de l'organisateur (prébuild, coûts, démo) : [CODESPACES.md](CODESPACES.md).
