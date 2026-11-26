"""Tests de l'agent BO3 sur les VRAIES données Olist :  python -m unittest tests/test_bo3.py -v

Prérequis (sinon les tests sont ignorés avec la marche à suivre) :
  python src/prepare_data.py --source-zip <olist.zip> --project-dir .
  python src/build_model_features.py --project-dir .
  python src/train_seller_models.py --project-dir .
Dossier du projet : variable d'environnement SHOPINSIGHT_PROJECT_DIR (par défaut : la racine du dépôt).

Cas réel de non-régression : le vendeur 2eb70248… est en alerte « niveau » à la fin de juin 2018 sur les avis 1-2 étoiles et la
remise tardive au transporteur (réglages de data/model/artifacts/bo3_model_card.json). À mettre à jour si les réglages changent.
"""
import json
import os
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agents.bo3_agent import SellerAuditAgent  # noqa: E402
from agents.bo3_sellers import alerts, apply_gate, decision_date, inject, month_frame  # noqa: E402
from agents.bo3_support import load_multi_seller_links, verify_bo3_narrative  # noqa: E402
from evaluate_bo3 import truncate_orders  # noqa: E402

PROJECT = Path(os.environ.get("SHOPINSIGHT_PROJECT_DIR", str(ROOT)))
FLAGGED, FLAGGED_MONTH = "2eb70248d66e0e3ef83659f71b244378", "2018-06"


class FakeLLM:
    def __init__(self, replies):
        self.replies = list(replies)

    def chat(self, messages, tools=None, max_tokens=700):
        return self.replies.pop(0)


_FIX: dict = {}


def setUpModule():
    orders = PROJECT / "data/silver/orders_analysis.csv.gz"
    card = PROJECT / "data/model/artifacts/bo3_model_card.json"
    if not orders.exists() or not card.exists():
        raise unittest.SkipTest(f"Données réelles ou modèle BO3 absents dans {PROJECT} : lancer prepare_data.py, build_model_features.py "
                                "puis train_seller_models.py (voir l'en-tête de ce fichier).")
    if "is_late_handover" not in pd.read_csv(orders, nrows=1).columns:
        raise unittest.SkipTest("orders_analysis sans is_late_handover : relancer prepare_data.py.")
    _FIX["ag"] = SellerAuditAgent(PROJECT)  # ≈ 20 s : chargement des 99 441 commandes


class BO3Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ag = _FIX["ag"]

    def frames(self, sd, month, metric):
        """Statistiques et alertes des deux familles pour tous les vendeurs, avec les réglages du modèle retenu."""
        f, _ = month_frame(sd, month, metric, self.ag.cfg, self.ag.base, {})
        f = f.reset_index()
        out = {}
        for fam, c in self.ag.card["detection"].items():
            G = apply_gate(f, int(c["min_history"]), self.ag.base.min_recent)
            out[fam] = G.assign(alert=alerts(G, c["detector"], c["params"]).to_numpy()).set_index("seller_id")
        return out


class TestAsOfRule(BO3Base):
    def test_only_outcomes_known_at_decision(self):
        sd, T = self.ag.sd, decision_date("2018-05")
        d = sd.d
        for metric in ("late", "poor", "handover"):
            c = sd.counts(T, metric)
            rec = d[(d["seller_id"] == FLAGGED) & (d["ts"] >= T - pd.Timedelta(days=90)) & (d["ts"] < T)
                    & d[f"y_{metric}"].notna() & (d[f"k_{metric}"] <= T)]
            self.assertGreater(len(rec), 0)
            self.assertEqual(int(c.loc[FLAGGED, "rec_n"]), len(rec))
            self.assertEqual(int(c.loc[FLAGGED, "rec_x"]), int(rec[f"y_{metric}"].sum()))
            self.assertTrue((rec[f"k_{metric}"] <= T).all() and (rec["ts"] < T).all())

    def test_same_answer_on_truncated_data(self):
        """Mêmes chiffres et mêmes alertes quand on supprime tout ce qui suit la décision (vendeur en alerte + vendeur sans alerte)."""
        m = FLAGGED_MONTH
        quiet = self.frames(self.ag.sd, m, "late")["level"]
        quiet = quiet[quiet["eligible"] & ~quiet["alert"]].sort_values("rec_n", ascending=False).index[0]
        tg = SellerAuditAgent(PROJECT, orders=truncate_orders(self.ag.store.orders, decision_date(m)))
        for sid in (FLAGGED, quiet):
            for metric in ("late", "poor", "handover"):
                a = json.loads(json.dumps(self.ag.compare_to_peers(sid, m, metric)["observed"]))
                b = json.loads(json.dumps(tg.compare_to_peers(sid, m, metric)["observed"]))
                self.assertEqual(a, b)
                da, db = self.ag.detect_deterioration(sid, m, metric), tg.detect_deterioration(sid, m, metric)
                self.assertEqual({f: x["alert"] for f, x in da["families"].items()}, {f: x["alert"] for f, x in db["families"].items()})

    def test_multi_seller_orders_excluded_from_rates(self):
        o = self.ag.store.orders
        multi_ids = set(o.loc[o["is_multi_seller"].astype(bool), "order_id"])
        self.assertEqual(len(multi_ids), 1278)
        self.assertFalse(multi_ids & set(self.ag.sd.d["order_id"]))
        links = load_multi_seller_links(PROJECT)
        both = set(links["seller_id"]) & set(self.ag.sd.d["seller_id"])
        sid = links[links["seller_id"].isin(both)]["seller_id"].value_counts().index[0]
        exp = self.ag.multi_seller_exposure(sid, "2018-06")
        self.assertGreater(exp["multi_seller_orders_12m"], 0)
        self.assertIn("pas attribués", exp["note"])


