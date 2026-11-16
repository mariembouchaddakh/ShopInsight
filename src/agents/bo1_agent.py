"""Agent BO1 — DS1.3 « Agent de diagnostic préventif » (Anticiper les commandes problématiques).

Question traitée : « Cette commande risque-t-elle d'arriver en retard ou de recevoir une note de 1-2 ? Pourquoi ?
Que faire avant que cela arrive ? » + tri d'une liste de commandes à surveiller.

Outils (tous déterministes, sources = fichiers du pipeline) :
  get_order_context     faits connus à l'approbation (+ issue réelle uniquement en mode audit/rétrospectif)
  predict_risk          scores DS1.1 (retard) et DS1.2 (note 1-2), percentile, tranche, taux observé sur TEST
  explain_risk          facteurs : effet d'un groupe de variables sur le percentile (occlusion vs commande médiane)
  find_similar_orders   commandes comparables DÉJÀ TERMINÉES au moment de l'achat, avec leur issue
  get_context_rates     taux de retard / mauvaise note de la région, de la catégorie, du vendeur (issues connues avant l'achat)
  triage_orders         classement des commandes d'un mois à surveiller en priorité

Aucune cause de retard n'est enregistrée dans Olist : les « facteurs » sont des associations du modèle, pas des causes.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .core import (ESTIMATE, FACT, SIMILAR, DataStore, EvidenceLog, LLMClient, Line, Report, Tool, pct, run_tool_loop,
                   to_native, verify_narrative)

GROUPS = {
    "la promesse de livraison": lambda c: c == "promised_days",
    "la géographie (région, distance)": lambda c: c.startswith("state_") or c in ("same_state", "distance_km_log", "distance_km_missing"),
    "le vendeur (historique, retards passés)": lambda c: c.startswith("te_seller") or c in ("seller_train_orders_log", "seller_count"),
    "le produit et sa catégorie": lambda c: c.startswith("te_category") or c.startswith("product_"),
    "le panier (valeur, frais de port, nombre d'articles)": lambda c: c in ("item_price_total_log", "freight_total_log", "item_count",
                                                                          "item_price_total_missing", "freight_total_missing"),
    "le paiement": lambda c: c.startswith("payment_"),
    "le calendrier et le délai d'approbation": lambda c: c in ("purchase_weekday", "purchase_hour", "purchase_month_num", "is_weekend",
                                                              "approval_delay_hours_log", "approval_delay_hours_missing"),
}
SIM_COLS = ["promised_days", "distance_km_log", "freight_total_log", "item_price_total_log", "product_weight_mean_g_log"]
TARGET_LABEL = {"late": "retard de livraison (DS1.1)", "poor": "note de 1 ou 2 (DS1.2)"}
HEX32 = re.compile(r"\b[0-9a-f]{32}\b")


def _group_of(col: str) -> str | None:
    for g, f in GROUPS.items():
        if f(col):
            return g
    return None


class PreventiveDiagnosisAgent:
    def __init__(self, project_dir: str | Path = ".", llm: LLMClient | None = None) -> None:
        self.store = DataStore(project_dir)
        self.llm = llm
        art = self.store.dir / "data/model/artifacts"
        if not (art / "model_late.joblib").exists():
            raise FileNotFoundError("Modèles absents : lancez `python src/train_agent_models.py --project-dir .`")
        self.bundles = {s: joblib.load(art / f"model_{s}.joblib") for s in ("late", "poor")}
        self.card = json.loads((art / "model_card.json").read_text())
        self.log = EvidenceLog()
        self.audit = False
        self.target_order: str | None = None
        self._reviews_by_order: pd.DataFrame | None = None

    # ------------------------------------------------------------------ utilitaires
    def _score(self, short: str, X: np.ndarray) -> np.ndarray:
        return self.bundles[short]["model"].predict_proba(X)[:, 1]

    def _percentile(self, short: str, s: np.ndarray | float) -> np.ndarray | float:
        ref = self.bundles[short]["ref_scores"]
        return np.searchsorted(ref, s, side="right") / len(ref)

    def _row(self, order_id: str) -> pd.Series:
        f = self.store.all_features
        if order_id not in f.index:
            raise KeyError(f"Commande {order_id} hors périmètre de modélisation (mois incomplet, statut sans étiquette ou identifiant inconnu).")
        r = f.loc[order_id]
        return r.iloc[0] if isinstance(r, pd.DataFrame) else r

    def _band(self, short: str, percentile: float) -> dict:
        dec = self.card[short]["deciles"]

        def pooled(ids):
            sel = [d for d in dec if d["decile"] in ids and d["observed_rate"] is not None]
            n = sum(d["n"] for d in sel)
            return {"n": n, "rate": sum(d["n"] * d["observed_rate"] for d in sel) / n if n else None}

        if percentile >= 0.90:
            return {"band": "élevé", "definition": "10 % des scores les plus hauts", **pooled([10])}
        if percentile >= 0.70:
            return {"band": "modéré", "definition": "scores entre le 70e et le 90e percentile", **pooled([8, 9])}
        return {"band": "faible", "definition": "70 % des scores les plus bas", **pooled(range(1, 8))}

    def _reviews_idx(self) -> pd.DataFrame:
        if self._reviews_by_order is None:
            try:
                r = self.store.reviews()
                self._reviews_by_order = r.drop_duplicates("order_id").set_index("order_id")
            except FileNotFoundError:
                self._reviews_by_order = pd.DataFrame()
        return self._reviews_by_order

    # ------------------------------------------------------------------ outils
    def get_order_context(self, order_id: str) -> dict:
        """Faits connus au moment de l'approbation de la commande (et, en mode audit seulement, son issue réelle)."""
        o = self.store.orders
        if order_id not in o.index:
            raise KeyError(f"Commande inconnue : {order_id}")
        r = o.loc[order_id]
        feat = self.store.all_features.loc[order_id] if order_id in self.store.all_features.index else None
        km = None
        if feat is not None and not feat["distance_km_missing"]:
            km = float(np.expm1(feat["distance_km_log"]))
        promised = None
        if pd.notna(r["order_estimated_delivery_date"]):
            promised = int((r["order_estimated_delivery_date"].normalize() - r["order_purchase_timestamp"].normalize()).days)
        payload = {"order_id": order_id, "purchase_month": r["purchase_month"], "customer_state": r["customer_state"],
                   "primary_category": r["primary_category"], "promised_days": promised, "distance_km": None if km is None else round(km),
                   "item_count": int(r["item_count"]), "seller_count": int(r["seller_count"]),
                   "item_price_total": None if pd.isna(r["item_price_total"]) else round(float(r["item_price_total"]), 2),
                   "freight_total": None if pd.isna(r["freight_total"]) else round(float(r["freight_total"]), 2),
                   "single_seller_id": None if pd.isna(r["single_seller_id"]) else r["single_seller_id"],
                   "split": None if feat is None else feat["split"],
                   "missing_flags": [] if feat is None else [c.replace("_missing", "") for c in feat.index if c.endswith("_missing") and feat[c] == 1]}
        self.log.add(f"ord:{order_id}", FACT, "silver/orders_analysis.csv.gz (variables connues à l'approbation)", payload)
        self.target_order = order_id
        if self.audit:
            out = {"is_late": None if pd.isna(r["is_late"]) else int(r["is_late"]),
                   "late_days": None if pd.isna(r["late_days"]) else round(float(r["late_days"]), 1),
                   "review_score": None if pd.isna(r["review_score"]) else int(r["review_score"]),
                   "order_status": r["order_status"]}
            self.log.add(f"ord:{order_id}:issue", FACT, "silver/orders_analysis.csv.gz (RÉTROSPECTIF, inconnu à la décision)", out)
            payload = {**payload, "retrospective_outcome": out}
        return to_native(payload)

    def predict_risk(self, order_id: str) -> dict:
        """Scores DS1.1 et DS1.2, percentile par rapport à la période TEST, tranche et taux observé dans cette tranche."""
        row = self._row(order_id)
        res = {}
        for short in ("late", "poor"):
            b = self.bundles[short]
            x = row[b["features"]].astype(float).values.reshape(1, -1)
            s = float(self._score(short, x)[0])
            pc = float(self._percentile(short, s))
            band = self._band(short, pc)
            c = self.card[short]
            payload = {"target": TARGET_LABEL[short], "model": b["model_name"], "score": round(s, 4), "percentile": round(pc, 3), "percentile_points": int(round(100 * pc)),
                       "band": band["band"], "band_definition": band["definition"], "band_observed_rate": band["rate"], "band_n": band["n"],
                       "base_rate_test": c["test_prevalence"], "test_pr_auc": round(c["test_pr_auc"], 3),
                       "top10_precision": c["top10_precision"], "top10_recall": c["top10_recall"],
                       "in_sample": row["split"] in ("train", "valid")}
            self.log.add(f"mdl:{short}:{order_id}", ESTIMATE, f"data/model/artifacts/model_{short}.joblib", payload)
            res[short] = payload
        return to_native(res)

    def explain_risk(self, order_id: str, target: str = "late", top: int = 3) -> dict:
        """Facteurs associés au score : on remplace chaque groupe de variables par la commande médiane (TRAIN) et on mesure
        le changement de percentile. > 0 : le groupe pousse le risque vers le haut. Association, pas cause."""
        short = {"late": "late", "poor": "poor"}[target]
        b = self.bundles[short]
        row = self._row(order_id)
        cols = b["features"]
        x0 = row[cols].astype(float).values.copy()
        ref = np.array([b["reference_row"][c] for c in cols], dtype=float)
        base_pc = float(self._percentile(short, self._score(short, x0.reshape(1, -1))[0]))
        groups: dict[str, list[int]] = {}
        for i, c in enumerate(cols):
            g = _group_of(c)
            if g is None:
                raise ValueError(f"variable sans groupe d'explication : {c}")
            groups.setdefault(g, []).append(i)
        effects = []
        for g, idx in groups.items():
            x = x0.copy()
            x[idx] = ref[idx]
            pc = float(self._percentile(short, self._score(short, x.reshape(1, -1))[0]))
            effects.append({"group": g, "delta_percentile_points": round(100 * (base_pc - pc), 1)})
        effects.sort(key=lambda e: -abs(e["delta_percentile_points"]))
        kept = [e for e in effects if abs(e["delta_percentile_points"]) >= 2][:top]
        ctx = {"promised_days": float(row["promised_days"]), "promised_days_typical": float(b["reference_row"]["promised_days"]),
               "distance_km": None if row["distance_km_missing"] else round(float(np.expm1(row["distance_km_log"]))),
               "customer_state": next((c[6:] for c in cols if c.startswith("state_") and row[c] == 1), "unknown"),
               "seller_orders_seen_in_train": round(float(np.expm1(row["seller_train_orders_log"])))}
        payload = {"target": TARGET_LABEL[short], "percentile": round(base_pc, 3), "percentile_points": int(round(100 * base_pc)), "drivers": kept, "values": ctx,
                   "method": "occlusion par groupe vs commande médiane du TRAIN"}
        self.log.add(f"mdl:{short}:drivers:{order_id}", ESTIMATE, "occlusion sur le modèle " + b["model_name"], payload)
        return to_native(payload)

    def find_similar_orders(self, order_id: str, k: int = 8) -> dict:
        """k commandes comparables (même État si possible ; promesse, distance, port, valeur, poids proches) dont l'issue était
        DÉJÀ connue à la date d'achat de la commande cible : aucune information du futur."""
        f = self.store.all_features
        o = self.store.orders
        row = self._row(order_id)
        t0 = row["order_purchase_timestamp"]
        cand = f[f["late_label_eligible"].astype(bool) & (f.index != order_id)]
        delivered = o["order_delivered_customer_date"].reindex(cand.index)
        cand = cand[(delivered <= t0).values]
        state_cols = [c for c in f.columns if c.startswith("state_")]
        my_state = next((c for c in state_cols if row[c] == 1), None)
        same = cand[cand[my_state] == 1] if my_state else cand
        pool = same if len(same) >= 3 * k else cand
        if len(pool) == 0:
            payload = {"k": 0, "note": "aucune commande terminée avant cette date d'achat"}
            self.log.add(f"ord:{order_id}:similar", SIMILAR, "features + orders_analysis", payload)
            return payload
        Z = pool[SIM_COLS].astype(float)
        sd = Z.std().replace(0, 1)
        d = (((Z - row[SIM_COLS].astype(float)) / sd) ** 2).sum(axis=1) ** 0.5
        nn = d.nsmallest(k).index
        rv = self._reviews_idx()
        cases = []
        for oid in nn:
            r = o.loc[oid]
            known_review = pd.notna(r["review_answer_timestamp"]) and r["review_answer_timestamp"] <= t0
            case = {"order_id": oid, "month": r["purchase_month"], "state": r["customer_state"], "category": r["primary_category"],
                    "promised_days": int(f.loc[oid, "promised_days"]), "is_late": int(r["is_late"]),
                    "late_days": None if pd.isna(r["late_days"]) else round(float(r["late_days"]), 1),
                    "review_score": int(r["review_score"]) if known_review and pd.notna(r["review_score"]) else None,
                    "distance_to_target": round(float(d[oid]), 2)}
            if known_review and len(rv) and oid in rv.index:
                txt = rv.loc[oid, "full_fr"] or rv.loc[oid, "full_pt"]
                case["review_excerpt"] = (txt[:220] + "…") if len(txt) > 220 else txt
                case["review_id"] = rv.loc[oid, "review_id"]
                case["excerpt_is_machine_translated"] = bool(rv.loc[oid, "full_fr"])
            cases.append(case)
            self.log.add(f"ord:{oid}", SIMILAR, "features + orders_analysis (commande comparable, issue connue avant l'achat cible)", case)
        known = [c for c in cases if c["review_score"] is not None]
        payload = {"k": len(cases), "same_state_pool": bool(len(same) >= 3 * k), "n_late": sum(c["is_late"] for c in cases),
                   "n_reviewed": len(known), "n_poor": sum(1 for c in known if c["review_score"] <= 2),
                   "pool_size": int(len(pool)), "cases": cases, "criteria": "promesse, distance, frais de port, valeur, poids"}
        self.log.add(f"ord:{order_id}:similar", SIMILAR, "synthèse des commandes comparables", payload)
        return to_native(payload)

    def get_context_rates(self, order_id: str, window_days: int = 90) -> dict:
        """Taux de retard / note 1-2 récents (État du client, catégorie, vendeur, marketplace), calculés UNIQUEMENT sur les issues
        déjà connues à la date d'achat t0 de la commande cible :
          - retard : commandes achetées dans les `window_days` jours avant t0 dont la date PROMISE est passée avant t0
            (à cette date on sait si la commande est arrivée à temps ou non) ;
          - note 1-2 : avis déjà publiés avant t0.
        Les tables KPI mensuelles ne conviennent pas ici : elles agrègent des issues observées après t0."""
        o = self.store.orders
        r = o.loc[order_id]
        t0 = r["order_purchase_timestamp"]
        recent = o[(o["order_purchase_timestamp"] < t0) & (o["order_purchase_timestamp"] >= t0 - pd.Timedelta(days=window_days))]
        late_known = recent[recent["late_label_eligible"].astype(bool) & (recent["order_estimated_delivery_date"] < t0)]
        rev_known = recent[recent["poor_review_label_eligible"].astype(bool) & (recent["review_answer_timestamp"] <= t0)]
        months = sorted(recent["purchase_month"].dropna().unique().tolist())
        out: dict = {}

        def rates(mask_late, mask_rev) -> dict | None:
            lk, rk = late_known[mask_late(late_known)], rev_known[mask_rev(rev_known)]
            if len(lk) < 20 and len(rk) < 20:
                return None
            return {"months": months, "window_days": window_days, "n_late_known": int(len(lk)), "n_reviews_known": int(len(rk)),
                    "late_rate": float(lk["is_late"].astype(float).mean()) if len(lk) >= 20 else None,
                    "poor_review_rate": float(rk["is_poor_review"].astype(float).mean()) if len(rk) >= 20 else None}

        for tag, col in (("state", "customer_state"), ("category", "primary_category")):
            key = r[col]
            if isinstance(key, str):
                res = rates(lambda d, c=col, k=key: d[c] == k, lambda d, c=col, k=key: d[c] == k)
                if res:
                    out[tag] = res
                    self.log.add(f"kpi:{tag}:{key}:{r['purchase_month']}", FACT, f"orders_analysis — issues connues avant l'achat ({window_days} j)", res)
        nat = rates(lambda d: np.ones(len(d), bool), lambda d: np.ones(len(d), bool))
        if nat:
            out["national"] = nat
            self.log.add(f"kpi:national:{r['purchase_month']}", FACT, f"orders_analysis — issues connues avant l'achat ({window_days} j)", nat)
        sid = r["single_seller_id"]
        if isinstance(sid, str):
            hist = o[(o["single_seller_id"] == sid) & (o["order_purchase_timestamp"] < t0)]
            known = hist[hist["late_label_eligible"].astype(bool) & (hist["order_estimated_delivery_date"] < t0)]
            if len(hist):
                res = {"orders_before": int(len(hist)), "n_late_known": int(len(known)),
                       "late_rate": float(known["is_late"].astype(float).mean()) if len(known) else None,
                       "low_volume": bool(len(known) < 10)}
                self.log.add(f"kpi:seller:{sid[:8]}:{r['purchase_month']}", FACT, "orders_analysis (commandes mono-vendeur, issues connues avant l'achat)", res)
                out["seller"] = res
        return to_native(out)

    def triage_orders(self, period: str, top_k: int = 20, target: str = "late") -> dict:
        """Classe les commandes approuvées d'un mois (AAAA-MM) selon le risque. En mode audit, mesure ce que ce tri aurait capturé."""
        short = target
        f = self.store.all_features
        d = f[f["order_purchase_timestamp"].dt.strftime("%Y-%m") == period]
        if d.empty:
            raise KeyError(f"Aucune commande modélisée pour {period} (mois incomplet ou hors période).")
        b = self.bundles[short]
        sc = self._score(short, d[b["features"]].astype(float).values)
        d = d.assign(score=sc, percentile=self._percentile(short, sc)).sort_values("score", ascending=False)
        n_top = max(1, int(len(d) * 0.10))
        listing = [{"order_id": i, "percentile": round(float(p), 3), "percentile_points": int(round(100 * float(p))), "state": next((c[6:] for c in d.columns if c.startswith("state_") and d.loc[i, c] == 1), "?"),
                    "promised_days": int(d.loc[i, "promised_days"])} for i, p in zip(d.index[:top_k], d["percentile"].iloc[:top_k])]
        payload = {"period": period, "target": TARGET_LABEL[short], "n_orders": int(len(d)), "top10pct_size": n_top, "listing": listing,
                   "expected_capture": self.card[short]["top10_recall"], "expected_precision": self.card[short]["top10_precision"],
                   "evaluated_on": self.card[short]["evaluated_on"]}
        elig = {"late": "late_label_eligible", "poor": "poor_review_label_eligible"}[short]
        tcol = self.bundles[short]["target"]
        lab = d[d[elig].astype(bool)]
        if self.audit and len(lab):
            top_lab = lab.nlargest(max(1, int(len(lab) * 0.10)), "score")
            payload["backtest"] = {"n_labelled": int(len(lab)), "positives": int(lab[tcol].sum()),
                                   "captured_in_top10pct": int(top_lab[tcol].sum()), "precision_top10pct": float(top_lab[tcol].mean()),
                                   "base_rate": float(lab[tcol].mean()), "split": d["split"].iloc[0],
                                   "warning": "modèle entraîné sur ce mois" if d["split"].iloc[0] in ("train", "valid") else None}
        self.log.add(f"mdl:triage:{short}:{period}", ESTIMATE, f"model_{short}.joblib", payload)
        return to_native(payload)

    # ------------------------------------------------------------------ composition du rapport
    def _tools(self) -> list[Tool]:
        oid = {"type": "object", "properties": {"order_id": {"type": "string", "description": "identifiant de commande (32 hex)"}}, "required": ["order_id"]}
        tgt = {"type": "object", "properties": {"order_id": {"type": "string"}, "target": {"type": "string", "enum": ["late", "poor"]}}, "required": ["order_id"]}
        return [
            Tool("get_order_context", "Faits connus à l'approbation d'une commande.", oid, self.get_order_context),
            Tool("predict_risk", "Risque de retard (DS1.1) et de note 1-2 (DS1.2) d'une commande.", oid, self.predict_risk),
            Tool("explain_risk", "Facteurs associés au risque d'une commande.", tgt, self.explain_risk),
            Tool("find_similar_orders", "Commandes comparables déjà terminées, avec leur issue.", oid, self.find_similar_orders),
            Tool("get_context_rates", "Taux récents de la région, catégorie, vendeur.", oid, self.get_context_rates),
            Tool("triage_orders", "Classe les commandes d'un mois par risque.",
                 {"type": "object", "properties": {"period": {"type": "string", "description": "AAAA-MM"}, "top_k": {"type": "integer"},
                                                    "target": {"type": "string", "enum": ["late", "poor"]}}, "required": ["period"]}, self.triage_orders),
        ]

    def diagnose(self, order_id: str, audit: bool = False, use_llm: bool = True) -> Report:
        """Pipeline complet pour une commande. audit=True : affiche aussi l'issue réelle (rétrospectif, pour évaluer l'agent)."""
        self.log, self.audit = EvidenceLog(), audit
        order_id = order_id.strip().lower()
        ctx = self.get_order_context(order_id)
        try:
            self.predict_risk(order_id)
        except KeyError as e:
            rep = Report(f"Diagnostic préventif — commande {order_id[:8]}…")
            rep.facts.append(Line(f"{e}", [f"ord:{order_id}"]))
            rep.caveats.append("Pas de score : la commande n'a pas de variables de modélisation.")
            return rep
        self.explain_risk(order_id, "late")
        self.explain_risk(order_id, "poor")
        self.find_similar_orders(order_id)
        self.get_context_rates(order_id)
        rep = self._compose_order(order_id, audit)
        if use_llm and self.llm:
            self._llm_narrative(rep, f"Rédige un résumé de diagnostic préventif pour la commande {order_id}.")
        return rep

    def _compose_order(self, oid: str, audit: bool) -> Report:
        L = self.log
        ctx = L.get(f"ord:{oid}").payload
        pl, pp = L.get(f"mdl:late:{oid}").payload, L.get(f"mdl:poor:{oid}").payload
        dl, dp = L.get(f"mdl:late:drivers:{oid}").payload, L.get(f"mdl:poor:drivers:{oid}").payload
        sim = L.get(f"ord:{oid}:similar").payload
        rep = Report(f"Diagnostic préventif — commande {oid[:8]}… ({ctx['customer_state']}, {ctx['primary_category']})")

        # FAITS
        dist = f", vendeur à ≈ {ctx['distance_km']} km" if ctx["distance_km"] is not None else ""
        rep.facts.append(Line(f"Commande passée en {ctx['purchase_month']} par un client de l'État {ctx['customer_state']} : catégorie {ctx['primary_category']}, "
                              f"{ctx['item_count']} article(s), valeur {ctx['item_price_total']} R$ + port {ctx['freight_total']} R$, "
                              f"promesse de livraison affichée : {ctx['promised_days']} jours{dist}.", [f"ord:{oid}"]))
        for key, label in (("state", "État du client"), ("category", "catégorie"), ("national", "ensemble de la marketplace")):
            for e in L.with_prefix(f"kpi:{key}:"):
                v = e.payload
                if key == "national" and not e.id.startswith("kpi:national"):
                    continue
                if v.get("late_rate") is not None or v.get("poor_review_rate") is not None:
                    lr = pct(v["late_rate"]) if v.get("late_rate") is not None else "n/d"
                    pr = pct(v["poor_review_rate"]) if v.get("poor_review_rate") is not None else "n/d"
                    rep.facts.append(Line(f"Sur les {v['window_days']} jours avant l'achat, {label} (issues déjà connues à cette date : "
                                          f"{v['n_late_known']} livraisons, {v['n_reviews_known']} avis) : retard {lr}, note 1-2 {pr}.", [e.id]))
        for e in L.with_prefix("kpi:seller:"):
            v = e.payload
            txt = (f"Vendeur : {v['orders_before']} commandes mono-vendeur avant celle-ci, dont {v['n_late_known']} à l'issue connue ; "
                   f"retard {pct(v['late_rate']) if v['late_rate'] is not None else 'n/d'}.")
            if v["low_volume"]:
                txt += " Historique trop court (< 10 commandes) pour juger le vendeur."
            rep.facts.append(Line(txt, [e.id]))
        if ctx["missing_flags"]:
            rep.facts.append(Line("Valeurs manquantes imputées pour le modèle : " + ", ".join(ctx["missing_flags"]) + ".", [f"ord:{oid}"]))
        if audit:
            out = L.get(f"ord:{oid}:issue").payload
            rep.facts.append(Line(f"RÉTROSPECTIF (inconnu à la décision) — retard : {out['is_late']} (jours : {out['late_days']}), note : {out['review_score']}, statut : {out['order_status']}.",
                                  [f"ord:{oid}:issue"]))

        # ESTIMATIONS
        for short, p, dr in (("late", pl, dl), ("poor", pp, dp)):
            rate = p["band_observed_rate"]
            rep.estimates.append(Line(
                f"Risque de {p['target']} : {p['band']} (percentile {p['percentile_points']} des scores). Dans cette tranche ({p['band_definition']}), "
                f"{pct(rate)} des commandes d'avril–août 2018 ont connu l'événement, contre {pct(p['base_rate_test'])} en moyenne ({p['band_n']} commandes).",
                [f"mdl:{short}:{oid}"]))
            if dr["drivers"]:
                parts = [f"{e['group']} ({'+' if e['delta_percentile_points'] > 0 else ''}{e['delta_percentile_points']} points de percentile)" for e in dr["drivers"]]
                rep.estimates.append(Line(f"Facteurs associés au score ({p['target']}) : " + " ; ".join(parts) + ". Ce sont des associations, pas des causes.",
                                          [f"mdl:{short}:drivers:{oid}"]))
        # AUTRES CLIENTS
        if sim.get("k"):
            rep.similar.append(Line(f"Parmi {sim['k']} commandes comparables terminées avant cet achat ({sim['criteria']}), {sim['n_late']} ont été livrées en retard"
                                    + (f" et {sim['n_poor']} sur {sim['n_reviewed']} évaluées ont reçu 1-2 étoiles." if sim["n_reviewed"] else ".")
                                    + (" Petit échantillon : indicatif seulement." if sim["k"] < 20 else ""), [f"ord:{oid}:similar"]))
            for c in [c for c in sim["cases"] if c.get("review_excerpt")][:3]:
                if True:
                    mt = " (traduction automatique)" if c.get("excerpt_is_machine_translated") else ""
                    rep.similar.append(Line(f"Autre client, {c['state']}, promesse {c['promised_days']} j, {'en retard' if c['is_late'] else 'à l’heure'}, note {c['review_score']}/5 : « {c['review_excerpt']} »{mt}",
                                            [f"ord:{c['order_id']}"]))
        # ACTIONS
        rep.actions.extend(self._actions(oid, pl, pp, dl, dp, ctx))
        # LIMITES
        rep.caveats += [
            f"Signal faible : PR-AUC test {pl['test_pr_auc']} (retard) et {pp['test_pr_auc']} (note 1-2) pour des taux de base de {pct(pl['base_rate_test'])} et {pct(pp['base_rate_test'])}. "
            "Le score sert à prioriser une surveillance, pas à prédire un cas individuel.",
            "Aucune cause de retard n'est enregistrée dans Olist ; les facteurs et actions sont des hypothèses à tester.",
            "Données historiques (2016–2018), pas de flux temps réel.",
        ]
        if pl["in_sample"]:
            rep.caveats.append("Cette commande appartient à la période d'entraînement : le score est optimiste (dans l'échantillon). Utiliser une commande d'avril–août 2018 pour une évaluation honnête.")
        if ctx["seller_count"] > 1:
            rep.caveats.append("Commande multi-vendeurs : retard et avis ne sont pas attribuables à un seul vendeur.")
        rep.narrative = self._deterministic_narrative(pl, pp, dl, ctx)
        rep.meta = {"order_id": oid, "audit": audit, "tool_calls": len(self.log.tool_calls)}
        return rep

    @staticmethod
    def _deterministic_narrative(pl: dict, pp: dict, dl: dict, ctx: dict) -> str:
        s = (f"Risque de retard {pl['band']} (percentile {pl['percentile_points']}) et risque de mauvaise note {pp['band']} "
             f"(percentile {pp['percentile_points']}) pour cette commande vers {ctx['customer_state']}.")
        if dl["drivers"]:
            top = dl["drivers"][0]
            s += f" Premier facteur associé au retard : {top['group']} ({top['delta_percentile_points']:+} points de percentile)."
        return s

    def _actions(self, oid: str, pl: dict, pp: dict, dl: dict, dp: dict, ctx: dict) -> list[Line]:
        acts: list[Line] = []
        late_hi, poor_hi = pl["band"] in ("élevé", "modéré"), pp["band"] in ("élevé", "modéré")
        drivers = {e["group"]: e["delta_percentile_points"] for e in dl["drivers"]}
        ev = [f"mdl:late:drivers:{oid}"]
        if late_hi:
            if drivers.get("la promesse de livraison", 0) > 0:
                acts.append(Line(f"Prévenir le client avec une fourchette de délai réaliste ; examiner si la promesse de {ctx['promised_days']} jours "
                                 "est trop courte pour ce trajet.", ev))
            if drivers.get("la géographie (région, distance)", 0) > 0:
                acts.append(Line("Suivi renforcé du colis (point de contrôle à mi-parcours) : région ou distance associée à davantage de retards.", ev))
            if drivers.get("le vendeur (historique, retards passés)", 0) > 0:
                acts.append(Line("Rappeler au vendeur la date limite d'expédition et vérifier son historique récent.", ev))
            if drivers.get("le produit et sa catégorie", 0) > 0 or drivers.get("le panier (valeur, frais de port, nombre d'articles)", 0) > 0:
                acts.append(Line("Vérifier le conditionnement et le transporteur pour ce type de produit (poids, volume, valeur).", ev))
            if not acts:
                acts.append(Line("Placer la commande sur la liste de surveillance (risque élevé sans facteur dominant).", [f"mdl:late:{oid}"]))
        if poor_hi and not late_hi:
            acts.append(Line("Risque de mauvaise note sans risque de retard : vérifier la conformité de la fiche produit (description, photos) et prévoir un message de suivi après livraison.",
                             [f"mdl:poor:{oid}"]))
        if not late_hi and not poor_hi:
            acts.append(Line("Aucune action spécifique : surveillance standard.", [f"mdl:late:{oid}", f"mdl:poor:{oid}"]))
        acts.append(Line("Mesurer l'effet de toute action (comparaison avec des commandes comparables non traitées) avant de la généraliser.", []))
        return acts

    def triage(self, period: str, top_k: int = 20, target: str = "late", audit: bool = False) -> Report:
        self.log, self.audit = EvidenceLog(), audit
        p = self.triage_orders(period, top_k, target)
        rep = Report(f"Commandes à surveiller en priorité — {period} ({p['target']})")
        rep.facts.append(Line(f"{p['n_orders']} commandes approuvées en {period} ; le top 10 % représente {p['top10pct_size']} commandes.", [f"mdl:triage:{target}:{period}"]))
        rep.estimates.append(Line(f"Sur avril–août 2018 (hors échantillon), le top 10 % des scores contenait {pct(p['expected_capture'])} des événements, "
                                  f"avec une précision de {pct(p['expected_precision'])}.", [f"mdl:triage:{target}:{period}"]))
        if "backtest" in p:
            b = p["backtest"]
            rep.facts.append(Line(f"Rétrospectif ({period}) : {b['captured_in_top10pct']} événements sur {b['positives']} capturés dans le top 10 % ; précision {pct(b['precision_top10pct'])} "
                                  f"contre {pct(b['base_rate'])} au hasard." + (f" ATTENTION : {b['warning']}." if b["warning"] else ""), [f"mdl:triage:{target}:{period}"]))
        for it in p["listing"][:10]:
            rep.estimates.append(Line(f"Commande {it['order_id']} — {it['state']}, promesse {it['promised_days']} j, percentile {it['percentile_points']}.", [f"mdl:triage:{target}:{period}"]))
        rep.actions.append(Line("Affecter la liste à l'équipe logistique : suivi renforcé et message proactif sur le top 10 % ; mesurer le taux de retard avant/après.", [f"mdl:triage:{target}:{period}"]))
        rep.caveats += ["Le tri améliore la priorisation mais reste faible en absolu (la majorité des commandes du top 10 % arrivent à l'heure).",
                        "Associations statistiques, pas de causes enregistrées."]
        rep.narrative = f"{p['top10pct_size']} commandes à surveiller en priorité sur {p['n_orders']} en {period}."
        return rep

    def ask(self, question: str, audit: bool = False) -> Report:
        """Point d'entrée en langage naturel. Avec LLM : boucle outils ; sans LLM : routage par mots-clés."""
        m = HEX32.search(question.lower())
        per = re.search(r"\b(20\d{2}-\d{2})\b", question)
        if m:
            return self.diagnose(m.group(0), audit=audit)
        if per and re.search(r"priorit|risque|surveill|trier|tri |top|liste", question.lower()):
            tgt = "poor" if re.search(r"avis|note|satisf", question.lower()) else "late"
            return self.triage(per.group(1), target=tgt, audit=audit)
        if self.llm:
            self.log, self.audit = EvidenceLog(), audit
            sys_p = ("Tu es l'agent de diagnostic préventif REHEARSE. Utilise les outils pour répondre ; ne donne jamais de chiffre qui ne vienne pas d'un outil. "
                     "Distingue faits, estimations et expériences d'autres clients. Réponds en français.")
            txt = run_tool_loop(self.llm, sys_p, question, self._tools(), self.log)
            rep = Report("Réponse de l'agent BO1")
            rep.narrative = txt or ""
            return rep
        rep = Report("Agent BO1 — question non comprise")
        rep.narrative = "Donnez un identifiant de commande (32 caractères hexadécimaux) ou une période AAAA-MM pour obtenir une liste de commandes à surveiller."
        return rep

    def _llm_narrative(self, rep: Report, instruction: str) -> None:
        payload = json.dumps(to_native({"facts": [vars(x) for x in rep.facts], "estimates": [vars(x) for x in rep.estimates],
                                        "similar": [vars(x) for x in rep.similar]}), ensure_ascii=False)[:5000]
        try:
            msg = self.llm.chat([
                {"role": "system", "content": "Tu rédiges en français 3 phrases maximum à partir des seules preuves fournies. Aucun chiffre hors preuves. "
                                              "Distingue ce qui est observé de ce qui est estimé. Pas de cause affirmée."},
                {"role": "user", "content": instruction + "\nPREUVES :\n" + payload}])
            text = (msg.get("content") or "").strip()
        except Exception:
            return
        ok, problems = verify_narrative(text, self.log)
        if ok and text:
            rep.narrative, rep.narrative_source = text, "llm_verifie"
        else:
            rep.meta["llm_narrative_rejected"] = problems
