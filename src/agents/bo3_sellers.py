"""BO3 — briques de calcul « vendeurs » : DS3.1 (groupes de pairs) et DS3.2 (détection de dégradation).

Règle centrale (pas de fuite temporelle). À une date de décision T (début du mois qui suit le mois M analysé),
l'issue d'une commande n'est utilisée que si elle était CONNUE à T (au plus tard à T) :
  late      retard de livraison : livrée avant T, ou jour promis terminé avant T sans livraison (le retard est alors certain) ;
  poor      avis 1-2 étoiles     : avis publié (review_answer_timestamp) avant T ;
  handover  remise tardive au transporteur : remise avant T, ou jour limite d'expédition terminé avant T sans remise.
La valeur utilisée est toujours la valeur finale ; seule la DATE à laquelle elle devient connue décide si elle entre dans le calcul.
Seules les commandes mono-vendeur entrent dans les taux d'un vendeur (les multi-vendeurs sont rapportées à part, sans attribution).

Fenêtres (en jours, achats) : récente [T-90, T), historique [T-365, T-90), future [T, T+60) — la future ne sert qu'à l'ÉVALUATION.
Le tableau est la base de l'agent BO3 (agents/bo3_agent.py) et des scripts build_seller_panel.py / train_seller_models.py.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.cluster import KMeans
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

# Évite la détection des cœurs physiques de joblib/loky sous Windows (≈ 5 s par processus, sans effet sur les résultats).
os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(os.cpu_count() or 1))

METRICS = {"late": ("is_late", "late_label_eligible"),
           "poor": ("is_poor_review", "poor_review_label_eligible"),
           "handover": ("is_late_handover", "handover_label_eligible")}
METRIC_LABEL = {"late": "retard de livraison", "poor": "avis 1-2 étoiles", "handover": "remise tardive au transporteur"}
RECENT_DAYS, HISTORY_DAYS, FUTURE_DAYS, CUSUM_ODDS = 90, 365, 60, 2.0
LONG_HISTORY_DAYS, EWMA_LAMBDA = 540, 0.2
MIN_PROFILE_ORDERS, MIN_PEER_N = 5, 30

# Mois de décision M (T = début du mois M+1). Découpage chronologique identique au reste du dépôt :
# TRAIN = décisions jusqu'à fin 2017, VALID = 2018-01..03, TEST = 2018-04..06 (la fenêtre future de 60 jours doit finir avant sept. 2018).
SPLIT_MONTHS = {
    "train": [str(p) for p in pd.period_range("2017-03", "2017-12", freq="M")],
    "valid": ["2018-01", "2018-02", "2018-03"],
    "test": ["2018-04", "2018-05", "2018-06"],
}
ALL_DECISION_MONTHS = [str(p) for p in pd.period_range("2017-03", "2018-08", freq="M")]
# Phase 1 : validation glissante sur trois trimestres antérieurs à TEST (docs/ShopInsight_Dossier_Technique.pdf, annexe A).
VALID_FOLDS = {"2017Q3": ["2017-07", "2017-08", "2017-09"], "2017Q4": ["2017-10", "2017-11", "2017-12"],
               "2018Q1": ["2018-01", "2018-02", "2018-03"]}


def fold_of(month: str) -> str | None:
    return next((k for k, v in VALID_FOLDS.items() if month in v), None)


def decision_date(month: str) -> pd.Timestamp:
    """Date de décision pour le mois M : minuit au début du mois suivant (tout ce qui est connu « fin M »)."""
    return (pd.Period(month, "M") + 1).start_time


def split_of(month: str) -> str:
    for k, v in SPLIT_MONTHS.items():
        if month in v:
            return k
    return "hors_evaluation"


def wilson(x: float, n: float, z: float = 1.96) -> tuple[float | None, float | None]:
    if not n:
        return None, None
    p = x / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return float(max(0.0, c - h)), float(min(1.0, c + h))


def bh(p: np.ndarray) -> np.ndarray:
    """q-valeurs de Benjamini-Hochberg (NaN conservés)."""
    p = np.asarray(p, float)
    q = np.full_like(p, np.nan)
    ok = ~np.isnan(p)
    if ok.sum() == 0:
        return q
    pv = p[ok]
    order = np.argsort(pv)
    m = len(pv)
    ranked = pv[order] * m / np.arange(1, m + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1].clip(0, 1)
    out = np.empty(m)
    out[order] = ranked
    q[ok] = out
    return q


# --------------------------------------------------------------------------------------
# Données vendeurs « à date »
# --------------------------------------------------------------------------------------
class SellerData:
    """Commandes mono-vendeur avec, pour chaque indicateur, la valeur finale `y_<m>` et la date `k_<m>` à laquelle elle devient connue."""

    def __init__(self, orders: pd.DataFrame, expected: pd.DataFrame | None = None) -> None:
        o = orders.reset_index(drop=True)
        single = o["single_seller_id"].notna()
        if "seller_count" in o.columns:
            single &= pd.to_numeric(o["seller_count"], errors="coerce").fillna(1).eq(1)
        o = o.loc[single].reset_index(drop=True)
        dt = lambda c: pd.to_datetime(o[c], errors="coerce", format="mixed") if c in o.columns else pd.Series(pd.NaT, index=o.index)  # noqa: E731
        num = lambda c: pd.to_numeric(o[c], errors="coerce") if c in o.columns else pd.Series(np.nan, index=o.index)  # noqa: E731
        ts = dt("order_purchase_timestamp")
        est = dt("order_estimated_delivery_date")
        d = pd.DataFrame({
            "order_id": o["order_id"].astype(str).to_numpy(), "seller_id": o["single_seller_id"].astype(str).to_numpy(), "ts": ts,
            "state": o["customer_state"].astype(object) if "customer_state" in o.columns else None,
            "category": o["primary_category"].astype(object) if "primary_category" in o.columns else "unknown",
            "seller_state": o["seller_state"].astype(object) if "seller_state" in o.columns else None,
            "price": num("item_price_total"), "freight": num("freight_total"), "weight": num("product_weight_mean_g"),
            # position du client (centroïde du préfixe postal : déjà agrégée, jamais l'adresse) — cartes géographiques descriptives
            "lat": num("customer_lat"), "lng": num("customer_lng"),
            "promised": (est.dt.normalize() - ts.dt.normalize()).dt.days.astype(float),
            "late_days": num("late_days"), "handover_delay_days": num("handover_delay_days"), "review_score": num("review_score"),
        })
        elig = lambda c: o[c].astype("boolean").fillna(False).astype(bool).to_numpy() if c in o.columns else np.zeros(len(o), bool)  # noqa: E731
        # Retard : connu à la livraison, ou dès la fin du jour promis sans livraison.
        delivered, est_end = dt("order_delivered_customer_date"), est.dt.normalize() + pd.Timedelta(days=1)
        k_late = delivered.where(delivered < est_end, est_end)
        # Remise au transporteur : connue à la remise, ou dès la fin du jour limite sans remise.
        carrier, lim_end = dt("order_delivered_carrier_date"), dt("shipping_limit_max").dt.normalize() + pd.Timedelta(days=1)
        k_hand = carrier.where(carrier < lim_end, lim_end)
        known = {"late": k_late, "poor": dt("review_answer_timestamp"), "handover": k_hand}
        d["t_delivered"], d["t_carrier"] = delivered, carrier  # pour n'afficher une durée de retard que si l'événement a eu lieu avant T
        self.available: dict[str, bool] = {}
        for m, (col, el) in METRICS.items():
            e = elig(el)
            y = num(col).where(e)
            d[f"y_{m}"] = y
            d[f"k_{m}"] = known[m].where(e & y.notna().to_numpy())
            self.available[m] = bool(y.notna().any())
        if expected is not None and len(expected):
            ex = expected.set_index("order_id")
            for m in ("late", "poor"):
                if f"e_{m}" in ex.columns:
                    d[f"e_{m}"] = d["order_id"].map(ex[f"e_{m}"]).astype(float)
        self.d = d
        self.has_expected = {m: f"e_{m}" in d.columns and d[f"e_{m}"].notna().any() for m in ("late", "poor")}

    # ------------------------------------------------------------------ comptages
    def counts(self, T: pd.Timestamp, metric: str) -> pd.DataFrame:
        """Par vendeur : fenêtres récente / historique (issues CONNUES avant T) et future (issues finales, évaluation uniquement)."""
        d = self.d
        ts, y, k = d["ts"], d[f"y_{metric}"], d[f"k_{metric}"]
        rec = (ts >= T - pd.Timedelta(days=RECENT_DAYS)) & (ts < T)
        hist = (ts >= T - pd.Timedelta(days=HISTORY_DAYS)) & (ts < T - pd.Timedelta(days=RECENT_DAYS))
        hist2 = (ts >= T - pd.Timedelta(days=LONG_HISTORY_DAYS)) & (ts < T - pd.Timedelta(days=RECENT_DAYS))
        fut = (ts >= T) & (ts < T + pd.Timedelta(days=FUTURE_DAYS))
        known = y.notna() & (k <= T)
        yv = y.fillna(0)
        f = pd.DataFrame({"seller_id": d["seller_id"],
                          "n_orders_year": (rec | hist).astype(int), "n_orders_recent": rec.astype(int),
                          "rec_n": (rec & known).astype(int), "rec_x": (rec & known) * yv,
                          "hist_n": (hist & known).astype(int), "hist_x": (hist & known) * yv,
                          "hist2_n": (hist2 & known).astype(int), "hist2_x": (hist2 & known) * yv,
                          "fut_n": (fut & y.notna()).astype(int), "fut_x": (fut & y.notna()) * yv})
        e_col = f"e_{metric}"
        if e_col in d.columns:
            e = d[e_col]
            ok = rec & known & e.notna()
            f["rec_ne"], f["rec_xe"] = ok.astype(int), ok * yv
            f["rec_e"], f["rec_v"] = ok * e.fillna(0), ok * (e * (1 - e)).fillna(0)
        f = f[(rec | hist2 | fut).to_numpy()]
        g = f.groupby("seller_id", sort=True).sum()
        g["year_n"], g["year_x"] = g["rec_n"] + g["hist_n"], g["rec_x"] + g["hist_x"]
        return g

    def known_orders(self, T: pd.Timestamp, seller_id: str, metric: str, days: int = RECENT_DAYS) -> pd.DataFrame:
        d = self.d
        m = (d["seller_id"] == seller_id) & (d["ts"] >= T - pd.Timedelta(days=days)) & (d["ts"] < T) & d[f"y_{metric}"].notna() & (d[f"k_{metric}"] <= T)
        return d.loc[m]

    def cusum(self, T: pd.Timestamp, metric: str, p0: pd.Series, odds: float = CUSUM_ODDS) -> pd.Series:
        """CUSUM de Bernoulli sur les commandes récentes (issues connues avant T), dans l'ordre d'achat ;
        H0 : taux = p0 (historique du vendeur rétréci vers ses pairs) ; H1 : cote multipliée par `odds`. Retourne la statistique finale."""
        d = self.d
        m = d["seller_id"].isin(p0.index) & (d["ts"] >= T - pd.Timedelta(days=RECENT_DAYS)) & (d["ts"] < T) & d[f"y_{metric}"].notna() & (d[f"k_{metric}"] <= T)
        sub = d.loc[m, ["seller_id", "ts", f"y_{metric}"]].sort_values(["seller_id", "ts"])
        out = {}
        for sid, g in sub.groupby("seller_id", sort=False):
            p = float(np.clip(p0[sid], 1e-3, 0.95))
            p1 = odds * p / (1 - p + odds * p)
            w1, w0 = np.log(p1 / p), np.log((1 - p1) / (1 - p))
            s = 0.0
            for v in g[f"y_{metric}"].to_numpy():
                s = max(0.0, s + (w1 if v >= 0.5 else w0))
            out[sid] = s
        return pd.Series(out, dtype=float).reindex(p0.index).fillna(0.0)

    def sequence_stats(self, T: pd.Timestamp, metric: str, p0: pd.Series) -> pd.DataFrame:
        """Un seul passage sur les commandes récentes (issues connues à T, ordre d'achat) de chaque vendeur de p0 :
        CUSUM de Bernoulli pour des cotes ×1,5, ×2, ×3 et EWMA (λ = 0,2) standardisé, tous vs p0 (historique rétréci)."""
        d = self.d
        m = d["seller_id"].isin(p0.index) & (d["ts"] >= T - pd.Timedelta(days=RECENT_DAYS)) & (d["ts"] < T) & d[f"y_{metric}"].notna() & (d[f"k_{metric}"] <= T)
        sub = d.loc[m, ["seller_id", "ts", f"y_{metric}"]].sort_values(["seller_id", "ts"])
        lam, rows = EWMA_LAMBDA, {}
        for sid, g in sub.groupby("seller_id", sort=False):
            p = float(np.clip(p0[sid], 1e-3, 0.95))
            ws = []
            for odds in (1.5, 2.0, 3.0):
                p1 = odds * p / (1 - p + odds * p)
                ws.append((np.log(p1 / p), np.log((1 - p1) / (1 - p))))
            cs = [0.0, 0.0, 0.0]
            z, t = p, 0
            for v in g[f"y_{metric}"].to_numpy():
                hit = v >= 0.5
                cs = [max(0.0, c_ + (w1 if hit else w0)) for c_, (w1, w0) in zip(cs, ws)]
                z = lam * float(hit) + (1 - lam) * z
                t += 1
            sd_ = np.sqrt(p * (1 - p) * lam / (2 - lam) * (1 - (1 - lam) ** (2 * t))) if t else np.nan
            rows[sid] = (cs[0], cs[1], cs[2], (z - p) / sd_ if t and sd_ > 0 else 0.0)
        out = pd.DataFrame.from_dict(rows, orient="index", columns=["cusum_15", "cusum", "cusum_3", "ewma_z"])
        return out.reindex(p0.index).fillna(0.0)

    # ------------------------------------------------------------------ profil (aucune issue utilisée)
    def profile(self, T: pd.Timestamp, min_orders: int = MIN_PROFILE_ORDERS) -> pd.DataFrame:
        d = self.d
        before = d[d["ts"] < T]
        win = before[before["ts"] >= T - pd.Timedelta(days=HISTORY_DAYS)]
        if win.empty:
            return pd.DataFrame()
        top_cats = before["category"].value_counts().index[:12]
        top_states = before["state"].value_counts().index[:3] if before["state"].notna().any() else []
        sid = win["seller_id"]
        cat = win["category"].where(win["category"].isin(top_cats), "autre")
        cats = pd.crosstab(sid, cat, normalize="index").add_prefix("cat_")
        st = win["state"].where(win["state"].isin(top_states), "autre")
        dest = pd.crosstab(sid, st, normalize="index").add_prefix("dest_")
        g = win.groupby("seller_id")
        prof = pd.DataFrame({"n_orders": g.size()})
        prof["log_orders"] = np.log1p(prof["n_orders"])
        prof["log_price"] = np.log1p(win["price"]).groupby(sid).median()
        prof["freight_ratio"] = (win["freight"] / win["price"].clip(lower=1)).groupby(sid).median()
        prof["log_weight"] = np.log1p(win["weight"]).groupby(sid).mean()
        prof["promised_days"] = g["promised"].mean()
        if win["seller_state"].notna().any():
            prof["same_state"] = (win["state"] == win["seller_state"]).groupby(sid).mean()
            prof["seller_state"] = g["seller_state"].first()
        else:
            prof["seller_state"] = None
        prof["main_category"] = win.groupby("seller_id")["category"].agg(lambda s: s.value_counts().index[0])
        prof["first_order"], prof["last_order"] = g["ts"].min(), g["ts"].max()
        prof = prof.join(cats).join(dest)
        return prof[prof["n_orders"] >= min_orders].sort_index()


# --------------------------------------------------------------------------------------
# DS3.1 — groupes de pairs
# --------------------------------------------------------------------------------------
SIZE_COLS = ["log_orders", "log_price", "freight_ratio", "log_weight", "promised_days"]


def feature_matrix(prof: pd.DataFrame) -> np.ndarray:
    """Variables standardisées ; chaque bloc (catégories, destinations, taille/prix/délai) pèse autant dans la distance."""
    blocks = [[c for c in prof.columns if c.startswith("cat_")],
              [c for c in prof.columns if c.startswith("dest_")] + (["same_state"] if "same_state" in prof.columns else []),
              [c for c in SIZE_COLS if c in prof.columns]]
    parts = []
    for cols in blocks:
        if not cols:
            continue
        X = prof[cols].astype(float)
        X = X.fillna(X.median()).fillna(0.0)
        Z = StandardScaler().fit_transform(X.to_numpy()) if len(X) > 1 else np.zeros(X.shape)
        parts.append(np.nan_to_num(Z) / np.sqrt(len(cols)))
    return np.hstack(parts) if parts else np.zeros((len(prof), 1))


@dataclass(frozen=True)
class PeerConfig:
    method: str = "knn"     # global | category | knn | cluster
    k: int = 20             # knn : nombre de pairs
    n_clusters: int = 8     # cluster : nombre de groupes

    @property
    def label(self) -> str:
        return {"global": "toute la marketplace", "category": "même catégorie principale",
                "knn": f"{self.k} vendeurs les plus proches (k plus proches voisins)", "cluster": f"groupe KMeans ({self.n_clusters} groupes)"}[self.method]

    @property
    def key(self) -> str:
        return {"knn": f"knn_k{self.k}", "cluster": f"cluster_{self.n_clusters}"}.get(self.method, self.method)

    def to_dict(self) -> dict:
        return asdict(self)


class PeerModel:
    def __init__(self, cfg: PeerConfig, seed: int = 0) -> None:
        self.cfg, self.seed = cfg, seed

    def fit(self, prof: pd.DataFrame) -> "PeerModel":
        self.index = prof.index
        self.prof = prof
        n = len(prof)
        self.Z = feature_matrix(prof)
        m = self.cfg.method
        self.nb = self.labels = None
        if m == "knn":
            kk = min(self.cfg.k + 1, n)
            dist, ind = NearestNeighbors(n_neighbors=kk).fit(self.Z).kneighbors(self.Z)
            nb = np.empty((n, kk - 1), dtype=int)
            nd = np.empty((n, kk - 1))
            for i in range(n):
                keep = ind[i] != i
                row, rd = ind[i][keep][: kk - 1], dist[i][keep][: kk - 1]
                if len(row) < kk - 1:  # doublons exacts : complète avec le dernier voisin
                    row = np.pad(row, (0, kk - 1 - len(row)), mode="edge")
                    rd = np.pad(rd, (0, kk - 1 - len(rd)), mode="edge")
                nb[i], nd[i] = row, rd
            self.nb, self.nb_dist = nb, nd
        elif m == "cluster":
            k = max(1, min(self.cfg.n_clusters, n))
            self.labels = KMeans(n_clusters=k, n_init=4, random_state=self.seed).fit(self.Z).labels_
        elif m == "category":
            self.labels = pd.factorize(prof["main_category"])[0]
        else:
            self.labels = np.zeros(n, dtype=int)
        return self

    def pooled(self, n: np.ndarray, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Taux groupé des pairs (le vendeur lui-même exclu) et effectif d'issues connues des pairs."""
        n, x = np.asarray(n, float), np.asarray(x, float)
        if self.nb is not None:
            npeer, xpeer = n[self.nb].sum(1), x[self.nb].sum(1)
        else:
            gn = np.bincount(self.labels, weights=n)
            gx = np.bincount(self.labels, weights=x)
            npeer, xpeer = gn[self.labels] - n, gx[self.labels] - x
        with np.errstate(invalid="ignore", divide="ignore"):
            p = np.where(npeer > 0, xpeer / npeer, np.nan)
        return p, npeer

    def peers_of(self, seller_id: str, top: int = 20) -> list[tuple[str, float]]:
        i = self.index.get_loc(seller_id)
        if self.nb is not None:
            return [(self.index[j], float(dd)) for j, dd in zip(self.nb[i][:top], self.nb_dist[i][:top])]
        same = np.flatnonzero(self.labels == self.labels[i])
        same = same[same != i]
        dist = np.linalg.norm(self.Z[same] - self.Z[i], axis=1)
        o = np.argsort(dist)[:top]
        return [(self.index[same[j]], float(dist[j])) for j in o]

    def group_sets(self) -> dict[str, frozenset]:
        """Pour la stabilité : ensemble des pairs (knn) ou identifiant de groupe, par vendeur."""
        if self.nb is not None:
            return {s: frozenset(self.index[self.nb[i]]) for i, s in enumerate(self.index)}
        return {s: int(self.labels[i]) for i, s in enumerate(self.index)}


# --------------------------------------------------------------------------------------
# DS3.2 — statistiques de dégradation pour un mois et un indicateur
# --------------------------------------------------------------------------------------
@dataclass
class DetectionParams:
    min_history: int = 50      # issues connues sur 12 mois avant une alerte (proposition du plan projet ; réglé sur VALID)
    min_recent: int = 10       # issues connues sur les 90 derniers jours
    prior_strength: float = 20.0  # poids (en commandes) de l'a priori « pairs » pour rétrécir les petits vendeurs


def month_frame(sd: SellerData, month: str, metric: str, cfg: PeerConfig, params: DetectionParams,
                cache: dict | None = None, with_cusum: bool = True) -> tuple[pd.DataFrame, PeerModel | None]:
    """Une ligne par vendeur ayant un profil à la date T : comptages, taux des pairs, statistiques brutes des détecteurs,
    et (colonnes eval_*) la vérité future pour l'évaluation. Aucun seuil n'est appliqué ici."""
    cache = {} if cache is None else cache
    T = decision_date(month)
    key_p = ("profile", month)
    if key_p not in cache:
        cache[key_p] = sd.profile(T)
    prof = cache[key_p]
    if prof.empty:
        return pd.DataFrame(), None
    key_m = ("peers", month, cfg)
    if key_m not in cache:
        cache[key_m] = PeerModel(cfg).fit(prof)
    pm = cache[key_m]
    key_c = ("counts", month, metric)
    if key_c not in cache:
        cache[key_c] = sd.counts(T, metric)
    cnt = cache[key_c].reindex(prof.index).fillna(0)
    # Colonnes calculées en numpy puis assemblées en une fois (insérer ~40 colonnes une à une coûte cher avec pandas).
    c = {k: cnt[k].to_numpy(dtype=float) for k in cnt.columns}
    allc = cache[key_c]
    G = float(allc["year_x"].sum() / allc["year_n"].sum()) if allc["year_n"].sum() else np.nan
    p_peer, n_peer = pm.pooled(c["year_n"], c["year_x"])
    fallback = ~(n_peer >= MIN_PEER_N) | np.isnan(p_peer)
    pp = np.clip(np.where(fallback, G, p_peer), 1e-3, 0.999)
    s = params.prior_strength
    rn, rx = c["rec_n"], c["rec_x"]
    ph = (c["hist_x"] + s * pp) / (c["hist_n"] + s)
    has = rn > 0
    c.update({"p_global": np.full(len(pp), G), "p_peer": pp, "n_peer": n_peer, "peer_fallback": fallback, "p_hist": ph,
              "p_shrunk": (c["year_x"] + s * pp) / (c["year_n"] + s)})
    with np.errstate(invalid="ignore", divide="ignore"):
        c["rec_rate"] = np.where(has, rx / np.maximum(rn, 1), np.nan)
        c["year_rate"] = np.where(c["year_n"] > 0, c["year_x"] / np.maximum(c["year_n"], 1), np.nan)
    c["level_p"] = np.where(has, stats.binom.sf(rx - 1, np.maximum(rn, 1), pp), np.nan)
    c["trend_p"] = np.where(has, stats.binom.sf(rx - 1, np.maximum(rn, 1), ph), np.nan)
    c["level_post"] = stats.beta.sf(pp, s * pp + rx, s * (1 - pp) + rn - rx)
    c["eligible"] = (c["year_n"] >= params.min_history) & (rn >= params.min_recent)
    # Tendance, variantes Phase 1 : historique long (T-540 à T-90 j) et comparaison bayésienne à deux échantillons.
    ph2 = (c["hist2_x"] + s * pp) / (c["hist2_n"] + s)
    c["p_hist_long"] = ph2
    c["trend_long_p"] = np.where(has, stats.binom.sf(rx - 1, np.maximum(rn, 1), ph2), np.nan)
    a1, b1 = 1 + rx, 1 + rn - rx
    a2, b2 = s * pp + c["hist_x"], s * (1 - pp) + c["hist_n"] - c["hist_x"]
    m1, m2 = a1 / (a1 + b1), a2 / (a2 + b2)
    v1 = a1 * b1 / ((a1 + b1) ** 2 * (a1 + b1 + 1))
    v2 = a2 * b2 / ((a2 + b2) ** 2 * (a2 + b2 + 1))
    c["trend_post2"] = np.where(has, stats.norm.cdf((m1 - m2) / np.sqrt(v1 + v2)), np.nan)
    # Points forts : 12 mois d'issues connues nettement SOUS la référence (test unilatéral inférieur).
    c["strength_p"] = np.where(c["year_n"] > 0, stats.binom.cdf(c["year_x"], np.maximum(c["year_n"], 1), pp), np.nan)
    if with_cusum:
        idx = prof.index[rn >= params.min_recent]
        seq = (sd.sequence_stats(T, metric, pd.Series(ph, index=prof.index)[idx]).reindex(prof.index).fillna(0.0)
               if len(idx) else pd.DataFrame(0.0, index=prof.index, columns=["cusum_15", "cusum", "cusum_3", "ewma_z"]))
        for col in seq.columns:
            c[col] = seq[col].to_numpy()
    # Observé / attendu (modèle entraîné sur TRAIN seulement), recalé sur le niveau de la marketplace à T.
    if "rec_e" in c and allc["rec_e"].sum() > 0:
        kT = float(allc["rec_xe"].sum() / allc["rec_e"].sum())
        E, V = c["rec_e"] * kT, c["rec_v"] * kT
        with np.errstate(invalid="ignore", divide="ignore"):
            c["oe_ratio"] = np.where(E > 0, c["rec_xe"] / np.where(E > 0, E, 1), np.nan)
            c["oe_z"] = np.where(V > 0, (c["rec_xe"] - E) / np.sqrt(np.where(V > 0, V, 1)), np.nan)
        c["oe_expected"], c["oe_calibration"] = E, np.full(len(pp), kT)
    # Vérité future (ÉVALUATION UNIQUEMENT — jamais montrée par l'agent)
    fn, fx = c["fut_n"], c["fut_x"]
    ev = fn >= 5
    c["eval_evaluable"] = ev
    c["eval_truth_level"] = np.where(ev, stats.binom.sf(fx - 1, np.maximum(fn, 1), pp) < 0.05, False)
    c["eval_truth_trend"] = np.where(ev, stats.binom.sf(fx - 1, np.maximum(fn, 1), ph) < 0.05, False)
    ev_s = fn >= 10
    c["eval_evaluable_strength"] = ev_s
    with np.errstate(invalid="ignore", divide="ignore"):
        c["eval_truth_strength"] = np.where(ev_s, fx / np.maximum(fn, 1) <= pp, False)
    c["month"], c["metric"], c["split"] = month, metric, split_of(month)
    c["main_category"], c["n_orders_profile"] = prof["main_category"].to_numpy(), prof["n_orders"].to_numpy()
    seg = describe_segments(prof)
    for col in seg.columns:
        c[col] = seg[col].to_numpy()
    f = pd.DataFrame(c, index=prof.index)
    f.index.name = "seller_id"
    return f, pm


# --------------------------------------------------------------------------------------
# Détecteurs (seuils appliqués à month_frame) et évaluation
# --------------------------------------------------------------------------------------
DETECTORS = {
    # nom : (famille, description, fonction d'alerte, grille de réglage)
    "regle_pairs": ("level", "taux récent > facteur × taux de référence (règle simple)",
                    lambda f, p: f["rec_rate"] > p["factor"] * f["p_peer"], [{"factor": v} for v in (1.5, 2.0, 3.0)]),
    "binomial_bh_pairs": ("level", "test binomial unilatéral vs taux de référence, correction de Benjamini-Hochberg",
                          lambda f, p: (f["level_q"] < p["alpha"]) & (f["rec_rate"] > f["p_peer"]), [{"alpha": v} for v in (0.05, 0.10, 0.20)]),
    "beta_binomial_pairs": ("level", "a posteriori bêta-binomial (a priori = référence) : P(taux > référence) > seuil",
                            lambda f, p: f["level_post"] > p["tau"], [{"tau": v} for v in (0.90, 0.95, 0.99)]),
    "observe_attendu": ("level", "observé / attendu (modèle entraîné sur TRAIN, recalé sur la marketplace à T), score z",
                        lambda f, p: f["oe_z"] > p["z"] if "oe_z" in f.columns else pd.Series(False, index=f.index), [{"z": v} for v in (2.0, 2.5, 3.0)]),
    "regle_historique": ("trend", "taux récent > facteur × historique du vendeur (règle simple)",
                         lambda f, p: f["rec_rate"] > p["factor"] * f["p_hist"], [{"factor": v} for v in (1.5, 2.0, 3.0)]),
    "binomial_bh_historique": ("trend", "test binomial unilatéral vs historique rétréci du vendeur, correction de Benjamini-Hochberg",
                               lambda f, p: (f["trend_q"] < p["alpha"]) & (f["rec_rate"] > f["p_hist"]), [{"alpha": v} for v in (0.05, 0.10, 0.20)]),
    "cusum_historique": ("trend", "CUSUM de Bernoulli (cote ×2) sur les 90 derniers jours vs historique",
                         lambda f, p: f["cusum"] > p["h"], [{"h": v} for v in (2.0, 3.0, 4.0, 5.0)]),
    # --- candidats Phase 1 (docs/ShopInsight_Dossier_Technique.pdf, annexe A)
    "cusum_historique_x1.5": ("trend", "CUSUM de Bernoulli (cote ×1,5) sur les 90 derniers jours vs historique",
                              lambda f, p: f["cusum_15"] > p["h"], [{"h": v} for v in (2.0, 3.0, 4.0, 5.0)]),
    "cusum_historique_x3": ("trend", "CUSUM de Bernoulli (cote ×3) sur les 90 derniers jours vs historique",
                            lambda f, p: f["cusum_3"] > p["h"], [{"h": v} for v in (2.0, 3.0, 4.0, 5.0)]),
    "binomial_bh_historique_long": ("trend", "test binomial vs historique long (achats T-540 à T-90 j), correction de Benjamini-Hochberg",
                                    lambda f, p: (f["trend_long_q"] < p["alpha"]) & (f["rec_rate"] > f["p_hist_long"]), [{"alpha": v} for v in (0.05, 0.10, 0.20)]),
    "bayes_historique": ("trend", "comparaison bayésienne : P(taux récent > taux historique du vendeur) > seuil",
                         lambda f, p: f["trend_post2"] > p["tau"], [{"tau": v} for v in (0.95, 0.99, 0.995)]),
    "ewma_historique": ("trend", "EWMA (λ = 0,2) des issues récentes vs historique, écart standardisé > L",
                        lambda f, p: f["ewma_z"] > p["L"], [{"L": v} for v in (2.0, 2.5, 3.0)]),
}
# Porte d'éligibilité propre à un détecteur (par défaut : eligible pour « niveau », eligible_trend pour « tendance »).
GATE = {"binomial_bh_historique_long": "eligible_trend_long"}
SEVERITY_RULE = "élevée : q < 0,001 et alerte le mois précédent ; moyenne : q < 0,01 ou alerte le mois précédent ; faible : autres alertes"


def apply_gate(frames: pd.DataFrame, min_history: int, min_recent: int) -> pd.DataFrame:
    """Applique le seuil de volume et recalcule les q-valeurs BH parmi les vendeurs éligibles (par mois et indicateur)."""
    f = frames.copy()
    f["eligible"] = (f["year_n"] >= min_history) & (f["rec_n"] >= min_recent)
    # Tendance : il faut un vrai historique propre au vendeur (sinon « historique » = taux des pairs).
    f["eligible_trend"] = f["eligible"] & (f["hist_n"] >= max(min_recent, min_history // 2))
    if "hist2_n" in f.columns:
        f["eligible_trend_long"] = f["eligible"] & (f["hist2_n"] >= max(min_recent, min_history // 2))
    f["eligible_strength"] = f["year_n"] >= min_history
    f["level_q"], f["trend_q"], f["trend_long_q"], f["strength_q"] = np.nan, np.nan, np.nan, np.nan
    for gate, pcol, qcol in (("eligible", "level_p", "level_q"), ("eligible_trend", "trend_p", "trend_q"),
                             ("eligible_trend_long", "trend_long_p", "trend_long_q"), ("eligible_strength", "strength_p", "strength_q")):
        if gate not in f.columns or pcol not in f.columns:
            continue
        for _, idx in f[f[gate]].groupby(["month", "metric"]).groups.items():
            f.loc[idx, qcol] = bh(f.loc[idx, pcol].to_numpy())
    return f


def alerts(f: pd.DataFrame, detector: str, params: dict) -> pd.Series:
    fam, _, fn, _ = DETECTORS[detector]
    return (f[gate_of(detector, f)] & fn(f, params).fillna(False).astype(bool)).astype(bool)


def gate_of(detector: str, f: pd.DataFrame | None = None) -> str:
    fam = DETECTORS[detector][0]
    g = GATE.get(detector, "eligible_trend" if fam == "trend" else "eligible")
    return g if f is None or g in f.columns else "eligible"


def strengths(f: pd.DataFrame, alpha: float = 0.05) -> pd.Series:
    """Point fort : 12 mois d'issues connues significativement SOUS la référence (BH q < alpha)."""
    return (f["eligible_strength"] & (f["strength_q"] < alpha) & (f["year_rate"] < f["p_peer"])).fillna(False).astype(bool)


def previous_alerts(f: pd.DataFrame, alert: pd.Series) -> pd.Series:
    """Vrai si le même vendeur × indicateur était en alerte au mois de décision précédent (f contient plusieurs mois)."""
    keys = set(zip(f.loc[alert, "seller_id"], f.loc[alert, "metric"], f.loc[alert, "month"]))
    prev = [str(pd.Period(m, "M") - 1) for m in f["month"]]
    return pd.Series([(s_, m_, pm) in keys for s_, m_, pm in zip(f["seller_id"], f["metric"], prev)], index=f.index)


def severity(level_q: float | None, prev_alert: bool) -> str:
    """Règle fixe (non réglée) : voir SEVERITY_RULE."""
    q = 1.0 if level_q is None or not np.isfinite(level_q) else float(level_q)
    if q < 0.001 and prev_alert:
        return "élevée"
    if q < 0.01 or prev_alert:
        return "moyenne"
    return "faible"


SE_STATES, S_STATES = {"SP", "RJ", "MG", "ES"}, {"PR", "SC", "RS"}


def describe_segments(prof: pd.DataFrame) -> pd.DataFrame:
    """Segments DESCRIPTIFS (étiquettes, pas des références prédictives) : volume sur 12 mois (terciles à T), région du vendeur."""
    n = prof["n_orders"].astype(float)
    q1, q2 = (n.quantile([1 / 3, 2 / 3]).tolist() if len(n) >= 3 else (n.min(), n.max()))
    vol = np.where(n <= q1, "petit volume", np.where(n <= q2, "volume moyen", "grand volume"))
    st = prof["seller_state"] if "seller_state" in prof.columns else pd.Series(None, index=prof.index)
    reg = np.where(st.isin(SE_STATES), "Sudeste", np.where(st.isin(S_STATES), "Sul", np.where(st.notna(), "autres régions", "inconnue")))
    return pd.DataFrame({"segment_volume": vol, "segment_region": reg}, index=prof.index)


def detector_score(f: pd.DataFrame, detector: str) -> pd.Series:
    """Score continu pour classer les alertes (plus haut = plus préoccupant)."""
    return {"regle_pairs": f["rec_rate"] / f["p_peer"], "binomial_bh_pairs": -np.log10(f["level_q"].clip(lower=1e-12)),
            "beta_binomial_pairs": f["level_post"], "observe_attendu": f.get("oe_z", pd.Series(np.nan, index=f.index)),
            "regle_historique": f["rec_rate"] / f["p_hist"], "binomial_bh_historique": -np.log10(f["trend_q"].clip(lower=1e-12)),
            "cusum_historique": f.get("cusum", pd.Series(0.0, index=f.index)),
            "cusum_historique_x1.5": f.get("cusum_15", pd.Series(0.0, index=f.index)),
            "cusum_historique_x3": f.get("cusum_3", pd.Series(0.0, index=f.index)),
            "binomial_bh_historique_long": -np.log10(f.get("trend_long_q", pd.Series(1.0, index=f.index)).clip(lower=1e-12)),
            "bayes_historique": f.get("trend_post2", pd.Series(np.nan, index=f.index)),
            "ewma_historique": f.get("ewma_z", pd.Series(np.nan, index=f.index))}[detector]


def evaluate(f: pd.DataFrame, alert: pd.Series, family: str, gate_col: str | None = None) -> dict:
    truth = f[f"eval_truth_{family}"].astype(bool)
    gate = f[gate_col] if gate_col else (f["eligible_trend"] if family == "trend" and "eligible_trend" in f.columns else f["eligible"])
    ev = f["eval_evaluable"].astype(bool) & gate
    tp = int((alert & truth & ev).sum())
    fp = int((alert & ~truth & ev).sum())
    fn = int((~alert & truth & ev).sum())
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    f1 = 2 * prec * rec / (prec + rec) if prec and rec else 0.0
    base = float(truth[ev].mean()) if ev.any() else None
    n_months = max(1, f["month"].nunique())
    return {"alerts": int(alert.sum()), "alerts_per_month": round(float(alert.sum()) / n_months, 2), "eligible_cases": int(gate.sum()),
            "alert_share_of_eligible": round(float(alert.sum()) / max(1, int(gate.sum())), 4),
            "evaluable_cases": int(ev.sum()), "tp": tp, "fp": fp, "fn": fn,
            "precision": None if prec is None else round(prec, 4), "recall": None if rec is None else round(rec, 4), "f1": round(f1, 4),
            "truth_base_rate": None if base is None else round(base, 4),
            "lift": None if (prec is None or not base) else round(prec / base, 2)}


def peer_prediction_loss(f: pd.DataFrame, pred_col: str) -> dict:
    """DS3.1 : perte log et Brier (par commande) quand `pred_col` prédit le taux futur du vendeur (issues finales des 60 jours suivants)."""
    g = f[f["fut_n"] >= 5]
    if g.empty:
        return {"n_sellers": 0, "n_orders": 0, "logloss": None, "brier": None}
    p = g[pred_col].clip(1e-3, 0.999).to_numpy()
    n, x = g["fut_n"].to_numpy(), g["fut_x"].to_numpy()
    ll = -(x * np.log(p) + (n - x) * np.log(1 - p)).sum() / n.sum()
    br = (x * (1 - p) ** 2 + (n - x) * p ** 2).sum() / n.sum()
    return {"n_sellers": int(len(g)), "n_orders": int(n.sum()), "logloss": round(float(ll), 5), "brier": round(float(br), 5)}


def inject(sd: SellerData, sellers: list[str], metric: str, start: pd.Timestamp, delta: float, seed: int = 0) -> SellerData:
    """Dégradation SIMULÉE : pour les commandes de `sellers` achetées après `start`, des issues 0 deviennent 1
    de sorte que le taux augmente d'environ `delta` (points). Sert à mesurer rappel et délai de détection."""
    rng = np.random.default_rng(seed)
    new = SellerData.__new__(SellerData)
    new.__dict__.update(sd.__dict__)
    d = sd.d.copy()
    col = f"y_{metric}"
    for s_ in sellers:
        base_m = (d["seller_id"] == s_) & (d["ts"] < start) & d[col].notna()
        base = float(d.loc[base_m, col].mean()) if base_m.any() else 0.05
        prob = min(1.0, delta / max(1e-6, 1 - base))
        m = (d["seller_id"] == s_) & (d["ts"] >= start) & (d[col] == 0)
        flip = m & (rng.random(len(d)) < prob)
        d.loc[flip, col] = 1.0
    new.d = d
    return new


# --------------------------------------------------------------------------------------
# Positionnement concurrentiel (DESCRIPTIF) : rang dans la catégorie et parmi les concurrents directs
# --------------------------------------------------------------------------------------
# La détection reste calibrée sur la marketplace (DS3.1 : aucun regroupement ne prédit mieux) ; ces rangs servent seulement
# à situer le vendeur. Tout est calculé au 12 mois d'issues CONNUES à T (mêmes colonnes year_n / year_x que la détection).
BENCH_METRICS = ("handover", "late", "poor")
DESCRIPTIVE_METRICS = {"median_price": "prix médian (R$)", "freight_share": "part du port dans le prix", "promised_days": "délai promis moyen (jours)"}
MIN_RANK_N = 20          # issues connues sur 12 mois pour être classé sur un indicateur
TOP_QUARTILE = 0.25
COMPETITOR_SIZE_COLS = ["log_orders", "log_price", "freight_ratio", "promised_days"]


def competitor_neighbors(prof: pd.DataFrame, k: int = 20) -> tuple[np.ndarray, np.ndarray]:
    """Concurrents directs : k plus proches voisins sur le mix de catégories, le volume, le prix, la part du port et le délai promis
    (pas de destinations ni de poids, pas d'issue). Retourne (indices, distances) par vendeur, le vendeur lui-même exclu."""
    cols = [c for c in prof.columns if c.startswith("cat_")] + [c for c in COMPETITOR_SIZE_COLS if c in prof.columns]
    Z = feature_matrix(prof[cols])
    n = len(prof)
    kk = min(k + 1, n)
    dist, ind = NearestNeighbors(n_neighbors=kk).fit(Z).kneighbors(Z)
    nb, nd = np.empty((n, kk - 1), dtype=int), np.empty((n, kk - 1))
    for i in range(n):
        keep = ind[i] != i
        row, rd = ind[i][keep][: kk - 1], dist[i][keep][: kk - 1]
        if len(row) < kk - 1:
            row, rd = np.pad(row, (0, kk - 1 - len(row)), mode="edge"), np.pad(rd, (0, kk - 1 - len(rd)), mode="edge")
        nb[i], nd[i] = row, rd
    return nb, nd


def benchmark_frame(prof: pd.DataFrame, year_counts: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Une ligne par vendeur profilé : taux sur 12 mois (issues connues à T ; NaN si moins de MIN_RANK_N issues), prix, port, délai.
    year_counts[metric] : DataFrame indexé par vendeur avec year_n et year_x."""
    B = pd.DataFrame(index=prof.index)
    B["n_orders"] = prof["n_orders"]
    B["main_category"] = prof["main_category"]
    B["seller_state"] = prof["seller_state"] if "seller_state" in prof.columns else None
    B["median_price"] = np.expm1(prof["log_price"])
    B["freight_share"] = prof["freight_ratio"]
    B["promised_days"] = prof["promised_days"]
    for m in BENCH_METRICS:
        c = year_counts.get(m)
        if c is None:
            B[f"n_{m}"], B[f"rate_{m}"] = 0, np.nan
            continue
        n = c["year_n"].reindex(B.index).fillna(0).astype(int)
        x = c["year_x"].reindex(B.index).fillna(0)
        B[f"n_{m}"] = n
        B[f"rate_{m}"] = np.where(n >= MIN_RANK_N, x / n.clip(lower=1), np.nan)
    return B


def _med(s: pd.Series) -> float | None:
    s = s.dropna()
    return float(s.median()) if len(s) else None


def group_benchmark(B: pd.DataFrame, seller_id: str, members: list[str]) -> dict:
    """Rang du vendeur dans un groupe (lui compris). Rang 1 = taux le plus bas (meilleur) ; ex aequo : meilleur rang partagé.
    Quart supérieur : 25 % des membres au meilleur score composite (moyenne des rangs centiles sur les indicateurs classés)."""
    ids = list(dict.fromkeys([seller_id, *members]))
    G = B.loc[[i for i in ids if i in B.index]]
    pct_cols = {}
    out_metrics = {}
    for m in BENCH_METRICS:
        v = G[f"rate_{m}"]
        ranked = v.dropna()
        pct_cols[m] = ranked.rank(pct=True, method="average")
        own = v.get(seller_id)
        rank = better = None
        if own is not None and pd.notna(own) and len(ranked):
            rank = int((ranked < own).sum()) + 1
            others = ranked.drop(seller_id)
            better = float((others > own).mean()) if len(others) else None
        out_metrics[m] = {"seller_rate": None if own is None or pd.isna(own) else float(own), "seller_known_n": int(G.at[seller_id, f"n_{m}"]),
                          "rank": rank, "n_ranked": int(len(ranked)), "better_than_share": better,
                          "group_median": _med(ranked), "top_quartile_threshold": float(ranked.quantile(TOP_QUARTILE)) if len(ranked) else None}
    score = pd.DataFrame(pct_cols).mean(axis=1)
    top = score[score <= score.quantile(TOP_QUARTILE)].index if len(score) else pd.Index([])
    for m in BENCH_METRICS:
        out_metrics[m]["top_quartile_median"] = _med(G.loc[top, f"rate_{m}"]) if len(top) else None
    for m in DESCRIPTIVE_METRICS:
        out_metrics[m] = {"seller_value": float(G.at[seller_id, m]) if pd.notna(G.at[seller_id, m]) else None,
                          "group_median": _med(G[m]), "top_quartile_median": _med(G.loc[top, m]) if len(top) else None}
    vol_rank = int((G["n_orders"] > G.at[seller_id, "n_orders"]).sum()) + 1
    overall = {"rank": None, "n_ranked": int(len(score)), "score": None, "in_top_quartile": bool(seller_id in top)}
    if seller_id in score.index:
        overall.update(rank=int((score < score[seller_id]).sum()) + 1, score=float(score[seller_id]))
    return {"n_members": int(len(G)), "metrics": out_metrics, "overall": overall, "volume_rank": vol_rank,
            "n_top_quartile": int(len(top)), "min_known_n": MIN_RANK_N}
