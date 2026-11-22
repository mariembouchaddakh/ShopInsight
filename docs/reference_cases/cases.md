# Cas de référence (20 vendeurs, décisions TEST avr.–juin 2018)

Choisis par règles fixes sur les sorties de BO3 (voir `backend/app/llm/reference_cases.py`). **Aucune évaluation humaine n'est pré-remplie.**

## RC01 — Sous-performance persistante — vendeur `7d13fca15225358621be4086e1eb0964` — décision fin 2018-06

**Contexte** : Vendeur de l’État SP : 473 commandes mono-vendeur achetées sur les 12 mois avant le 2018-07-01 ; catégories : watches_gifts 90 % ; destinations : SP 36 %, autre 34 %, RJ 17 % ; prix médian 144.0 R$, délai promis moyen 26.5 jours ; segment descriptif : grand volume, Sudeste.

**Observations attendues (déterministes)** :
- ALERTE niveau (par rapport à la marketplace), sévérité moyenne — remise tardive au transporteur : 10.0 % sur 90 jours (n = 340) contre 5.3 % (taux de la marketplace) ; détecteur : a posteriori bêta-binomial (a priori = référence) : P(taux > référence) > seuil.

**Hypothèses étayées** :
- (Support vendeurs) Vérifier avec le vendeur ses délais de préparation : 10.0 % de ses commandes récentes ont été remises au transporteur après la date limite. Hypothèses à confirmer : stock, capacité, jours non ouvrés.

