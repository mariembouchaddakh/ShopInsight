# Évaluation OM5 LangGraph + Gemini

Le 27 novembre 2026, la suite complète a passé **92/92 tests** en 299,78 s, puis le test de cohérence numérique ajouté ensuite a passé séparément (**93 cas réussis au total, aucun échec**). Le build frontend passe, le lint ne contient aucune erreur et l'audit npm de production ne relève aucune vulnérabilité.

Sur les données Olist authentiques, juillet 2017 suit le chemin sans anomalie (3 appels analytiques, aucune collaboration inutile, PDF de 3 pages). Mars 2018 détecte trois anomalies et active séquentiellement BO1, BO2 et BO3 (8 appels, preuves valides, PDF de 4 pages).

L'essai réel `gemini-2.5-flash` a été exécuté. Le service a successivement produit un délai dépassé, un JSON tronqué puis des JSON structurés rejetés par le contrôle de preuves/nombres. Dans tous les cas, aucun contenu non validé n'a été affiché et le repli déterministe a abouti. Les chemins Gemini valides, la correction bornée et les erreurs sont couverts par des réponses simulées dans les tests automatisés.

La comparaison de latence n'est pas un benchmark strict entre commits, car les caches et mois diffèrent. L'overhead du graphe est négligeable devant les calculs Olist et les collaborateurs; le coût réseau Gemini n'existe que lorsqu'il est activé. La validité des preuves déterministes reste à 100 %, tandis que la nouvelle architecture ajoute une barrière dédiée aux textes générés.
