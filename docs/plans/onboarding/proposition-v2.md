# Hypotrail : de « j'arrive avec mon dataset » à une étude lancée (proposition v2)

Synthèse de la v1 et de deux revues fraîches du 1er novembre 2026 (`review-A.md` produit et expérience, `review-B.md` méthode et technique, avec essais réels).

## 1. Ce que les revues changent

| Sujet | v1 | v2 (après revue) |
|---|---|---|
| Préparation avant scellement | un `case.yaml` complet, ≈ 40 questions | **six questions seulement** avant de sceller ; descriptions et disponibilités viennent **après**, comme décisions de l'étude |
| Qui prépare | un skill de préparation distinct | **le même agent d'étude**, qui pilote une commande **déterministe** `hypotrail new --data` |
| Holdout | nouvelle clé `holdout` (méthode, fraction, graine) | **pas de nouvelle clé** : le cas déclare des **faits** (usage futur ? entités récurrentes ? horloge ?), le moteur **déduit** la méthode via `analysis_contract` (profil `review-v1`, qui existe déjà) ; fraction 0,2 par défaut, effective bornée [0,1 ; 0,35] ; **graine non réglable** |
| Aperçu du holdout | `holdout --preview` avec proportions | `case check --feasibility` : comptes **sans la cible** et un verdict réussi / échoué (pas de « choisir le holdout qui arrange ») |
| Protection des données | hook qui refuse le nom du fichier | **les données restent hors de l'espace de travail du chat** ; plus de lien `data/` dans les nouvelles études ; inspection structurelle **tracée** en `prior_exposure` ; le hook n'est qu'une aide, pas une barrière |
| Empaquetage | « cassé hors checkout » | **en partie faux** : la wheel s'installe avec `uv tool install` et `init`, `render`, `data`, l'export Marimo marchent. Ce qui casse vraiment : `hypotrail-runtime` en dépendance de chemin (absent de PyPI), la commande `env PYTHONPATH=…` dans `agent.json`, `uv.lock` absent du snapshot |
| Panneau | VSIX via Node | **pas de Node chez l'utilisateur** : VSIX construit par la CI, **embarqué dans le paquet**, installé par `hypotrail setup vscode` ; un VSIX construit en Python pur a été vérifié identique octet pour octet à celui de vsce |
| Windows | non traité | **Windows natif au premier rang** : aucun script bash dans le parcours, verrous multiplateformes, CI Windows |

## 2. Le parcours cible

1. **Installer** (une fois)
   - Windows, PowerShell : `winget install astral-sh.uv`, puis `uv tool install hypotrail` (au début : `uv tool install "git+https://github.com/hypotrail/hypotrail#subdirectory=framework"`).
   - macOS / Linux : le script d'uv, puis la même commande.
   - Codespaces : « Use this template » sur `hypotrail/study-template`, tout est prêt.
   - `hypotrail doctor` vérifie Python, VS Code (`code`), Copilot ou Claude Code, le panneau, la politique d'exécution PowerShell, les chemins longs, OneDrive, le proxy, et affiche la commande pour corriger.
2. **Créer l'étude**
   `hypotrail new churn --data C:\data\churn.csv [--brief fiche.pdf] --open`
   La commande garde les données **hors** de l'espace de travail (`cases/churn/data/`, exclu de la recherche et de l'index du chat), calcule l'empreinte et un profil **en comptes**, installe l'agent, le hook et le panneau (`setup vscode` si besoin), puis ouvre VS Code.
3. **Préparer dans le chat** : « Prépare l'étude ». L'agent lit la fiche et pose **six questions**, une à la fois, avec des réponses proposées et sourcées ; l'utilisateur tranche avec ses mots :
   1. Quelle est la cible (et la valeur « positive ») ?
   2. Que représente une ligne ?
   3. Quand prédit-on, et l'usage vise-t-il le futur ? (horloge)
   4. Des entités reviennent-elles (client, véhicule, patient) ?
   5. Avez-vous déjà exploré ce fichier ? (exposition préalable : posée **en premier**)
   6. Acceptez-vous ce test final ? présenté **en mots et en comptes** : « les 20 % les plus récents, 1 840 lignes, de mars à juin 2025 ».
4. **Sceller** : `hypotrail seal` (lancé par l'agent après l'accord). Le chapitre 0 du rapport explique comment et pourquoi le test final a été mis de côté.
5. **Mener l'étude** : comme aujourd'hui, guidée ou automatique.

