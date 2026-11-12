# ShopInsight

Projet REHEARSE (CRISP-DM) sur le jeu de données e-commerce brésilien Olist : préparation des données, traduction locale des avis en français et premiers modèles.

> **Données non incluses.** Le dossier `data/` (≈ 200 Mo) n'est pas versionné. Téléchargez l'archive Olist sur Kaggle
> ([Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)),
> puis reconstruisez tout avec les commandes de la section « Exécution » ci-dessous.

## REHEARSE - Phase 2 : collecte, stockage et préparation des données

Cette phase prépare les données nécessaires aux cinq objectifs validés :

1. anticiper les commandes problématiques ;
2. analyser les avis clients ;
3. examiner les performances vendeurs ;
4. assister le client à partir de faits et d'expériences comparables ;
5. automatiser les KPI, les dashboards et le reporting.

## Types de données couverts

| Type | Données | Stockage |
|---|---|---|
| Structurées | commandes, clients, articles, paiements, produits, vendeurs, géolocalisation, notes | CSV source et tables CSV compressées |
| Semi-structurées | manifeste des sources, contrôles qualité, documents d'avis enrichis de métadonnées | JSON et JSONL compressé |
| Non structurées | titres et commentaires libres des avis clients, principalement en portugais | champ `text` dans `reviews_text.jsonl.gz` |

Le JSONL des avis est dérivé des fichiers Olist. Il ne constitue pas une nouvelle source et n'invente aucun commentaire.

## Organisation du stockage

```text
data/
  raw/       fichiers Olist originaux, non modifiés
  bronze/    inventaire, empreintes SHA-256 et profil des sources
  silver/    tables nettoyées et jointes pour l'analyse et les modèles
  gold/      KPI prêts pour dashboards et agent de reporting
quality/     contrôles exécutés et rapport de qualité
docs/        dictionnaire détaillé des tables préparées
src/         pipeline reproductible (prepare_data.py) et validation indépendante (validate_outputs.py)
```

## Jeux préparés principaux

- `orders_analysis.csv.gz` : une ligne par commande avec les résultats rétrospectifs et les indicateurs d'incohérence de dates. Utiliser pour l'analyse descriptive.
- `orders_model_base.csv.gz` : variables disponibles au moment de l'approbation et cibles séparées. Utiliser comme point de départ des modèles OM1 et OM4.
- `reviews_text.jsonl.gz` : tout le texte libre des avis (42 687 documents, dont 40 950 avec un message). Utiliser pour OM2 et la recherche d'avis de OM4.
- `multi_seller_order_links.csv.gz` : une ligne par commande multi-vendeurs et vendeur (2 622 lignes, 1 278 commandes). Utiliser pour étudier les plaintes de ces commandes à part, dans OM3.
- `seller_monthly_kpis.csv.gz` : indicateurs mensuels sur les commandes mono-vendeur. Utiliser pour OM3.
- `monthly_business_kpis.csv`, `state_monthly_kpis.csv.gz` et `category_monthly_kpis.csv.gz` : tables destinées à OM5.
- `geo_zip_centroid.csv.gz` : coordonnées par préfixe postal, calculées sur les points situés au Brésil.
- `metric_catalog.csv` : définition des KPI, formules, populations et objectifs associés.

## Règles de préparation essentielles

- Les articles et paiements sont agrégés avant leur jointure aux commandes ; les totaux restent égaux aux fichiers bruts.
- Un seul avis est sélectionné par commande pour les cibles : le dernier `review_answer_timestamp`, puis `review_id`. Tout le texte libre reste disponible pour le NLP, y compris les avis supplémentaires et les avis n'ayant qu'un titre.
- Un commentaire vide est une donnée manquante, pas un avis positif.
- Une livraison tardive signifie que le jour réel dépasse le jour promis. Les commandes sans date de livraison réelle restent sans étiquette de retard.
- La durée de livraison n'est calculée que pour les commandes au statut `delivered` avec date réelle (96 470).
- Les 775 commandes sans article portent la catégorie `no_items` ; `unknown` désigne uniquement des produits sans catégorie (1 393 commandes).
- `orders_model_base.csv.gz` exclut la livraison réelle, le statut final, les avis et les indicateurs d'incohérence de dates, tous postérieurs à l'approbation.
- Les KPI vendeurs excluent les commandes multi-vendeurs. Celles-ci sont analysées dans `multi_seller_order_links.csv.gz`, où le retard et l'avis restent des attributs de la commande, accompagnés de la part de chaque vendeur dans le montant.
- **Mois partiels** : toutes les tables KPI contiennent `is_complete_period` et `period_status`. Les mois 2016-09, 2016-12, 2018-09 et 2018-10 (moins de 100 commandes) et le mois sans commande 2016-11 sont marqués non complets. Les graphiques de tendance et l'agent de reporting doivent filtrer `is_complete_period == True`.
- **Incohérences de dates** : signalées, jamais corrigées ni supprimées. `flag_carrier_before_approval` (1 359), `flag_delivered_before_carrier` (23), `flag_delivered_status_missing_date` (8), `flag_delivery_date_on_undelivered_status` (6), et `flag_any_date_issue` (1 396 commandes au total).
- **Géolocalisation** : 261 831 points dupliqués retirés ; 33 points hors du Brésil exclus du calcul des centroïdes. 99 162 commandes disposent des coordonnées du client.
- Les évaluations futures devront utiliser un découpage chronologique.

