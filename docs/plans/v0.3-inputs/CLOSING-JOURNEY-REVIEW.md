## Revue du parcours junior v0.3 (Hotel booking, FR « vous » et EN, tip 2c3592c)

Je n'ai rien modifié dans le dépôt. Tout ce que j'ai produit est dans `/tmp/claude-0/-home-user-hypotrail/d627b9a6-d196-5d88-8cd2-a6e477a31532/scratchpad/v03-journey-review/` :
- les études `fr/` et `en/` menées jusqu'à la conclusion confirmée ;
- `log.tsv`, qui donne pour chaque appel CLI sa taille, sa durée et son code de sortie, et `out/*.json` pour les sorties ;
- `msg-fr-*.txt`, mes messages de pause ;
- dans `panel/`, la capture par le vrai `lib/controller.js` et un rendu Chromium de chaque onglet (`shots-*-tabs.json`, `*.png`).

**[V]** signale un fait que j'ai reproduit, **[I]** une inférence. J'ai joué l'agent à la main en suivant CLAUDE.md et le skill à la lettre. Ce n'est pas une session LLM réelle.

### Verdict
1. Le moteur a nettement progressé. La confirmation guidée tient : un « oui » après la question fermée passe, aucune raison n'est demandée. Le critère arrive avec son taux de base, ses options et la traduction pour 1 000 actions. Le piège de la révision périmée a disparu, et les diagnostics restent à jour quand on adopte la même règle.
2. Le parcours n'est pas encore fluide. L'agent compose encore lui-même la majorité de chaque pause à partir de JSON bruts : `diag.binary` fait 9 400 puis 17 600 mots, et il n'y a aucun digest junior pour l'EDA, les diagnostics, la règle, le test final ni la conclusion.
3. Trois cibles ne sont pas atteintes : appels par pause 4,5 en moyenne (max 7, cible ≤ 4), messages de pause souvent au-dessus de 150 mots, et environ 200 s d'attente entre la variante et la pause suivante.
4. Une étude en français reste en anglais presque partout hors `next_action` : fiche de données, `explain`, titres du plan, objectif, rapport HTML, récit du notebook, et de nombreux restes dans le panneau.
5. Le panneau est propre visuellement et en lecture seule, mais il est encore long (1 270 à 1 760 mots par onglet) et se contredit sur quelques points (« vos mots », « bloquant » fantôme, « pas de colonne de temps »).

### R12–R38

