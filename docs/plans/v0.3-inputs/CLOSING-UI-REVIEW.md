## Revue visuelle et UX du panneau d'étude Hypotrail (v0.3, tip 2c3592c)

Je n'ai rien modifié dans le dépôt (`git status` est propre). Tout ce que j'ai produit est dans `/tmp/claude-0/-home-user-hypotrail/d627b9a6-d196-5d88-8cd2-a6e477a31532/scratchpad/v03-ui-review/` :
- `shots/` : 384 captures pleine page. Couverture : 4 études capturées (split, cv, families, regression) × 6 onglets × {420, 900} × {light-modern, dark-modern, hc}, plus 1280 en light, en EN et en FR. Les variantes `-open` ont toutes les disclosures ouvertes.
- `parts/` et `parts420/` : tranches des pages longues.
- `crops/` : zooms sur les graphiques.
- `text/` : texte visible de chaque onglet.
- `mock-parts/` : maquettes découpées.
- Scripts : `tools/test_shoot.py`, qui réutilise `conftest.py` et `panel_cases.py` du dépôt.

La gate structurelle et de contraste est **verte** : `test_webview_gate.py -k "structural or contrast"`, 24 passés. Tous les défauts listés ci-dessous passent donc la gate.

### Verdict en 5 lignes
1. Le système visuel est en place : tokens, cartes, chips pleins, graphiques fluides, rien ne déborde à 420 px, Dark et HC propres. On est loin du « journal d'audit » de la revue précédente.
2. La hiérarchie des maquettes, elle, n'est pas reprise. L'onglet Preuves enterre la réponse : le chiffre final arrive après le registre, le développement, les variantes et les familles. Overview et EDA font 3 000 à 7 400 px.
3. Le français est une traduction de surface. Pas de virgule décimale (`38.0%`, `3,617`), dates US (`10/21/2026, 12:17:21 PM`), « : » collés, et des fautes : « à les », « 1 variantes », « de AUC ».
4. Il reste des contradictions de contenu qu'un junior ne peut pas résoudre seul : la carte familles dit « Rester linéaire » alors que la règle d'une erreur type retient le gradient boosting, et des lignes « training rows » apparaissent dans une étude CV.
5. La gate FR ne prouve presque rien : toutes les études capturées sont `language: en`. Aucune étude française réelle n'est rendue.

### Conformité aux maquettes, onglet par onglet (900 px, light, FR sauf mention)

**Overview : partiellement conforme.**
- Conformes : la carte héros, la barre de parcours avec ses libellés courts et la note « étape revenue », les limites tagguées, et « Comment fonctionne ce panneau ».
- Écarts :
  - l'en-tête tient sur 2 lignes (`Étude : … révision 48 lu par la CLI` plus le chip « Expérimental · option activée ») au lieu d'une ;
  - les 4 tuiles chiffrées de la maquette manquent ;
  - « Où nous en sommes » double le parcours ;
  - les livrables sont dans l'Overview, pas dans un onglet Fichiers.
- Captures :
  - `/tmp/claude-0/-home-user-hypotrail/d627b9a6-d196-5d88-8cd2-a6e477a31532/scratchpad/v03-ui-review/parts/binary-overview-light-modern-900-fr.p0.png`
  - `/tmp/claude-0/-home-user-hypotrail/d627b9a6-d196-5d88-8cd2-a6e477a31532/scratchpad/v03-ui-review/parts/binary-overview-light-modern-900-fr.p1.png`
  - `/tmp/claude-0/-home-user-hypotrail/d627b9a6-d196-5d88-8cd2-a6e477a31532/scratchpad/v03-ui-review/mock-parts/overview-light-900.p0.png`

