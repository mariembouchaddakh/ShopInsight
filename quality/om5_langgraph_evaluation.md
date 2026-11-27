# Évaluation OM5 LangGraph + Groq

Le 27 novembre 2026, les appels réels ont utilisé le SDK Python officiel Groq, le modèle `openai/gpt-oss-120b` et un JSON Schema strict. Les calculs, détecteurs, scores et activations d'agents sont restés déterministes. La régression complète passe avec 93 tests en 249,56 s; le build frontend passe, le lint ne contient aucune erreur et l'audit npm ne relève aucune vulnérabilité.

Sur les données Olist authentiques, juillet 2017 suit le chemin sans anomalie et sans collaborateur. La génération Groq a été acceptée en 2 680,8 ms: `generation_mode=groq`, `validation_status=valid`, `evidence_valid=true`, `fallback_used=false`. Le PDF contient la synthèse et la recommandation de surveillance générées.

Mars 2018 détecte trois anomalies et exécute BO1, BO2 et BO3. La génération Groq a été acceptée en 4 292,5 ms sans correction: mêmes quatre statuts de succès. Les recommandations citent à la fois la preuve d'anomalie et les résultats collaborateurs; les scores 100,0, 100,0 et 76,2 sont réinjectés depuis le calcul déterministe, jamais générés par le modèle.

Un essai intermédiaire a exposé deux échecs réels: `json_validate_failed` pour un champ `priority_level` omis par la génération, puis une limite TPM lors de la correction. Le schéma n'a pas été assoupli. Le pipeline transmet désormais l'erreur structurée à l'unique correction autorisée, conserve le repli pour les échecs persistants et limite la complétion à 2 200 tokens. Les deux scénarios finaux passent sans repli.

Les PDF finaux sont sous `reports/om5-groq-demo/`. Les limites demeurent celles du dataset: Olist est historique, ne fournit pas de vérité terrain d'anomalie métier et ne permet pas d'attribuer un impact causal.
