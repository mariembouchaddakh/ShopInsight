# OM5 — guide de présentation technique

## Démonstration en 7 minutes

1. Ouvrir `http://127.0.0.1:5173/om5` et choisir **mars 2018 / À date**.
2. Montrer les KPI calculés sans LLM, puis les trois anomalies authentiques Olist.
3. Parcourir la trace: KPI → comparaisons → détection → segments → planificateur → BO1/BO2/BO3 → consolidation → priorité → génération LLM → validation.
4. Montrer que les scores de priorité restent déterministes et que chaque affirmation générée cite un identifiant de preuve existant.
5. Télécharger le PDF: couverture, KPI, tendances, anomalies, investigations, recommandations et références.
6. Désactiver `OM5_LLM_ENABLED`, relancer l'API et montrer que le même workflow aboutit à un rapport déterministe complet.
7. Comparer avec juillet 2017: aucune anomalie, donc aucun appel BO1/BO2/BO3 inutile.

## Choix à défendre

- LangGraph orchestre; il ne remplace aucun calcul statistique.
- Groq rédige à partir d'un paquet compact et ne reçoit jamais les tables Olist brutes; Gemini reste un fournisseur optionnel.
- Pydantic valide la structure; le validateur OM5 contrôle période, mode, preuves, nombres, scores, causalité et disponibilité des agents.
- Une seule régénération est autorisée. Toute erreur de clé, quota, réseau, modèle, délai ou JSON déclenche le repli déterministe.
- Les collaborateurs sont exécutés séquentiellement via les verrous du registre.
- Le cache API de cinq minutes évite un second appel LLM lors du téléchargement du PDF.

## Commandes

```powershell
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
cd frontend
npm run dev -- --host 127.0.0.1
```

```powershell
python -m pytest tests/test_om5.py tests/test_om5_temporal.py tests/test_om5_langgraph.py tests/api/test_om5.py -q
```
