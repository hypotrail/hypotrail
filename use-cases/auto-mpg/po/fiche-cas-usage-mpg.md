# Fiche du cas d'usage : estimer la consommation dès la fiche technique

Confluence > Espace « Produit véhicules » > Cas d'usage data > Estimation de la consommation

Rédigée par : le PO Produit véhicules · Statut : prête pour l'étude · Version 1.2

**SCÉNARIO FICTIF pour la simulation de l'atelier : l'entreprise, les équipes et les chiffres métier sont inventés. Seule la provenance des données est réelle (jeu public UCI Auto MPG).**

## 1. Contexte et problème

L'équipe Conception doit annoncer la consommation d'un nouveau modèle dès que sa fiche technique est validée, environ six mois avant les essais sur route.

Aujourd'hui, un ingénieur l'estime à la main en comparant avec un modèle proche de la gamme. Sur les deux dernières années, l'écart moyen constaté entre cette estimation et la consommation mesurée aux essais est d'environ 4,5 mpg (écart absolu moyen).

## 2. Décision que l'estimation doit éclairer

- Quels prototypes envoyer d'abord aux essais de consommation : nous avons une vingtaine d'essais par an, et ils sont chers.
- Quel chiffre provisoire afficher dans les premières fiches produit, avant les essais.

## 3. Utilisateurs

- Les ingénieurs de conception, qui saisissent la fiche technique.
- Le chef de produit, qui arbitre l'ordre des essais et valide les fiches produit.

<!-- page -->

## 4. Objectif

Estimer la consommation (en mpg) à partir de la fiche technique seule, nettement mieux que l'estimation manuelle : nous visons un écart moyen d'environ 3,5 mpg (écart absolu moyen), avec une fourchette autour de chaque estimation.

## 5. Mise en production envisagée

Un service de prédiction appelé par l'outil de conception à chaque nouvelle fiche technique. L'estimation et sa fourchette sont relues par un ingénieur avant tout usage. Le modèle serait réentraîné chaque année avec les nouveaux essais.

## 6. Données

- Source : le jeu « Auto MPG » du UCI Machine Learning Repository (issu de StatLib, Carnegie Mellon ; utilisé par Quinlan en 1993). 398 modèles de voitures vendus aux États-Unis de 1970 à 1982, une ligne par modèle et par année.
- Colonnes : consommation (mpg), cylindres, cylindrée, puissance, poids, accélération, année du modèle, origine, nom du modèle.
- Dans notre scénario, ce jeu sert d'historique en attendant l'extraction de l'entrepôt interne des essais. Les données sont publiques et déjà très explorées : aucune ligne n'est vraiment « jamais vue ».

## 7. Coût d'une erreur

Annoncer une consommation trop basse nous expose à une correction publique. Une estimation trop haute peut faire écarter à tort un prototype des essais. Les grosses erreurs sur un modèle phare sont particulièrement gênantes.

<!-- page -->

## 8. Contraintes

- L'estimation doit être disponible dès la validation de la fiche technique, sans aucune mesure sur route.
- Elle doit rester compréhensible par les ingénieurs qui la relisent.

## 9. Hors périmètre

- L'homologation officielle : elle reste mesurée sur route.
- Expliquer les causes de la consommation.

## 10. Risques identifiés

- Les voitures récentes diffèrent des anciennes : le modèle peut dériver.
- Les données s'arrêtent en 1982.

## 11. Contacts

PO Produit véhicules (rédaction) · Responsable des essais (calendrier des essais).
