# Dictionnaire des tables préparées

## orders_analysis

Grain : une ligne par commande, avec résultats rétrospectifs et indicateurs d'incohérence de dates.

| Colonne | Type | Valeurs manquantes |
|---|---|---:|
| `order_id` | str | 0 |
| `customer_id` | str | 0 |
| `order_status` | str | 0 |
| `order_purchase_timestamp` | datetime64[us] | 0 |
| `order_approved_at` | datetime64[us] | 160 |
| `order_delivered_carrier_date` | datetime64[us] | 1783 |
| `order_delivered_customer_date` | datetime64[us] | 2965 |
| `order_estimated_delivery_date` | datetime64[us] | 0 |
| `customer_unique_id` | str | 0 |
| `customer_zip_code_prefix` | string | 0 |
| `customer_city` | str | 0 |
| `customer_state` | str | 0 |
| `item_count` | Int64 | 0 |
| `product_count` | Int64 | 0 |
| `seller_count` | Int64 | 0 |
| `item_price_total` | float64 | 775 |
| `freight_total` | float64 | 775 |
| `product_weight_mean_g` | float64 | 791 |
| `product_volume_mean_cm3` | float64 | 791 |
| `primary_category` | str | 0 |
| `single_seller_id` | str | 2053 |
| `payment_rows` | Int64 | 0 |
| `payment_type_count` | Int64 | 0 |
| `payment_installments_max` | float64 | 1 |
| `payment_total` | float64 | 1 |
| `review_id` | str | 768 |
| `review_score` | float64 | 768 |
| `review_comment_title` | str | 87891 |
| `review_comment_message` | str | 58666 |
| `review_creation_date` | datetime64[us] | 768 |
| `review_answer_timestamp` | datetime64[us] | 768 |
| `has_written_comment` | bool | 0 |
| `is_poor_review` | Int64 | 768 |
| `has_items` | boolean | 0 |
| `is_multi_seller` | boolean | 0 |
| `customer_lat` | float64 | 279 |
| `customer_lng` | float64 | 279 |
| `customer_has_geo` | bool | 0 |
| `purchase_month` | str | 0 |
| `purchase_weekday` | Int64 | 0 |
| `purchase_hour` | Int64 | 0 |
| `approval_delay_hours` | float64 | 160 |
| `delivery_observed` | bool | 0 |
| `delivery_duration_days` | float64 | 2971 |
| `flag_carrier_before_approval` | bool | 0 |
| `flag_delivered_before_carrier` | bool | 0 |
| `flag_delivered_status_missing_date` | bool | 0 |
| `flag_delivery_date_on_undelivered_status` | bool | 0 |
| `flag_any_date_issue` | bool | 0 |
| `late_days` | float64 | 2965 |
| `late_label_eligible` | bool | 0 |
| `is_late` | Int64 | 2971 |
| `poor_review_label_eligible` | bool | 0 |

## orders_model_base

Grain : une ligne par commande, variables disponibles à l'approbation et cibles séparées.

| Colonne | Type | Valeurs manquantes |
|---|---|---:|
| `order_id` | str | 0 |
| `order_purchase_timestamp` | datetime64[us] | 0 |
| `order_approved_at` | datetime64[us] | 160 |
| `purchase_month` | str | 0 |
| `purchase_weekday` | Int64 | 0 |
| `purchase_hour` | Int64 | 0 |
| `approval_delay_hours` | float64 | 160 |
| `customer_state` | str | 0 |
| `customer_city` | str | 0 |
| `customer_zip_code_prefix` | string | 0 |
| `customer_lat` | float64 | 279 |
| `customer_lng` | float64 | 279 |
| `customer_has_geo` | bool | 0 |
| `has_items` | boolean | 0 |
| `item_count` | Int64 | 0 |
| `product_count` | Int64 | 0 |
| `seller_count` | Int64 | 0 |
| `is_multi_seller` | boolean | 0 |
| `single_seller_id` | str | 2053 |
| `primary_category` | str | 0 |
| `item_price_total` | float64 | 775 |
| `freight_total` | float64 | 775 |
| `product_weight_mean_g` | float64 | 791 |
| `product_volume_mean_cm3` | float64 | 791 |
| `payment_rows` | Int64 | 0 |
| `payment_type_count` | Int64 | 0 |
| `payment_installments_max` | float64 | 1 |
| `payment_total` | float64 | 1 |
| `late_label_eligible` | bool | 0 |
| `is_late` | Int64 | 2971 |
| `poor_review_label_eligible` | bool | 0 |
| `is_poor_review` | Int64 | 768 |

## multi_seller_order_links

Grain : une ligne par couple (commande multi-vendeurs, vendeur) ; retard et avis restent des attributs de la commande.

| Colonne | Type | Valeurs manquantes |
|---|---|---:|
| `order_id` | str | 0 |
| `seller_id` | str | 0 |
| `seller_item_count` | int64 | 0 |
| `seller_product_count` | int64 | 0 |
| `seller_price_total` | float64 | 0 |
| `seller_freight_total` | float64 | 0 |
| `seller_shipping_limit_max` | datetime64[us] | 0 |
| `seller_primary_category` | str | 0 |
| `seller_price_share` | Float64 | 0 |
| `purchase_month` | str | 0 |
| `order_status` | str | 0 |
| `customer_state` | str | 0 |
| `order_seller_count` | Int64 | 0 |
| `order_is_late` | Int64 | 6 |
| `order_late_days` | float64 | 6 |
| `order_review_score` | float64 | 28 |
| `order_is_poor_review` | Int64 | 28 |
| `order_has_written_comment` | bool | 0 |
| `attribution_note` | str | 0 |