class TestDetection(BO3Base):
    def test_known_real_case_still_flagged(self):
        for metric in ("poor", "handover"):
            d = self.ag.detect_deterioration(FLAGGED, FLAGGED_MONTH, metric)
            self.assertTrue(d["families"]["level"]["alert"], metric)

    def test_simulated_deterioration_on_real_seller_detected(self):
        """Vendeur réel stable fin mars 2018 ; +35 points de retards simulés à partir d'avril → au moins une alerte d'ici fin juin."""
        sd = self.ag.sd
        base = self.frames(sd, "2018-03", "late")
        lv, tr = base["level"], base["trend"]
        pool = lv[lv["eligible"] & ~lv["alert"] & ~tr.reindex(lv.index)["alert"].fillna(False).astype(bool)]
        sellers = list(pool.sort_values("rec_n", ascending=False).index[:3])
        self.assertTrue(sellers)
        sdi = inject(sd, sellers, "late", decision_date("2018-03"), 0.35, seed=1)
        detected = set()
        for m in ("2018-04", "2018-05", "2018-06"):
            fr = self.frames(sdi, m, "late")
            for fam in fr:
                detected |= set(fr[fam].index[fr[fam]["alert"]]) & set(sellers)
        self.assertTrue(detected, f"aucun des vendeurs {sellers} détecté")

    def test_model_outputs(self):
        res = json.loads((PROJECT / "quality/bo3_model_results.json").read_text(encoding="utf-8"))
        self.assertIn(res["ds3_1_peer_groups"]["selected"], res["ds3_1_peer_groups"]["configs"])
        self.assertEqual(set(res["selected"]), {"level", "trend"})
        for c in res["selected"].values():
            self.assertLessEqual(res["ds3_2_detectors"][c["detector"]]["valid"]["alert_share_of_eligible"], 0.10 + 1e-9)
        self.assertEqual(set(res["injection_test"]["by_metric"]), {"late", "poor", "handover"})
        hist = pd.read_csv(PROJECT / "data/gold/seller_alert_history.csv")
        self.assertTrue(set(hist["status"]) <= {"new", "ongoing", "resolved"})
        # une alerte « ongoing » doit avoir été active le mois de décision précédent
        on = hist[hist["status"] != "resolved"]
        prev = {(r.seller_id, r.metric, r.family, r.month) for r in on.itertuples()}
        for r in hist[hist["status"] == "ongoing"].head(200).itertuples():
            pm = str(pd.Period(r.month, "M") - 1)
            self.assertIn((r.seller_id, r.metric, r.family, pm), prev)


