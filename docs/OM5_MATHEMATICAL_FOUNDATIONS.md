# Fondements mathématiques OM5

## KPI et temporalité

Pour un taux de retard mensuel :

\[
\hat p_t = \frac{x_t}{n_t},\quad
x_t=\sum_i \mathbb{1}(livraison_i > promesse_i),\quad
n_t=\sum_i \mathbb{1}(livraison_i\ connue\ à\ T)
\]

En mode `as_of`, une livraison, un avis ou une remise transporteur n'entre que si son timestamp est strictement antérieur au premier jour du mois suivant. En rétrospectif, l'issue finale connue est utilisée. Une division par zéro retourne `null`, jamais zéro.

Les montants d'articles et de port sont déjà agrégés par commande dans Silver, ce qui évite le double comptage. La moyenne article/commande vaut `SUM(item_price_total) / COUNT DISTINCT(order_id)`.

## Comparaisons

\[
\Delta_t=K_t-K_{t-1},\qquad
\Delta_{rel}=100\frac{K_t-K_{t-1}}{|K_{t-1}|},\qquad
\Delta_{pp}=100(p_t-p_{t-1})
\]

La variation relative est indéfinie si la référence vaut zéro. L'annuel n'est calculé que lorsque N−12 existe.

## Détection robuste

Pour les KPI continus ou de volume, avec au moins six mois historiques :

\[
z_r=0.67448975\frac{x_t-\tilde x}{MAD},\quad
MAD=median(|x_i-\tilde x|)
\]

Le seuil fixé avant TEST est `|z_r| ≥ 3,5`, uniquement dans le sens métier défavorable. Ce choix résiste mieux aux pics Olist qu'une moyenne/écart-type sur un historique de 21 mois complets.

Pour un taux, le baseline historique groupé est `p0 = Σx/Σn` et :

\[
z=\frac{\hat p_t-p_0}{\sqrt{p_0(1-p_0)/n_t}}
\]

Le test bilatéral évite d'ignorer une variation avant application du sens métier. Il exige `n ≥ 30`. Les p-values des taux sont corrigées par Benjamini–Hochberg à `q < 0,05`. L'intervalle de Wilson, réutilisé de BO3, accompagne le taux car il reste fiable aux faibles effectifs.

## Analyse de segments

Pour un segment `s`, la contribution absolue d'un taux à l'écart global est :

\[
C_s=|x_s-\hat p_{global}n_s|
\]

Elle distingue un petit segment au taux élevé d'un segment représentant beaucoup de volume. `n < 30` est marqué insuffisant. Cette décomposition est descriptive et ne démontre aucune causalité.

## Priorisation

Le score est une règle métier heuristique, non un modèle appris :

\[
Score=100(0.45M+0.35C+0.20V)
\]

`M` est l'amplitude bornée, `C` la confiance statistique et `V` le volume borné. Les poids donnent priorité au signal lui-même, puis à sa fiabilité, sans laisser le volume écraser une faible preuve. Aucune action punitive automatique n'est permise.

## Sélection et évaluation

La baseline simple est un seuil `taux > 1,5 × médiane historique`. La méthode statistique utilise les dénominateurs. Les paramètres sont fixés avant la lecture TEST; TEST correspond à avril–juin 2018. Olist ne fournit pas de vérité terrain d'anomalie globale : précision, rappel et F1 ne sont donc calculables que sur des anomalies explicitement injectées, séparées des observations historiques.

