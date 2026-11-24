"""Point-in-time hybrid retrieval for BO4 historical customer experiences."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

from .core import DataStore

TOKEN = re.compile(r"\w+", re.UNICODE)


def tokens(text: str) -> list[str]: return TOKEN.findall(str(text).lower())


def rrf(rankings: list[list[int]], k: int = 60) -> dict[int, float]:
    out: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking, 1): out[idx] = out.get(idx, 0.) + 1. / (k + rank)
    return out


class HistoricalReviewIndex:
    """Queries only the corpus observable at ``as_of``.

    Lexical statistics are fitted on that snapshot at query time, so future
    documents cannot alter IDF/BM25 or ranking in historical simulations.
    """
    def __init__(self, project_dir: str | Path, dense: bool = True):
        self.root = Path(project_dir); self.store = DataStore(self.root); self.df = self.store.reviews().copy()
        ocols = [c for c in ("order_id", "customer_state", "primary_category", "delivery_duration_days", "order_delivered_customer_date",
                             "promised_days", "distance_km", "freight_total", "item_price_total", "product_weight_mean_g") if c in self.store.orders]
        orders = self.store.orders[ocols].reset_index(drop=True)
        self.df = self.df.merge(orders, on="order_id", how="left", suffixes=("", "_order"))
        self.df["available_at"] = self.df.review_answered_at.fillna(self.df.review_created_at)
        self.df["text_search"] = np.where(self.df.full_fr.str.len() > 0, self.df.full_fr + " " + self.df.full_pt, self.df.full_pt)
        self.encoder = self.embeddings = None
        emb = self.root / "data/model/bo4_review_embeddings.joblib"
        if dense and emb.exists():
            bundle = joblib.load(emb); self.embeddings = bundle["embeddings"]
            from sentence_transformers import SentenceTransformer
            self.encoder = SentenceTransformer(bundle["model"])

    def _eligible(self, as_of: Any, order_id: str | None, context: dict | None) -> pd.DataFrame:
        t = pd.Timestamp(as_of).tz_localize(None)
        d = self.df[self.df.available_at.notna() & (self.df.available_at <= t)]
        if order_id: d = d[d.order_id != order_id]
        if context:
            # strict context first; caller progressively relaxes if necessary
            if context.get("customer_state"): d = d[d.customer_state == context["customer_state"]]
            if context.get("primary_category"): d = d[d.primary_category == context["primary_category"]]
        return d

    @staticmethod
    def _bm25(corpus: list[list[str]], query: list[str]) -> np.ndarray:
        n = len(corpus); lens = np.array([len(x) for x in corpus]); avg = max(float(lens.mean()), 1.); scores = np.zeros(n)
        df = {q: sum(q in set(doc) for doc in corpus) for q in set(query)}
        for i, doc in enumerate(corpus):
            counts = {q: doc.count(q) for q in set(query)}
            for q, tf in counts.items():
                idf = math.log(1 + (n - df[q] + .5) / (df[q] + .5))
                scores[i] += idf * tf * 2.2 / (tf + 1.2 * (1 - .75 + .75 * lens[i] / avg))
        return scores

    def search(self, query: str, as_of: Any, order_id: str | None = None, context: dict | None = None, k: int = 5,
               system: str = "hybrid") -> list[dict]:
        if system not in {"tfidf", "bm25", "dense", "hybrid"}: raise ValueError(f"Système de recherche inconnu: {system}")
        snapshots = [self._eligible(as_of, order_id, context), self._eligible(as_of, order_id, {"customer_state": (context or {}).get("customer_state")}),
                     self._eligible(as_of, order_id, None)]
        d = next((x for x in snapshots if len(x) >= max(k, 3)), snapshots[-1]).copy()
        d = d[d.text_search.str.strip().str.len() > 0]
        if d.empty: return []
        texts = d.text_search.tolist(); vec = TfidfVectorizer(lowercase=True, ngram_range=(1, 2), min_df=1).fit(texts)
        tf = np.asarray((vec.transform(texts) @ vec.transform([query]).T).toarray()).ravel()
        bm = self._bm25([tokens(x) for x in texts], tokens(query))
        rankings = []
        if system in {"tfidf", "hybrid"}: rankings.append(np.argsort(-tf).tolist())
        if system in {"bm25", "hybrid"}: rankings.append(np.argsort(-bm).tolist())
        dense_scores = None
        if system in {"dense", "hybrid"} and self.encoder is not None and self.embeddings is not None:
            q = self.encoder.encode([query], normalize_embeddings=True)[0]
            dense_scores = self.embeddings[d.index.to_numpy()] @ q; rankings.append(np.argsort(-dense_scores).tolist())
        if not rankings: return []
        fused = rrf(rankings); order = sorted(fused, key=fused.get, reverse=True)
        out = []
        for pos in order:
            # Never fill top-k with zero-relevance lexical/dense results.
            if tf[pos] <= 0 and bm[pos] <= 0 and (dense_scores is None or dense_scores[pos] < .25): continue
            r = d.iloc[pos]
            out.append({"review_id": r.review_id, "order_id": r.order_id, "score": int(r.score), "text_pt": r.full_pt,
                        "text_fr": r.full_fr, "translation_status": r.translation_status, "published_at": r.available_at.isoformat(),
                        "customer_state": r.get("customer_state"), "category": r.get("primary_category"),
                        "delivery_duration_days": None if pd.isna(r.get("delivery_duration_days")) else float(r.delivery_duration_days),
                        "retrieval_system": system, "rrf_score": fused[pos]})
            if len(out) >= k: break
        return out


def similar_orders(store: DataStore, order_id: str, as_of: Any, k: int = 5) -> list[dict]:
    o = store.orders; oid = str(order_id)
    if oid not in o.index: raise KeyError(f"Commande {oid} introuvable")
    target = o.loc[oid]; t = pd.Timestamp(as_of).tz_localize(None)
    known = o[(o.order_id != oid) & o.order_delivered_customer_date.notna() & (o.order_delivered_customer_date <= t)].copy()
    if "order_status" in known: known = known[known.order_status == "delivered"]
    dims = [c for c in ("promised_days", "distance_km", "freight_total", "item_price_total", "product_weight_mean_g") if c in known and pd.notna(target.get(c))]
    for c in dims:
        scale = max(float(known[c].mad() if hasattr(known[c], "mad") else (known[c] - known[c].median()).abs().median()), 1e-6)
        known[f"_d_{c}"] = (known[c] - float(target[c])).abs() / scale
    known["_distance"] = known[[f"_d_{c}" for c in dims]].mean(axis=1) if dims else 0.
    if "customer_state" in known: known["_distance"] += (known.customer_state != target.get("customer_state")).astype(float) * .5
    if "primary_category" in known: known["_distance"] += (known.primary_category != target.get("primary_category")).astype(float) * .75
    cols = [c for c in ("order_id", "customer_state", "primary_category", "delivery_duration_days", "order_delivered_customer_date", "is_late", "review_score") if c in known]
    return [{**r[cols].to_dict(), "similarity_distance": float(r["_distance"])} for _, r in known.nsmallest(k, "_distance").iterrows()]