class TestAgent(BO3Base):
    def test_audit_cited_and_verified(self):
        r = self.ag.audit(FLAGGED, FLAGGED_MONTH, use_llm=False)
        log = self.ag.log
        for l in r.facts + r.estimates + r.similar + r.actions:
            for e in l.evidence:
                self.assertIn(e, log.ids())
        self.assertTrue(verify_bo3_narrative(r.narrative, log)[0])
        self.assertTrue(any("ALERTE" in l.text for l in r.estimates))
        for l in r.similar:
            if l.evidence and l.evidence[0].startswith("rev:"):
                self.assertTrue("traduction automatique" in l.text or "portugais original" in l.text)

    def test_no_future_details_in_orders(self):
        T = decision_date(FLAGGED_MONTH)
        p = self.ag.get_seller_orders(FLAGGED, FLAGGED_MONTH, k=10)
        self.assertTrue(p["shown"])
        o = self.ag.store.orders
        for c in p["shown"]:
            if c["late_days"] is not None:
                self.assertLessEqual(o.loc[c["order_id"], "order_delivered_customer_date"], T)
            if c["review_score"] is not None:
                self.assertLessEqual(o.loc[c["order_id"], "review_answer_timestamp"], T)
            if c["handover_delay_days"] is not None:
                self.assertLessEqual(pd.Timestamp(o.loc[c["order_id"], "order_delivered_carrier_date"]), T)

    def test_llm_narrative_verified_or_rejected(self):
        self.ag.audit(FLAGGED, FLAGGED_MONTH, use_llm=False)
        rate = self.ag.log.get(f"kpi:seller:{FLAGGED[:8]}:{FLAGGED_MONTH}:handover").payload["recent_rate"]
        try:
            self.ag.llm = FakeLLM([{"content": f"Le vendeur {FLAGGED[:8]} remet {100 * rate:.1f} % de ses commandes en retard au transporteur."}])
            self.assertEqual(self.ag.audit(FLAGGED, FLAGGED_MONTH).narrative_source, "llm_verifie")
            self.ag.llm = FakeLLM([{"content": "Ce vendeur a 97.3 % de retards sur 4321 commandes."}])
            r = self.ag.audit(FLAGGED, FLAGGED_MONTH)
            self.assertEqual(r.narrative_source, "deterministe")
            self.assertIn("llm_narrative_rejected", r.meta)
        finally:
            self.ag.llm = None

    def test_small_volume_refused(self):
        m = "2018-06"
        T = decision_date(m)
        d = self.ag.sd.d
        counts = d[(d["ts"] < T) & (d["ts"] >= T - pd.Timedelta(days=365))].groupby("seller_id").size()
        small = counts[counts < 5].index[0]
        r = self.ag.audit(small, m, use_llm=False)
        self.assertTrue(any("aucune comparaison fiable" in l.text for l in r.facts))

    def test_persistence_and_severity_consistent(self):
        """Une alerte finale avec règle de persistance exige une alerte brute au mois précédent ; sévérité ∈ {élevée, moyenne, faible}."""
        for metric in ("late", "poor", "handover"):
            d = self.ag.detect_deterioration(FLAGGED, FLAGGED_MONTH, metric)
            for fam, x in d["families"].items():
                if x["alert"] and x["persistence_rule"]:
                    self.assertTrue(x["raw_alert"] and x["alert_previous_month"])
                if fam == "level":
                    self.assertTrue((x["severity"] in ("élevée", "moyenne", "faible")) if x["alert"] else x["severity"] is None)

    def test_history_stops_at_decision_month_and_matches_live(self):
        h = self.ag.get_seller_history(FLAGGED, FLAGGED_MONTH, n_months=24)
        self.assertTrue(h["available"])
        for met, series in h["series"].items():
            self.assertTrue(all(x["month"] <= FLAGGED_MONTH for x in series))
        live = self.ag.compare_to_peers(FLAGGED, FLAGGED_MONTH, "poor")["observed"]
        last = h["series"]["poor"][-1]
        self.assertEqual(last["month"], FLAGGED_MONTH)
        self.assertEqual(last["known_n"], live["recent_known_n"])
        self.assertAlmostEqual(last["rate_90d"], live["recent_rate"], places=4)

    def test_strengths_payload(self):
        s = self.ag.find_strengths(FLAGGED, FLAGGED_MONTH)
        self.assertEqual({it["metric"] for it in s["items"]}, {"late", "poor", "handover"})
        for it in s["items"]:
            if it["strength"]:  # un point fort est forcément sous la référence
                self.assertLess(it["year_rate"], it["reference_rate"])

    def test_audit_shows_history_severity_and_segment(self):
        r = self.ag.audit(FLAGGED, FLAGGED_MONTH, use_llm=False)
        self.assertTrue(any(l.text.startswith("Évolution") for l in r.facts))
        self.assertTrue(any("sévérité" in l.text for l in r.estimates if l.text.startswith("ALERTE niveau")))
        self.assertTrue(any("segment descriptif" in l.text for l in r.facts))

    def test_unknown_seller(self):
        with self.assertRaises(KeyError):
            self.ag.audit("f" * 32, "2018-05")

    def test_ask_routing(self):
        self.assertIn("Audit vendeur", self.ag.ask(f"Audit du vendeur {FLAGGED[:8]} fin {FLAGGED_MONTH}").title)
        r = self.ag.ask("Quels vendeurs se dégradent en juin 2018 ?")
        self.assertIn("Vendeurs à investiguer", r.title)
        self.assertIn("2018-06", r.title)
        self.assertTrue(np.isfinite(len(r.estimates)) and len(r.estimates) > 1)


