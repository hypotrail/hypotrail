# Atelier Hypotrail : installation et démarrage (participants)

Cette page s'adresse aux participants de l'atelier « Découvrir le développement ML assisté par agents ». **L'installation se fait avant l'atelier**, de préférence au plus tard trois jours avant : le jour J, on n'a plus qu'à créer son étude.

Dépôt : [https://github.com/hypotrail/hypotrail](https://github.com/hypotrail/hypotrail). Version mise en page (même contenu) : [ouvrir dans le navigateur](https://htmlpreview.github.io/?https://github.com/hypotrail/hypotrail/blob/main/docs/workshop/README.html), ou le fichier [README.html](README.html).

Il y a deux façons de travailler :

- **Option 1, recommandée : GitHub Codespaces.** VS Code tourne dans le navigateur, et rien n'est à installer sur votre poste.
- **Option 2 : en local.** Sur votre machine, sous Linux, macOS ou Windows avec WSL2.

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

### 2. Créer le codespace (avant l'atelier)

Sur la page de **votre fork**, cliquez sur **Code**, puis **Codespaces** et **…**, puis **New with options**. Choisissez :

- la branche `main` ;
- la région la plus proche (Europe West) ;
- une machine **4-core**.

Cliquez ensuite sur *Create codespace*.

La première création prend **4 à 6 minutes**. Elle installe l'environnement du moteur et le panneau d'étude, et le terminal « Configuring codespace » doit se terminer sans erreur. Le jour J, il suffit de rouvrir ce codespace depuis [github.com/codespaces](https://github.com/codespaces).

Pour l'atelier, passez le délai d'inactivité à 60 minutes : [github.com/settings/codespaces](https://github.com/settings/codespaces), *Default idle timeout*.

### 3. Vérifier (avant l'atelier)

Dans le terminal du codespace :

```sh
bash scripts/workshop/new-mpg-study.sh essai --open
```

Puis faites la partie [Vérification commune](#vérification-commune).

## Option 2 : en local

### 1. Prérequis

| Système | À faire |
|---|---|
| **Linux** | Rien de particulier. |
| **macOS** | Installer la commande `code` : dans VS Code, palette, puis *Shell Command: Install 'code' command in PATH*. |
| **Windows** | Le moteur ne fonctionne **pas** sous Windows natif. Installez **WSL2** (Ubuntu), puis l'extension VS Code **WSL**. Faites toutes les étapes suivantes **dans WSL** (clone, uv), et ouvrez VS Code en mode WSL (`code .` depuis le terminal WSL). Sans droits pour installer WSL2, prenez l'option 1. |

Il faut aussi :

- **git** ;
- **uv**, qui installe lui-même Python 3.13 s'il manque :

  ```sh
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

  Ou bien `brew install uv` sous macOS.
- **Node.js 18 ou plus**, seulement pour fabriquer le panneau. Si l'organisateur vous a fourni le fichier `hypotrail-companion-0.1.0.vsix`, Node est inutile.

### 2. Cloner et installer l'environnement

Clonez votre fork, ou le dépôt, dans un chemin **sans espaces** :

```sh
git clone https://github.com/<votre-compte>/hypotrail.git ~/hypotrail
# ou, sans fork : git clone https://github.com/hypotrail/hypotrail.git ~/hypotrail
cd ~/hypotrail
uv sync --project framework --group azureml
```

L'environnement fait environ 650 Mo sur disque (pandas, scikit-learn, SciPy, Marimo, InterpretML…). Faites cette étape sur un bon réseau.

**Derrière un proxy d'entreprise :** définissez `HTTPS_PROXY` et `UV_SYSTEM_CERTS=1` avant `uv sync`, ainsi que `UV_DEFAULT_INDEX` si l'entreprise a un miroir PyPI.

### 3. Installer le panneau d'étude

Avec Node :

```sh
bash scripts/workshop/install-panel.sh
```

Sans Node, avec le fichier fourni : dans VS Code, vue *Extensions*, menu **…**, puis *Install from VSIX…*, et choisissez `hypotrail-companion-0.1.0.vsix`.

Faites ensuite *Developer: Reload Window*.

Pour mettre à jour un panneau déjà installé : `bash scripts/workshop/install-panel.sh --force`.

> Si l'installation est refusée (« extension not allowed »), c'est que la politique de l'entreprise filtre les extensions. Le panneau est optionnel : le chat et le rapport suffisent. Prévenez l'organisateur.

### 4. Vérifier (avant l'atelier)

Depuis le **terminal intégré de VS Code**, à la racine du clone :

```sh
bash scripts/workshop/new-mpg-study.sh essai --open
```

Puis faites la partie [Vérification commune](#vérification-commune).

## Vérification commune

1. La fenêtre VS Code se rouvre sur le dossier `studies/essai`. Si VS Code le demande, **faites confiance au dossier**.
2. Ouvrez la palette (`Ctrl+Shift+P`, ou `Cmd+Shift+P` sur Mac) et lancez **Hypotrail: open the study panel**. Le panneau s'affiche.
3. Ouvrez le chat Copilot (`Ctrl+Alt+I`) :
   - passez en mode **Agent** ;
   - choisissez l'agent **hypotrail** ;
   - dans *Configure Tools*, vérifiez que `vscode/askQuestions` est coché.
4. Écrivez « On commence ». L'agent lance des commandes `uv run … hypotrail` et affiche la fiche des données.


### Les autorisations de l'agent : une règle visible

Le script installe dans l'étude une **règle de l'atelier**, un « hook » Copilot écrit dans `.github/hooks/hypotrail.json`. Avant chaque action de l'agent, elle s'applique ainsi :

- **autorisé sans demande** : une commande simple du moteur, `uv run … hypotrail …`. Vous n'avez pas à valider chaque étape de l'étude ;
- **refusé** : toute lecture directe du fichier de données brut (`auto-mpg.data`). Ce fichier contient aussi les lignes du test final, mises de côté et scellées. On regarde les données par le panneau, `hypotrail data` ou les notebooks, et l'étude compte ces regards ;
- **demandé, comme d'habitude** : tout le reste.

Chaque décision de la règle est notée dans `.github/hooks/hypotrail-hook.log`, que l'on regardera ensemble.

Les hooks sont une fonction **en préversion** de VS Code. Si VS Code vous demande quand même d'autoriser une commande `uv run … hypotrail`, lisez-la, puis choisissez **Allow in this Session**. N'utilisez pas « Allow all », qui autoriserait toutes les actions de l'agent, y compris les modifications de fichiers.

## Le jour J

```sh
git pull
bash scripts/workshop/new-mpg-study.sh binome-XX --from-pdf --open
```

Remplacez `XX` par votre numéro de binôme.

En Codespaces, faites `git pull` depuis votre fork : l'organisateur vous dira si une mise à jour est à récupérer avec *Sync fork* sur GitHub. En local, faites `git pull` dans votre clone, puis `bash scripts/workshop/install-panel.sh --force` si le panneau a changé.

Dans le chat, écrivez : **« Prépare l'étude à partir de la fiche du PO »**.

## Dépannage

| Symptôme | À faire |
|---|---|
| La commande « Hypotrail: open the study panel » n'existe pas | `bash scripts/workshop/install-panel.sh`, puis *Developer: Reload Window* |
| « Companion disabled (feature flag) » | Le dossier ouvert n'est pas une étude créée par le script : rouvrez `studies/<nom>` |
| L'agent hypotrail n'apparaît pas | Le dossier ouvert doit être l'étude elle-même. Faites *Reload Window*. En secours : mode Agent par défaut, puis « Suis les instructions de .github/agents/hypotrail.agent.md. On commence. » |
| Pas de sélecteur de réponses | VS Code trop ancien ou `vscode/askQuestions` décoché : l'agent pose ses questions en texte, on continue |
| `platform_unsupported` | Vous êtes sous Windows natif : passez par WSL2 ou Codespaces |
| `uv sync` échoue (réseau) | Proxy : voir l'étape 2 de l'option 2. Sinon, prenez Codespaces |
| Marimo demande un jeton | Ouvrez le lien complet affiché dans le terminal |

Le panneau reste optionnel : le chat, le rapport HTML (`studies/<nom>/reports/study.html`) et le notebook suffisent.

Guide de l'organisateur (prébuild, coûts, démo) : [CODESPACES.md](CODESPACES.md).