## Exécution

À partir de l'archive Kaggle :

```powershell
python src/prepare_data.py `
  --source-zip chemin\vers\olist_original.zip `
  --project-dir chemin\vers\REHEARSE_Phase2_Data_Preparation
```

Ou à partir des CSV déjà extraits dans `data/raw` :

```powershell
python src/prepare_data.py --raw-dir data\raw --project-dir .
python src/validate_outputs.py --project-dir .
```

Le pipeline vérifie que les 9 fichiers bruts ont les empreintes SHA-256 de la version Olist d'origine.

## Traduction des avis en français

`src/translate_reviews.py` traduit localement les avis portugais vers le français. Aucun avis n'est envoyé à un service en ligne ; seuls les modèles sont téléchargés une fois (environ 600 Mo).

- Modèles : `Helsinki-NLP/opus-mt-ROMANCE-en` puis `Helsinki-NLP/opus-mt-en-fr` (pivot par l'anglais).
- Les 52 516 textes (messages et titres) ne comptent que 39 075 phrases uniques : chacune n'est traduite qu'une fois.
- Le cache `data/silver/translation_cache_fr.jsonl` permet de relancer le script après une interruption sans perdre le travail fait.
- Sortie : `data/silver/reviews_text_fr.jsonl.gz`, avec pour chaque avis `text_original_pt`, `text_fr`, `title_original_pt`, `title_fr`, `translation_status` (`traduit` / `vide` / `à vérifier`) et `translation_flags`. Le fichier `reviews_text.jsonl.gz` n'est pas modifié.
- Contrôle : `quality/translation_report.json`, et `quality/translation_sample_for_review.csv` contenant 200 avis tirés au hasard à vérifier à la main (colonne « correct »).
- Une traduction est marquée `à vérifier` si elle est vide, identique au portugais, de longueur anormale ou répétitive.

```powershell
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-translation.txt
python src/translate_reviews.py --project-dir . --limit 200   # test rapide
python src/translate_reviews.py --project-dir .               # traduction complète
```

## Historique des versions

**V2 (octobre 2026)** : application des étapes de nettoyage prévues dans la présentation et non encore réalisées.

- Nouvelle table `multi_seller_order_links.csv.gz` pour traiter à part les commandes multi-vendeurs.
- Étiquette `no_items` distincte de `unknown`.
- Durée de livraison limitée aux commandes livrées (96 476 → 96 470, cohérent avec la présentation).
- Mois partiels et mois manquant 2016-11 marqués dans toutes les tables KPI.
- Indicateurs d'incohérence de dates.
- Centroïdes géographiques sans points hors du Brésil ; coordonnées client ajoutées.
- Avis n'ayant qu'un titre ajoutés au JSONL (40 950 → 42 687 documents ; `has_message` permet de retrouver les 40 950).
- Contrôles qualité étendus de 7 à 37, et script de validation indépendante.

## Limites

Olist est historique et statique. Le reporting mensuel peut être démontré en révélant progressivement les mois d'achat, mais il ne s'agit pas d'un flux temps réel. Les commentaires sont en portugais ; leur traduction française est produite par `src/translate_reviews.py` (voir plus haut). C'est une traduction automatique : l'échantillon de 200 avis doit être relu avant de s'appuyer dessus pour l'analyse de sentiment. Les thèmes et sentiments nécessitent un échantillon annoté pour une évaluation valide. Le classeur `REHEARSE_Phase2_Summary.xlsx` provient de la V1 : ses chiffres principaux restent valables, mais il n'intègre pas les nouveaux indicateurs.

Source : Brazilian E-Commerce Public Dataset by Olist, Kaggle. Licence affichée par la source : CC BY-NC-SA 4.0.