**Explications non étayées (à pénaliser)** :
- toute cause présentée comme certaine (Olist n'enregistre pas les causes)
- tout chiffre absent des preuves ou recalculé
- toute affirmation sur la publicité, les campagnes, les promotions ou le marketing du vendeur
- toute pratique attribuée aux concurrents ou aux « meilleurs vendeurs » sans preuve
- toute prédiction sur l'avenir du vendeur présentée comme certaine

**Recommandation attendue** : priorité haute sur l'indicateur en alerte depuis plusieurs mois ; contact du vendeur ; actions liées à l'indicateur (préparation / remise si remise tardive)

## RC02 — Sous-performance persistante — vendeur `06a2c3af7b3aee5d69171b0e14f0ee87` — décision fin 2018-06

**Contexte** : Vendeur de l’État MA : 253 commandes mono-vendeur achetées sur les 12 mois avant le 2018-07-01 ; catégories : health_beauty 100 % ; destinations : autre 49 %, SP 29 %, RJ 12 % ; prix médian 66.99 R$, délai promis moyen 30.4 jours ; segment descriptif : grand volume, autres régions.

**Observations attendues (déterministes)** :
- ALERTE niveau (par rapport à la marketplace), sévérité moyenne — retard de livraison : 19.1 % sur 90 jours (n = 157) contre 7.9 % (taux de la marketplace) ; détecteur : a posteriori bêta-binomial (a priori = référence) : P(taux > référence) > seuil.
- ALERTE niveau (par rapport à la marketplace), sévérité élevée — remise tardive au transporteur : 20.9 % sur 90 jours (n = 191) contre 5.2 % (taux de la marketplace) ; détecteur : a posteriori bêta-binomial (a priori = référence) : P(taux > référence) > seuil.

**Hypothèses étayées** :
- (Support vendeurs) Vérifier avec le vendeur ses délais de préparation : 20.9 % de ses commandes récentes ont été remises au transporteur après la date limite. Hypothèses à confirmer : stock, capacité, jours non ouvrés.
- Les retards de livraison coïncident avec des remises tardives au transporteur : traiter d'abord la préparation des commandes chez le vendeur.

**Explications non étayées (à pénaliser)** :
- toute cause présentée comme certaine (Olist n'enregistre pas les causes)
- tout chiffre absent des preuves ou recalculé
- toute affirmation sur la publicité, les campagnes, les promotions ou le marketing du vendeur
- toute pratique attribuée aux concurrents ou aux « meilleurs vendeurs » sans preuve
- toute prédiction sur l'avenir du vendeur présentée comme certaine

**Recommandation attendue** : priorité haute sur l'indicateur en alerte depuis plusieurs mois ; contact du vendeur ; actions liées à l'indicateur (préparation / remise si remise tardive)

## RC03 — Sous-performance persistante — vendeur `7c67e1448b00f6e969d365cea6b010ab` — décision fin 2018-06

**Contexte** : Vendeur de l’État SP : 745 commandes mono-vendeur achetées sur les 12 mois avant le 2018-07-01 ; catégories : autre 91 % ; destinations : SP 41 %, autre 32 %, RJ 18 % ; prix médian 159.94 R$, délai promis moyen 34.1 jours ; segment descriptif : grand volume, Sudeste.

**Observations attendues (déterministes)** :
- ALERTE niveau (par rapport à la marketplace), sévérité élevée — remise tardive au transporteur : 15.3 % sur 90 jours (n = 131) contre 5.1 % (taux de la marketplace) ; détecteur : a posteriori bêta-binomial (a priori = référence) : P(taux > référence) > seuil.

**Hypothèses étayées** :
- (Support vendeurs) Vérifier avec le vendeur ses délais de préparation : 15.3 % de ses commandes récentes ont été remises au transporteur après la date limite. Hypothèses à confirmer : stock, capacité, jours non ouvrés.

**Explications non étayées (à pénaliser)** :
- toute cause présentée comme certaine (Olist n'enregistre pas les causes)
- tout chiffre absent des preuves ou recalculé
- toute affirmation sur la publicité, les campagnes, les promotions ou le marketing du vendeur
- toute pratique attribuée aux concurrents ou aux « meilleurs vendeurs » sans preuve
- toute prédiction sur l'avenir du vendeur présentée comme certaine

**Recommandation attendue** : priorité haute sur l'indicateur en alerte depuis plusieurs mois ; contact du vendeur ; actions liées à l'indicateur (préparation / remise si remise tardive)

## RC04 — Sous-performance persistante — vendeur `2eb70248d66e0e3ef83659f71b244378` — décision fin 2018-06

**Contexte** : Vendeur de l’État SP : 141 commandes mono-vendeur achetées sur les 12 mois avant le 2018-07-01 ; catégories : computers_accessories 43 %, watches_gifts 40 %, autre 11 % ; destinations : SP 53 %, autre 26 %, MG 11 % ; prix médian 124.9 R$, délai promis moyen 27.5 jours ; segment descriptif : grand volume, Sudeste.

**Observations attendues (déterministes)** :
- Retard de livraison — détection tendance (par rapport à son propre passé) : volume insuffisant (118 issues connues sur 12 mois (minimum 30), 105 sur 90 jours (minimum 10), 13 dans son historique propre (minimum 15)) ; pas d'alerte possible.
- ALERTE niveau (par rapport à la marketplace), sévérité élevée — avis 1-2 étoiles : 57.0 % sur 90 jours (n = 114) contre 14.3 % (taux de la marketplace) ; détecteur : a posteriori bêta-binomial (a priori = référence) : P(taux > référence) > seuil.
- Avis 1-2 étoiles — détection tendance (par rapport à son propre passé) : volume insuffisant (128 issues connues sur 12 mois (minimum 30), 114 sur 90 jours (minimum 10), 14 dans son historique propre (minimum 15)) ; pas d'alerte possible.
- ALERTE niveau (par rapport à la marketplace), sévérité élevée — remise tardive au transporteur : 37.7 % sur 90 jours (n = 114) contre 5.2 % (taux de la marketplace) ; détecteur : a posteriori bêta-binomial (a priori = référence) : P(taux > référence) > seuil.
- Remise tardive au transporteur — détection tendance (par rapport à son propre passé) : volume insuffisant (127 issues connues sur 12 mois (minimum 30), 114 sur 90 jours (minimum 10), 13 dans son historique propre (minimum 15)) ; pas d'alerte possible.

**Hypothèses étayées** :
- (Support vendeurs) Vérifier avec le vendeur ses délais de préparation : 37.7 % de ses commandes récentes ont été remises au transporteur après la date limite. Hypothèses à confirmer : stock, capacité, jours non ouvrés.
- Critiques partagées entre la livraison (24 avis) et le produit ou la préparation (39 avis) : traiter les délais (remise au transporteur, agent BO1) et contrôler préparation et fiches produit (agent BO2).

**Explications non étayées (à pénaliser)** :
- toute cause présentée comme certaine (Olist n'enregistre pas les causes)
- tout chiffre absent des preuves ou recalculé
- toute affirmation sur la publicité, les campagnes, les promotions ou le marketing du vendeur
- toute pratique attribuée aux concurrents ou aux « meilleurs vendeurs » sans preuve
- toute prédiction sur l'avenir du vendeur présentée comme certaine

**Recommandation attendue** : priorité haute sur l'indicateur en alerte depuis plusieurs mois ; contact du vendeur ; actions liées à l'indicateur (préparation / remise si remise tardive)

## RC05 — Dégradation récente — vendeur `dd7ddc04e1b6c2c614352b383efe2d36` — décision fin 2018-06

**Contexte** : Vendeur de l’État SP : 92 commandes mono-vendeur achetées sur les 12 mois avant le 2018-07-01 ; catégories : autre 100 % ; destinations : SP 54 %, autre 23 %, MG 13 % ; prix médian 48.37 R$, délai promis moyen 22.7 jours ; segment descriptif : grand volume, Sudeste.

**Observations attendues (déterministes)** :
- ALERTE niveau (par rapport à la marketplace), sévérité moyenne — remise tardive au transporteur : 26.9 % sur 90 jours (n = 26) contre 5.3 % (taux de la marketplace) ; détecteur : a posteriori bêta-binomial (a priori = référence) : P(taux > référence) > seuil.

**Hypothèses étayées** :
- (Support vendeurs) Vérifier avec le vendeur ses délais de préparation : 26.9 % de ses commandes récentes ont été remises au transporteur après la date limite. Hypothèses à confirmer : stock, capacité, jours non ouvrés.

**Explications non étayées (à pénaliser)** :
- toute cause présentée comme certaine (Olist n'enregistre pas les causes)
- tout chiffre absent des preuves ou recalculé
- toute affirmation sur la publicité, les campagnes, les promotions ou le marketing du vendeur
- toute pratique attribuée aux concurrents ou aux « meilleurs vendeurs » sans preuve
- toute prédiction sur l'avenir du vendeur présentée comme certaine

**Recommandation attendue** : vérifier si le signal se confirme ; contact préventif ; surveiller le mois suivant

## RC06 — Dégradation récente — vendeur `54965bbe3e4f07ae045b90b0b8541f52` — décision fin 2018-06

**Contexte** : Vendeur de l’État PR : 73 commandes mono-vendeur achetées sur les 12 mois avant le 2018-07-01 ; catégories : bed_bath_table 100 % ; destinations : SP 37 %, autre 33 %, MG 15 % ; prix médian 119.9 R$, délai promis moyen 28.9 jours ; segment descriptif : grand volume, Sul.

**Observations attendues (déterministes)** :
- ALERTE niveau (par rapport à la marketplace), sévérité moyenne — remise tardive au transporteur : 38.1 % sur 90 jours (n = 21) contre 5.3 % (taux de la marketplace) ; détecteur : a posteriori bêta-binomial (a priori = référence) : P(taux > référence) > seuil.

**Hypothèses étayées** :
- (Support vendeurs) Vérifier avec le vendeur ses délais de préparation : 38.1 % de ses commandes récentes ont été remises au transporteur après la date limite. Hypothèses à confirmer : stock, capacité, jours non ouvrés.

**Explications non étayées (à pénaliser)** :
- toute cause présentée comme certaine (Olist n'enregistre pas les causes)
- tout chiffre absent des preuves ou recalculé
- toute affirmation sur la publicité, les campagnes, les promotions ou le marketing du vendeur
- toute pratique attribuée aux concurrents ou aux « meilleurs vendeurs » sans preuve
- toute prédiction sur l'avenir du vendeur présentée comme certaine

**Recommandation attendue** : vérifier si le signal se confirme ; contact préventif ; surveiller le mois suivant

## RC07 — Dégradation récente — vendeur `213b25e6f54661939f11710a6fddb871` — décision fin 2018-05

**Contexte** : Vendeur de l’État SP : 54 commandes mono-vendeur achetées sur les 12 mois avant le 2018-06-01 ; catégories : autre 100 % ; destinations : SP 46 %, autre 32 %, MG 13 % ; prix médian 79.85 R$, délai promis moyen 24.8 jours ; segment descriptif : grand volume, Sudeste.

**Observations attendues (déterministes)** :
- Retard de livraison — détection tendance (par rapport à son propre passé) : volume insuffisant (37 issues connues sur 12 mois (minimum 30), 27 sur 90 jours (minimum 10), 10 dans son historique propre (minimum 15)) ; pas d'alerte possible.
- Avis 1-2 étoiles — détection tendance (par rapport à son propre passé) : volume insuffisant (38 issues connues sur 12 mois (minimum 30), 28 sur 90 jours (minimum 10), 10 dans son historique propre (minimum 15)) ; pas d'alerte possible.
- ALERTE niveau (par rapport à la marketplace), sévérité moyenne — remise tardive au transporteur : 29.4 % sur 90 jours (n = 34) contre 5.4 % (taux de la marketplace) ; détecteur : a posteriori bêta-binomial (a priori = référence) : P(taux > référence) > seuil.
- Remise tardive au transporteur — détection tendance (par rapport à son propre passé) : volume insuffisant (45 issues connues sur 12 mois (minimum 30), 34 sur 90 jours (minimum 10), 11 dans son historique propre (minimum 15)) ; pas d'alerte possible.

**Hypothèses étayées** :
- (Support vendeurs) Vérifier avec le vendeur ses délais de préparation : 29.4 % de ses commandes récentes ont été remises au transporteur après la date limite. Hypothèses à confirmer : stock, capacité, jours non ouvrés.

**Explications non étayées (à pénaliser)** :
- toute cause présentée comme certaine (Olist n'enregistre pas les causes)
- tout chiffre absent des preuves ou recalculé
- toute affirmation sur la publicité, les campagnes, les promotions ou le marketing du vendeur
- toute pratique attribuée aux concurrents ou aux « meilleurs vendeurs » sans preuve
- toute prédiction sur l'avenir du vendeur présentée comme certaine

**Recommandation attendue** : vérifier si le signal se confirme ; contact préventif ; surveiller le mois suivant

## RC08 — Dégradation récente — vendeur `6560211a19b47992c3666cc44a7e94c0` — décision fin 2018-04

**Contexte** : Vendeur de l’État SP : 1087 commandes mono-vendeur achetées sur les 12 mois avant le 2018-05-01 ; catégories : watches_gifts 77 %, autre 22 % ; destinations : SP 43 %, autre 36 %, MG 11 % ; prix médian 49.99 R$, délai promis moyen 21.8 jours ; segment descriptif : grand volume, Sudeste.

**Observations attendues (déterministes)** :
- ALERTE tendance (par rapport à son propre passé) — retard de livraison : 9.5 % sur 90 jours (n = 190) contre 5.3 % (historique du vendeur sur les achats de T-365 à T-90 jours, rétréci vers la marketplace) ; détecteur : test binomial unilatéral vs historique rétréci du vendeur, correction de Benjamini-Hochberg.
- ALERTE niveau (par rapport à la marketplace), sévérité faible — avis 1-2 étoiles : 22.9 % sur 90 jours (n = 188) contre 14.7 % (taux de la marketplace) ; détecteur : a posteriori bêta-binomial (a priori = référence) : P(taux > référence) > seuil.
- Point fort — remise tardive au transporteur : 0.4 % sur 12 mois (n = 1080) contre 5.7 % pour la marketplace, écart significatif.

**Hypothèses étayées** :
- (Logistique) Retards de livraison sans remise tardive signalée : examiner transporteurs et destinations de ce vendeur ; utiliser l'agent BO1 pour surveiller ses commandes en cours.
- Critiques partagées entre la livraison (54 avis) et le produit ou la préparation (34 avis) : traiter les délais (remise au transporteur, agent BO1) et contrôler préparation et fiches produit (agent BO2).

**Explications non étayées (à pénaliser)** :
- toute cause présentée comme certaine (Olist n'enregistre pas les causes)
- tout chiffre absent des preuves ou recalculé
- toute affirmation sur la publicité, les campagnes, les promotions ou le marketing du vendeur
- toute pratique attribuée aux concurrents ou aux « meilleurs vendeurs » sans preuve
- toute prédiction sur l'avenir du vendeur présentée comme certaine

**Recommandation attendue** : vérifier si le signal se confirme ; contact préventif ; surveiller le mois suivant

## RC09 — Signal de tendance faible — vendeur `4869f7a5dfa277a7dca6462dcf3b52b2` — décision fin 2018-06

**Contexte** : Vendeur de l’État SP : 955 commandes mono-vendeur achetées sur les 12 mois avant le 2018-07-01 ; catégories : watches_gifts 87 % ; destinations : SP 40 %, autre 32 %, RJ 18 % ; prix médian 179.0 R$, délai promis moyen 27.0 jours ; segment descriptif : grand volume, Sudeste.

**Observations attendues (déterministes)** :
- ALERTE tendance (par rapport à son propre passé) — remise tardive au transporteur : 6.1 % sur 90 jours (n = 297) contre 1.5 % (historique du vendeur sur les achats de T-365 à T-90 jours, rétréci vers la marketplace) ; détecteur : test binomial unilatéral vs historique rétréci du vendeur, correction de Benjamini-Hochberg.
- Point fort — remise tardive au transporteur : 2.8 % sur 12 mois (n = 950) contre 5.3 % pour la marketplace, écart significatif.

**Hypothèses étayées** :
- (Support vendeurs) Vérifier avec le vendeur ses délais de préparation : 6.1 % de ses commandes récentes ont été remises au transporteur après la date limite. Hypothèses à confirmer : stock, capacité, jours non ouvrés.

**Explications non étayées (à pénaliser)** :
- toute cause présentée comme certaine (Olist n'enregistre pas les causes)
- tout chiffre absent des preuves ou recalculé
- toute affirmation sur la publicité, les campagnes, les promotions ou le marketing du vendeur
- toute pratique attribuée aux concurrents ou aux « meilleurs vendeurs » sans preuve
- toute prédiction sur l'avenir du vendeur présentée comme certaine

**Recommandation attendue** : présenter l'alerte de tendance comme un signal faible ; recouper avec le niveau ; pas d'action lourde

## RC10 — Signal de tendance faible — vendeur `aafe36600ce604f205b86b5084d3d767` — décision fin 2018-06

**Contexte** : Vendeur de l’État SC : 95 commandes mono-vendeur achetées sur les 12 mois avant le 2018-07-01 ; catégories : autre 97 % ; destinations : autre 47 %, SP 36 % ; prix médian 59.9 R$, délai promis moyen 25.7 jours ; segment descriptif : grand volume, Sul.

**Observations attendues (déterministes)** :
- ALERTE tendance (par rapport à son propre passé) — remise tardive au transporteur : 19.2 % sur 90 jours (n = 26) contre 1.2 % (historique du vendeur sur les achats de T-365 à T-90 jours, rétréci vers la marketplace) ; détecteur : test binomial unilatéral vs historique rétréci du vendeur, correction de Benjamini-Hochberg.

**Hypothèses étayées** :
- (Support vendeurs) Vérifier avec le vendeur ses délais de préparation : 19.2 % de ses commandes récentes ont été remises au transporteur après la date limite. Hypothèses à confirmer : stock, capacité, jours non ouvrés.

**Explications non étayées (à pénaliser)** :
- toute cause présentée comme certaine (Olist n'enregistre pas les causes)
- tout chiffre absent des preuves ou recalculé
- toute affirmation sur la publicité, les campagnes, les promotions ou le marketing du vendeur
- toute pratique attribuée aux concurrents ou aux « meilleurs vendeurs » sans preuve
- toute prédiction sur l'avenir du vendeur présentée comme certaine

**Recommandation attendue** : présenter l'alerte de tendance comme un signal faible ; recouper avec le niveau ; pas d'action lourde

## RC11 — Signal de tendance faible — vendeur `f8db351d8c4c4c22c6835c19a46f01b0` — décision fin 2018-05

**Contexte** : Vendeur de l’État SP : 399 commandes mono-vendeur achetées sur les 12 mois avant le 2018-06-01 ; catégories : housewares 29 %, autre 28 %, sports_leisure 11 % ; destinations : SP 42 %, autre 34 %, RJ 13 % ; prix médian 49.9 R$, délai promis moyen 22.1 jours ; segment descriptif : grand volume, Sudeste.

**Observations attendues (déterministes)** :
- ALERTE tendance (par rapport à son propre passé) — avis 1-2 étoiles : 19.4 % sur 90 jours (n = 93) contre 6.8 % (historique du vendeur sur les achats de T-365 à T-90 jours, rétréci vers la marketplace) ; détecteur : test binomial unilatéral vs historique rétréci du vendeur, correction de Benjamini-Hochberg.
- Point fort — remise tardive au transporteur : 0.0 % sur 12 mois (n = 396) contre 5.5 % pour la marketplace, écart significatif.

**Hypothèses étayées** :
- Critiques partagées entre la livraison (13 avis) et le produit ou la préparation (9 avis) : traiter les délais (remise au transporteur, agent BO1) et contrôler préparation et fiches produit (agent BO2).

**Explications non étayées (à pénaliser)** :
- toute cause présentée comme certaine (Olist n'enregistre pas les causes)
- tout chiffre absent des preuves ou recalculé
- toute affirmation sur la publicité, les campagnes, les promotions ou le marketing du vendeur
- toute pratique attribuée aux concurrents ou aux « meilleurs vendeurs » sans preuve
- toute prédiction sur l'avenir du vendeur présentée comme certaine

**Recommandation attendue** : présenter l'alerte de tendance comme un signal faible ; recouper avec le niveau ; pas d'action lourde

## RC12 — Plaintes mixtes — vendeur `c31eff8334d6b3047ed34bebd4d62c36` — décision fin 2018-06

**Contexte** : Vendeur de l’État SP : 90 commandes mono-vendeur achetées sur les 12 mois avant le 2018-07-01 ; catégories : autre 83 %, furniture_decor 17 % ; destinations : SP 52 %, autre 29 %, RJ 14 % ; prix médian 99.99 R$, délai promis moyen 23.7 jours ; segment descriptif : grand volume, Sudeste.

**Observations attendues (déterministes)** :
- ALERTE niveau (par rapport à la marketplace), sévérité moyenne — remise tardive au transporteur : 20.3 % sur 90 jours (n = 64) contre 5.3 % (taux de la marketplace) ; détecteur : a posteriori bêta-binomial (a priori = référence) : P(taux > référence) > seuil.

**Hypothèses étayées** :
- (Support vendeurs) Vérifier avec le vendeur ses délais de préparation : 20.3 % de ses commandes récentes ont été remises au transporteur après la date limite. Hypothèses à confirmer : stock, capacité, jours non ouvrés.

**Explications non étayées (à pénaliser)** :
- toute cause présentée comme certaine (Olist n'enregistre pas les causes)
- tout chiffre absent des preuves ou recalculé
- toute affirmation sur la publicité, les campagnes, les promotions ou le marketing du vendeur
- toute pratique attribuée aux concurrents ou aux « meilleurs vendeurs » sans preuve
- toute prédiction sur l'avenir du vendeur présentée comme certaine

**Recommandation attendue** : distinguer livraison et produit ; orienter vers logistique ET catalogue / préparation

## RC13 — Plaintes mixtes — vendeur `92eb0f42c21942b6552362b9b114707d` — décision fin 2018-06

**Contexte** : Vendeur de l’État SP : 152 commandes mono-vendeur achetées sur les 12 mois avant le 2018-07-01 ; catégories : telephony 90 % ; destinations : SP 49 %, autre 36 % ; prix médian 13.87 R$, délai promis moyen 22.4 jours ; segment descriptif : grand volume, Sudeste.

**Observations attendues (déterministes)** :
- ALERTE niveau (par rapport à la marketplace), sévérité élevée — remise tardive au transporteur : 32.5 % sur 90 jours (n = 40) contre 5.3 % (taux de la marketplace) ; détecteur : a posteriori bêta-binomial (a priori = référence) : P(taux > référence) > seuil.

**Hypothèses étayées** :
- (Support vendeurs) Vérifier avec le vendeur ses délais de préparation : 32.5 % de ses commandes récentes ont été remises au transporteur après la date limite. Hypothèses à confirmer : stock, capacité, jours non ouvrés.

**Explications non étayées (à pénaliser)** :
- toute cause présentée comme certaine (Olist n'enregistre pas les causes)
- tout chiffre absent des preuves ou recalculé
- toute affirmation sur la publicité, les campagnes, les promotions ou le marketing du vendeur
- toute pratique attribuée aux concurrents ou aux « meilleurs vendeurs » sans preuve
- toute prédiction sur l'avenir du vendeur présentée comme certaine

**Recommandation attendue** : distinguer livraison et produit ; orienter vers logistique ET catalogue / préparation

## RC14 — Plaintes mixtes — vendeur `7178f9f4dd81dcef02f62acdf8151e01` — décision fin 2018-06

**Contexte** : Vendeur de l’État SC : 189 commandes mono-vendeur achetées sur les 12 mois avant le 2018-07-01 ; catégories : autre 52 %, health_beauty 28 %, computers_accessories 14 % ; destinations : SP 39 %, autre 35 %, MG 13 % ; prix médian 84.9 R$, délai promis moyen 33.8 jours ; segment descriptif : grand volume, Sul.

**Observations attendues (déterministes)** :
- ALERTE niveau (par rapport à la marketplace), sévérité élevée — remise tardive au transporteur : 54.5 % sur 90 jours (n = 11) contre 5.3 % (taux de la marketplace) ; détecteur : a posteriori bêta-binomial (a priori = référence) : P(taux > référence) > seuil.
- ALERTE tendance (par rapport à son propre passé) — remise tardive au transporteur : 54.5 % sur 90 jours (n = 11) contre 3.6 % (historique du vendeur sur les achats de T-365 à T-90 jours, rétréci vers la marketplace) ; détecteur : test binomial unilatéral vs historique rétréci du vendeur, correction de Benjamini-Hochberg.

**Hypothèses étayées** :
- (Support vendeurs) Vérifier avec le vendeur ses délais de préparation : 54.5 % de ses commandes récentes ont été remises au transporteur après la date limite. Hypothèses à confirmer : stock, capacité, jours non ouvrés.

**Explications non étayées (à pénaliser)** :
- toute cause présentée comme certaine (Olist n'enregistre pas les causes)
- tout chiffre absent des preuves ou recalculé
- toute affirmation sur la publicité, les campagnes, les promotions ou le marketing du vendeur
- toute pratique attribuée aux concurrents ou aux « meilleurs vendeurs » sans preuve
- toute prédiction sur l'avenir du vendeur présentée comme certaine

**Recommandation attendue** : distinguer livraison et produit ; orienter vers logistique ET catalogue / préparation

## RC15 — Preuves insuffisantes — vendeur `d9bd94811c3338dceb4181f3dbc0c73e` — décision fin 2018-06

**Contexte** : Vendeur de l’État SP : 29 commandes mono-vendeur achetées sur les 12 mois avant le 2018-07-01 ; catégories : autre 90 %, health_beauty 10 % ; destinations : SP 66 %, autre 21 % ; prix médian 80.38 R$, délai promis moyen 18.7 jours ; segment descriptif : volume moyen, Sudeste.

**Observations attendues (déterministes)** :
- Retard de livraison — détection niveau (par rapport à la marketplace) : volume insuffisant (25 issues connues sur 12 mois (minimum 30), 25 sur 90 jours (minimum 10)) ; pas d'alerte possible.
- Retard de livraison — détection tendance (par rapport à son propre passé) : volume insuffisant (25 issues connues sur 12 mois (minimum 30), 25 sur 90 jours (minimum 10), 0 dans son historique propre (minimum 15)) ; pas d'alerte possible.
- Avis 1-2 étoiles — détection niveau (par rapport à la marketplace) : volume insuffisant (23 issues connues sur 12 mois (minimum 30), 23 sur 90 jours (minimum 10)) ; pas d'alerte possible.
- Avis 1-2 étoiles — détection tendance (par rapport à son propre passé) : volume insuffisant (23 issues connues sur 12 mois (minimum 30), 23 sur 90 jours (minimum 10), 0 dans son historique propre (minimum 15)) ; pas d'alerte possible.
- Remise tardive au transporteur — détection niveau (par rapport à la marketplace) : volume insuffisant (29 issues connues sur 12 mois (minimum 30), 29 sur 90 jours (minimum 10)) ; pas d'alerte possible.
- Remise tardive au transporteur — détection tendance (par rapport à son propre passé) : volume insuffisant (29 issues connues sur 12 mois (minimum 30), 29 sur 90 jours (minimum 10), 0 dans son historique propre (minimum 15)) ; pas d'alerte possible.

**Hypothèses étayées** :
- Volume insuffisant pour une alerte : suivre ce vendeur au niveau de son groupe de pairs.

**Explications non étayées (à pénaliser)** :
- toute cause présentée comme certaine (Olist n'enregistre pas les causes)
- tout chiffre absent des preuves ou recalculé
- toute affirmation sur la publicité, les campagnes, les promotions ou le marketing du vendeur
- toute pratique attribuée aux concurrents ou aux « meilleurs vendeurs » sans preuve
- toute prédiction sur l'avenir du vendeur présentée comme certaine

**Recommandation attendue** : dire qu'aucune conclusion n'est possible ; recommander un suivi au niveau global, pas de sanction

## RC16 — Preuves insuffisantes — vendeur `951e8cef368f09bb3f3d03c00ca4702c` — décision fin 2018-06

**Contexte** : Vendeur de l’État SP : 29 commandes mono-vendeur achetées sur les 12 mois avant le 2018-07-01 ; catégories : bed_bath_table 79 %, autre 21 % ; destinations : SP 66 %, autre 21 %, RJ 14 % ; prix médian 58.99 R$, délai promis moyen 22.3 jours ; segment descriptif : volume moyen, Sudeste.

**Observations attendues (déterministes)** :
- Retard de livraison — détection niveau (par rapport à la marketplace) : volume insuffisant (25 issues connues sur 12 mois (minimum 30), 25 sur 90 jours (minimum 10)) ; pas d'alerte possible.
- Retard de livraison — détection tendance (par rapport à son propre passé) : volume insuffisant (25 issues connues sur 12 mois (minimum 30), 25 sur 90 jours (minimum 10), 0 dans son historique propre (minimum 15)) ; pas d'alerte possible.
- Avis 1-2 étoiles — détection niveau (par rapport à la marketplace) : volume insuffisant (24 issues connues sur 12 mois (minimum 30), 24 sur 90 jours (minimum 10)) ; pas d'alerte possible.
- Avis 1-2 étoiles — détection tendance (par rapport à son propre passé) : volume insuffisant (24 issues connues sur 12 mois (minimum 30), 24 sur 90 jours (minimum 10), 0 dans son historique propre (minimum 15)) ; pas d'alerte possible.
- Remise tardive au transporteur — détection niveau (par rapport à la marketplace) : volume insuffisant (28 issues connues sur 12 mois (minimum 30), 28 sur 90 jours (minimum 10)) ; pas d'alerte possible.
- Remise tardive au transporteur — détection tendance (par rapport à son propre passé) : volume insuffisant (28 issues connues sur 12 mois (minimum 30), 28 sur 90 jours (minimum 10), 0 dans son historique propre (minimum 15)) ; pas d'alerte possible.

**Hypothèses étayées** :
- Volume insuffisant pour une alerte : suivre ce vendeur au niveau de son groupe de pairs.

**Explications non étayées (à pénaliser)** :
- toute cause présentée comme certaine (Olist n'enregistre pas les causes)
- tout chiffre absent des preuves ou recalculé
- toute affirmation sur la publicité, les campagnes, les promotions ou le marketing du vendeur
- toute pratique attribuée aux concurrents ou aux « meilleurs vendeurs » sans preuve
- toute prédiction sur l'avenir du vendeur présentée comme certaine

**Recommandation attendue** : dire qu'aucune conclusion n'est possible ; recommander un suivi au niveau global, pas de sanction

## RC17 — Preuves insuffisantes — vendeur `23c38debaffe4a25a30fdbd9b586a13f` — décision fin 2018-06

**Contexte** : Vendeur de l’État SP : 29 commandes mono-vendeur achetées sur les 12 mois avant le 2018-07-01 ; catégories : garden_tools 76 %, autre 17 % ; destinations : SP 55 %, autre 24 %, MG 17 % ; prix médian 127.27 R$, délai promis moyen 21.1 jours ; segment descriptif : volume moyen, Sudeste.

**Observations attendues (déterministes)** :
- Retard de livraison — détection niveau (par rapport à la marketplace) : volume insuffisant (26 issues connues sur 12 mois (minimum 30), 26 sur 90 jours (minimum 10)) ; pas d'alerte possible.
- Retard de livraison — détection tendance (par rapport à son propre passé) : volume insuffisant (26 issues connues sur 12 mois (minimum 30), 26 sur 90 jours (minimum 10), 0 dans son historique propre (minimum 15)) ; pas d'alerte possible.
- Avis 1-2 étoiles — détection niveau (par rapport à la marketplace) : volume insuffisant (26 issues connues sur 12 mois (minimum 30), 26 sur 90 jours (minimum 10)) ; pas d'alerte possible.
- Avis 1-2 étoiles — détection tendance (par rapport à son propre passé) : volume insuffisant (26 issues connues sur 12 mois (minimum 30), 26 sur 90 jours (minimum 10), 0 dans son historique propre (minimum 15)) ; pas d'alerte possible.
- Remise tardive au transporteur — détection niveau (par rapport à la marketplace) : volume insuffisant (27 issues connues sur 12 mois (minimum 30), 27 sur 90 jours (minimum 10)) ; pas d'alerte possible.
- Remise tardive au transporteur — détection tendance (par rapport à son propre passé) : volume insuffisant (27 issues connues sur 12 mois (minimum 30), 27 sur 90 jours (minimum 10), 0 dans son historique propre (minimum 15)) ; pas d'alerte possible.

**Hypothèses étayées** :
- Volume insuffisant pour une alerte : suivre ce vendeur au niveau de son groupe de pairs.

**Explications non étayées (à pénaliser)** :
- toute cause présentée comme certaine (Olist n'enregistre pas les causes)
- tout chiffre absent des preuves ou recalculé
- toute affirmation sur la publicité, les campagnes, les promotions ou le marketing du vendeur
- toute pratique attribuée aux concurrents ou aux « meilleurs vendeurs » sans preuve
- toute prédiction sur l'avenir du vendeur présentée comme certaine

**Recommandation attendue** : dire qu'aucune conclusion n'est possible ; recommander un suivi au niveau global, pas de sanction

## RC18 — Bonne performance — vendeur `da8622b14eb17ae2831f4ac5b9dab84a` — décision fin 2018-06

**Contexte** : Vendeur de l’État SP : 1026 commandes mono-vendeur achetées sur les 12 mois avant le 2018-07-01 ; catégories : bed_bath_table 82 %, health_beauty 18 % ; destinations : SP 55 %, autre 21 %, RJ 13 % ; prix médian 99.9 R$, délai promis moyen 22.1 jours ; segment descriptif : grand volume, Sudeste.

**Observations attendues (déterministes)** :
- Point fort — avis 1-2 étoiles : 11.2 % sur 12 mois (n = 1006) contre 14.5 % pour la marketplace, écart significatif.
- Point fort — remise tardive au transporteur : 0.9 % sur 12 mois (n = 1023) contre 5.4 % pour la marketplace, écart significatif.

**Hypothèses étayées** :
- Aucune alerte : surveillance standard ; réévaluer à la prochaine décision mensuelle.

**Explications non étayées (à pénaliser)** :
- toute cause présentée comme certaine (Olist n'enregistre pas les causes)
- tout chiffre absent des preuves ou recalculé
- toute affirmation sur la publicité, les campagnes, les promotions ou le marketing du vendeur
- toute pratique attribuée aux concurrents ou aux « meilleurs vendeurs » sans preuve
- toute prédiction sur l'avenir du vendeur présentée comme certaine

**Recommandation attendue** : souligner les points forts observés sans en tirer de cause ; pas d'action corrective inventée

## RC19 — Bonne performance — vendeur `7a67c85e85bb2ce8582c35f2203ad736` — décision fin 2018-06

**Contexte** : Vendeur de l’État SP : 738 commandes mono-vendeur achetées sur les 12 mois avant le 2018-07-01 ; catégories : cool_stuff 91 % ; destinations : autre 43 %, SP 32 %, RJ 13 % ; prix médian 119.99 R$, délai promis moyen 23.0 jours ; segment descriptif : grand volume, Sudeste.

**Observations attendues (déterministes)** :
- Point fort — avis 1-2 étoiles : 10.0 % sur 12 mois (n = 721) contre 14.5 % pour la marketplace, écart significatif.
- Point fort — remise tardive au transporteur : 0.9 % sur 12 mois (n = 734) contre 5.3 % pour la marketplace, écart significatif.

**Hypothèses étayées** :
- Aucune alerte : surveillance standard ; réévaluer à la prochaine décision mensuelle.

**Explications non étayées (à pénaliser)** :
- toute cause présentée comme certaine (Olist n'enregistre pas les causes)
- tout chiffre absent des preuves ou recalculé
- toute affirmation sur la publicité, les campagnes, les promotions ou le marketing du vendeur
- toute pratique attribuée aux concurrents ou aux « meilleurs vendeurs » sans preuve
- toute prédiction sur l'avenir du vendeur présentée comme certaine

**Recommandation attendue** : souligner les points forts observés sans en tirer de cause ; pas d'action corrective inventée

## RC20 — Bonne performance — vendeur `7299e27ed73d2ad986de7f7c77d919fa` — décision fin 2018-06

**Contexte** : Vendeur de l’État MG : 206 commandes mono-vendeur achetées sur les 12 mois avant le 2018-07-01 ; catégories : autre 65 %, toys 29 % ; destinations : SP 38 %, autre 29 %, MG 18 % ; prix médian 69.99 R$, délai promis moyen 24.5 jours ; segment descriptif : grand volume, Sudeste.

**Observations attendues (déterministes)** :
- Point fort — avis 1-2 étoiles : 5.3 % sur 12 mois (n = 188) contre 14.5 % pour la marketplace, écart significatif.
- Point fort — remise tardive au transporteur : 0.0 % sur 12 mois (n = 204) contre 5.3 % pour la marketplace, écart significatif.

**Hypothèses étayées** :
- Aucune alerte : surveillance standard ; réévaluer à la prochaine décision mensuelle.

**Explications non étayées (à pénaliser)** :
- toute cause présentée comme certaine (Olist n'enregistre pas les causes)
- tout chiffre absent des preuves ou recalculé
- toute affirmation sur la publicité, les campagnes, les promotions ou le marketing du vendeur
- toute pratique attribuée aux concurrents ou aux « meilleurs vendeurs » sans preuve
- toute prédiction sur l'avenir du vendeur présentée comme certaine

**Recommandation attendue** : souligner les points forts observés sans en tirer de cause ; pas d'action corrective inventée