## 3. Règles du test final (déduites, pas choisies)

1. Usage futur avec horloge documentée → **temporel** (les dernières périodes), avec purge des labels connus trop tard.
2. Entités récurrentes → **groupé** (une entité d'un seul côté) ; avec une horloge aussi → **groupé temporel**.
3. Dépendance temporelle supposée → temporel.
4. Sinon → **stratifié** sur la cible (binaire) ou ses quantiles (régression).
5. Réponse « je ne sais pas » → stratifié, et les conclusions de l'étude sont **plafonnées** (pas de prétention sur le futur).

Garde-fous : au moins 100 lignes et 30 cas minoritaires dans le test (à calibrer), sinon **refus motivé**, jamais de repli silencieux ; fraction effective rapportée ; dates : horloge `date` avec format explicite ou copie triée tracée (modèle Hotel), jamais de conversion implicite ; cible manquante : copie dérivée tracée, jamais d'exclusion silencieuse.

Si le fichier a déjà été exploré en entier avec la cible : le rapport le dit et les conclusions excluent la « preuve indépendante » ; mieux : attendre des données postérieures pour le test final.

## 4. Windows natif

À faire avant de lever `require_posix` :
- verrous : `msvcrt` / `portalocker` sur un octet hors du contenu (les verrous Windows sont obligatoires), revérifier la détection des baux orphelins ;
- `os.replace` : réessais bornés (antivirus, panneau, Marimo qui gardent un fichier ouvert) ;
- UTF-8 forcé sur la sortie et à chaque ouverture de fichier ;
- commandes en **listes d'arguments** vers `hypotrail.exe`, jamais `env …` ni `shlex` ; affichage au format PowerShell ;
- textes libres de l'utilisateur passés par fichier (`--user-words-file`), pas par les guillemets PowerShell ;
- hook livré dans le paquet (`hypotrail hook pretool`), motif déduit de `agent.json` ;
- scripts bash d'atelier remplacés par `hypotrail new` / `setup` / `doctor` ;
- **CI GitHub Actions** sur `ubuntu`, `windows`, `macos-latest`, avec deux tests de concurrence (verrou disputé ; remplacement pendant une lecture), puis un essai VS Code + Copilot.

Critère de sortie : un parcours chronométré sur un poste d'entreprise **sans droits d'administrateur**.

## 5. Plan de livraison

| Lot | Contenu | Effort estimé |
|---|---|---|
| **0. Socle** | `hypotrail-runtime` publié ou fusionné dans la wheel ; commande portable dans `agent.json` ; `uv.lock` embarqué ; CI 3 OS ; **réserver dès maintenant les noms `hypotrail` et `hypotrail-runtime` sur PyPI** | 3–4 j |
| **1. Démarrage** | `hypotrail new`, `setup vscode` (VSIX embarqué), `doctor`, hook dans le paquet, profil `review-v1` par défaut, plus de lien `data/` ; modèle Codespaces | 3–4 j |
| **2. Préparation** | profil en comptes, `case check --feasibility`, les six questions dans l'agent (skill chargé à la demande, le budget d'instructions étant presque plein), `seal`, exposition tracée, chapitre 0 | 6–8 j |
| **3. Test final** | règles du §3 sur `analysis_contract`, garde-fous, amendement de l'ADR 0006 ; puis horloge `date` | 3–5 j + 2–4 j |
| **4. Windows natif** | §4, après les tests de concurrence | 6–10 j |
| **5. Validation** | un cas inédit, préparé par une personne extérieure, sous Windows natif et Codespaces, chronométré | 1–2 j |

Total : environ 25 à 35 jours. Gain rapide dès maintenant : CI, réservation PyPI, VSIX en release.

## 6. Décisions à prendre par le propriétaire

1. Valider « six questions avant le scellement, le reste après » (le `case.yaml` complet n'est plus un préalable).
2. Valider « faits déclarés, méthode déduite », sans clé `holdout` ni graine réglable (amendement de l'ADR 0006 pour les bornes de fraction).
3. Supprimer le lien `data/` (R69) dans les nouvelles études, au profit des données hors espace de travail.
4. PyPI public tout de suite, ou Git d'abord ?
5. Ordre : Windows natif (lot 4) avant ou après la préparation (lot 2) ?