| R | Statut | Preuve |
|---|---|---|
| R12 | Résolu | Bascule « Sens EN / Sens FR » et une ligne d'aide dans le dictionnaire [V] |
| R13 / R20 | Partiel | Seulement dans les instructions (CLAUDE.md règle 6) ; non testable sans agent réel [I] |
| R14 | Résolu | Le digest donne la reformulation citée et « Adoptez-vous cette décision ? » [V] |
| R15 | Partiel | Le moteur dit bien plis, hors pli, échantillon de développement. Restent :<br>• `copy-fr/eda.js:23-24,80,87` : « lignes d'entraînement » sous CV ;<br>• `copy-fr/evidence.js:167,197` : « Précision moyenne » ;<br>• le rapport : « training rows » ×5 ;<br>• le panneau : « part de succès parmi les cas retenus » au lieu de « précision » [V] |
| R16 | Partiel | Le canal `choice` existe. Les instructions Copilot ne nomment que `AskUserQuestion`, sans équivalent Copilot [V] |
| R17 | Partiel | Graphiques du panneau refaits, mais le rapport n'a pas changé (E2.6) [V via décisions] |
| R18 / R19 | Résolu | `criterion_options` donne la référence 25,9 %, les options +2/+5/+10 avec la traduction pour 1 000, et un `recommended` [V] |
| R21 | Partiel | En panneau FR, restent en anglais :<br>• les reformulations ;<br>• les titres d'étapes (« après Choose a decision policy ») ;<br>• les en-têtes de groupes, les unités (days/nights) ;<br>• le sens des valeurs spéciales ;<br>• la limite « Data contingent preprocessing » ;<br>• deux paragraphes de Preuves.<br>Les nombres sont au format en-US (« 73.6% », « 8,011 ») [V] |
| R22 | Partiel | Carte en lecture seule. « révision 32 » s'affiche dans l'en-tête. Les effets restent sur « Lecture… » dans ma capture : artefact de mon harnais, qui ne répond pas aux requêtes de prévisualisation [V/I] |
| R23 | Résolu | Ni W1, ni W2, ni W3 dans `lib/` ; « Ce panneau n'enregistre aucune décision » [V] |
| R24bis | Résolu, avec réserves | CV imbriquée, budget, règle d'une erreur type et optimisme présents [V]. Deux réserves :<br>• le pli intérieur n'est pas temporel (F1.4), et la variante réglée est moins bonne (AUC 0,776 contre 0,785) ;<br>• `advice` dit « diffère de plus que le bruit » alors que `largest_difference` vaut 0,0090 et `noise` 0,0104 [V] |
| R25 | Résolu | Historique du plus récent au plus ancien ; « oui » est noté « approuvée » [V] |
| R26 | Partiel | Rendu propre, mais Overview fait 1 274 mots et 3 063 px, EDA 5 048 px, Preuves 6 369 px à 900 px [V] |
| R27 | Résolu côté moteur, partiel côté UI | Le moteur est conforme. Mais :<br>• `copy-fr/overview.js:93` affiche « pause N · vos mots » en mode guidé ;<br>• des réponses naturelles sont refusées (voir friction 6) [V] |
| R28 | Partiel | `next_action` impose les diagnostics après le fit et après l'évaluation [V]. La matrice 2×2 est composée par l'agent ; la matrice de corrélation n'est ni dans le flux par défaut ni dans le rapport [V] |
| R29 | Partiel | Quelques `value_counts` / `groupby` dans le notebook ; le récit reste en anglais (F2.1) [V] |
| R30 | Résolu | « lignes de l'échantillon de développement » [V] |
| R31 / R38 | Résolu | Cas Hotel, test final temporel, pièges de fuite documentés [V] |
| R32 | Partiel | `data_contingent` arrive avant la présentation [V]. Mais le défaut « ne rien faire » est marqué dépendant des données après deux simples regards au taux de base (`commands.py:1140-1172`), et la raison est en anglais [V] |
| R33 | Partiel | Toujours refusés [V] :<br>• « 25,4 à 26,4 % » : le `%` n'est pas propagé à la première borne, `numtrace.py:224-227,1034` ;<br>• 7 265 / 1 912, les doublons que la fiche imprime elle-même (`cmd_data.py:87`, non enregistrés) ;<br>• « 10 % » dans une phrase sur le test final (la portée `FINAL_SCOPE` lie la phrase au test final) ;<br>• les taux de base dev et final dans une même phrase |
| R34 | Partiel | La règle adoptée garde les diagnostics à jour [V]. Mais l'ancien `diag.binary` remplacé reste dans `state['stale']` (`state.py:1507-1514`) : limite `stale_results` en tête du résumé, et « bloquant » dans le panneau, alors que tous les résultats sont à jour [V] |
| R35 | Résolu | `digest.channel_actions` porte le canal webview et un `junior_text` [V] |
| R36 | Partiel | La conclusion est en FR (écrite par l'agent). L'objectif, le moment de la prédiction (texte du cas) et le rapport restent en EN [V] |
| R37 | Partiel | `next_action` est en FR. Restent en EN : `explain`, les titres du plan, `data --format text`, les messages des livrables, `data_contingent_reason` [V] |

### Mesures

| Mesure | Cible | Moi (FR / EN) | Round 3 S14 | Revue précédente |
|---|---|---|---|---|
| Tours du junior | ≤ 12 | 13 (11 sans les 2 « explique-moi d'abord ») | 13–15 | ~16–20 |
| Refus visibles | 0 | 0 sur mon chemin, mais risque vérifié (friction 6) | 0 | plusieurs |
| Refus moteur | — | FR 4 (3 `check` + 1 `propose`) ; EN 5 (+1 `confirm`) | 15 | >0 |
| Appels par pause | ≤ 4 | moyenne 4,5, max 7 (FR, 53 appels) | 4,3–5,2 | ~65 appels |
| Mots lus par l'agent | — | ~53 k, ~82 k avec `status --json` (29 k) | — | 32 k min, 60–70 k réels |
| Prompt | ≤ 4 k | 3 506 (CLAUDE.md 2 719 + skill 787), atteint | — | 8 176 |
| Mots par pause | ≤ 150 | 104–165, 4 pauses sur 10 au-dessus | 151–210 | — |
| Temps moteur | « continue » ≤ 60 s | 429 s FR / 356 s EN ; `fit.variant` 154–181 s | 8–25 min | 127 s |

Il faut composer ou chercher ailleurs à 10 endroits [V] :
- le moment de la prédiction et le texte de l'objectif, en anglais ;
- la reformulation de la disponibilité des variables ;
- « explique-moi d'abord » : `explain` n'est pas documenté dans CLAUDE.md, il est en anglais avec des exemples bancaires, et j'ai eu 2 erreurs d'arguments ;
- l'EDA ;
- les diagnostics ;
- les gains à 5, 10 et 20 % ;
- l'enquête sur le « stale » fantôme ;
- les chiffres finaux ;
- la conclusion (`recommended: null`) ;
- la fiche de données (4 010 mots à réduire à 150).

### Top 10 des frictions, par impact

1. **Pas de digest junior pour les résultats.** L'agent compose les tableaux, la calibration et les gains depuis 9–18 k mots de JSON. Le plafond de 150 mots (skill) et la liste de la règle 3 de CLAUDE.md (2×2, précision/rappel, calibration, segments) sont incompatibles.
   - Correctif : `junior_digest` et un tableau 2×2 pré-rendus dans la langue de l'étude pour chaque `run`, avec le JSON complet seulement sur `--fields`.
2. **Le traçage refuse encore des chiffres honnêtes** (voir R33).
   - Correctif : propager l'unité de la seconde borne à la première ; enregistrer les chiffres de la fiche ; rendre les valeurs de décision confirmées traçables quelle que soit la portée ; ajouter un test « golden » qui rejoue mes messages.
3. **Une étude FR reste en anglais hors `next_action`** : fiche, `explain`, titres du plan, objectif, rapport de 26,7 k mots en EN, récit du notebook (décisions C7 et F2.1). Pour un junior francophone, le « rapport unique » est en anglais.
   - Correctif : `labels.fr` pour l'objectif et le moment de la prédiction dans le cas ; `title_fr` dans le plan ; une passe FR du rapport et du notebook.
4. **Faux « résultats périmés »** (`state.py:1507`). Le panneau ignore `junior:false` et affiche « bloquant ». La règle 10 force alors une enquête (2 appels, 31 k mots).
   - Correctif : retirer de `stale` un résultat dont le slot a un résultat courant ; faire respecter `junior` par le panneau.
5. **Attente.** La variante réglée prend 154 à 181 s ; il faut environ 200 s entre « oui » à la variante et la pause suivante. En plus, les plis intérieurs non temporels donnent une variante moins bonne.
   - Correctif : plis intérieurs temporels, grille réduite, ou fit de la variante pendant la pause de la règle, avec un message d'attente.
6. **Réponses naturelles après une explication refusées, même avec la question fermée** : « oui, c'est clair maintenant », « yes, makes sense now », « ok c'est clair », « je vous fais confiance » (`commands.py:1319`, `unrelated_reply`). C'est exactement ce que dit un junior après « explique-moi d'abord ».
   - Correctif : avec `--adoption-question`, toute réponse non négative et non conditionnelle vaut adhésion.
7. **Le défaut « ne rien faire » est déclaré dépendant des données** (`commands.py:1140-1172`). On dit au junior que les résultats « peuvent être optimistes » pour un choix rédigé avant tout regard sur la cible.
   - Correctif : un défaut inchangé et sans `motivated_by` n'est pas contingent ; ajouter `text_fr`.
8. **Ni conclusion ni moment de la prédiction rédigés par le moteur** (`recommended` nul). Cela coûte un tour de plus ou laisse l'agent improviser (échec S12 du round 3).
   - Correctif : verdict proposé à partir de `criterion.judged_status`, avec un texte FR modèle.
9. **Le panneau contredit le chat ou se contredit** :
   - « pause N · vos mots » ;
   - « Ce qui compte comme votre réponse », répété dans Overview et Décisions ;
   - « +47.7% » pour des points ;
   - la reformulation EN dans le panneau FR ;
   - la limite « ni colonne de temps » (`state.py:1446-1469`) à côté de « les lignes les plus récentes dans l'ordre du temps » ;
   - « Prédire avant de regarder » alors que le taux de base a déjà été lu ;
   - une carte concept vide.
   - Correctif : un audit de la copie FR et la suppression des doublons.
10. **La dérive vers le test final est invisible** : taux de base 25,9 % en développement contre 35,3 % sur le test final. Le moteur ne le signale pas, et `check` refuse la phrase qui compare les deux [V].
    - Correctif : `diag.final_test.shift` avec un texte junior, montré dans le rituel de conclusion.

### Ce qui est sur-dimensionné
- **`numtrace`** : 1 137 lignes et 39 regex de portée. On joue au chat et à la souris, chaque round élargit la tolérance, et un faux chiffre égal à une valeur enregistrée passe quand même.
- **Le classement lexical des confirmations** : il reste en mode guidé alors que la question fermée suffit.
- **Le panneau désactivé par défaut** :
  - environ 89 k mots de JS ;
  - stades v0–v3, mode relecteur, couche « Learn », rapport de session, export ;
  - 108 PNG de référence ;
  - une Overview de 1 270 mots.
- **Des sorties géantes** : `status --json` à 29 k mots, et `--fields model_families` qui renvoie encore 1 030 mots.
- **`--request-id` et `--expected-revision`** à chaque appel, pour un agent unique.

### Trois suggestions inattendues
1. **Citation par jeton plutôt que par correspondance.** L'agent écrit `{{policy.evaluation:…precision|pct1}}`, et une commande `hypotrail render-text` remplace. Cela donne zéro faux refus et une garantie plus forte (un chiffre inventé ne peut plus passer), et cela supprime `check` sur les textes de chat.
2. **Une commande `hypotrail pause --lang fr`** qui renvoie le message de pause complet (≤ 150 mots, chiffres déjà tracés, reformulation rédigée, ligne d'onglet). L'agent relaie, ne compose plus, et le skill tient en une page.
3. **Un « agent littéral » sans LLM en CI** qui rejoue ce parcours (mes scripts en sont l'ébauche). Il aurait attrapé, pour 0 $, le « 10 % » refusé, les doublons de la fiche, le « stale » fantôme et les réponses post-explication refusées. Il faudrait aussi journaliser les « explique-moi d'abord » par décision : c'est un signal produit sur les pauses qui confondent.

**Limites** :
- Ce n'est pas une session Claude, Copilot ou VS Code réelle. J'ai écrit les messages moi-même, en m'efforçant de rester sous 150 mots.
- Les panneaux sont rendus dans Chromium à partir des messages du vrai contrôleur ; les zones « Lecture… / Mise à jour… » viennent de mon harnais.
- Les étapes FR et EN sont identiques jusqu'à la conclusion. En EN, j'ai testé les variantes de réponse sur des clones.