class TestBenchmark(BO3Base):
    """Positionnement concurrentiel (descriptif) : rangs, quart supérieur, flux, filtres — mêmes règles « connu à la décision »."""

    def test_ranks_and_quartiles_consistent(self):
        b = self.ag.competitive_benchmark(FLAGGED, FLAGGED_MONTH)
        prof = self.ag._profile(FLAGGED_MONTH)
        self.assertEqual(b["category"]["n_members"], int((prof["main_category"] == b["category"]["category"]).sum()))
        self.assertEqual(b["direct_competitors"]["n_members"], 21)
        self.assertNotIn(FLAGGED, [c["seller_id"] for c in b["competitors"]])
        for grp in ("category", "direct_competitors"):
            for m in ("late", "poor", "handover"):
                x = b[grp]["metrics"][m]
                self.assertTrue(1 <= x["rank"] <= x["n_ranked"] <= b[grp]["n_members"])
                self.assertLessEqual(x["top_quartile_threshold"], x["group_median"])
                self.assertLessEqual(x["top_quartile_median"], x["group_median"])
                G = self.ag._frame(FLAGGED_MONTH, m)[0]["level"].loc[FLAGGED]
                self.assertEqual(x["seller_known_n"], int(G["year_n"]))  # 12 mois d'issues connues, comme la détection
                self.assertAlmostEqual(x["seller_rate"], G["year_x"] / G["year_n"], places=4)
        # vendeur signalé : parmi les moins bons de sa catégorie sur les avis 1-2 étoiles
        self.assertGreater(b["category"]["metrics"]["poor"]["rank"], b["category"]["metrics"]["poor"]["n_ranked"] // 2)

    def test_benchmark_same_on_truncated_data(self):
        tg = SellerAuditAgent(PROJECT, orders=truncate_orders(self.ag.store.orders, decision_date(FLAGGED_MONTH)))
        a = json.loads(json.dumps(self.ag.competitive_benchmark(FLAGGED, FLAGGED_MONTH), default=str))
        b = json.loads(json.dumps(tg.competitive_benchmark(FLAGGED, FLAGGED_MONTH), default=str))
        self.assertEqual(a, b)

    def test_flows_and_category_distribution(self):
        p = self.ag.get_seller_profile(FLAGGED, FLAGGED_MONTH)
        fl = p["flows"]
        self.assertEqual(fl["orders_12m"], p["orders_12m"])
        self.assertEqual(sum(x["orders"] for x in fl["destinations"]), p["orders_12m"])
        self.assertEqual(sum(x["orders"] for x in p["category_distribution"]), p["orders_12m"])
        own = next(x for x in fl["destinations"] if x["state"] == fl["origin_state"])
        self.assertEqual(own["orders"], fl["same_state_orders"])

    def test_seller_geography_as_of_and_consistent(self):
        """Carte des clients : mêmes chiffres sur données amputées après T ; États / régions / tranches de distance cohérents."""
        g = self.ag.get_seller_geography(FLAGGED, FLAGGED_MONTH)
        self.assertEqual(g["origin"]["state"], "SP")
        self.assertEqual(sum(x["orders"] for x in g["states"]), g["orders_12m"])
        self.assertEqual(sum(x["orders"] for x in g["regions"]), g["orders_12m"])
        self.assertEqual(sum(x["orders"] for x in g["points"]), sum(x["orders"] for x in g["distance_bands"]))
        self.assertTrue(all(x["state_name"] and len(x["state_name"]) > 2 for x in g["states"]))
        self.assertEqual([b["band"] for b in g["distance_bands"]], sorted((b["band"] for b in g["distance_bands"]),
                         key=["moins de 300 km", "300 à 1 000 km", "plus de 1 000 km"].index))
        tg = SellerAuditAgent(PROJECT, orders=truncate_orders(self.ag.store.orders, decision_date(FLAGGED_MONTH)))
        self.assertEqual(json.loads(json.dumps(g, default=str)), json.loads(json.dumps(tg.get_seller_geography(FLAGGED, FLAGGED_MONTH), default=str)))

    def test_market_map_partitions_profiled_sellers(self):
        m = self.ag.market_map(FLAGGED_MONTH)
        self.assertEqual(len(m["points"]), len(self.ag._profile(FLAGGED_MONTH)))
        self.assertEqual(sum(g["n_sellers"] for g in m["groups"]), m["n_sellers"])
        self.assertEqual({p["group"] for p in m["points"]}, {g["group"] for g in m["groups"]})
        self.assertIn(FLAGGED, {p["seller_id"] for p in m["points"] if p["alerted"]})

    def test_state_late_alerts_as_of_and_rule(self):
        """Retards par État : mêmes signaux sur données amputées après T ; chaque signal respecte la règle (n ≥ 15, q < 0,05, taux ≥ 1,5 × réf.)."""
        a = self.ag.state_late_alerts(FLAGGED_MONTH, top_k=500)
        for r in a["alerts"]:
            self.assertGreaterEqual(r["known_n"], 15)
            self.assertLess(r["q"], 0.05)
            self.assertGreaterEqual(r["rate"] + 1e-4, 1.5 * r["reference_rate"])
        tg = SellerAuditAgent(PROJECT, orders=truncate_orders(self.ag.store.orders, decision_date(FLAGGED_MONTH)))
        self.assertEqual(json.loads(json.dumps(a, default=str)), json.loads(json.dumps(tg.state_late_alerts(FLAGGED_MONTH, top_k=500), default=str)))

    def test_call_list_cites_and_orders_by_severity(self):
        c = self.ag.call_list(FLAGGED_MONTH)
        self.assertTrue(c["sellers"])
        rank = {"élevée": 3, "moyenne": 2, "faible": 1, None: 0}
        sev = [rank[s["top_severity"]] for s in c["sellers"]]
        self.assertEqual(sev, sorted(sev, reverse=True))
        for s in c["sellers"]:
            self.assertTrue(s["reasons"] and s["email"]["body"].startswith("Bonjour") and len(s["call_script"]) == 5)
            self.assertTrue(verify_bo3_narrative(s["email"]["body"], self.ag.log)[0], s["email"]["body"])

    def test_market_family_trends_fixed_membership(self):
        t = self.ag.market_family_trends(FLAGGED_MONTH)
        self.assertEqual(t["months"][-1], FLAGGED_MONTH)
        self.assertEqual(len(t["families"]), len(self.ag.market_map(FLAGGED_MONTH)["groups"]))
        H = self.ag.monthly
        h = H[(H["month"] == FLAGGED_MONTH) & (H["metric"] == "late")]
        n_total = sum(f["series"][-1]["late"]["known_n"] for f in t["families"] if "late" in f["series"][-1])
        self.assertEqual(n_total, int(h[h["seller_id"].isin({p["seller_id"] for p in self.ag.market_map(FLAGGED_MONTH)["points"]})]["rec_n"].sum()))

    def test_overview_filters(self):
        o = self.ag.sellers_overview(FLAGGED_MONTH, limit=None, seller_state="SP", alert_status="level")
        self.assertTrue(o["sellers"])
        for r in o["sellers"]:
            self.assertEqual(r["seller_state"], "SP")
            self.assertTrue(any(m["alert_level"] for m in r["metrics"].values()))
        s = o["summary"]
        self.assertEqual(sum(s["level_alerts_by_top_severity"].values()), s["n_with_level_alert"])
        self.assertLessEqual(s["n_with_any_alert"], s["n_evaluated"])
        hi = self.ag.sellers_overview(FLAGGED_MONTH, limit=None, severity="élevée")["sellers"]
        self.assertEqual(len(hi), s["level_alerts_by_top_severity"]["élevée"])
        self.assertIn("SP", o["facets"]["seller_state"])
        with self.assertRaises(KeyError):
            self.ag.sellers_overview(FLAGGED_MONTH, trend="bizarre")

    def test_audit_positioning_cited_and_verified(self):
        r = self.ag.audit(FLAGGED, FLAGGED_MONTH, use_llm=False)
        pos = [l for l in r.similar if l.text.startswith("Positionnement descriptif")]
        self.assertEqual(len(pos), 2)
        self.assertTrue(all(f"peer:bench:{FLAGGED[:8]}:{FLAGGED_MONTH}" in l.evidence for l in pos))
        self.assertTrue(any(l.text.startswith("Flux sortants") for l in r.facts))
        for l in pos + r.facts:
            self.assertTrue(verify_bo3_narrative(l.text, self.ag.log)[0], l.text)


if __name__ == "__main__":
    unittest.main()
