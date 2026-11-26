"""Agent BO3 — DS3.3 « Agent d'audit vendeur » (Évaluer les vendeurs en contexte et détecter les dégradations).

Questions traitées : « Audit du vendeur <id> fin 2018-05 », « Quels vendeurs se dégradent en juin 2018 ? », « Remises tardives en 2018-06 ».
Chaque réponse est prise à une DATE DE DÉCISION (fin du mois demandé) et n'utilise que ce qui était connu à cette date.

Outils (seule source de chiffres ; chaque sortie est inscrite dans le journal de preuves) :
  get_seller_profile     volume, catégories, destinations, prix (12 mois avant T)                         sel:<id8>:<M>
  get_peer_group         vendeurs comparables (méthode retenue sur VALID, DS3.1)                            peer:<id8>:<M>
  compare_to_peers       taux récent / 12 mois avec n et IC, taux des pairs, entonnoir, observé/attendu      kpi:seller:<id8>:<M>:<ind.>, mdl:expected:…
  detect_deterioration   alertes « niveau » (vs pairs) et « tendance » (vs son passé), alertes passées      alr:<id8>:<M>:<ind.>
  list_alerts            vendeurs en alerte pour un mois (charge de travail)                                alr:list:<M>:<ind.>
  get_seller_orders      commandes récentes dont un problème était déjà connu à T                          ord:<order_id>
  seller_voice           aspects critiqués dans les avis des clients du vendeur (baseline BO2)             mdl:aspects:seller:<id8>:<M>, rev:<review_id>
  multi_seller_exposure  commandes multi-vendeurs : comptées à part, jamais attribuées                      ctx:multi:<id8>:<M>
  competitive_benchmark  rang dans la catégorie et parmi les concurrents directs (descriptif)              peer:bench:<id8>:<M>
Le rapport est assemblé de façon déterministe ; un résumé LLM optionnel n'est gardé que s'il passe verify_bo3_narrative
(core.verify_narrative + identifiants BO3). core.py, partagé avec BO1/BO2, n'est pas modifié (voir bo3_support.py).
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from .bo3_sellers import (BENCH_METRICS, DESCRIPTIVE_METRICS, DETECTORS, METRIC_LABEL, METRICS, MIN_RANK_N, RECENT_DAYS, SEVERITY_RULE,
                          DetectionParams, PeerConfig, SellerData, alerts, apply_gate, benchmark_frame, competitor_neighbors, decision_date,
                          bh, detector_score, feature_matrix, gate_of, group_benchmark, month_frame, severity, strengths, wilson)
from .bo3_support import BO3Report, load_multi_seller_links, verify_bo3_narrative
from .category_labels import cat_label
from .core import ESTIMATE, FACT, SIMILAR, DataStore, EvidenceLog, LLMClient, Line, Report, Tool, run_tool_loop, to_native


def pct(x: float, nd: int = 1) -> str:
    """Pourcentage à la française (« 2,9 % ») ; remplace core.pct (format anglais) pour les textes BO3, sans modifier core.py."""
    return f"{100 * float(x):.{nd}f} %".replace(".", ",")


def _fr(x, nd: int = 1) -> str:
    """Nombre décimal à la française (« 120,00 »)."""
    return "n/d" if x is None else f"{float(x):.{nd}f}".replace(".", ",")

DEFAULT_CARD = {
    "peer_config": {"method": "knn", "k": 20, "n_clusters": 8},
    "detection": {"level": {"detector": "beta_binomial_pairs", "params": {"tau": 0.95}, "min_history": 50, "persistence": False},
                  "trend": {"detector": "cusum_historique", "params": {"h": 4.0}, "min_history": 50, "persistence": False}},
    "min_recent": 10, "prior_strength": 20.0,
}
# États brésiliens (UF) : nom complet et grande région (IBGE), pour des libellés lisibles et les agrégats régionaux.
UF_NAMES = {"AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia", "CE": "Ceará", "DF": "District fédéral", "ES": "Espírito Santo",
            "GO": "Goiás", "MA": "Maranhão", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul", "MG": "Minas Gerais", "PA": "Pará", "PB": "Paraíba",
            "PR": "Paraná", "PE": "Pernambouc", "PI": "Piauí", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte", "RS": "Rio Grande do Sul",
            "RO": "Rondônia", "RR": "Roraima", "SC": "Santa Catarina", "SP": "São Paulo", "SE": "Sergipe", "TO": "Tocantins"}


def uf_name(uf: str | None) -> str:
    """Nom complet d'un État brésilien (« SP » → « São Paulo ») ; le sigle reste dans les données et les identifiants de preuve."""
    return UF_NAMES.get(uf or "", uf or "")


UF_REGION = {**{u: "Nord" for u in ("AC", "AP", "AM", "PA", "RO", "RR", "TO")}, **{u: "Nord-Est" for u in ("AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE")},
             **{u: "Centre-Ouest" for u in ("DF", "GO", "MT", "MS")}, **{u: "Sud-Est" for u in ("ES", "MG", "RJ", "SP")}, **{u: "Sud" for u in ("PR", "RS", "SC")}}
FAMILY_LABEL = {"level": "niveau (par rapport aux vendeurs comparables)", "trend": "tendance (par rapport à son propre passé)"}
HEX = re.compile(r"\b[0-9a-f]{8,32}\b")
FR_MONTHS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "aout": 8, "septembre": 9, "octobre": 10,
             "novembre": 11, "decembre": 12}


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _r(x, nd: int = 4):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), nd)


