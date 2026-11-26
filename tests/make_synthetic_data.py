"""Génère un jeu de données SYNTHÉTIQUE au même schéma que le pipeline REHEARSE (pour tester les agents sans les 200 Mo d'Olist).
Les chiffres n'ont aucune valeur analytique. Usage : python tests/make_synthetic_data.py --out /tmp/rehearse_synth --repo <ShopInsight>"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

STATES = ["SP", "RJ", "MG", "RS", "PR", "BA", "AL", "MA", "SC", "GO"]
STATE_P = [.42, .13, .12, .06, .06, .04, .02, .02, .05, .08]
STATE_LATE = {"SP": .03, "RJ": .10, "MG": .04, "RS": .05, "PR": .03, "BA": .11, "AL": .20, "MA": .16, "SC": .06, "GO": .05}
CATS = ["cama_mesa_banho", "beleza_saude", "esporte_lazer", "informatica_acessorios", "moveis_decoracao", "telefonia"]
NEG = {
    "livraison": ["O produto não chegou no prazo, entrega muito atrasada.", "Demorou demais para chegar, péssimo prazo de entrega.", "Ainda não recebi o pedido, está atrasado."],
    "qualite_produit": ["Produto veio com defeito e quebrado.", "A qualidade é ruim, material frágil, não funciona."],
    "article_errone_ou_manquant": ["Veio produto errado, faltou uma peça.", "Recebi apenas um dos dois produtos comprados."],
    "vendeur_service": ["O vendedor não respondeu, atendimento péssimo.", "Sem resposta da loja, nenhum contato."],
    "conformite_annonce": ["Não corresponde à descrição do anúncio, a cor é diferente da foto."],
    "retour_remboursement": ["Quero devolver e pedir reembolso, ninguém resolve."],
    "golpe": ["Isso foi um golpe, nunca mais compro, golpe total."],
}
POS = ["Ótimo produto, recomendo, chegou rápido.", "Excelente qualidade, perfeito, adorei.", "Entrega antes do prazo, muito satisfeito.", "Produto bom, preço justo, recomendo."]
FR = {"Ótimo": "Excellent", "chegou": "est arrivé", "produto": "produit", "entrega": "livraison", "prazo": "délai", "Recebi": "J'ai reçu"}


def fr(t: str) -> str:
    for a, b in FR.items():
        t = t.replace(a, b)
    return "[FR] " + t


def oid(i: int, p: str = "o") -> str:
    return hashlib.md5(f"{p}{i}".encode()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--repo", type=Path, required=True, help="dépôt ShopInsight cloné (pour quality/encoding_spec.json et baseline_results.json)")
    ap.add_argument("--n", type=int, default=24000)
    a = ap.parse_args()
    rng = np.random.default_rng(7)
    out = a.out
    for d in ("data/silver", "data/gold", "data/model", "quality"):
        (out / d).mkdir(parents=True, exist_ok=True)
    spec = json.loads((a.repo / "quality/encoding_spec.json").read_text())
    shutil.copy(a.repo / "quality/encoding_spec.json", out / "quality/encoding_spec.json")
    shutil.copy(a.repo / "quality/baseline_results.json", out / "quality/baseline_results.json")

    n = a.n
    months = pd.period_range("2017-01", "2018-08", freq="M")
    w = np.array([1 + 0.25 * i for i in range(len(months))])
    mi = rng.choice(len(months), n, p=w / w.sum())
    ts = pd.to_datetime([months[i].start_time + pd.Timedelta(seconds=int(rng.integers(0, 27 * 86400))) for i in mi])
    state = rng.choice(STATES, n, p=STATE_P)
    cat = rng.choice(CATS, n)
    sellers = np.array([oid(i, "s") for i in range(300)])
    srate = rng.beta(1.2, 18, 300)
    sidx = rng.integers(0, 300, n)
    dist = np.where(state == "SP", rng.gamma(2, 120, n), rng.gamma(4, 330, n)).clip(5, 3500)
    promised = (7 + dist / 90 + rng.normal(0, 4, n)).clip(4, 60).round()
    month_boost = np.array([{"2017-11": 2.2, "2018-02": 2.6, "2018-03": 3.5}.get(str(months[i]), 1.0) for i in mi])
    p_late = (np.array([STATE_LATE[s] for s in state]) * 0.6 + srate[sidx] * 0.6 + np.where(promised < 12, 0.04, 0)) * month_boost
    late = rng.random(n) < p_late.clip(0, .9)
    actual = np.where(late, promised + rng.integers(1, 15, n), (promised * rng.uniform(.3, .95, n))).round().clip(2, None)
    delivered = ts + pd.to_timedelta(actual, unit="D")
    est = ts + pd.to_timedelta(promised, unit="D")
    has_rev = rng.random(n) < 0.97
    pr_poor = np.where(late, 0.62, 0.09) + (rng.random(n) < 0.0)
    poor = rng.random(n) < pr_poor
    score = np.where(poor, rng.choice([1, 2], n, p=[.8, .2]), rng.choice([3, 4, 5], n, p=[.12, .28, .6]))
    ans = delivered + pd.to_timedelta(rng.integers(1, 6, n), unit="D")
    ids = [oid(i) for i in range(n)]
    month_str = np.array([str(months[i]) for i in mi])
    price = np.exp(rng.normal(4.3, .8, n)).round(2)
    freight = (8 + dist / 60 + rng.normal(0, 3, n)).clip(4, None).round(2)

    approved = ts + pd.to_timedelta(rng.integers(1, 24, n), unit="h")
    carrier = approved + pd.to_timedelta((actual * rng.uniform(.1, .45, n)).clip(1), unit="D")
    o = pd.DataFrame({"order_id": ids, "order_purchase_timestamp": ts, "order_approved_at": approved,
                      "order_delivered_carrier_date": carrier, "order_estimated_delivery_date": est, "order_delivered_customer_date": delivered,
                      "review_answer_timestamp": np.where(has_rev, ans, pd.NaT), "purchase_month": month_str, "customer_state": state, "primary_category": cat,
                      "item_count": rng.integers(1, 3, n), "seller_count": np.where(rng.random(n) < .013, 2, 1), "item_price_total": price,
                      "freight_total": freight, "single_seller_id": sellers[sidx], "is_late": late.astype(int), "late_days": np.where(late, actual - promised, np.nan),
                      "review_score": np.where(has_rev, score, np.nan), "order_status": "delivered", "delivery_duration_days": actual,
                      "promised_days": promised, "distance_km": dist, "product_weight_mean_g": rng.gamma(2, 400, n),
                      "late_label_eligible": True,
                      "poor_review_label_eligible": has_rev, "is_poor_review": np.where(has_rev, poor.astype(int), np.nan)})
    o.to_csv(out / "data/silver/orders_analysis.csv.gz", index=False, compression="gzip")

    # features au schéma réel
    feats = {c: np.zeros(n) for c in spec["features"]}
    feats["promised_days"] = promised
    feats["purchase_weekday"], feats["purchase_hour"], feats["purchase_month_num"] = ts.weekday, ts.hour, ts.month
    feats["is_weekend"] = (ts.weekday >= 5).astype(int)
    feats["item_count"], feats["product_count"], feats["seller_count"] = o["item_count"], o["item_count"], o["seller_count"]
    feats["payment_rows"] = 1; feats["payment_type_count"] = 1; feats["payment_installments_max"] = rng.integers(1, 8, n)
    feats["same_state"] = (rng.random(n) < .3).astype(int)
    feats["seller_train_orders_log"] = np.log1p(rng.integers(0, 400, n))
    for c, v in {"item_price_total_log": np.log1p(price), "freight_total_log": np.log1p(freight), "payment_total_log": np.log1p(price + freight),
                 "product_weight_mean_g_log": np.log1p(rng.gamma(2, 400, n)), "product_volume_mean_cm3_log": np.log1p(rng.gamma(2, 5000, n)),
                 "approval_delay_hours_log": np.log1p(rng.exponential(10, n)), "distance_km_log": np.log1p(dist)}.items():
        feats[c] = v
    for s in STATES:
        feats[f"state_{s}"] = (state == s).astype(int)
    feats["te_category_late"] = 0.056 + rng.normal(0, .01, n)
    feats["te_seller_late"] = (srate[sidx] * .7 + .056 * .3 + rng.normal(0, .01, n))
    feats["te_sellerstate_late"] = np.array([STATE_LATE[s] for s in state]) * .5 + .03
    feats["te_category_poor"] = 0.146 + rng.normal(0, .02, n)
    feats["te_seller_poor"] = 0.146 + (srate[sidx] - .06) * 1.5 + rng.normal(0, .02, n)
    feats["te_sellerstate_poor"] = 0.146 + rng.normal(0, .01, n)
    F = pd.DataFrame(feats)
    F.insert(0, "order_id", ids)
    F.insert(1, "order_purchase_timestamp", ts)
    F.insert(2, "late_label_eligible", True); F.insert(3, "is_late", late.astype(int))
    F.insert(4, "poor_review_label_eligible", has_rev); F.insert(5, "is_poor_review", np.where(has_rev, poor.astype(int), np.nan))
    ok = np.array([m not in ("2016-09", "2016-12") for m in month_str])
    split = np.select([ts < "2018-01-01", ts < "2018-04-01"], ["train", "valid"], "test")
    for s in ("train", "valid", "test"):
        F[(split == s) & ok].to_csv(out / f"data/model/features_{s}.csv.gz", index=False, compression="gzip")

    # KPI
    def kpis(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
        g = df.groupby(keys).agg(order_count=("order_id", "size"), late_eligible_count=("late_label_eligible", "sum"), late_order_count=("is_late", "sum"),
                                 reviewed_order_count=("review_score", "count"), poor_review_count=("is_poor_review", "sum"),
                                 average_review_score=("review_score", "mean")).reset_index()
        g["late_rate"] = g["late_order_count"] / g["late_eligible_count"]
        g["poor_review_rate"] = g["poor_review_count"] / g["reviewed_order_count"]
        g["written_comment_rate"] = 0.43
        g["is_complete_period"] = True
        return g
    kpis(o, ["purchase_month"]).to_csv(out / "data/gold/monthly_business_kpis.csv", index=False)
    kpis(o, ["purchase_month", "customer_state"]).to_csv(out / "data/gold/state_monthly_kpis.csv.gz", index=False, compression="gzip")
    kpis(o, ["purchase_month", "primary_category"]).to_csv(out / "data/gold/category_monthly_kpis.csv.gz", index=False, compression="gzip")
    kpis(o, ["purchase_month", "single_seller_id"]).to_csv(out / "data/silver/seller_monthly_kpis.csv.gz", index=False, compression="gzip")

    # avis
    recs, recs_fr = [], []
    for i in range(n):
        if not has_rev[i] or rng.random() > 0.45:
            continue
        m = month_str[i]
        if score[i] <= 2:
            if late[i] and rng.random() < .7 or (m in ("2018-02", "2018-03") and rng.random() < .35):
                t = rng.choice(NEG["livraison"])
            else:
                k = rng.choice([x for x in NEG if x not in ("livraison", "golpe")])
                t = rng.choice(NEG[k])
            if m == "2018-07" and rng.random() < .2:
                t = rng.choice(NEG["golpe"])
        elif score[i] == 3:
            t = "Produto ok, mas demorou um pouco."
        else:
            t = rng.choice(POS)
        rec = {"review_id": oid(i, "r"), "order_id": ids[i], "review_score": int(score[i]), "title": None, "text": t, "has_message": True, "has_title": False,
               "review_created_at": pd.Timestamp(delivered[i] + pd.Timedelta(days=1)).isoformat(),
               "review_answered_at": pd.Timestamp(ans[i]).isoformat(),
               "metadata": {"purchase_month": m, "customer_state": state[i], "primary_category": cat[i], "is_late": int(late[i]), "delivery_duration_days": float(actual[i])}}
        recs.append(rec)
        rf = dict(rec); rf.update({"text_original_pt": t, "text_fr": fr(t), "title_original_pt": None, "title_fr": None, "translation_status": "traduit"})
        recs_fr.append(rf)
    for name, rr in (("reviews_text", recs), ("reviews_text_fr", recs_fr)):
        with gzip.open(out / f"data/silver/{name}.jsonl.gz", "wt", encoding="utf-8") as f:
            for r in rr:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("ok", n, "commandes,", len(recs), "avis ->", out)


if __name__ == "__main__":
    main()