## seller_monthly_kpis

Grain : une ligne par vendeur et mois, commandes mono-vendeur.

| Colonne | Type | Valeurs manquantes |
|---|---|---:|
| `purchase_month` | str | 0 |
| `single_seller_id` | str | 0 |
| `order_count` | int64 | 0 |
| `delivered_order_count` | int64 | 0 |
| `late_eligible_count` | int64 | 0 |
| `late_order_count` | Int64 | 0 |
| `observed_delivery_count` | int64 | 0 |
| `delivery_duration_mean_days` | float64 | 382 |
| `delivery_duration_median_days` | float64 | 382 |
| `reviewed_order_count` | int64 | 0 |
| `poor_review_count` | Int64 | 0 |
| `average_review_score` | float64 | 37 |
| `written_comment_count` | int64 | 0 |
| `item_price_total` | float64 | 0 |
| `freight_total` | float64 | 0 |
| `late_rate` | Float64 | 382 |
| `poor_review_rate` | Float64 | 37 |
| `written_comment_rate` | Float64 | 37 |
| `is_complete_period` | bool | 0 |
| `period_status` | str | 0 |

## monthly_business_kpis

Grain : une ligne par mois d'achat, y compris les mois sans commande.

| Colonne | Type | Valeurs manquantes |
|---|---|---:|
| `purchase_month` | str | 0 |
| `order_count` | int64 | 0 |
| `delivered_order_count` | int64 | 0 |
| `late_eligible_count` | int64 | 0 |
| `late_order_count` | int64 | 0 |
| `observed_delivery_count` | int64 | 0 |
| `delivery_duration_mean_days` | float64 | 3 |
| `delivery_duration_median_days` | float64 | 3 |
| `reviewed_order_count` | int64 | 0 |
| `poor_review_count` | int64 | 0 |
| `average_review_score` | float64 | 1 |
| `written_comment_count` | int64 | 0 |
| `item_price_total` | float64 | 0 |
| `freight_total` | float64 | 0 |
| `late_rate` | Float64 | 3 |
| `poor_review_rate` | Float64 | 1 |
| `written_comment_rate` | Float64 | 1 |
| `is_complete_period` | bool | 0 |
| `period_status` | str | 0 |
| `date_issue_count` | int64 | 0 |

## state_monthly_kpis

Grain : une ligne par mois et État client.

| Colonne | Type | Valeurs manquantes |
|---|---|---:|
| `purchase_month` | str | 0 |
| `customer_state` | str | 0 |
| `order_count` | int64 | 0 |
| `delivered_order_count` | int64 | 0 |
| `late_eligible_count` | int64 | 0 |
| `late_order_count` | Int64 | 0 |
| `observed_delivery_count` | int64 | 0 |
| `delivery_duration_mean_days` | float64 | 9 |
| `delivery_duration_median_days` | float64 | 9 |
| `reviewed_order_count` | int64 | 0 |
| `poor_review_count` | Int64 | 0 |
| `average_review_score` | float64 | 0 |
| `written_comment_count` | int64 | 0 |
| `item_price_total` | float64 | 0 |
| `freight_total` | float64 | 0 |
| `late_rate` | Float64 | 9 |
| `poor_review_rate` | Float64 | 0 |
| `written_comment_rate` | Float64 | 0 |
| `is_complete_period` | bool | 0 |
| `period_status` | str | 0 |

## category_monthly_kpis

Grain : une ligne par mois et catégorie principale.

| Colonne | Type | Valeurs manquantes |
|---|---|---:|
| `purchase_month` | str | 0 |
| `primary_category` | str | 0 |
| `order_count` | int64 | 0 |
| `delivered_order_count` | int64 | 0 |
| `late_eligible_count` | int64 | 0 |
| `late_order_count` | Int64 | 0 |
| `observed_delivery_count` | int64 | 0 |
| `delivery_duration_mean_days` | float64 | 34 |
| `delivery_duration_median_days` | float64 | 34 |
| `reviewed_order_count` | int64 | 0 |
| `poor_review_count` | Int64 | 0 |
| `average_review_score` | float64 | 1 |
| `written_comment_count` | int64 | 0 |
| `item_price_total` | float64 | 0 |
| `freight_total` | float64 | 0 |
| `late_rate` | Float64 | 34 |
| `poor_review_rate` | Float64 | 1 |
| `written_comment_rate` | Float64 | 1 |
| `is_complete_period` | bool | 0 |
| `period_status` | str | 0 |

## geo_zip_centroid

Grain : une ligne par préfixe postal ; centroïde calculé sur les points situés au Brésil.

| Colonne | Type | Valeurs manquantes |
|---|---|---:|
| `geolocation_zip_code_prefix` | string | 0 |
| `latitude` | float64 | 5 |
| `longitude` | float64 | 5 |
| `city` | str | 5 |
| `state` | str | 5 |
| `source_observation_count` | int64 | 0 |
| `excluded_outside_points` | int64 | 0 |
| `is_within_brazil` | bool | 0 |