**Données et EDA : la structure est conforme, le contenu l'est moins.**
- Présents : le zero-tile avec bins log, le rate-by en point + intervalle + bande nulle + n, la matrice de corrélation et le toggle « Sens EN | FR ».
- Écarts :
  - les titres sont les questions génériques du moteur, en anglais (« How are the values of previous distributed… ») ; la maquette avait des questions métier ;
  - la carte asymétrique n'a ni unité ni « Manquants », et le dernier bin n'est pas borné (`1 · 3 · 10 ·` puis rien jusqu'au Max 25) ;
  - « EIQ 0–0 » n'apporte rien ;
  - des cartes demi-largeur sont orphelines, avec un trou à droite.
- Captures :
  - `/tmp/claude-0/-home-user-hypotrail/d627b9a6-d196-5d88-8cd2-a6e477a31532/scratchpad/v03-ui-review/parts/binary-eda-light-modern-900-fr.p2.png`
  - `…/parts/binary-eda-light-modern-900-fr.p4.png`
  - `…/parts/binary-eda-light-modern-900-fr.p5.png`
  - `…/parts/binary-eda-light-modern-900-fr.p6.png`
  - `…/crops/skewed-420-fr.png`
  - `…/crops/corr-420-fr.png`
  - `…/crops/rateby-420-fr.png`

**Décisions : R23 et R25 sont respectées** (lecture seule, plus récent en premier). Mais :
- l'historique est un tableau à 3 colonnes, pas la timeline de la maquette ;
- les règles du mode sont répétées en entier (déjà présentes sur l'Overview) ;
- le titre de la proposition est en anglais (« Choose a decision policy ») ;
- le bouton mélange les langues : « Voir the decision-rule evaluation → ».
- Captures : `/tmp/claude-0/-home-user-hypotrail/d627b9a6-d196-5d88-8cd2-a6e477a31532/scratchpad/v03-ui-review/parts/binary-decisions-light-modern-900-fr.p0.png` et `.p1.png`.

**Preuves : non conforme.**
- La maquette ouvre sur le héros « preuve finale contre votre critère (+5) », puis le 2×2 et l'exposition.
- L'implémentation ouvre sur la carte test final, puis le registre d'exposition complet (tableau à 4 colonnes avec `init.structure`, `fit.variant`…), le développement, les variantes et les familles. La « Preuve finale » arrive vers 5 000 px et n'est jamais comparée au critère.
- Captures :
  - `/tmp/claude-0/-home-user-hypotrail/d627b9a6-d196-5d88-8cd2-a6e477a31532/scratchpad/v03-ui-review/parts/cv-evidence-light-modern-900-fr.p0.png`
  - `…/parts/families-evidence-light-modern-900-fr.p2.png`
  - `…/parts/families-evidence-light-modern-900-fr.p3.png`
  - `…/crops/fam-dev-420-fr.png`

**Et si ? :** cet onglet n'a pas de maquette. Les étiquettes de la courbe de gain se chevauchent : « 9%: 30% » et « 10%: 31% » s'écrasent l'une sur l'autre.
- Captures : `/tmp/claude-0/-home-user-hypotrail/d627b9a6-d196-5d88-8cd2-a6e477a31532/scratchpad/v03-ui-review/parts/binary-whatif-light-modern-900-fr.p0.png` et `…/parts/regression-whatif-light-modern-900-en.p0.png`.

**Apprendre : pas de maquette.**
- La fiche notion est vide : un titre anglais plus « Ce texte apparaît quand… ».
- Les prédictions et leurs boutons sont en anglais (« Common / Rare / Not sure »).
- Capture : `/tmp/claude-0/-home-user-hypotrail/d627b9a6-d196-5d88-8cd2-a6e477a31532/scratchpad/v03-ui-review/parts/binary-learn-light-modern-900-fr.p0.png`.

### Défauts classés

**A. Vérifiés par capture ou texte rendu**

1. **Contradiction familles / variantes** (families, Preuves) :
   - la carte variantes dit « La règle d'une erreur type retient : Gradient boosting » (+0.022 ± 0.004) ;
   - juste en dessous, la carte familles dit « Rester linéaire… restez sur le modèle linéaire » et classe EBM et boosting « hors de la liste courte », alors qu'ils ont été ajustés et ont chacun leur carte ;
   - le tableau AUC voisin les nomme « deuxième / troisième variante » et la section développement « La variante face au candidat » n'en compare qu'une.

   Un junior ne peut pas réconcilier tout ça.
2. **Ordre de l'onglet Preuves** : il ne répond pas à « qu'est-ce que l'étude peut affirmer ? » avant plusieurs écrans (`views/evidence.js:1165-1167`).
3. **Registre d'exposition faux après ouverture** (cv) : il garde « Scellé, non lu… Personne ne les a lues · 904 » à côté de « Test final, mesuré une fois · 904 », alors que l'en-tête dit « Test final ouvert ».
4. **R17 / R15 non résolues sous CV** :
   - la carte s'intitule « OUTCOME RATE · DEVELOPMENT ROWS », mais son graphique dit « Outcome y, training rows » ;
   - le lead de l'onglet EDA, la ligne cible et les questions disent aussi « training rows » ;
   - le Why dit « In this study's training rows… ».
5. **Barres du taux cible en unités mélangées** : « yes 11.5% » face à « autres lignes 2,239 » (`views/eda.js:312-315`).
6. **Format français** :
   - décimales avec un point : `38.0%`, `0.2 ou plus`, `Moyenne 41.24` ;
   - milliers avec une virgule : `3,617`, `2,000 réplications` ;
   - pas d'espace avant `%` ;
   - date US à la seconde : « le 10/21/2026, 12:17:21 PM » (`format.js:74`, `toLocaleString()` ignore la langue du panneau) ;
   - « : » collés : « En bref: », « Cible y: », « Détecteur de fuite: », « le moment de la prédiction: », « Méthodes: » (`views/overview.js:171`, `views/eda.js:277`, `views/eda.js:553`, `views/decisions.js:167`, `:231`, `:502`).
7. **Fautes en français** :
   - « Modèle et référence à les 100 premières lignes » (`copy-fr/whatif.js:34`, `:37`) ;
   - « 1 variantes sur 3 », « 0 restantes » (`copy-fr/evidence.js:237-238`) ;
   - « 1 incertaines » (`copy-fr/junior.js:192`) ;
   - « environ 0.003 de AUC », « Perte de AUC » (`copy-fr/evidence.js:253`, `:301`) ;
   - « Différence de Précision » ;
   - « deux valeurs · 2 valeurs » ;
   - « unknown (special value) (petit) n 19 » ;
   - guillemets « «Does…» » sans espaces ;
   - « Précision moyenne » pour l'average precision, déjà signalé en R23 et toujours là.
8. **Texte non traduit sans marqueur « (en) »** :
   - titres d'étapes et de décisions : survol du parcours, historique, carte de proposition ;
   - « Voir the decision-rule evaluation » (`views/decisions.js:49`, mots anglais codés en dur) ;
   - groupes du dictionnaire (« LAST CONTACT OF THIS CAMPAIGN », « OUTCOME ») ;
   - unités (`years`, `days`, `seconds`) ;
   - sens des valeurs spéciales ;
   - prédictions de l'onglet Apprendre.
9. **Id brut** : « fit.variant » s'affiche comme nom de modèle dans Et si ? en régression. Le libellé manque dans `copy/whatif.js:82` et `copy-fr/whatif.js:79`. Les clés `fit.variant:2` et `:3` manquent aussi dans la table binaire, ligne 40.
10. **Le parcours affiche « pause 1 · vos mots » pour un simple « oui » en mode guidé.** Le code assimile un oui (endorsed) aux propres mots du junior (`views/overview.js:219` ; libellé `copy-fr/overview.js:93`, `copy/overview.js:106`). Ça contredit la règle R27 affichée plus bas.
11. **Lisibilité des graphiques** :
    - à 420 px, le rate-by tasse le tracé à environ 140 px et coupe « n / 510 » sur deux lignes ;
    - les tableaux se transforment en cartes clé · valeur sur 1 700 px (développement) ;
    - l'histogramme `age` a des graduations `32.60 / 46.20` ;
    - le rate-by a des graduations `0% / 22% / 45%` ;
    - la boîte des résidus (régression) n'a que min et max ;
    - en HC, les cases vides de la diagonale de la corrélation ressortent plus que les données ;
    - les valeurs spéciales affichent le graphique et aussi le tableau complet, toujours ouvert.
12. **Bruit résiduel** :
    - « Calculé : un résultat. » (chip « réévalué ») dans « Depuis votre dernière session » ;
    - « Il répond à… » plus un second bouton « Le montrer » sans titre dans « Lancer un autre graphique ».

**B. Inférés (non vérifiés en VS Code réel)**
- Les états « Lecture de ce que changerait une confirmation… », « Mise à jour… », « Lecture du brouillon du moteur… » et « Vérifications en cours… » ne se résolvent jamais dans le harnais, parce que `open_case` ne livre ni `preview_effects`, ni `preview`, ni `check`. La gate et les baselines ne couvrent donc pas ces blocs résolus.
- Le rendu « a-t-il » qui ressemble à du monospace est un artefact de police du harnais : le style calculé est bien `system-ui`. Ce n'est pas un défaut.
- Dans une vraie étude `--lang fr`, les textes moteur seraient en français (WP-C/WP-V). Aucune capture ne le prouve.

### Le panneau s'explique-t-il à un junior ?
En partie.
- Points positifs : la carte « Comment fonctionne ce panneau », une phrase d'introduction par onglet, « Pourquoi ? » partout et un vrai effort de pédagogie.
- Points faibles :
  - « pause 3 », « Registre d'exposition », « Configurations évaluées : 4 » et « Optimisme de sélection » arrivent sans le terme expliqué d'abord ;
  - Preuves et EDA sont des murs à faire défiler ;
  - le junior ne trouve pas « est-ce que ça marche ? » dans le premier écran de Preuves.

### Ce qui fait encore doublon avec le chat (ou avec le panneau lui-même)
- La proposition, son résumé « En bref » et le texte sur ce qu'elle change : répétés sur l'Overview et dans Décisions.
- Les règles du mode de réponse en entier, deux fois.
- Les limites et « Où nous en sommes », qui reprennent le récapitulatif de l'agent.
- La phrase « Répondez dans le chat », présente sur trois cartes.

Le reste (graphiques, registre, variantes) est propre au panneau.

### 5 corrections prioritaires
1. **Réordonner Preuves** (`views/evidence.js:1165-1167`) : un héros « preuve finale contre votre critère », ou « scellé : voici le meilleur chiffre de développement contre +5 », puis le 2×2, puis variantes et familles. Mettre le registre sous disclosure. Corriger la ligne « Scellé, non lu » une fois le test ouvert (`ledger`, `views/evidence.js:386`).
2. **Rendre familles et variantes cohérentes** (`views/evidence.js:787` `familiesCard`, `:685` `selectionCard`, `:910`) :
   - quand une famille a été ajustée, ne plus dire « hors de la liste courte » ni « restez linéaire » ;
   - dire explicitement « les diagnostics linéaires ne signalent rien, mais la comparaison des variantes retient X » ;
   - utiliser un seul nommage (« Gradient boosting ») partout, AUC et développement compris.
3. **Ajouter une couche locale d'affichage pour le français**, sans toucher aux valeurs citées :
   - `format.js:49`, `:55` et `:63` : virgule décimale, espace fine pour les milliers et avant `%` ;
   - `format.js:74` : date selon `HT.language()` ;
   - remplacer les `': '` codés en dur (`views/overview.js:171`, `views/eda.js:277`, `:553`, `views/decisions.js:167`, `:231`, `:502`) par une clé de copy.
4. **Lot de copy FR et ids** :
   - `copy-fr/whatif.js:34` (« aux ») ;
   - `copy-fr/evidence.js:237-238`, `:253`, `:301` (pluriels, « d'AUC ») ;
   - `copy-fr/junior.js:192` ;
   - `views/decisions.js:49` (mots anglais → copy) ;
   - `copy/whatif.js:82` et `copy-fr/whatif.js:79` (`fit.variant`) ;
   - `views/overview.js:219` (endorsed → « confirmé », pas « vos mots »).
5. **Terminer R17 sous CV** :
   - `copy/eda.js:25-26`, `:149`, `:239-240`, `:270-271`, le titre du graphique cible et le lead de l'onglet EDA dans `copy/core.js` : mots selon le mode de split ;
   - `views/eda.js:312-315` : barres cible dans une seule unité, en % ;
   - histogramme : unité, manquants, borne du dernier bin.

### 3 idées que l'équipe n'aurait sans doute pas
1. **Capturer une vraie étude française** (`init --lang fr`) et la passer dans la gate et les baselines. Aujourd'hui « FR » veut dire « panneau FR sur étude EN », ce qui masque exactement ce que l'owner verra. Ajouter à la gate une sonde « nombre au format FR » qui ne regarde que l'affichage, en laissant `data-value` intact.
2. **Assertions de cohérence entre cartes**, en plus des assertions de style. Sous CV, aucun texte visible ne contient « training/entraînement ». Si la recommandation des familles diffère du choix d'une erreur type, une phrase de raccord doit exister. Si `final_test` est ouvert, aucune ligne ne dit « Personne ne les a lues ». La gate vérifie la forme, jamais le sens.
3. **Budget « réponse au-dessus de la ligne de flottaison »** : pour chaque onglet, mesurer la position y du premier élément qui porte la conclusion (`[data-finding]` ou un chiffre héros) et échouer au-delà de 800 px. Ça transforme « la hiérarchie des maquettes » en contrainte testable : aujourd'hui Preuves échouerait vers 5 000 px.

### Vérifié et inféré
- **Vérifié** : tout ce qui cite une capture ou une ligne de `text/*.txt`, et les références file:line, lues dans le code. La gate est verte au tip.
- **Inféré** :
  - le comportement réel des blocs « Lecture… » en VS Code ;
  - le format de date sous une UI VS Code française (`toLocaleString` suit la locale de l'hôte, pas le toggle) ;
  - les textes moteur en français dans une étude FR.