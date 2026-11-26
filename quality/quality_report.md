# Rapport de qualité des données

Statut global : **RÉUSSI** — 39/39 contrôles réussis.

| Catégorie | Contrôle | Observé | Attendu | Résultat |
|---|---|---:|---:|---|
| Sources | source_file_count | 9 | 9 | OK |
| Sources | source_sha256_unchanged | identiques | identiques | OK |
| Grain commande | orders_rows | 99441 | 99441 | OK |
| Grain commande | duplicate_order_id | 0 | 0 | OK |
| Agrégation avant jointure | item_price_total_matches_raw | 13591643.7 | 13591643.7 | OK |
| Agrégation avant jointure | freight_total_matches_raw | 2251909.54 | 2251909.54 | OK |
| Agrégation avant jointure | payment_total_matches_raw | 16008872.12 | 16008872.12 | OK |
| Intégrité référentielle | orphan_items_to_orders | 0 | 0 | OK |
| Intégrité référentielle | orphan_items_to_products | 0 | 0 | OK |
| Intégrité référentielle | orphan_items_to_sellers | 0 | 0 | OK |
| Intégrité référentielle | orphan_payments_to_orders | 0 | 0 | OK |
| Intégrité référentielle | orphan_reviews_to_orders | 0 | 0 | OK |
| Intégrité référentielle | orphan_orders_to_customers | 0 | 0 | OK |
| Couverture | orders_without_items_labelled_no_items | 775 | 775 | OK |
| Couverture | orders_without_review_kept | 768 | 768 | OK |
| Avis | selected_review_one_per_order | 98673 | 98673 | OK |
| Avis | written_comment_documents | 40950 | 40950 | OK |
| Avis | all_free_text_documents | 42687 | 42687 | OK |
| Retard | late_eligible_count | 96470 | 96470 | OK |
| Retard | late_order_count | 6534 | 6534 | OK |
| Retard | is_late_missing_when_not_eligible | 0 | 0 | OK |
| Durée de livraison | delivery_duration_observed | 96470 | 96470 | OK |
| Multi-vendeurs | multi_seller_orders | 1278 | 1278 | OK |
| Multi-vendeurs | multi_seller_links_cover_all_orders | 1278 | 1278 | OK |
| Multi-vendeurs | multi_seller_price_share_sums_to_1 | oui | oui | OK |
| Multi-vendeurs | seller_kpis_exclude_multi_seller | 97388 | 97388 | OK |
| Fuite d'information | model_base_rows | 99441 | 99441 | OK |
| Fuite d'information | model_base_forbidden_columns | aucune | aucune | OK |
| Périodes | monthly_kpis_no_missing_month | 26 | 26 | OK |
| Périodes | sparse_months_flagged | 2016-09, 2016-11, 2016-12, 2018-09, 2018-10 | 2016-09, 2016-11, 2016-12, 2018-09, 2018-10 | OK |
| Périodes | monthly_order_sum | 99441 | 99441 | OK |
| Dates (signalées) | flag_carrier_before_approval | 1359 | 1359 | OK |
| Dates (signalées) | flag_delivered_before_carrier | 23 | 23 | OK |
| Dates (signalées) | flag_delivered_status_missing_date | 8 | 8 | OK |
| Dates (signalées) | flag_delivery_date_on_undelivered_status | 6 | 6 | OK |
| Géolocalisation | geo_centroids_outside_brazil | 0 | 0 | OK |
| Géolocalisation | customers_with_geo | 99162 | information | OK |
| Remise au transporteur | late_handover_label_only_when_eligible | 97657 étiquetées / 97657 éligibles | égalité | OK |
| Remise au transporteur | shipping_limit_matches_raw | 98666 | 98666 | OK |

## Règles appliquées

- Les articles et paiements sont agrégés au niveau commande avant les jointures ; les totaux sont égaux aux fichiers bruts.
- Un seul avis est retenu pour les cibles commande : le dernier `review_answer_timestamp`, puis `review_id` pour départager. Tout le texte libre (messages et titres) reste disponible dans `reviews_text.jsonl.gz`.
- Les 775 commandes sans article portent la catégorie `no_items` ; `unknown` est réservé aux produits sans catégorie.
- Le retard compare les jours calendaires de livraison réelle et promise. Une commande sans date réelle n'est jamais classée automatiquement à l'heure.
- La durée de livraison n'est calculée que pour les commandes au statut `delivered` avec date réelle (96 470).
- Les 1 278 commandes multi-vendeurs sont exclues des KPI vendeurs et analysées à part dans `multi_seller_order_links.csv.gz`, sans attribution du retard ou de l'avis à un vendeur.
- Les variables futures restent dans `orders_analysis.csv.gz`, mais sont exclues de `orders_model_base.csv.gz`.
- Les mois de moins de 100 commandes, et le mois sans commande 2016-11, sont marqués `is_complete_period = False` dans toutes les tables KPI. Ils doivent être exclus des graphiques de tendance.
- Les incohérences de dates sont signalées par des colonnes `flag_*`, jamais corrigées ni supprimées.
- Géolocalisation : 261831 points dupliqués retirés et 33 points hors du Brésil exclus du calcul des centroïdes ; 5 préfixes n'ont plus de point valide.