class SellerAuditAgent:
    def __init__(self, project_dir: str | Path = ".", llm: LLMClient | None = None, orders: pd.DataFrame | None = None,
                 translate_quotes: bool = False) -> None:
        self.dir = Path(project_dir)
        self.store = DataStore(project_dir)
        self.llm = llm
        self.log = EvidenceLog()
        card_path = self.dir / "data/model/artifacts/bo3_model_card.json"
        self.trained = card_path.exists()
        self.card = json.loads(card_path.read_text(encoding="utf-8")) if self.trained else DEFAULT_CARD
        self.cfg = PeerConfig(**self.card["peer_config"])
        self.global_ref = self.cfg.method == "global"
        self.ref_name = "la marketplace" if self.global_ref else "ses pairs"
        self.base = DetectionParams(min_recent=int(self.card["min_recent"]), prior_strength=float(self.card["prior_strength"]))
        exp_path = self.dir / "data/model/bo3_expected.csv.gz"
        expected = pd.read_csv(exp_path) if exp_path.exists() else None
        self.sd = SellerData(orders if orders is not None else self.store.orders, expected)
        self._sellers = np.sort(self.sd.d["seller_id"].unique())
        self._cache: dict = {}
        self._frames: dict = {}
        self._history: pd.DataFrame | None = None
        self._monthly: pd.DataFrame | None = None
        self._states: dict = {}
        self._voc = None
        self._links: pd.DataFrame | None = None
        self._sellers_geo: pd.DataFrame | None = None
        # Traduction locale à la demande des extraits d'avis affichés (activée par l'API ; désactivée par défaut pour les tests et l'évaluation).
        self._translator = None
        self._quote_sources: dict = {}
        if translate_quotes:
            from .review_translation import OnDemandTranslator
            self._translator = OnDemandTranslator(self.dir)

    # ------------------------------------------------------------------ utilitaires
    def _resolve(self, seller_id: str) -> str:
        s = str(seller_id).strip().lower()
        i = np.searchsorted(self._sellers, s)
        if i < len(self._sellers) and self._sellers[i] == s:
            return s
        cand = [x for x in self._sellers[i:i + 3] if x.startswith(s)] if len(s) >= 8 else []
        if len(cand) == 1:
            return cand[0]
        raise KeyError(f"Vendeur {s} inconnu (identifiant complet ou préfixe d'au moins 8 caractères, commandes mono-vendeur)." if not cand
                       else f"Préfixe {s} ambigu : {len(cand)} vendeurs.")

    def default_month(self) -> str:
        c = self.sd.d["ts"].dt.to_period("M").astype(str).value_counts()
        return sorted(m for m in c.index if c[m] >= 0.5 * c.median())[-1]

    def _month(self, month: str | None) -> str:
        if not month:
            return self.default_month()
        if not re.fullmatch(r"20\d{2}-\d{2}", str(month)):
            raise KeyError(f"Mois {month} invalide (format AAAA-MM).")
        return str(month)

    def _frame(self, month: str, metric: str) -> tuple[dict, object]:
        if metric not in METRICS:
            raise KeyError(f"Indicateur {metric} inconnu ({', '.join(METRICS)}).")
        if not self.sd.available[metric]:
            raise KeyError(f"Indicateur {metric} indisponible dans ces données.")
        key = (month, metric)
        if key not in self._frames:
            f, pm = month_frame(self.sd, month, metric, self.cfg, self.base, self._cache)
            if f.empty:
                raise KeyError(f"Aucun vendeur avec un historique suffisant à la fin de {month}.")
            f = f.reset_index()
            gated = {fam: apply_gate(f, int(c["min_history"]), self.base.min_recent).set_index("seller_id") for fam, c in self.card["detection"].items()}
            self._frames[key] = (gated, pm)
        return self._frames[key]

    def _alert_state(self, month: str, metric: str) -> dict:
        """Par famille : alerte brute du mois, alerte brute du mois précédent, alerte finale (règle de persistance si retenue),
        sévérité (famille niveau). Tout est recalculé à partir des données connues à chaque date de décision."""
        key = (month, metric)
        if key in self._states:
            return self._states[key]
        gated, _ = self._frame(month, metric)
        prev_m = str(pd.Period(month, "M") - 1)
        try:
            gated_prev, _ = self._frame(prev_m, metric)
        except KeyError:
            gated_prev = None
        out = {}
        for fam, c in self.card["detection"].items():
            G = gated[fam]
            raw = pd.Series(alerts(G.reset_index(), c["detector"], c["params"]).to_numpy(), index=G.index)
            if gated_prev is not None:
                Gp = gated_prev[fam]
                prev_set = set(Gp.index[alerts(Gp.reset_index(), c["detector"], c["params"]).to_numpy()])
            else:
                prev_set = set()
            prev = pd.Series(G.index.isin(list(prev_set)), index=G.index)
            final = raw & prev if c.get("persistence") else raw
            st = pd.DataFrame({"raw": raw, "prev": prev, "final": final})
            if fam == "level":
                st["severity"] = [severity(q, pv) if fl else None for q, pv, fl in zip(G["level_q"], prev, final)]
                st["strength"] = strengths(G.reset_index(), float(self.card.get("strength_alpha", 0.05))).to_numpy()
            out[fam] = st
        self._states[key] = out
        return out

    @property
    def monthly(self) -> pd.DataFrame:
        if self._monthly is None:
            path = self.dir / "data/model/bo3_monthly_history.csv.gz"
            self._monthly = pd.read_csv(path) if path.exists() else pd.DataFrame()
        return self._monthly

    def _profile(self, month: str) -> pd.DataFrame:
        self._frame(month, "late" if self.sd.available["late"] else next(m for m, ok in self.sd.available.items() if ok))
        return self._cache[("profile", month)]

    @property
    def history(self) -> pd.DataFrame:
        if self._history is None:
            p = self.dir / "data/gold/seller_alert_history.csv"
            self._history = pd.read_csv(p) if p.exists() else pd.DataFrame(columns=["month", "seller_id", "metric", "family", "status"])
        return self._history

    @property
    def metrics(self) -> list[str]:
        return [m for m in METRICS if self.sd.available[m]]

    def _fam(self, fam: str) -> str:
        if fam == "level":
            return "niveau (par rapport à la marketplace)" if self.global_ref else FAMILY_LABEL["level"]
        return FAMILY_LABEL[fam]

    # ------------------------------------------------------------------ outils
    def get_seller_profile(self, seller_id: str, month: str | None = None) -> dict:
        sid, M = self._resolve(seller_id), self._month(month)
        T = decision_date(M)
        prof = self._profile(M)
        if sid not in prof.index:
            n = int(((self.sd.d["seller_id"] == sid) & (self.sd.d["ts"] < T) & (self.sd.d["ts"] >= T - pd.Timedelta(days=365))).sum())
            payload = {"seller_id": sid, "decision_month": M, "decision_date": T.date().isoformat(), "orders_12m": n, "insufficient": True}
        else:
            r = prof.loc[sid]
            mix = lambda pref: sorted(({"value": c[len(pref):], "share": _r(r[c], 3)} for c in prof.columns if c.startswith(pref) and r[c] >= 0.10),  # noqa: E731
                                      key=lambda x: -x["share"])
            payload = {"seller_id": sid, "decision_month": M, "decision_date": T.date().isoformat(), "insufficient": False,
                       "orders_12m": int(r["n_orders"]), "main_category": r["main_category"], "category_mix": mix("cat_"), "destination_mix": mix("dest_"),
                       "seller_state": r.get("seller_state") if isinstance(r.get("seller_state"), str) else None,
                       "same_state_share": _r(r["same_state"], 3) if "same_state" in prof.columns else None,
                       "median_price": _r(np.expm1(r["log_price"]), 2), "median_freight_ratio": _r(r["freight_ratio"], 3),
                       "mean_promised_days": _r(r["promised_days"], 1),
                       "first_order_in_window": r["first_order"].date().isoformat(), "last_order_before_decision": r["last_order"].date().isoformat()}
            payload.update(self._flows(sid, T, payload["seller_state"]))
            G = self._frame(M, self.metrics[0])[0]["level"]
            if sid in G.index and "segment_volume" in G.columns:
                payload["descriptive_segment"] = {"volume": G.at[sid, "segment_volume"], "region": G.at[sid, "segment_region"],
                                                  "note": "segment descriptif (étiquette) ; sans gain prédictif démontré, la référence reste la marketplace"}
        self.log.add(f"sel:{sid[:8]}:{M}", FACT, "silver/orders_analysis (commandes mono-vendeur des 12 mois avant la décision)", payload)
        return to_native(payload)

    def _flows(self, sid: str, T: pd.Timestamp, origin: str | None, top: int = 8) -> dict:
        """Flux sortants (État du vendeur → États des clients) et répartition des catégories, commandes mono-vendeur de [T-365 j, T)."""
        d = self.sd.d
        w = d[(d["seller_id"] == sid) & (d["ts"] < T) & (d["ts"] >= T - pd.Timedelta(days=365))]
        n = int(len(w))

        def dist(col: str, key: str) -> list[dict]:
            c = w[col].fillna("inconnu").value_counts()
            rows = [{key: str(v), "orders": int(k), "share": _r(k / n, 3)} for v, k in c.head(top).items()]
            rest = int(c.iloc[top:].sum())
            if rest:
                rows.append({key: "autres", "orders": rest, "share": _r(rest / n, 3)})
            return rows
        same = int((w["state"] == origin).sum()) if origin else None
        # Volume mensuel (mois d'achat, tous connus à T puisque l'achat précède T) : met en évidence les hausses ou baisses d'activité.
        per_month = w["ts"].dt.to_period("M").astype(str).value_counts().sort_index()
        months = [str(p) for p in pd.period_range(end=pd.Period(T - pd.Timedelta(days=1), "M"), periods=12, freq="M")]
        return {"flows": {"origin_state": origin, "orders_12m": n, "destinations": dist("state", "state") if n else [],
                          "same_state_orders": same, "same_state_share": _r(same / n, 3) if origin and n else None,
                          "interstate_orders": n - same if origin and n else None,
                          "interstate_share": _r((n - same) / n, 3) if origin and n else None,
                          "n_destination_states": int(w["state"].nunique())},
                "category_distribution": dist("category", "category") if n else [],
                "monthly_orders": [{"month": m, "orders": int(per_month.get(m, 0))} for m in months]}

    def _bench(self, M: str) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
        key = ("bench", M)
        if key not in self._cache:
            prof = self._profile(M)
            counts = {met: self._frame(M, met)[0]["level"][["year_n", "year_x"]] for met in BENCH_METRICS if self.sd.available.get(met)}
            B = benchmark_frame(prof, counts)
            nb, nd = competitor_neighbors(prof, k=20)
            self._cache[key] = (B, nb, nd)
        return self._cache[key]

    def competitive_benchmark(self, seller_id: str, month: str | None = None, n_competitors: int = 10) -> dict:
        """Positionnement DESCRIPTIF : rang et centile du vendeur (a) parmi les vendeurs de sa catégorie principale,
        (b) parmi ses 20 concurrents directs (plus proches voisins : catégories, volume, prix, port, délai promis) ; vendeur, médiane
        du groupe et quart supérieur côte à côte. Taux sur 12 mois d'issues connues à la décision ; la détection reste calibrée
        sur la marketplace."""
        sid, M = self._resolve(seller_id), self._month(month)
        B, nb, nd = self._bench(M)
        if sid not in B.index:
            raise KeyError(f"Vendeur {sid[:8]} sans profil à la fin de {M} (moins de 5 commandes sur 12 mois).")
        i = B.index.get_loc(sid)
        cat = B.at[sid, "main_category"]
        cat_members = B.index[B["main_category"] == cat].tolist()
        comp_ids = [B.index[j] for j in nb[i]]

        def clean(g: dict) -> dict:
            mets = {}
            for m, v in g["metrics"].items():
                nd_ = 2 if m == "median_price" else 1 if m == "promised_days" else 4
                mets[m] = {k: (_r(x, nd_) if isinstance(x, float) else x) for k, x in v.items()}
                if v.get("better_than_share") is not None:
                    mets[m]["better_than_share"] = _r(v["better_than_share"], 3)
            g["metrics"] = mets
            g["overall"].pop("score", None)  # score interne de classement : non affiché, non journalisé
            return g
        category = clean(group_benchmark(B, sid, cat_members)) | {"label": f"catégorie {cat_label(cat)}", "category": cat, "category_label": cat_label(cat)}
        direct = clean(group_benchmark(B, sid, comp_ids)) | {"label": "concurrents directs (20 plus proches voisins)"}
        comps = []
        for j, dd in list(zip(nb[i], nd[i]))[:n_competitors]:
            c = B.iloc[j]
            comps.append({"seller_id": B.index[j], "main_category": c["main_category"],
                          "seller_state": c["seller_state"] if isinstance(c["seller_state"], str) else None, "orders_12m": int(c["n_orders"]),
                          **{f"rate_{m}": _r(c[f"rate_{m}"]) for m in BENCH_METRICS}, **{f"known_n_{m}": int(c[f"n_{m}"]) for m in BENCH_METRICS},
                          "median_price": _r(c["median_price"], 2), "freight_share": _r(c["freight_share"], 3),
                          "promised_days": _r(c["promised_days"], 1), "distance": _r(dd, 3)})
        payload = {"seller_id": sid, "decision_month": M, "category": category, "direct_competitors": direct, "competitors": comps,
                   "metric_labels": {**{m: METRIC_LABEL[m] for m in BENCH_METRICS}, **DESCRIPTIVE_METRICS},
                   "definitions": {"rank": f"1 = taux le plus bas du groupe (meilleur) ; vendeurs classés : au moins {MIN_RANK_N} issues connues sur 12 mois",
                                   "top_quartile": "25 % des membres au meilleur score composite (moyenne des rangs centiles sur les trois taux)",
                                   "top_quartile_threshold": "taux à atteindre pour entrer dans le meilleur quart sur cet indicateur",
                                   "competitors": "similarité : catégories vendues, volume, prix médian, part du port, délai promis ; aucune issue"},
                   "note": "positionnement descriptif ; la détection des alertes reste calibrée sur la marketplace (DS3.1)"}
        # Journal : version compacte (sans prix, port, délai ni distance de chaque concurrent) pour ne pas multiplier les nombres
        # « autorisés » lors de la vérification des textes ; ces détails restent dans la réponse de l'outil (tableau de l'interface).
        logged = {**payload, "competitors": [{k: c[k] for k in ("seller_id", "main_category", "seller_state", "orders_12m",
                                                                *(f"rate_{m}" for m in BENCH_METRICS), *(f"known_n_{m}" for m in BENCH_METRICS))}
                                             for c in comps]}
        self.log.add(f"peer:bench:{sid[:8]}:{M}", FACT, "BO3 positionnement concurrentiel (12 mois d'issues connues à la décision)", logged)
        return to_native(payload)

    def get_peer_group(self, seller_id: str, month: str | None = None, k: int = 8) -> dict:
        sid, M = self._resolve(seller_id), self._month(month)
        gated, pm = self._frame(M, self.metrics[0])
        if sid not in pm.index:
            raise KeyError(f"Vendeur {sid[:8]} sans profil à la fin de {M} (moins de 5 commandes sur 12 mois).")
        prof = self._profile(M)
        peers = pm.peers_of(sid, top=max(k, 20))
        i = pm.index.get_loc(sid)
        n_peers = pm.nb.shape[1] if pm.nb is not None else int((pm.labels == pm.labels[i]).sum() - 1)
        cats = pd.Series([prof.loc[p, "main_category"] for p, _ in peers]).value_counts()
        payload = {"seller_id": sid, "decision_month": M, "method": self.cfg.label, "method_key": self.cfg.key, "n_peers": int(n_peers),
                   "peer_main_categories": [{"category": c, "count": int(v)} for c, v in cats.head(4).items()],
                   "peers": [{"seller_id": p, "main_category": prof.loc[p, "main_category"], "orders_12m": int(prof.loc[p, "n_orders"]),
                              "distance": _r(d, 3)} for p, d in peers[:k]],
                   "similarity_basis": "catégories vendues, destinations (États clients), volume, prix médian, part du port, poids, délai promis ; "
                                       "aucune issue (retard, avis) n'entre dans la similarité",
                   "selection": "méthode retenue sur VALID (bo3_model_card.json)" if self.trained else "réglage par défaut (modèle BO3 non entraîné)"}
        bench = self.competitive_benchmark(sid, M)
        payload["benchmark"] = {k: bench[k] for k in ("category", "direct_competitors")} | {"evidence": f"peer:bench:{sid[:8]}:{M}"}
        self.log.add(f"peer:{sid[:8]}:{M}", ESTIMATE, "DS3.1 groupes de pairs", payload)
        payload = {**payload, "benchmark": bench}
        return to_native(payload)

    def compare_to_peers(self, seller_id: str, month: str | None = None, metric: str = "late") -> dict:
        sid, M = self._resolve(seller_id), self._month(month)
        T = decision_date(M)
        gated, _ = self._frame(M, metric)
        G = gated["level"]
        if sid not in G.index:
            raise KeyError(f"Vendeur {sid[:8]} sans profil à la fin de {M}.")
        r = G.loc[sid]
        rn, rx, yn, yx = int(r["rec_n"]), int(r["rec_x"]), int(r["year_n"]), int(r["year_x"])
        p = float(r["p_peer"])
        lo95 = hi95 = hi998 = None
        position = "non évaluable (aucune issue connue sur 90 jours)"
        if rn:
            lo95, hi95 = (stats.binom.ppf([0.025, 0.975], rn, p) / rn).tolist()
            hi998 = float(stats.binom.ppf(0.999, rn, p) / rn)
            rate = rx / rn
            position = ("au-dessus de la limite haute à 99,8 %" if rate > hi998 else "au-dessus de la limite haute à 95 %" if rate > hi95
                        else "sous la limite basse à 95 %" if rate < lo95 else "dans l'intervalle attendu")
        ci_r, ci_y = wilson(rx, rn), wilson(yx, yn)
        payload = {"seller_id": sid, "decision_month": M, "metric": metric, "label": METRIC_LABEL[metric],
                   "recent_window": f"achats du {(T - pd.Timedelta(days=RECENT_DAYS)).date().isoformat()} au {(T - pd.Timedelta(days=1)).date().isoformat()}",
                   "orders_recent": int(r["n_orders_recent"]), "recent_known_n": rn, "recent_events": rx, "recent_rate": _r(rx / rn) if rn else None,
                   "recent_ci95": [_r(ci_r[0]), _r(ci_r[1])], "share_known_recent": _r(rn / r["n_orders_recent"], 3) if r["n_orders_recent"] else None,
                   "year_known_n": yn, "year_events": yx, "year_rate": _r(yx / yn) if yn else None, "year_ci95": [_r(ci_y[0]), _r(ci_y[1])],
                   "peer_rate": _r(p), "peer_known_n": int(r["n_peer"]), "peer_fallback_to_marketplace": bool(r["peer_fallback"]),
                   "marketplace_rate": _r(r["p_global"]), "shrunk_rate": _r(r["p_shrunk"]),
                   "ratio_to_peers": _r((rx / rn) / p, 2) if rn else None, "funnel_95": [_r(lo95), _r(hi95)], "funnel_998_high": _r(hi998),
                   "funnel_position": position}
        self.log.add(f"kpi:seller:{sid[:8]}:{M}:{metric}", FACT, "orders_analysis — issues connues avant la décision (mono-vendeur) ; pairs : DS3.1", payload)
        out = {"observed": payload}
        if "oe_ratio" in G.columns and pd.notna(r.get("oe_ratio")) and r.get("rec_ne", 0) > 0:
            e = {"seller_id": sid, "decision_month": M, "metric": metric, "observed_events": int(r["rec_xe"]), "expected_events": _r(r["oe_expected"], 1),
                 "oe_ratio": _r(r["oe_ratio"], 2), "z": _r(r["oe_z"], 1), "n_orders_scored": int(r["rec_ne"]), "marketplace_calibration": _r(r["oe_calibration"], 3),
                 "in_sample": bool(T - pd.Timedelta(days=RECENT_DAYS) < pd.Timestamp("2018-01-01")),
                 "model": "modèle de risque par commande entraîné sur TRAIN (achats < 2018-01-01), recalé sur le niveau de la marketplace à la décision"}
            self.log.add(f"mdl:expected:{sid[:8]}:{M}:{metric}", ESTIMATE, "data/model/bo3_expected.csv.gz", e)
            out["expected"] = e
        if metric in BENCH_METRICS:
            bench = self.competitive_benchmark(sid, M)
            pos = {"seller_id": sid, "decision_month": M, "metric": metric, "label": METRIC_LABEL[metric],
                   "category": {"label": bench["category"]["label"], **bench["category"]["metrics"][metric]},
                   "direct_competitors": {"label": bench["direct_competitors"]["label"], **bench["direct_competitors"]["metrics"][metric]},
                   "marketplace_rate": payload["marketplace_rate"],
                   "note": "taux sur 12 mois d'issues connues ; descriptif, la référence de détection reste la marketplace"}
            self.log.add(f"peer:bench:{sid[:8]}:{M}:{metric}", FACT, "BO3 positionnement concurrentiel", pos)
            out["benchmark"] = pos
        return to_native(out)

    def detect_deterioration(self, seller_id: str, month: str | None = None, metric: str = "late") -> dict:
        sid, M = self._resolve(seller_id), self._month(month)
        gated, _ = self._frame(M, metric)
        fams = {}
        for fam, c in self.card["detection"].items():
            G = gated[fam]
            if sid not in G.index:
                raise KeyError(f"Vendeur {sid[:8]} sans profil à la fin de {M}.")
            row = G.loc[[sid]]
            r = G.loc[sid]
            det = c["detector"]
            gate = bool(r[gate_of(det, G)])
            st = self._alert_state(M, metric)[fam].loc[sid]
            a = bool(st["final"])
            sc = detector_score(row, det).iloc[0]
            need_hist = max(self.base.min_recent, int(c["min_history"]) // 2) if fam == "trend" else None
            fams[fam] = {"detector": det, "description": DETECTORS[det][1], "params": c["params"], "min_history": int(c["min_history"]),
                         "min_recent": self.base.min_recent, "min_own_history": need_hist, "eligible": gate, "alert": a,
                         "raw_alert": bool(st["raw"]), "alert_previous_month": bool(st["prev"]), "persistence_rule": bool(c.get("persistence")),
                         "severity": st.get("severity") if fam == "level" else None,
                         "score": _r(sc, 3) if pd.notna(sc) else None,
                         "baseline": _r(r["p_peer"] if fam == "level" else r["p_hist"]),
                         "baseline_label": (("taux de la marketplace" if self.global_ref else "taux des pairs") if fam == "level"
                                            else "historique du vendeur sur les achats de T-365 à T-90 jours, rétréci vers " + self.ref_name),
                         "recent_rate": _r(r["rec_rate"]), "recent_known_n": int(r["rec_n"]), "history_known_n": int(r["hist_n"]), "year_known_n": int(r["year_n"]),
                         "raw": {"posterior_above_peers": _r(r["level_post"], 3), "q_vs_peers": _r(r.get("level_q"), 4), "q_vs_history": _r(r.get("trend_q"), 4),
                                 "cusum": _r(r.get("cusum"), 2)},
                         "test_performance": (self.card.get("test_summary") or {}).get(fam)}
        h = self.history
        past = h[(h["seller_id"] == sid) & (h["metric"] == metric) & (h["month"] < M) & (h["status"] != "resolved")]
        payload = {"seller_id": sid, "decision_month": M, "metric": metric, "label": METRIC_LABEL[metric], "families": fams,
                   "past_alerts": [{"month": x.month, "family": x.family, "status": x.status} for x in past.sort_values("month").tail(6).itertuples()],
                   "n_past_alert_months": int(past["month"].nunique())}
        self.log.add(f"alr:{sid[:8]}:{M}:{metric}", ESTIMATE, "DS3.2 détecteurs (bo3_model_card.json) + data/gold/seller_alert_history.csv", payload)
        return to_native(payload)

    def list_alerts(self, month: str | None = None, metric: str | None = None, top_k: int = 15) -> dict:
        M = self._month(month)
        metrics = [metric] if metric else self.metrics
        rows, eligible = [], {}
        for met in metrics:
            gated, _ = self._frame(M, met)
            eligible[met] = int(gated["level"]["eligible"].sum())
            state = self._alert_state(M, met)
            for fam, c in self.card["detection"].items():
                G = gated[fam]
                st = state[fam]
                a = st["final"].to_numpy()
                sc = detector_score(G, c["detector"]).to_numpy()
                sev = st["severity"].to_numpy() if "severity" in st.columns else np.full(len(G), None)
                for sid, s_, rr, n, b, cat, sv in zip(G.index[a], sc[a], G["rec_rate"].to_numpy()[a], G["rec_n"].to_numpy()[a],
                                                      (G["p_peer"] if fam == "level" else G["p_hist"]).to_numpy()[a], G["main_category"].to_numpy()[a], sev[a]):
                    rows.append({"seller_id": sid, "metric": met, "family": fam, "score": _r(s_, 3), "recent_rate": _r(rr), "recent_known_n": int(n),
                                 "baseline": _r(b), "main_category": cat, "severity": sv})
        df = pd.DataFrame(rows)
        listing = []
        if len(df):
            rank = {"élevée": 3, "moyenne": 2, "faible": 1}
            df["sev_rank"] = df["severity"].map(rank).fillna(0)
            agg = (df.groupby("seller_id").agg(top_severity=("sev_rank", "max"), n_alerts=("metric", "size"), max_rate=("recent_rate", "max"))
                   .sort_values(["top_severity", "n_alerts", "max_rate"], ascending=False))
            inv = {v: k for k, v in rank.items()}
            for sid in agg.index[:top_k]:
                sub = df[df["seller_id"] == sid]
                listing.append({"seller_id": sid, "main_category": sub["main_category"].iloc[0], "n_alerts": int(len(sub)),
                                "top_severity": inv.get(int(agg.at[sid, "top_severity"])),
                                "alerts": sub[["metric", "family", "severity", "recent_rate", "recent_known_n", "baseline"]].to_dict("records")})
        payload = {"decision_month": M, "metrics": metrics, "eligible_sellers": eligible, "n_alerted_sellers": int(df["seller_id"].nunique()) if len(df) else 0,
                   "n_alerts": int(len(df)), "listing": listing,
                   "detectors": {fam: c["detector"] for fam, c in self.card["detection"].items()},
                   "persistence": {fam: bool(c.get("persistence")) for fam, c in self.card["detection"].items()}, "severity_rule": SEVERITY_RULE}
        self.log.add(f"alr:list:{M}:{metric or 'all'}", ESTIMATE, "DS3.2 détecteurs appliqués à tous les vendeurs éligibles", payload)
        return to_native(payload)

    def find_strengths(self, seller_id: str, month: str | None = None) -> dict:
        """Indicateurs où le vendeur fait significativement MIEUX que la référence sur 12 mois (issues connues à la décision)."""
        sid, M = self._resolve(seller_id), self._month(month)
        alpha = float(self.card.get("strength_alpha", 0.05))
        items = []
        for met in self.metrics:
            G = self._frame(M, met)[0]["level"]
            if sid not in G.index:
                continue
            r = G.loc[sid]
            items.append({"metric": met, "label": METRIC_LABEL[met], "strength": bool(self._alert_state(M, met)["level"].at[sid, "strength"]),
                          "eligible": bool(r["eligible_strength"]), "year_rate": _r(r["year_rate"]), "year_known_n": int(r["year_n"]),
                          "reference_rate": _r(r["p_peer"]), "q_below_reference": _r(r.get("strength_q"), 4)})
        payload = {"seller_id": sid, "decision_month": M, "alpha": alpha, "items": items,
                   "definition": "12 mois d'issues connues significativement sous la référence (binomial unilatéral inférieur, Benjamini-Hochberg)"}
        self.log.add(f"alr:strength:{sid[:8]}:{M}", ESTIMATE, "DS3.2 points forts (bo3_model_card.json)", payload)
        return to_native(payload)

    def get_seller_history(self, seller_id: str, month: str | None = None, n_months: int = 6) -> dict:
        """Évolution mensuelle (taux sur 90 jours à chaque fin de mois, effectif, alertes) jusqu'au mois de décision inclus."""
        sid, M = self._resolve(seller_id), self._month(month)
        H = self.monthly
        if H.empty:
            payload = {"seller_id": sid, "decision_month": M, "available": False, "note": "lancer src/train_seller_models.py"}
        else:
            h = H[(H["seller_id"] == sid) & (H["month"] <= M)].sort_values("month")
            series = {}
            for met, g in h.groupby("metric"):
                g = g.tail(n_months)
                series[met] = [{"month": r.month, "rate_90d": _r(r.rec_rate), "known_n": int(r.rec_n), "reference": _r(r.p_peer),
                                "alert_level": bool(r.alert_level), "alert_trend": bool(r.alert_trend)} for r in g.itertuples()]
            payload = {"seller_id": sid, "decision_month": M, "available": True, "series": series,
                       "note": "chaque mois n'utilise que ce qui était connu à la fin de ce mois"}
        self.log.add(f"kpi:history:{sid[:8]}:{M}", FACT, "data/model/bo3_monthly_history.csv.gz", payload)
        return to_native(payload)

    # ------------------------------------------------------------------ vues d'ensemble (lecture seule, pour l'API / l'interface)
    def warm(self, month: str | None = None) -> None:
        """Préchargement (API) : analyse des avis pour seller_voice et calculs du mois par défaut et du mois précédent."""
        M = self._month(month)
        try:
            from .bo2_agent import VoiceOfCustomerAgent
            if self._voc is None:
                self._voc = VoiceOfCustomerAgent(self.dir)
            _ = self._voc.an, self._voc.index
        except FileNotFoundError:
            pass
        for met in self.metrics:
            self._alert_state(M, met)
        self._overview_rows(M)

    def _overview_rows(self, M: str) -> tuple[list[dict], dict]:
        key = ("overview", M)
        if key in self._cache:
            return self._cache[key]
        prof = self._profile(M)
        rows: dict[str, dict] = {}
        refs = {}
        for met in self.metrics:
            gated, _ = self._frame(M, met)
            G = gated["level"]
            st = self._alert_state(M, met)
            refs[met] = _r(G["p_global"].iloc[0]) if len(G) else None
            tr = st["trend"]["final"].reindex(G.index).fillna(False)
            cols = zip(G.index, G["main_category"], G["rec_rate"], G["rec_n"], G["year_rate"], G["year_n"], G["eligible"],
                       st["level"]["final"], st["level"]["severity"], tr, st["level"]["strength"],
                       G["segment_volume"] if "segment_volume" in G.columns else [None] * len(G),
                       G["segment_region"] if "segment_region" in G.columns else [None] * len(G))
            for sid, cat, rr, rn, yr, yn, el, al, sv, at, sg, vol, reg in cols:
                st_ = prof.at[sid, "seller_state"] if "seller_state" in prof.columns else None
                row = rows.setdefault(sid, {"seller_id": sid, "orders_12m": int(prof.at[sid, "n_orders"]), "main_category": cat,
                                            "seller_state": st_ if isinstance(st_, str) else None,
                                            "segment_volume": vol, "segment_region": reg, "metrics": {}})
                row["metrics"][met] = {"rate_90d": _r(rr), "known_n_90d": int(rn), "rate_12m": _r(yr), "known_n_12m": int(yn), "eligible": bool(el),
                                       "alert_level": bool(al), "severity": sv, "alert_trend": bool(at), "strength": bool(sg)}
        sev = {"élevée": 3, "moyenne": 2, "faible": 1}
        out = sorted(rows.values(), key=lambda r: (-max([sev.get(m["severity"], 0) for m in r["metrics"].values()] or [0]),
                                                   -sum(m["alert_level"] or m["alert_trend"] for m in r["metrics"].values()), -r["orders_12m"]))
        self._cache[key] = (out, refs)
        return out, refs

    def sellers_overview(self, month: str | None = None, alerted_only: bool = False, query: str | None = None,
                         limit: int | None = 200, seller_state: str | None = None, region: str | None = None,
                         main_category: str | None = None, segment: str | None = None, alert_status: str | None = None,
                         severity: str | None = None, trend: str | None = None) -> dict:
        """Tableau des vendeurs ayant un profil à la fin du mois : volume, État, segment descriptif, et par indicateur taux sur 90 jours,
        effectif, alertes finales, sévérité, point fort. Mêmes calculs que l'audit (données connues à la décision).
        Filtres : alerted_only, query (préfixe d'identifiant ou catégorie), seller_state, region (segment régional), main_category,
        segment (segment de volume), alert_status (any | level | trend | none), severity (élevée | moyenne | faible : sévérité la plus haute),
        trend (degradation : alerte de tendance ; stable : aucune). limit None = tous. Tri : sévérité, alertes, volume.
        Le résumé (summary) porte sur TOUS les vendeurs évalués du mois, les facettes donnent les valeurs disponibles."""
        M = self._month(month)
        rows, refs = self._overview_rows(M)
        sev_rank = {"élevée": 3, "moyenne": 2, "faible": 1}
        inv = {v: k for k, v in sev_rank.items()}

        def top_sev(r: dict) -> str | None:
            return inv.get(max([sev_rank.get(m["severity"], 0) for m in r["metrics"].values()] or [0]))

        def has(r: dict, key: str) -> bool:
            return any(m[key] for m in r["metrics"].values())
        sel = rows
        if alerted_only:
            sel = [r for r in sel if has(r, "alert_level") or has(r, "alert_trend")]
        if query:
            q = query.strip().lower()
            sel = [r for r in sel if r["seller_id"].startswith(q) or q in str(r["main_category"]).lower()]
        for key, val in (("seller_state", seller_state), ("segment_region", region), ("main_category", main_category), ("segment_volume", segment)):
            if val:
                sel = [r for r in sel if str(r.get(key) or "").lower() == val.strip().lower()]
        if alert_status:
            f = {"any": lambda r: has(r, "alert_level") or has(r, "alert_trend"), "level": lambda r: has(r, "alert_level"),
                 "trend": lambda r: has(r, "alert_trend"), "none": lambda r: not (has(r, "alert_level") or has(r, "alert_trend"))}.get(alert_status)
            if f is None:
                raise KeyError(f"alert_status {alert_status} inconnu (any, level, trend, none).")
            sel = [r for r in sel if f(r)]
        if severity:
            sel = [r for r in sel if top_sev(r) == severity]
        if trend:
            if trend not in ("degradation", "stable"):
                raise KeyError(f"trend {trend} inconnu (degradation, stable).")
            sel = [r for r in sel if has(r, "alert_trend") == (trend == "degradation")]
        n_match = len(sel)
        if limit:
            sel = sel[:limit]
        sev_counts = {k: 0 for k in sev_rank}
        for r in rows:
            t = top_sev(r)
            if t:
                sev_counts[t] += 1
        summary = {"n_evaluated": len(rows), "n_with_level_alert": sum(has(r, "alert_level") for r in rows),
                   "n_with_trend_alert": sum(has(r, "alert_trend") for r in rows),
                   "n_with_any_alert": sum(has(r, "alert_level") or has(r, "alert_trend") for r in rows),
                   "level_alerts_by_top_severity": sev_counts, "n_with_strength": sum(has(r, "strength") for r in rows)}
        facets = {k: sorted({r.get(k) for r in rows if r.get(k)}) for k in ("seller_state", "segment_region", "main_category", "segment_volume")}
        payload = {"decision_month": M, "decision_date": decision_date(M).date().isoformat(), "reference_rates": refs,
                   "n_sellers": len(rows), "n_matching": n_match, "n_returned": len(sel), "summary": summary, "facets": facets, "sellers": sel,
                   "note": "vendeurs avec au moins 5 commandes mono-vendeur sur 12 mois ; issues connues à la fin du mois"}
        self.log.add(f"kpi:overview:{M}", FACT, "BO3 sellers_overview (orders_analysis, issues connues à la décision)",
                     {"decision_month": M, "n_sellers": len(rows), "reference_rates": refs, "summary": summary})
        return to_native(payload)

    def marketplace_overview(self) -> dict:
        """Par indicateur et mois de décision : taux de référence de la marketplace, vendeurs évaluables, alertes (historique mensuel)."""
        H = self.monthly
        if H.empty:
            return {"available": False, "note": "lancer src/train_seller_models.py"}
        series = {}
        for met, g in H.groupby("metric"):
            agg = g.groupby("month").agg(reference=("p_peer", "median"), sellers=("seller_id", "size"), eligible=("eligible", "sum"),
                                         alerts_level=("alert_level", "sum"), alerts_trend=("alert_trend", "sum"), strengths=("strength", "sum"))
            series[met] = [{"month": m, "reference_rate": _r(r.reference), "sellers_with_profile": int(r.sellers), "eligible": int(r.eligible),
                            "alerts_level": int(r.alerts_level), "alerts_trend": int(r.alerts_trend), "strengths": int(r.strengths)}
                           for m, r in agg.sort_index().iterrows()]
        payload = {"available": True, "labels": METRIC_LABEL, "series": series,
                   "note": "chaque mois n'utilise que ce qui était connu à sa fin ; les mois après 2018-06 n'ont pas de vérité future pour l'évaluation"}
        self.log.add("kpi:marketplace", FACT, "data/model/bo3_monthly_history.csv.gz", {"metrics": list(series)})
        return to_native(payload)

    # ------------------------------------------------------------------ géographie et carte du marché (descriptif)
    def _seller_locations(self) -> pd.DataFrame:
        """Ville, État et position (centroïde du préfixe postal) de chaque vendeur : data/raw/olist_sellers_dataset.csv + silver/geo_zip_centroid."""
        if self._sellers_geo is None:
            raw, geo = self.dir / "data/raw/olist_sellers_dataset.csv", self.dir / "data/silver/geo_zip_centroid.csv.gz"
            if raw.exists() and geo.exists():
                s = pd.read_csv(raw, dtype={"seller_zip_code_prefix": str})
                g = pd.read_csv(geo, dtype={"geolocation_zip_code_prefix": str})
                g = g[g["is_within_brazil"].astype(bool)]
                s["zip"] = s["seller_zip_code_prefix"].str.zfill(5)
                g["zip"] = g["geolocation_zip_code_prefix"].str.zfill(5)
                self._sellers_geo = s.merge(g[["zip", "latitude", "longitude"]], on="zip", how="left").set_index("seller_id")
            else:
                self._sellers_geo = pd.DataFrame(columns=["seller_city", "seller_state", "latitude", "longitude"])
        return self._sellers_geo

    def geo_basemap(self, step: float = 0.2) -> dict:
        """Fond de carte TIRÉ DES DONNÉES : centroïdes des préfixes postaux brésiliens, regroupés sur une grille (aucune donnée externe)."""
        key = ("basemap", step)
        if key not in self._cache:
            path = self.dir / "data/silver/geo_zip_centroid.csv.gz"
            g = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=["latitude", "longitude", "is_within_brazil"])
            g = g[g["is_within_brazil"].astype(bool)]
            pts = (np.round(g[["longitude", "latitude"]].to_numpy() / step) * step).round(3)
            uniq = np.unique(pts, axis=0) if len(pts) else np.empty((0, 2))
            self._cache[key] = {"step": step, "points": uniq.tolist(), "bounds": {"lng": [-74.0, -34.0], "lat": [-34.0, 5.5]}}
        return self._cache[key]

    def get_seller_geography(self, seller_id: str, month: str | None = None, step: float = 0.25) -> dict:
        """Où sont les clients du vendeur et d'où il expédie (12 mois avant T, commandes mono-vendeur) : points agrégés sur une grille,
        répartition par État et par grande région, distance au client et retard de livraison par tranche de distance
        (retards CONNUS à T uniquement). Descriptif : aide à situer les difficultés de transport."""
        sid, M = self._resolve(seller_id), self._month(month)
        T = decision_date(M)
        d = self.sd.d
        w = d[(d["seller_id"] == sid) & (d["ts"] < T) & (d["ts"] >= T - pd.Timedelta(days=365))].copy()
        loc = self._seller_locations()
        origin = None
        if sid in loc.index:
            r = loc.loc[sid]
            origin = {"city": str(r["seller_city"]).title(), "state": r["seller_state"], "state_name": UF_NAMES.get(r["seller_state"], r["seller_state"]),
                      "region": UF_REGION.get(r["seller_state"]), "lat": _r(r["latitude"], 3), "lng": _r(r["longitude"], 3)}
        known = w["y_late"].notna() & (w["k_late"] <= T)
        w["late_known"], w["late_event"] = known.astype(int), (known & (w["y_late"] == 1)).astype(int)
        geo = w.dropna(subset=["lat", "lng"])
        pts = []
        if len(geo):
            gx = geo.assign(glat=(geo["lat"] / step).round() * step, glng=(geo["lng"] / step).round() * step)
            agg = gx.groupby(["glat", "glng", "state"]).agg(orders=("order_id", "size"), late_known=("late_known", "sum"), late=("late_event", "sum")).reset_index()
            pts = [{"lat": _r(a.glat, 3), "lng": _r(a.glng, 3), "state": a.state, "orders": int(a.orders), "late_known": int(a.late_known), "late": int(a.late)}
                   for a in agg.itertuples()]
        n = int(len(w))

        def table(col: str) -> list[dict]:
            g = w.groupby(col).agg(orders=("order_id", "size"), late_known=("late_known", "sum"), late=("late_event", "sum"))
            return [{col: k, "orders": int(v.orders), "share": _r(v.orders / n, 3), "late_known": int(v.late_known),
                     "late_rate": _r(v.late / v.late_known) if v.late_known >= 10 else None}
                    for k, v in g.sort_values("orders", ascending=False).iterrows()]
        w["region"] = w["state"].map(UF_REGION).fillna("inconnue")
        states = table("state")
        for s_ in states:
            s_["state_name"] = UF_NAMES.get(s_["state"], s_["state"])
        bands, dist_med = [], None
        if origin and origin["lat"] is not None and len(geo):
            lat1, lng1 = np.radians(origin["lat"]), np.radians(origin["lng"])
            lat2, lng2 = np.radians(w["lat"]), np.radians(w["lng"])
            a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lng2 - lng1) / 2) ** 2
            w["km"] = 2 * 6371 * np.arcsin(np.sqrt(a))
            dist_med = _r(w["km"].median(), 0)
            w["band"] = pd.cut(w["km"], [-1, 300, 1000, 1e6], labels=["moins de 300 km", "300 à 1 000 km", "plus de 1 000 km"])
            order = {"moins de 300 km": 0, "300 à 1 000 km": 1, "plus de 1 000 km": 2}
            bands = sorted((b for b in table("band") if b["orders"]), key=lambda b: order[b["band"]])
        flagged = self._state_late_frame(M)
        flagged = flagged[(flagged["seller_id"] == sid) & flagged["alert"]]
        state_alerts = [{"state": r.state, "state_name": UF_NAMES.get(r.state, r.state), "known_n": int(r.n), "rate": _r(r.rate), "reference_rate": _r(r.ref)}
                        for r in flagged.sort_values("q").itertuples()]
        payload = {"seller_id": sid, "decision_month": M, "origin": origin, "orders_12m": n, "points": pts, "grid_step_deg": step, "state_alerts": state_alerts,
                   "states": states, "regions": table("region"), "distance_bands": bands, "median_distance_km": dist_med,
                   "n_states": int(w["state"].nunique()),
                   "note": "positions = centroïdes des préfixes postaux (agrégés) ; retards connus à la décision ; taux affiché si au moins 10 livraisons connues"}
        # Journal : sans les points de la grille (trop de nombres « autorisés » pour la vérification des textes) ; ils restent dans la réponse.
        self.log.add(f"sel:geo:{sid[:8]}:{M}", FACT, "orders_analysis (positions clients agrégées) + olist_sellers_dataset (vendeur)",
                     {k: v for k, v in payload.items() if k != "points"})
        return to_native(payload)

    # dimensions MÉTIER de la carte du marché : (colonne du profil, libellé si élevé, libellé si faible)
    MAP_DIMS = [("log_price", "haut de gamme", "petits prix"), ("promised_days", "délais longs", "livraison rapide"),
                ("log_orders", "grands volumes", "petits volumes"), ("freight_ratio", "frais de port élevés", "frais de port légers"),
                ("same_state", "clientèle locale", "ventes nationales")]

    def market_map(self, month: str | None = None, n_groups: int = 5) -> dict:
        """Carte du marché (DESCRIPTIVE), sur des dimensions MÉTIER lisibles : prix médian, délai annoncé, volume, part du port,
        part de clients dans l'État du vendeur (12 mois avant T, aucune issue). Familles = regroupement KMeans de ces dimensions ;
        carte = projection en 2 axes dont le sens est fixé et décrit en clair. Les familles ne servent pas de référence d'alerte (DS3.1)."""
        from sklearn.cluster import KMeans
        from sklearn.decomposition import PCA
        from sklearn.preprocessing import StandardScaler
        M = self._month(month)
        key = ("market_map", M, n_groups)
        if key not in self._cache:
            prof = self._profile(M)
            cols = [c for c, _, _ in self.MAP_DIMS if c in prof.columns]
            X = prof[cols].astype(float)
            X = X.fillna(X.median())
            Z = StandardScaler().fit_transform(X.to_numpy())
            lab = KMeans(n_clusters=n_groups, n_init=10, random_state=0).fit(Z).labels_
            pca = PCA(n_components=2, random_state=0).fit(Z)
            comps = pca.components_.copy()
            # sens fixé (le signe d'une composante est arbitraire) : axe 1 croît avec le prix, axe 2 avec la clientèle locale
            for i, anchor in ((0, "log_price"), (1, "same_state")):
                if anchor in cols and comps[i, cols.index(anchor)] < 0:
                    comps[i] *= -1
            xy = (Z - pca.mean_) @ comps.T
            names = {c: (hi, lo) for c, hi, lo in self.MAP_DIMS}

            axes = []
            for i in range(2):
                vec = comps[i]
                plus = [names[c][0] for c, w in sorted(zip(cols, vec), key=lambda t: -t[1]) if w >= 0.3] + \
                       [names[c][1] for c, w in sorted(zip(cols, vec), key=lambda t: t[1]) if w <= -0.3]
                minus = [names[c][1] for c, w in sorted(zip(cols, vec), key=lambda t: -t[1]) if w >= 0.3] + \
                        [names[c][0] for c, w in sorted(zip(cols, vec), key=lambda t: t[1]) if w <= -0.3]
                axes.append({"plus": ", ".join(plus[:3]), "minus": ", ".join(minus[:3]), "variance_share": _r(pca.explained_variance_ratio_[i], 3)})
            rows, _ = self._overview_rows(M)
            al = {r["seller_id"]: r for r in rows}
            sev_rank = {"élevée": 3, "moyenne": 2, "faible": 1}
            counts = {met: self._frame(M, met)[0]["level"][["year_n", "year_x"]] for met in BENCH_METRICS if self.sd.available.get(met)}
            price = np.expm1(prof["log_price"])
            points, groups = [], []
            for i, sid in enumerate(prof.index):
                r = al.get(sid)
                alerted = bool(r and any(m["alert_level"] or m["alert_trend"] for m in r["metrics"].values()))
                top = max([sev_rank.get(m["severity"], 0) for m in r["metrics"].values()] or [0]) if r else 0
                points.append({"seller_id": sid, "x": _r(xy[i, 0], 3), "y": _r(xy[i, 1], 3), "group": int(lab[i]), "main_category": prof.at[sid, "main_category"],
                               "state": prof.at[sid, "seller_state"] if isinstance(prof.at[sid, "seller_state"], str) else None,
                               "orders_12m": int(prof.at[sid, "n_orders"]), "alerted": alerted, "severity": {3: "élevée", 2: "moyenne", 1: "faible"}.get(top)})
            for g in range(n_groups):
                mask = lab == g
                ids = prof.index[mask]
                P = prof.loc[ids]
                zc = Z[mask].mean(axis=0)  # écart moyen de la famille à la marketplace (en écarts-types), par dimension
                traits = [names[c][0] if v > 0 else names[c][1] for c, v in sorted(zip(cols, zc), key=lambda t: -abs(t[1])) if abs(v) >= 0.35][:2]
                cats = P["main_category"].value_counts()
                reg = P["seller_state"].map(UF_REGION).value_counts() if "seller_state" in P.columns else pd.Series(dtype=int)
                rates = {}
                for met, c in counts.items():
                    cc = c.reindex(ids).fillna(0)
                    rates[met] = {"rate_12m": _r(cc["year_x"].sum() / cc["year_n"].sum()) if cc["year_n"].sum() else None, "known_n": int(cc["year_n"].sum())}
                groups.append({"group": g, "name": (" · ".join(traits) or "profil médian").capitalize(), "traits": traits,
                               "n_sellers": int(mask.sum()), "n_alerted": int(sum(p["alerted"] for p in points if p["group"] == g)),
                               "top_categories": [{"category": k, "sellers": int(v)} for k, v in cats.head(4).items()],
                               "regions": [{"region": k, "sellers": int(v)} for k, v in reg.head(3).items()],
                               "median_orders_12m": _r(P["n_orders"].median(), 0), "median_price": _r(float(price.loc[ids].median()), 2),
                               "median_promised_days": _r(P["promised_days"].median(), 1), "median_freight_share": _r(P["freight_ratio"].median(), 3),
                               "median_same_state_share": _r(P["same_state"].median(), 3) if "same_state" in P.columns else None, "rates": rates,
                               "orders_12m_total": int(P["n_orders"].sum()),
                               "center": {"x": _r(float(xy[mask, 0].mean()), 3), "y": _r(float(xy[mask, 1].mean()), 3)}})
            groups.sort(key=lambda x: -x["n_sellers"])
            for i, g_ in enumerate(groups, start=1):  # numéro d'affichage stable : 1 = famille la plus nombreuse
                g_["rank"] = i
            market = {met: {"rate_12m": _r(c["year_x"].sum() / c["year_n"].sum()) if c["year_n"].sum() else None} for met, c in counts.items()}
            market_profile = {"median_price": _r(float(price.median()), 2), "median_promised_days": _r(prof["promised_days"].median(), 1),
                              "median_freight_share": _r(prof["freight_ratio"].median(), 3), "median_orders_12m": _r(prof["n_orders"].median(), 0),
                              "median_same_state_share": _r(prof["same_state"].median(), 3) if "same_state" in prof.columns else None,
                              "orders_12m_total": int(prof["n_orders"].sum()), "n_alerted": int(sum(p["alerted"] for p in points))}
            self._cache[key] = {"decision_month": M, "n_sellers": len(points), "groups": groups, "points": points, "marketplace": market, "axes": axes,
                                "market_profile": market_profile,
                                "dimensions": [names[c] for c in cols],
                                "method": "familles = regroupement KMeans de 5 dimensions métier standardisées ; carte = projection en 2 axes (sens fixé) ; descriptif",
                                "note": "aucun retard ni avis n'entre dans le placement ; les familles décrivent des modèles d'activité"}
        payload = self._cache[key]
        self.log.add(f"peer:map:{M}", ESTIMATE, "DS3.1 profils d'activité à la décision (familles et carte, descriptif)",
                     {k: v for k, v in payload.items() if k != "points"})
        return to_native(payload)

    # ------------------------------------------------------------------ retards par État de destination (signal descriptif)
    def _state_late_frame(self, M: str, min_known: int = 15, alpha: float = 0.05, min_ratio: float = 1.5) -> pd.DataFrame:
        """Par (vendeur, État client) : livraisons dont l'issue est CONNUE à T (achats des 12 mois avant T), taux de retard, taux des AUTRES
        vendeurs vers ce même État (référence), test binomial unilatéral, Benjamini-Hochberg sur toutes les paires d'au moins `min_known` issues.
        Signal = q < alpha ET taux ≥ min_ratio × référence."""
        key = ("state_late", M, min_known, alpha, min_ratio)
        if key in self._cache:
            return self._cache[key]
        T = decision_date(M)
        d = self.sd.d
        w = d[(d["ts"] >= T - pd.Timedelta(days=365)) & (d["ts"] < T) & d["y_late"].notna() & (d["k_late"] <= T) & d["state"].notna()]
        g = w.groupby(["seller_id", "state"])["y_late"].agg(n="size", x="sum").reset_index()
        tot = g.groupby("state")[["n", "x"]].sum()
        g["ref_n"] = g["state"].map(tot["n"]) - g["n"]
        g["ref"] = (g["state"].map(tot["x"]) - g["x"]) / g["ref_n"].where(g["ref_n"] > 0)
        g = g[(g["n"] >= min_known) & (g["ref_n"] >= 100)].copy()
        g["rate"] = g["x"] / g["n"]
        g["p"] = stats.binom.sf(g["x"] - 1, g["n"], g["ref"].clip(1e-3, 0.999))
        g["q"] = bh(g["p"].to_numpy()) if len(g) else []
        g["alert"] = (g["q"] < alpha) & (g["rate"] >= min_ratio * g["ref"])
        self._cache[key] = g
        return g

    def _state_alert_rows(self, g: pd.DataFrame, prof: pd.DataFrame) -> list[dict]:
        out = []
        for r in g.sort_values(["q", "n"], ascending=[True, False]).itertuples():
            out.append({"seller_id": r.seller_id, "main_category": prof.at[r.seller_id, "main_category"] if r.seller_id in prof.index else None,
                        "state": r.state, "state_name": UF_NAMES.get(r.state, r.state), "known_n": int(r.n), "late": int(r.x),
                        "rate": _r(r.rate), "reference_rate": _r(r.ref), "ratio": _r(r.rate / r.ref, 2) if r.ref else None, "q": _r(r.q, 4)})
        return out

    def state_late_alerts(self, month: str | None = None, top_k: int = 50) -> dict:
        """Vendeurs dont les livraisons vers UN État arrivent en retard bien plus souvent que celles des autres vendeurs vers ce même État."""
        M = self._month(month)
        g = self._state_late_frame(M)
        rows = self._state_alert_rows(g[g["alert"]], self._profile(M))
        payload = {"decision_month": M, "n_pairs_tested": int(len(g)), "n_alerts": len(rows), "n_sellers": len({r["seller_id"] for r in rows}),
                   "alerts": rows[:top_k], "rule": "au moins 15 livraisons connues vers l'État sur 12 mois ; test binomial vs les autres vendeurs vers cet État, "
                                                   "Benjamini-Hochberg q < 0,05 ; taux au moins 1,5 fois la référence",
                   "note": "signal descriptif (non évalué rétrospectivement) : à recouper avec le transporteur et la destination"}
        self.log.add(f"alr:state:{M}", ESTIMATE, "orders_analysis (retards connus à la décision, par vendeur et État client)", payload)
        return to_native(payload)

    def seller_state_alerts(self, seller_id: str, month: str | None = None) -> dict:
        sid, M = self._resolve(seller_id), self._month(month)
        g = self._state_late_frame(M)
        mine = g[g["seller_id"] == sid]
        rows = self._state_alert_rows(mine, self._profile(M))
        payload = {"seller_id": sid, "decision_month": M, "states_tested": len(rows), "alerts": [r for r in rows if r["q"] is not None and
                   bool(mine.loc[(mine["state"] == r["state"]), "alert"].iloc[0])], "tested": rows[:10],
                   "note": "signal descriptif : livraisons vers un État comparées aux autres vendeurs vers ce même État"}
        self.log.add(f"alr:state:{sid[:8]}:{M}", ESTIMATE, "orders_analysis (retards par État de destination)", payload)
        return to_native(payload)

    # ------------------------------------------------------------------ vendeurs à appeler cette semaine
    METRIC_PHRASE = {"handover": "remises au transporteur après la date limite d'expédition", "late": "livrées après la date annoncée au client",
                     "poor": "notées 1 ou 2 étoiles par vos clients"}
    CALL_QUESTIONS = {
        "handover": ["Avez-vous connu une rupture de stock ou un changement de fournisseur récemment ?",
                     "Votre capacité de préparation suit-elle le volume de commandes (effectif, horaires, jours fériés) ?",
                     "Le passage du transporteur est-il régulier et à quelle heure limite ?"],
        "late": ["Quel transporteur utilisez-vous pour les destinations éloignées ?", "Les délais annoncés au client vous semblent-ils réalistes ?",
                 "Observez-vous des retards concentrés sur certains États ?"],
        "poor": ["Avez-vous changé de produit, de fournisseur ou d'emballage récemment ?",
                 "Les fiches produit (photos, couleurs, tailles) correspondent-elles exactement aux articles expédiés ?",
                 "Comment traitez-vous aujourd'hui les demandes de retour et de remboursement ?"],
    }

    def call_list(self, month: str | None = None, top_k: int = 10) -> dict:
        """Liste hebdomadaire des vendeurs à appeler en priorité, avec le motif chiffré, un e-mail et un script d'appel pré-remplis.
        Priorité (règle fixe, déterministe) : sévérité la plus haute, puis nombre de mois d'alerte consécutifs, nombre d'alertes, volume.
        Tous les chiffres viennent des outils (alertes, avis, retards par État)."""
        M = self._month(month)
        ck = ("calls", M, top_k)
        if ck in self._cache:  # liste calculée une fois par mois de décision (lecture des avis de chaque vendeur)
            payload = self._cache[ck]
            self.log.add(f"alr:calls:{M}", ESTIMATE, "liste d'appels (alertes DS3.2, retards par État, avis clients)",
                         {k: v for k, v in payload.items() if k != "sellers"} | {"sellers": [{k: x[k] for k in ("rank", "seller_id", "reasons")} for x in payload["sellers"]]})
            return to_native(payload)
        al = self.list_alerts(M, None, 200)
        rows, _ = self._overview_rows(M)
        info = {r["seller_id"]: r for r in rows}
        h = self.history
        prev = [str(pd.Period(M, "M") - i) for i in range(1, 4)]
        sev_rank = {"élevée": 3, "moyenne": 2, "faible": 1}
        state_alerts = self.state_late_alerts(M, top_k=500)["alerts"]
        by_seller_state: dict = {}
        for a in state_alerts:
            by_seller_state.setdefault(a["seller_id"], []).append(a)
        cands = []
        for it in al["listing"]:
            sid = it["seller_id"]
            past = h[(h["seller_id"] == sid) & (h["month"].isin(prev)) & (h["status"] != "resolved")]["month"].nunique() if len(h) else 0
            vol = info.get(sid, {}).get("orders_12m", 0)
            score = sev_rank.get(it["top_severity"], 0) * 1000 + past * 100 + it["n_alerts"] * 10 + np.log10(max(vol, 1))
            cands.append((score, sid, it, int(past)))
        listed = {c[1] for c in cands}
        for sid, sa in by_seller_state.items():  # vendeurs sans alerte globale mais avec un État en difficulté
            if sid not in listed and sid in info:
                cands.append((np.log10(max(info[sid]["orders_12m"], 1)), sid, {"seller_id": sid, "main_category": info[sid]["main_category"],
                              "n_alerts": 0, "top_severity": None, "alerts": []}, 0))
        cands.sort(key=lambda c: -c[0])
        out = []
        for rank, (_, sid, it, past) in enumerate(cands[:top_k], start=1):
            r = info.get(sid, {})
            main = max(it["alerts"], key=lambda a: (sev_rank.get(a.get("severity"), 0), (a["recent_rate"] or 0) / max(a["baseline"] or 1e-3, 1e-3))) if it["alerts"] else None
            voice = self.seller_voice(sid, M)
            top_neg = (voice.get("top_negative") or [None])[0] if voice.get("available") else None
            st = sorted(by_seller_state.get(sid, []), key=lambda a: -a["known_n"])[:2]
            reasons = []
            if main:
                reasons.append(f"{METRIC_LABEL[main['metric']].capitalize()} : {pct(main['recent_rate'])} sur 90 jours contre {pct(main['baseline'])} "
                               f"({'écart à la marketplace' if main['family'] == 'level' else 'dégradation par rapport à son passé'})")
            if past:
                reasons.append(f"déjà en alerte {past} des 3 mois précédents")
            for a in st:
                reasons.append(f"livraisons vers {a['state_name']} en retard à {pct(a['rate'])} contre {pct(a['reference_rate'])} pour les autres vendeurs "
                               f"({a['known_n']} livraisons)")
            if top_neg:
                reasons.append(f"sujet le plus critiqué par ses clients : « {top_neg['label']} » ({top_neg['negative']} avis)")
            metric = main["metric"] if main else "late"
            fact = (f"Sur les 90 derniers jours, {pct(main['recent_rate'])} de vos commandes ont été {self.METRIC_PHRASE[metric]}, contre {pct(main['baseline'])} "
                    "en moyenne sur la marketplace." if main else
                    f"Nous observons davantage de retards de livraison vers {st[0]['state_name']} ({pct(st[0]['rate'])} de vos livraisons, contre "
                    f"{pct(st[0]['reference_rate'])} pour les autres vendeurs)." if st else "")
            extra = []
            if top_neg:
                extra.append(f"Dans leurs avis, vos clients évoquent surtout « {top_neg['label'].lower()} ».")
            if main and st:
                extra.append(f"Les livraisons vers {st[0]['state_name']} arrivent aussi plus souvent en retard ({pct(st[0]['rate'])}).")
            subject = {"handover": "Point sur vos délais d'expédition", "late": "Point sur vos délais de livraison",
                       "poor": "Point sur la satisfaction de vos clients"}[metric]
            email = ("Bonjour,\n\nNous suivons chaque mois la qualité de service des vendeurs de la marketplace. " + fact + (" " + " ".join(extra) if extra else "")
                     + "\n\nNous aimerions en parler avec vous pour comprendre la situation et voir comment vous accompagner. "
                     "Seriez-vous disponible pour un court échange cette semaine ?\n\nBien cordialement,\nL'équipe Qualité vendeurs")
            script = [{"step": "Ouverture", "text": "Se présenter (équipe Qualité vendeurs) et annoncer un échange de 10 minutes sur la qualité de service."},
                      {"step": "Constat", "text": fact + (" " + " ".join(extra) if extra else "")},
                      {"step": "Questions", "text": " ".join(f"« {q} »" for q in self.CALL_QUESTIONS[metric])},
                      {"step": "Proposition", "text": "Convenir d'une action simple et datée (ex. heure limite de préparation, contrôle avant expédition, mise à jour des fiches produit)."},
                      {"step": "Suivi", "text": "Annoncer le prochain point : les indicateurs seront revus au bilan de la fin du mois suivant."}]
            out.append({"rank": rank, "seller_id": sid, "main_category": it["main_category"], "category_label": cat_label(it["main_category"]),
                        "seller_state": r.get("seller_state"), "orders_12m": r.get("orders_12m"), "top_severity": it["top_severity"],
                        "n_alerts": it["n_alerts"], "months_alerted_before": past, "main_metric": metric, "reasons": reasons,
                        "email": {"subject": f"ShopInsight — {subject}", "body": email}, "call_script": script})
        payload = {"decision_month": M, "n_candidates": len(cands), "sellers": out,
                   "priority_rule": "sévérité la plus haute, puis mois d'alerte consécutifs, nombre d'alertes, volume ; puis vendeurs avec un État en difficulté"}
        self._cache[ck] = payload
        self.log.add(f"alr:calls:{M}", ESTIMATE, "liste d'appels (alertes DS3.2, retards par État, avis clients)",
                     {k: v for k, v in payload.items() if k != "sellers"} | {"sellers": [{k: s[k] for k in ("rank", "seller_id", "reasons")} for s in out]})
        return to_native(payload)

    # ------------------------------------------------------------------ évolution mensuelle des familles du marché
    def market_family_trends(self, month: str | None = None, n_months: int = 6, n_groups: int = 5) -> dict:
        """Pour chaque famille de la carte du marché (composition fixée au mois M), taux groupé sur 90 jours de chaque indicateur et nombre de
        vendeurs en alerte, mois par mois (chaque mois calculé avec les seules données connues à sa fin : bo3_monthly_history)."""
        M = self._month(month)
        mm = self.market_map(M, n_groups)
        members = {}
        for p in mm["points"]:
            members.setdefault(p["group"], set()).add(p["seller_id"])
        H = self.monthly
        months = [str(pd.Period(M, "M") - i) for i in range(n_months - 1, -1, -1)]
        H = H[H["month"].isin(months)]
        fams = []
        for g in mm["groups"]:
            sub = H[H["seller_id"].isin(members.get(g["group"], set()))]
            series = []
            for m_ in months:
                s_ = sub[sub["month"] == m_]
                row = {"month": m_}
                for met, gm in s_.groupby("metric"):
                    n = int(gm["rec_n"].sum())
                    row[met] = {"rate_90d": _r(gm["rec_x"].sum() / n) if n else None, "known_n": n}
                row["sellers_alerted"] = int(s_.loc[s_["alert_level"].astype(bool) | s_["alert_trend"].astype(bool), "seller_id"].nunique())
                series.append(row)
            fams.append({"group": g["group"], "name": g["name"], "series": series})
        market = []
        for m_ in months:
            s_ = H[H["month"] == m_]
            row = {"month": m_}
            for met, gm in s_.groupby("metric"):
                n = int(gm["rec_n"].sum())
                row[met] = {"rate_90d": _r(gm["rec_x"].sum() / n) if n else None, "known_n": n}
            market.append(row)
        payload = {"decision_month": M, "months": months, "families": fams, "marketplace": market,
                   "note": "composition des familles fixée à la fin du mois de décision ; chaque mois n'utilise que les données connues à sa fin"}
        self.log.add(f"peer:map:trend:{M}", FACT, "data/model/bo3_monthly_history.csv.gz (familles de la carte du marché)", payload)
        return to_native(payload)

    def marketplace_brief(self, month: str | None = None, top_k: int = 10, n_categories: int = 8, min_known: int = 50) -> dict:
        """Contexte « marketplace » de l'assistant global, à la fin du mois M (issues connues à T uniquement) :
        résumé des vendeurs évalués (kpi:overview), vendeurs en alerte classés par sévérité (alr:list), et par catégorie de produit
        (catégorie de la commande) le taux sur 90 jours de chaque indicateur avec son effectif, ainsi que le nombre de vendeurs en alerte
        par catégorie principale (kpi:categories)."""
        M = self._month(month)
        T = decision_date(M)
        ov = self.sellers_overview(M, limit=1)
        al = self.list_alerts(M, None, top_k)
        d = self.sd.d
        rec = (d["ts"] >= T - pd.Timedelta(days=RECENT_DAYS)) & (d["ts"] < T)
        by_cat, market = {}, {}
        for met in self.metrics:
            known = rec & d[f"y_{met}"].notna() & (d[f"k_{met}"] <= T)
            y = d.loc[known, f"y_{met}"]
            market[met] = {"rate_90d": _r(y.mean()) if len(y) else None, "known_n": int(len(y)), "events": int(y.sum())}
            g = d.loc[known].groupby("category")[f"y_{met}"].agg(["size", "sum"])
            g = g[g["size"] >= min_known]
            g["rate"] = g["sum"] / g["size"]
            by_cat[met] = [{"category": str(c), "rate_90d": _r(r["rate"]), "known_n": int(r["size"]), "events": int(r["sum"])}
                           for c, r in g.sort_values("rate", ascending=False).head(n_categories).iterrows()]
        alerted: dict[str, dict] = {}
        rows, _ = self._overview_rows(M)
        for r in rows:
            c = alerted.setdefault(str(r["main_category"]), {"category": str(r["main_category"]), "sellers_evaluated": 0, "sellers_alerted": 0})
            c["sellers_evaluated"] += 1
            c["sellers_alerted"] += int(any(m["alert_level"] or m["alert_trend"] for m in r["metrics"].values()))
        alerted_top = sorted((c for c in alerted.values() if c["sellers_alerted"]), key=lambda c: (-c["sellers_alerted"], -c["sellers_evaluated"]))[:n_categories]
        payload = {"decision_month": M, "decision_date": T.date().isoformat(), "labels": {m: METRIC_LABEL[m] for m in self.metrics},
                   "marketplace_90d": market, "highest_rate_categories": by_cat, "categories_with_most_alerted_sellers": alerted_top,
                   "min_known_per_category": min_known,
                   "note": "catégorie de la commande pour les taux (achats des 90 jours avant la décision, issues connues à la décision) ; "
                           "catégorie principale du vendeur pour le nombre de vendeurs en alerte"}
        self.log.add(f"kpi:categories:{M}", FACT, "orders_analysis (issues connues à la décision, commandes mono-vendeur) + alertes DS3.2", payload)
        return to_native({"overview": {k: ov[k] for k in ("decision_month", "reference_rates", "summary", "n_sellers")}, "alerts": al, "categories": payload})

    def alert_history_rows(self, seller_id: str | None = None, metric: str | None = None, family: str | None = None,
                           status: str | None = None, month: str | None = None, until: str | None = None, limit: int = 500) -> dict:
        """Lignes filtrées de data/gold/seller_alert_history.csv (« until » : seulement les mois de décision ≤ until)."""
        h = self.history
        if seller_id:
            h = h[h["seller_id"] == self._resolve(seller_id)]
        for col, val in (("metric", metric), ("family", family), ("status", status), ("month", month)):
            if val:
                h = h[h[col] == val]
        if until:
            h = h[h["month"] <= until]
        h = h.sort_values(["month", "seller_id"], ascending=[False, True])
        return to_native({"n_rows": int(len(h)), "rows": h.head(limit).where(h.head(limit).notna(), None).to_dict("records")})

    def get_seller_orders(self, seller_id: str, month: str | None = None, k: int = 5) -> dict:
        sid, M = self._resolve(seller_id), self._month(month)
        T = decision_date(M)
        d = self.sd.d
        sub = d[(d["seller_id"] == sid) & (d["ts"] >= T - pd.Timedelta(days=RECENT_DAYS)) & (d["ts"] < T)].copy()
        probs = []
        for met in self.metrics:
            known = sub[f"y_{met}"].notna() & (sub[f"k_{met}"] <= T)
            sub[f"p_{met}"] = known & (sub[f"y_{met}"] == 1)
            probs.append(f"p_{met}")
        sub["n_problems"] = sub[probs].sum(axis=1)
        sub = sub[sub["n_problems"] > 0].sort_values(["n_problems", "ts"], ascending=[False, False])
        cases = []
        for _, o in sub.head(k).iterrows():
            # Détails affichés seulement s'ils étaient connus à T : durée de retard si livrée avant T, note si avis publié avant T,
            # retard de remise si remise faite avant T. Sinon on sait seulement que le problème existe (date limite dépassée).
            c = {"order_id": o["order_id"], "purchase_date": o["ts"].date().isoformat(), "customer_state": o["state"], "category": o["category"],
                 "problems": [METRIC_LABEL[m[2:]] for m in probs if o[m]],
                 "late_days": int(o["late_days"]) if (o.get("p_late") and pd.notna(o["t_delivered"]) and o["t_delivered"] <= T and pd.notna(o["late_days"])) else None,
                 "review_score": int(o["review_score"]) if (o.get("p_poor") and pd.notna(o["review_score"])) else None,
                 "handover_delay_days": int(o["handover_delay_days"]) if (o.get("p_handover") and pd.notna(o["t_carrier"]) and o["t_carrier"] <= T
                                                                          and pd.notna(o["handover_delay_days"])) else None}
            cases.append(c)
            self.log.add(f"ord:{o['order_id']}", FACT, "orders_analysis (issue connue avant la décision)", c)
        n_recent = int(((d["seller_id"] == sid) & (d["ts"] >= T - pd.Timedelta(days=RECENT_DAYS)) & (d["ts"] < T)).sum())
        payload = {"seller_id": sid, "decision_month": M, "orders_recent": n_recent, "orders_with_known_problem": int(len(sub)), "shown": cases}
        self.log.add(f"ord:seller:{sid[:8]}:{M}", FACT, "orders_analysis", payload)
        return to_native(payload)

    def seller_voice(self, seller_id: str, month: str | None = None) -> dict:
        sid, M = self._resolve(seller_id), self._month(month)
        T = decision_date(M)
        try:
            from .bo2_agent import VoiceOfCustomerAgent
            from .bo2_nlp import ASPECTS
            if self._voc is None:
                self._voc = VoiceOfCustomerAgent(self.dir)
            an = self._voc.an
        except FileNotFoundError:
            payload = {"seller_id": sid, "decision_month": M, "available": False, "note": "fichier d'avis absent"}
            self.log.add(f"mdl:aspects:seller:{sid[:8]}:{M}", ESTIMATE, "bo2_nlp.LexiconAspectModel", payload)
            return payload
        d = self.sd.d
        known = d[(d["seller_id"] == sid) & (d["ts"] >= T - pd.Timedelta(days=365)) & (d["ts"] < T) & (d["k_poor"] <= T)]["order_id"]
        sub = an[an["order_id"].isin(set(known))]
        rows = []
        for a, (label, _) in ASPECTS.items():
            col = sub[f"a_{a}"]
            rows.append({"aspect": a, "label": label, "negative": int((col == -1).sum()), "positive": int((col == 1).sum())})
        neg = sorted([r for r in rows if r["aspect"] != "satisfaction_globale" and r["negative"] > 0], key=lambda r: -r["negative"])
        pos = sorted([r for r in rows if r["aspect"] != "satisfaction_globale" and r["positive"] > 0], key=lambda r: -r["positive"])
        payload = {"seller_id": sid, "decision_month": M, "available": True, "n_written_reviews": int(len(sub)),
                   "share_rated_1_2": _r((sub["score"] <= 2).mean(), 3) if len(sub) else None, "top_negative": neg[:5], "top_positive": pos[:3],
                   "quotes": [],
                   "method": "baseline mots-clés (portugais) + note, NON validée (DS2.1) ; avis publiés avant la décision, achats des 12 mois précédents"}
        if len(sub) >= 5 and neg:
            idx = self._voc.index
            # Deux extraits par aspect pour les trois aspects les plus critiqués : de quoi croiser opérations et ressenti des clients.
            # Choix déterministe (pas de recherche plein texte : les libellés d'aspect sont en français, les avis en portugais) :
            # avis traduits d'abord, puis note la plus basse, puis texte le plus informatif (long), puis identifiant.
            seen: set[str] = set()
            base = idx.df[idx.df["order_id"].isin(set(known)) & (idx.df["score"] <= 2)]
            for top in [r["aspect"] for r in neg[:3]]:
                cand = base[(base[f"a_{top}"] == -1) & ~base["review_id"].isin(seen)].assign(
                    _fr=lambda x: (x["translation_status"] == "traduit").astype(int), _len=lambda x: x["full_pt"].fillna("").str.len().clip(upper=400))
                for _, h in cand.sort_values(["_fr", "score", "_len", "review_id"], ascending=[False, True, False, True]).head(2).iterrows():
                    seen.add(h["review_id"])
                    fr_ok = bool(h["full_fr"]) and h["translation_status"] == "traduit"
                    text = h["full_fr"] if fr_ok else h["full_pt"]
                    if not fr_ok and self._translator is not None:  # traduction déjà en cache seulement (aucun calcul ici : l'audit reste immédiat)
                        fr = self._translator.review(h.get("title_pt"), h.get("text_pt"), allow_model=False)
                        if fr:
                            text, fr_ok = fr, True
                    self._quote_sources.setdefault((sid, M), {})[h["review_id"]] = (h.get("title_pt"), h.get("text_pt"))
                    cut = lambda t: (t[:200] + "…") if len(t) > 200 else t  # noqa: E731
                    q = {"review_id": h["review_id"], "order_id": h["order_id"], "score": int(h["score"]), "aspect": ASPECTS[top][0],
                         "excerpt": cut(text), "machine_translated": fr_ok, "excerpt_original": cut(h["full_pt"]) if fr_ok else None}
                    payload["quotes"].append(q)
                    self.log.add(f"rev:{h['review_id']}", SIMILAR, "silver/reviews_text(.fr).jsonl.gz (propos d'un client du vendeur)", q)
        self.log.add(f"mdl:aspects:seller:{sid[:8]}:{M}", ESTIMATE, "bo2_nlp.LexiconAspectModel (avis des clients du vendeur)", payload)
        return to_native(payload)

    def multi_seller_exposure(self, seller_id: str, month: str | None = None) -> dict:
        sid, M = self._resolve(seller_id), self._month(month)
        T = decision_date(M)
        if self._links is None:
            self._links = load_multi_seller_links(self.dir)
        links = self._links
        start = str((pd.Period(M, "M") - 11))
        L = links[(links["seller_id"] == sid) & (links["purchase_month"].astype(str) >= start) & (links["purchase_month"].astype(str) <= M)]
        d = self.sd.d
        single = int(((d["seller_id"] == sid) & (d["ts"] >= T - pd.Timedelta(days=365)) & (d["ts"] < T)).sum())
        n = int(len(L))
        payload = {"seller_id": sid, "decision_month": M, "multi_seller_orders_12m": n, "single_seller_orders_12m": single,
                   "multi_share": _r(n / (n + single), 3) if n + single else None,
                   "mean_price_share_in_multi": _r(L["seller_price_share"].astype(float).mean(), 3) if n else None,
                   "note": "commandes multi-vendeurs exclues des taux ; leur retard et leur avis ne sont pas attribués à ce vendeur"}
        self.log.add(f"ctx:multi:{sid[:8]}:{M}", FACT, "silver/multi_seller_order_links (sans attribution)", payload)
        return to_native(payload)

    # ------------------------------------------------------------------ composition
    def audit(self, seller_id: str, month: str | None = None, metric: str | None = None, use_llm: bool = True) -> Report:
        self.log = EvidenceLog()
        sid, M = self._resolve(seller_id), self._month(month)
        T = decision_date(M)
        rep = BO3Report(f"Audit vendeur {sid[:8]}… — décision fin {M}",
                     section_titles={"estimates": "Comparaisons et détection (estimations)", "similar": "Vendeurs comparables et voix des clients du vendeur"})
        prof = self.get_seller_profile(sid, M)
        if prof["insufficient"]:
            rep.facts.append(Line(f"Seulement {prof['orders_12m']} commandes mono-vendeur sur les 12 mois avant le {T.date().isoformat()} : "
                                  "aucune comparaison fiable possible.", [f"sel:{sid[:8]}:{M}"]))
            rep.actions.append(Line("Volume insuffisant pour juger ce vendeur seul : le suivre au niveau de sa catégorie.", [f"sel:{sid[:8]}:{M}"]))
            rep.caveats.append("Petit volume : un taux calculé sur quelques commandes n'a pas de valeur de comparaison.")
            rep.narrative = f"Vendeur {sid[:8]} : volume insuffisant à la fin de {M}."
            rep.meta = {"seller_id": sid, "month": M, "alerts": []}
            return rep
        metrics = [metric] if metric else self.metrics
        peer = self.get_peer_group(sid, M)
        multi = self.multi_seller_exposure(sid, M)
        cmp = {m: self.compare_to_peers(sid, M, m) for m in metrics}
        det = {m: self.detect_deterioration(sid, M, m) for m in metrics}
        orders = self.get_seller_orders(sid, M)
        voice = self.seller_voice(sid, M)
        strong = self.find_strengths(sid, M)
        hist = self.get_seller_history(sid, M, n_months=12)
        geo = self.get_seller_geography(sid, M)
        s8 = sid[:8]

        # FAITS
        mix = ", ".join(f"{cat_label(x['value'])} {pct(x['share'])}" for x in prof["category_mix"][:3])
        dest = ", ".join(f"{x['value']} {pct(x['share'])}" for x in prof["destination_mix"][:3])
        rep.facts.append(Line(f"Vendeur{(' de l’État ' + uf_name(prof['seller_state'])) if prof['seller_state'] else ''} : {prof['orders_12m']} commandes mono-vendeur "
                              f"achetées sur les 12 mois avant le {T.date().isoformat()} ; catégories : {mix} ; destinations : {dest} ; "
                              f"prix médian {_fr(prof['median_price'], 2)} R$, délai promis moyen {_fr(prof['mean_promised_days'])} jours"
                              + (f" ; segment descriptif : {prof['descriptive_segment']['volume']}, {prof['descriptive_segment']['region']}" if prof.get("descriptive_segment") else "")
                              + ".", [f"sel:{s8}:{M}"]))
        fl = prof.get("flows") or {}
        if fl.get("destinations"):
            top_d = ", ".join(f"{uf_name(x['state'])} {x['orders']} commandes ({pct(x['share'])})" for x in fl["destinations"][:4])
            same = (f" ; {fl['same_state_orders']} commandes ({pct(fl['same_state_share'])}) restent dans l’État d’origine"
                    if fl.get("same_state_share") is not None else "")
            rep.facts.append(Line(f"Flux sortants{(' depuis ' + uf_name(fl['origin_state'])) if fl.get('origin_state') else ''} : {fl['orders_12m']} commandes vers "
                                  f"{fl['n_destination_states']} États ; principales destinations : {top_d}{same}.", [f"sel:{s8}:{M}"]))
        bands = [b for b in geo.get("distance_bands") or [] if b.get("late_rate") is not None]
        if geo.get("origin") and geo.get("median_distance_km") is not None:
            txt = (f"Expédie depuis {geo['origin']['city']} ({geo['origin']['state_name']}) ; distance médiane au client "
                   f"{_fr(geo['median_distance_km'], 0)} km")
            if bands:
                txt += " ; retard de livraison sur 12 mois par distance : " + ", ".join(f"{b['band']} {pct(b['late_rate'])} (n = {b['late_known']})" for b in bands)
            rep.facts.append(Line(txt + ".", [f"sel:geo:{s8}:{M}"]))
        for a_ in (geo.get("state_alerts") or [])[:3]:
            rep.estimates.append(Line(f"Retards anormaux vers {a_['state_name']} : {pct(a_['rate'])} des livraisons (n = {a_['known_n']}) contre "
                                      f"{pct(a_['reference_rate'])} pour les autres vendeurs vers cet État (signal descriptif par État).", [f"sel:geo:{s8}:{M}"]))
        for m in metrics:
            o = cmp[m]["observed"]
            if o["recent_known_n"]:
                lo, hi = o["recent_ci95"]
                txt = (f"{o['label'].capitalize()} : {pct(o['recent_rate'])} sur les 90 derniers jours (n = {o['recent_known_n']} issues connues "
                       f"sur {o['orders_recent']} commandes ; IC 95 % {pct(lo)} – {pct(hi)})")
            else:
                txt = f"{o['label'].capitalize()} : aucune issue connue sur les 90 derniers jours ({o['orders_recent']} commandes)"
            if o["year_known_n"]:
                txt += f" ; {pct(o['year_rate'])} sur 12 mois (n = {o['year_known_n']})."
            rep.facts.append(Line(txt, [f"kpi:seller:{s8}:{M}:{m}"]))
            ser = [x for x in (hist.get("series") or {}).get(m, []) if x["known_n"] and x["rate_90d"] is not None]
            if len(ser) >= 2:
                rep.facts.append(Line(f"Évolution ({o['label']}, taux sur 90 jours à chaque fin de mois) : "
                                      + " → ".join(f"{x['month']} {pct(x['rate_90d'])} (n = {x['known_n']})" for x in ser[-4:]) + ".",
                                      [f"kpi:history:{s8}:{M}"]))
        if multi["multi_seller_orders_12m"]:
            rep.facts.append(Line(f"{multi['multi_seller_orders_12m']} commandes multi-vendeurs sur 12 mois ({pct(multi['multi_share'])} de son activité) : "
                                  "exclues des taux, leur retard et leur avis ne sont pas attribués à ce vendeur.", [f"ctx:multi:{s8}:{M}"]))
        if orders["shown"]:
            rep.facts.append(Line(f"{orders['orders_with_known_problem']} commandes des 90 derniers jours ont un problème déjà connu à la décision "
                                  f"(sur {orders['orders_recent']}) ; exemples :", [f"ord:seller:{s8}:{M}"]))
            for c in orders["shown"][:3]:
                det_txt = []
                if c["late_days"] is not None:
                    det_txt.append(f"livrée {c['late_days']} j après la date promise")
                if c["review_score"] is not None:
                    det_txt.append(f"note {c['review_score']}/5")
                if c["handover_delay_days"] is not None:
                    det_txt.append(f"remise au transporteur {c['handover_delay_days']} j après la limite")
                rep.facts.append(Line(f"Commande {c['order_id']} ({c['purchase_date']}, client {uf_name(c['customer_state'])}, {cat_label(c['category'])}) : "
                                      + ", ".join(c["problems"]) + (f" ({'; '.join(det_txt)})" if det_txt else "") + ".", [f"ord:{c['order_id']}"]))

        # ESTIMATIONS
        alerts_on: list[tuple[str, str]] = []
        for m in metrics:
            o = cmp[m]["observed"]
            if o["recent_known_n"]:
                if self.global_ref:
                    txt = (f"{o['label'].capitalize()} — comparaison à la marketplace : {pct(o['recent_rate'])} contre {pct(o['peer_rate'])} pour l'ensemble "
                           f"des autres vendeurs (n = {o['peer_known_n']}) ; ratio ×{_fr(o['ratio_to_peers'], 2)} ; position : {o['funnel_position']} ; "
                           f"taux du vendeur rétréci vers la marketplace : {pct(o['shrunk_rate'])}.")
                else:
                    ref = " (repli sur la marketplace : pairs trop peu nombreux)" if o["peer_fallback_to_marketplace"] else ""
                    txt = (f"{o['label'].capitalize()} — comparaison aux pairs : {pct(o['recent_rate'])} contre {pct(o['peer_rate'])} pour les vendeurs comparables{ref} "
                           f"(n = {o['peer_known_n']}) et {pct(o['marketplace_rate'])} pour la marketplace ; ratio ×{_fr(o['ratio_to_peers'], 2)} ; "
                           f"position : {o['funnel_position']} ; taux du vendeur rétréci vers ses pairs : {pct(o['shrunk_rate'])}.")
                rep.estimates.append(Line(txt, [f"kpi:seller:{s8}:{M}:{m}"]))
            e = cmp[m].get("expected")
            if e:
                rep.estimates.append(Line(
                    f"{o['label'].capitalize()} — observé / attendu : {e['observed_events']} événements contre {_fr(e['expected_events'])} attendus "
                    f"compte tenu des destinations, produits et promesses de ses commandes (ratio {_fr(e['oe_ratio'], 2)}, z = {_fr(e['z'])}, n = {e['n_orders_scored']})."
                    + (" Modèle évalué dans son échantillon d'entraînement pour une partie de ces commandes : optimiste." if e["in_sample"] else ""),
                    [f"mdl:expected:{s8}:{M}:{m}"]))
            for fam, x in det[m]["families"].items():
                ev = [f"alr:{s8}:{M}:{m}"]
                if not x["eligible"]:
                    need = (f"{x['year_known_n']} issues connues sur 12 mois (minimum {x['min_history']}), {x['recent_known_n']} sur 90 jours (minimum {x['min_recent']})"
                            + (f", {x['history_known_n']} dans son historique propre (minimum {x['min_own_history']})" if fam == "trend" else ""))
                    rep.estimates.append(Line(f"{o['label'].capitalize()} — détection {self._fam(fam)} : volume insuffisant ({need}) ; pas d'alerte possible.", ev))
                elif x["alert"]:
                    alerts_on.append((m, fam))
                    sev = f", sévérité {x['severity']}" if x.get("severity") else ""
                    conf = " ; signal confirmé : déjà présent le mois précédent" if x.get("persistence_rule") else ""
                    rep.estimates.append(Line(f"ALERTE {self._fam(fam)}{sev} — {o['label']} : {pct(x['recent_rate'])} sur 90 jours (n = {x['recent_known_n']}) contre "
                                              f"{pct(x['baseline'])} ({x['baseline_label']}){conf}.", ev))
                elif x.get("raw_alert") and x.get("persistence_rule"):
                    rep.estimates.append(Line(f"Signal {self._fam(fam)} non confirmé — {o['label']} : {pct(x['recent_rate'])} sur 90 jours (n = {x['recent_known_n']}) "
                                              f"contre {pct(x['baseline'])} ; la règle de persistance n'alerte que si le signal se répète le mois suivant.", ev))
                else:
                    rep.estimates.append(Line(f"Pas d'alerte {self._fam(fam)} — {o['label']} : {pct(x['recent_rate'])} sur 90 jours (n = {x['recent_known_n']}) "
                                              f"contre {pct(x['baseline'])} ({x['baseline_label']}).", ev))
            if det[m]["n_past_alert_months"]:
                last = det[m]["past_alerts"][-1]
                rep.estimates.append(Line(f"{o['label'].capitalize()} : déjà en alerte {det[m]['n_past_alert_months']} mois de décision auparavant "
                                          f"(dernière : {last['month']}, {self._fam(last['family'])}).", [f"alr:{s8}:{M}:{m}"]))
        for it in strong["items"]:
            if it["strength"]:
                rep.estimates.append(Line(f"Point fort — {it['label']} : {pct(it['year_rate'])} sur 12 mois (n = {it['year_known_n']}) contre "
                                          f"{pct(it['reference_rate'])} pour {self.ref_name}, écart significatif.", [f"alr:strength:{s8}:{M}"]))
        if voice.get("available") and voice["n_written_reviews"]:
            top = "; ".join(f"« {r['label']} » ({r['negative']} avis)" for r in voice["top_negative"]) or "aucun aspect critiqué"
            rep.estimates.append(Line(f"Avis écrits de ses clients (12 mois, publiés avant la décision) : {voice['n_written_reviews']} ; aspects les plus critiqués : {top}.",
                                      [f"mdl:aspects:seller:{s8}:{M}"]))

        # PAIRS ET VOIX DES CLIENTS
        cats = ", ".join(f"{cat_label(c['category'])} ({c['count']})" for c in peer["peer_main_categories"])
        head = (f"Référence : toute la marketplace ({peer['n_peers']} autres vendeurs) ; à titre descriptif, catégories principales des vendeurs à l'activité la plus proche : {cats}. "
                if self.global_ref else f"Vendeurs comparables : {peer['method']} ; {peer['n_peers']} pairs ; catégories principales des pairs les plus proches : {cats}. ")
        rep.similar.append(Line(head +
                                "La similarité ne repose que sur l'activité (catégories, destinations, volume, prix, port, poids, délai), jamais sur les retards ou les avis.",
                                [f"peer:{s8}:{M}"]))
        bench = peer.get("benchmark") or {}
        for grp in ("category", "direct_competitors"):
            g = bench.get(grp)
            if not g:
                continue
            parts = []
            for m in BENCH_METRICS:
                x = g["metrics"].get(m) or {}
                if m in metrics and x.get("rank"):
                    parts.append(f"{METRIC_LABEL[m]} {pct(x['seller_rate'])} (n = {x['seller_known_n']}), rang {x['rank']} sur {x['n_ranked']}, "
                                 f"médiane {pct(x['group_median'])}, seuil du meilleur quart {pct(x['top_quartile_threshold'])}")
            if parts:
                rep.similar.append(Line(f"Positionnement descriptif — {g['label']} ({g['n_members']} vendeurs, 12 mois d'issues connues) : "
                                        + " ; ".join(parts) + ".", [f"peer:bench:{s8}:{M}"]))
        for q in voice.get("quotes", []):
            mt = " (traduction automatique)" if q["machine_translated"] else " (portugais original)"
            rep.similar.append(Line(f"Client du vendeur, {q['score']}/5, « {q['aspect']} » : « {q['excerpt']} »{mt}", [f"rev:{q['review_id']}"]))

        # ACTIONS
        rep.actions.extend(self._actions(sid, M, metrics, cmp, det, voice, alerts_on))
        # LIMITES
        share = cmp[metrics[0]]["observed"].get("share_known_recent")
        rep.caveats += [
            f"Taux calculés sur les commandes mono-vendeur et les seules issues connues au {T.date().isoformat()}"
            + (f" ({pct(share)} des commandes récentes ont une issue de {METRIC_LABEL[metrics[0]]} connue)" if share is not None else "")
            + " : les commandes encore en transit ne comptent pas, ce qui sur-représente les livraisons rapides des dernières semaines.",
            f"Vendeurs comparables : {self.cfg.label} ; " + ("méthode et seuils retenus sur janv.–mars 2018, évalués une seule fois sur avr.–juin 2018 (quality/bo3_model_results.json)."
                                                          if self.trained else "réglages par défaut : lancer src/train_seller_models.py pour les choisir sur VALID."),
            "Associations observées, pas de causes : Olist n'enregistre pas pourquoi une commande est en retard ou mal notée ; contacter le vendeur avant toute décision.",
            "Données historiques (2016–2018), pas de flux temps réel.",
        ]
        if self.cfg.method == "global" and self.trained:
            rep.caveats.append("Sur VALID, aucun regroupement de vendeurs (catégorie, plus proches voisins, KMeans) n'a mieux prédit le taux futur d'un vendeur "
                               "que la moyenne de la marketplace : la référence est donc la marketplace ; les vendeurs les plus proches sont montrés à titre descriptif.")
        pers = [f for f, c in self.card["detection"].items() if c.get("persistence")]
        rep.caveats.append("Sévérité (règle fixe, non réglée) — " + SEVERITY_RULE + "."
                           + (f" Règle de persistance active pour : {', '.join(self._fam(f) for f in pers)}." if pers else ""))
        if prof.get("descriptive_segment"):
            rep.caveats.append("Le segment (volume, région) est descriptif : il n'a pas amélioré la prédiction du taux futur, la référence reste " + self.ref_name + ".")
        if voice.get("available"):
            rep.caveats.append("Aspects des avis : baseline par mots-clés non validée ; extraits français = traduction automatique (l'original portugais fait foi).")
        if multi["multi_seller_orders_12m"]:
            rep.caveats.append("Commandes multi-vendeurs : comptées à part, sans attribution du retard ni de l'avis.")
        tp = self.card.get("test_summary") or {}
        if tp.get("level") and tp["level"].get("precision") is not None:
            rep.caveats.append(f"Fiabilité mesurée sur avr.–juin 2018 : alertes de niveau confirmées dans les 60 jours suivants dans {pct(tp['level']['precision'])} des cas, "
                               f"{pct(tp['level']['recall'] or 0)} des écarts persistants signalés ; une alerte ouvre une enquête, elle ne prouve rien.")
        if tp.get("trend") and tp["trend"].get("precision") is not None and tp["trend"]["precision"] < 0.15:
            rep.caveats.append(f"Alertes de tendance peu fiables sur avr.–juin 2018 (confirmées dans {pct(tp['trend']['precision'])} des cas) : "
                               "les traiter comme un signal faible, à recouper avec l'alerte de niveau.")
        rep.narrative = self._narrative(sid, M, metrics, cmp, alerts_on)
        rep.meta = {"seller_id": sid, "month": M, "decision_date": T.date().isoformat(), "alerts": [{"metric": m, "family": f} for m, f in alerts_on],
                    "model": "bo3_model_card.json" if self.trained else "défauts", "tool_calls": len(self.log.tool_calls)}
        if use_llm and self.llm:
            self._llm_narrative(rep, f"Rédige le résumé de l'audit du vendeur {sid[:8]} à la fin de {M}.")
        return rep

    def _actions(self, sid, M, metrics, cmp, det, voice, alerts_on) -> list[Line]:
        s8 = sid[:8]
        on = {m for m, _ in alerts_on}
        acts: list[Line] = []
        if "handover" in on:
            o = cmp["handover"]["observed"]
            acts.append(Line(f"(Support vendeurs) Vérifier avec le vendeur ses délais de préparation : {pct(o['recent_rate'])} de ses commandes récentes ont été "
                             "remises au transporteur après la date limite. Hypothèses à confirmer : stock, capacité, jours non ouvrés.",
                             [f"alr:{s8}:{M}:handover", f"kpi:seller:{s8}:{M}:handover"]))
        if "late" in on:
            if "handover" in on:
                acts.append(Line("Les retards de livraison coïncident avec des remises tardives au transporteur : traiter d'abord la préparation des commandes chez le vendeur.",
                                 [f"alr:{s8}:{M}:late"]))
            else:
                acts.append(Line("(Logistique) Retards de livraison sans remise tardive signalée : examiner transporteurs et destinations de ce vendeur ; "
                                 "utiliser l'agent BO1 pour surveiller ses commandes en cours.", [f"alr:{s8}:{M}:late"]))
        if "poor" in on:
            top = (voice.get("top_negative") or [{}])[0].get("aspect")
            if top in ("qualite_produit", "conformite_annonce", "article_errone_ou_manquant", "emballage"):
                acts.append(Line(f"(Catalogue / gestion des vendeurs) Avis 1-2 étoiles en hausse, surtout sur « {voice['top_negative'][0]['label']} » : "
                                 "contrôler fiches produit, préparation et conditionnement ; approfondir avec l'agent BO2.",
                                 [f"alr:{s8}:{M}:poor", f"mdl:aspects:seller:{s8}:{M}"]))
            elif top == "livraison":
                neg = {r["aspect"]: r["negative"] for r in voice.get("top_negative", [])}
                product = sum(v for a, v in neg.items() if a in ("qualite_produit", "conformite_annonce", "article_errone_ou_manquant", "emballage"))
                if product >= 0.5 * neg["livraison"]:
                    acts.append(Line(f"Critiques partagées entre la livraison ({neg['livraison']} avis) et le produit ou la préparation ({product} avis) : "
                                     "traiter les délais (remise au transporteur, agent BO1) et contrôler préparation et fiches produit (agent BO2).",
                                     [f"alr:{s8}:{M}:poor", f"mdl:aspects:seller:{s8}:{M}"]))
                else:
                    acts.append(Line("Les avis négatifs portent surtout sur la livraison : traiter avec les retards (agent BO1) plutôt que comme un problème de produit.",
                                     [f"alr:{s8}:{M}:poor", f"mdl:aspects:seller:{s8}:{M}"]))
            else:
                acts.append(Line("(Service client) Relire les avis récents du vendeur (agent BO2) pour qualifier la hausse des notes 1-2.", [f"alr:{s8}:{M}:poor"]))
        if not on:
            if any(x["eligible"] for m in metrics for x in det[m]["families"].values()):
                acts.append(Line("Aucune alerte : surveillance standard ; réévaluer à la prochaine décision mensuelle.", [f"alr:{s8}:{M}:{m}" for m in metrics]))
            else:
                acts.append(Line("Volume insuffisant pour une alerte : suivre ce vendeur au niveau de son groupe de pairs.", [f"alr:{s8}:{M}:{m}" for m in metrics]))
        else:
            acts.append(Line("Prendre contact avec le vendeur avant toute sanction : les écarts sont des associations observées, sans cause enregistrée.", []))
        acts.append(Line("Mesurer l'effet de toute action (comparaison avec des vendeurs comparables non contactés) avant de la généraliser.", []))
        return acts

    def _narrative(self, sid, M, metrics, cmp, alerts_on) -> str:
        """Synthèse déterministe en français courant (décimales à virgule, mois en toutes lettres)."""
        fr = lambda x: "n/d" if x is None else f"{100 * float(x):.1f} %".replace(".", ",")  # noqa: E731
        y, mo = M.split("-")
        when = f"fin {list(FR_MONTHS)[int(mo) - 1].replace('fevrier', 'février').replace('aout', 'août').replace('decembre', 'décembre')} {y}"
        ref = "la marketplace" if self.global_ref else "ses pairs"
        if alerts_on:
            parts = []
            for m in dict.fromkeys(m for m, _ in alerts_on):
                o = cmp[m]["observed"]
                fams = " et ".join(f"écart à {ref}" if f == "level" else "dégradation par rapport à son passé" for mm, f in alerts_on if mm == m)
                parts.append(f"{o['label']} à {fr(o['recent_rate'])} sur les 90 derniers jours contre {fr(o['peer_rate'])} pour {ref} ({fams})")
            n = len(dict.fromkeys(m for m, _ in alerts_on))
            return f"Vendeur {sid[:8]}, {when} : {n} indicateur{'s' if n > 1 else ''} en alerte — " + " ; ".join(parts) + "."
        o = cmp[metrics[0]]["observed"]
        return (f"Vendeur {sid[:8]}, {when} : aucune alerte ; {o['label']} à {fr(o['recent_rate'])} sur les 90 derniers jours "
                f"contre {fr(o['peer_rate'])} pour {ref}.")

    def alerts_report(self, month: str | None = None, metric: str | None = None, top_k: int = 15) -> Report:
        self.log = EvidenceLog()
        M = self._month(month)
        p = self.list_alerts(M, metric, top_k)
        ev = [f"alr:list:{M}:{metric or 'all'}"]
        rep = BO3Report(f"Vendeurs à investiguer — décision fin {M}" + (f" ({METRIC_LABEL[metric]})" if metric else ""),
                     section_titles={"estimates": "Alertes (estimations)"})
        elig = ", ".join(f"{METRIC_LABEL[m]} : {n}" for m, n in p["eligible_sellers"].items())
        rep.facts.append(Line(f"Vendeurs ayant assez d'historique pour être évalués (par indicateur) — {elig}.", ev))
        rep.estimates.append(Line(f"{p['n_alerted_sellers']} vendeurs en alerte ({p['n_alerts']} alertes, niveau et tendance confondus).", ev))
        for it in p["listing"]:
            det = "; ".join(f"{METRIC_LABEL[a['metric']]} ({'niveau' if a['family'] == 'level' else 'tendance'}{', sévérité ' + a['severity'] if a.get('severity') else ''}) {pct(a['recent_rate'])} contre {pct(a['baseline'])} "
                            f"(n = {a['recent_known_n']})" for a in it["alerts"])
            rep.estimates.append(Line(f"Vendeur {it['seller_id']} — {cat_label(it['main_category'])} : {det}.", ev))
        rep.actions.append(Line("Ouvrir un audit (agent BO3, --seller) pour chaque vendeur de la liste, en commençant par ceux qui cumulent plusieurs alertes.", ev))
        rep.caveats += ["Alertes calculées avec les seules issues connues à la décision ; seuils réglés sur janv.–mars 2018." if self.trained
                        else "Réglages par défaut (modèle BO3 non entraîné).",
                        "Une alerte signale un écart statistique à investiguer, pas une faute du vendeur."]
        rep.narrative = f"{p['n_alerted_sellers']} vendeurs à investiguer à la fin de {M}."
        rep.meta = {"month": M, "metric": metric}
        return rep

    # ------------------------------------------------------------------ langage naturel
    def _parse(self, q: str) -> dict:
        f = _fold(q)
        month = None
        m = re.search(r"\b(20\d{2})-(\d{2})\b", f)
        if m:
            month = f"{m.group(1)}-{m.group(2)}"
        else:
            m = re.search(r"\b(" + "|".join(FR_MONTHS) + r")\s+(20\d{2})\b", f)
            if m:
                month = f"{m.group(2)}-{FR_MONTHS[m.group(1)]:02d}"
        metric = ("handover" if re.search(r"remise|expedi|transporteur|envoi|preparation", f) else
                  "poor" if re.search(r"avis|note|etoile|satisf", f) else "late" if re.search(r"retard|livraison|delai", f) else None)
        hx = [h for h in HEX.findall(q.lower()) if not re.fullmatch(r"\d+", h)]
        return {"seller": hx[0] if hx else None, "month": month, "metric": metric,
                "list": bool(re.search(r"alerte|degrad|surveill|liste|pire|investig|quels vendeurs|lesquels", f))}

    def ask(self, question: str) -> Report:
        p = self._parse(question)
        if p["seller"]:
            return self.audit(p["seller"], p["month"], p["metric"])
        if p["list"]:
            return self.alerts_report(p["month"], p["metric"])
        if self.llm:
            self.log = EvidenceLog()
            sys_p = ("Tu es l'agent d'audit vendeur REHEARSE. Appelle les outils ; aucun chiffre hors outils. Toute réponse est datée (fin de mois) "
                     "et n'utilise que ce qui était connu à cette date. Distingue faits, comparaisons et alertes ; pas de cause affirmée. Réponds en français.")
            txt = run_tool_loop(self.llm, sys_p, question, self._tools(), self.log)
            rep = BO3Report("Réponse de l'agent BO3")
            rep.narrative = txt or ""
            return rep
        rep = BO3Report("Agent BO3 — question non comprise")
        rep.narrative = ("Donnez un identifiant de vendeur (32 caractères hexadécimaux, ou ses 8 premiers) pour un audit, "
                         "ou demandez « quels vendeurs se dégradent en AAAA-MM ? » pour la liste des alertes.")
        return rep

    def _tools(self) -> list[Tool]:
        sm = {"type": "object", "properties": {"seller_id": {"type": "string"}, "month": {"type": "string", "description": "AAAA-MM (décision à la fin du mois)"}},
              "required": ["seller_id"]}
        smm = {"type": "object", "properties": {**sm["properties"], "metric": {"type": "string", "enum": list(METRICS)}}, "required": ["seller_id"]}
        return [
            Tool("get_seller_profile", "Profil d'activité du vendeur sur les 12 mois avant la décision.", sm, self.get_seller_profile),
            Tool("get_peer_group", "Vendeurs comparables (même activité).", sm, self.get_peer_group),
            Tool("competitive_benchmark", "Rang et centile dans la catégorie et parmi les concurrents directs ; vendeur, médiane et meilleur quart côte à côte.",
                 sm, self.competitive_benchmark),
            Tool("compare_to_peers", "Taux du vendeur (n, IC) vs pairs et marketplace ; observé/attendu.", smm, self.compare_to_peers),
            Tool("detect_deterioration", "Alertes niveau (vs pairs) et tendance (vs son passé).", smm, self.detect_deterioration),
            Tool("list_alerts", "Vendeurs en alerte pour un mois.", {"type": "object", "properties": {"month": {"type": "string"},
                 "metric": {"type": "string", "enum": list(METRICS)}, "top_k": {"type": "integer"}}}, self.list_alerts),
            Tool("marketplace_brief", "Synthèse marketplace du mois : vendeurs en alerte par sévérité, catégories aux taux les plus élevés.",
                 {"type": "object", "properties": {"month": {"type": "string"}}}, self.marketplace_brief),
            Tool("get_seller_geography", "Localisation du vendeur, de ses clients (par État et région) et retards par distance.", sm, self.get_seller_geography),
            Tool("get_seller_orders", "Commandes récentes avec un problème connu à la décision.", sm, self.get_seller_orders),
            Tool("find_strengths", "Indicateurs où le vendeur fait significativement mieux que la référence.", sm, self.find_strengths),
            Tool("get_seller_history", "Évolution mensuelle des taux et alertes jusqu'au mois de décision.", sm, self.get_seller_history),
            Tool("seller_voice", "Aspects critiqués dans les avis des clients du vendeur.", sm, self.seller_voice),
            Tool("multi_seller_exposure", "Commandes multi-vendeurs (non attribuées).", sm, self.multi_seller_exposure),
        ]

    def _llm_narrative(self, rep: Report, instruction: str) -> None:
        payload = json.dumps(to_native({"facts": [vars(x) for x in rep.facts], "estimates": [vars(x) for x in rep.estimates]}), ensure_ascii=False)[:5000]
        try:
            msg = self.llm.chat([
                {"role": "system", "content": "Tu rédiges en français 3 phrases maximum à partir des seules preuves fournies. Aucun chiffre hors preuves. "
                                              "Distingue l'observé des alertes estimées. Pas de cause affirmée, pas de reproche au vendeur."},
                {"role": "user", "content": instruction + "\nPREUVES :\n" + payload}])
            text = (msg.get("content") or "").strip()
        except Exception:
            return
        ok, problems = verify_bo3_narrative(text, self.log)
        if ok and text:
            rep.narrative, rep.narrative_source = text, "llm_verifie"
        else:
            rep.meta["llm_narrative_rejected"] = problems
