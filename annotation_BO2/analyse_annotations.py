"""Analyse des annotations humaines des avis (BO2) : accord entre annotateurs, arbitrage, fichier de référence.

Fonctionne sans le dossier data/ : seulement pandas et numpy.

    python analyse_annotations.py essai        # après l'essai : kappa de Fleiss entre les 5, liste des désaccords
    python analyse_annotations.py principal    # après l'annotation principale : kappa de Cohen, fichiers d'arbitrage
    python analyse_annotations.py final        # après l'arbitrage : quality/annotated_reviews.csv
    python analyse_annotations.py final --comparer-ia chemin/annotations_ia.csv   # accord IA / référence humaine

Les fichiers exportés par l'outil (…_annote.csv) se déposent dans retours/.
Valeurs : -1 critique, 0 mentionné sans jugement, 1 éloge, vide = non mentionné.
Dans les fichiers d'arbitrage, la colonne `decision` prend -1, 0, 1 ou x (= non mentionné).
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ASPECTS = ["livraison", "qualite_produit", "article_errone_ou_manquant", "vendeur_service", "emballage",
           "conformite_annonce", "prix_valeur", "retour_remboursement", "satisfaction_globale"]
CATS = ["vide", "-1", "0", "1"]
HERE = Path(__file__).resolve().parent


def norm(v) -> str:
    s = "" if pd.isna(v) else str(v).strip().replace("+", "")
    if s in ("", "x", "X", "nan"):
        return "vide"
    try:
        f = float(s)
    except ValueError:
        return "vide"
    return {-1.0: "-1", 0.0: "0", 1.0: "1"}.get(f, "vide")


def read_returns(pattern: str) -> dict[str, pd.DataFrame]:
    out = {}
    for f in sorted(glob.glob(str(HERE / "retours" / pattern))):
        m = re.match(r"([A-E])_", Path(f).name)
        if not m:
            continue
        d = pd.read_csv(f, encoding="utf-8-sig", dtype=str)
        val = d.get("valide", pd.Series([""] * len(d))).fillna("")
        missing = int((val != "oui").sum())
        if missing:
            print(f"  attention : {Path(f).name} contient {missing} avis non validés (ignorés)")
        d = d[val == "oui"].drop_duplicates("review_id").set_index("review_id")
        for a in ASPECTS:
            d[a] = d[a].map(norm)
        out[m.group(1)] = d
    return out


def cohen_kappa(x: list[str], y: list[str]) -> float | None:
    x, y = np.asarray(x), np.asarray(y)
    if len(x) == 0:
        return None
    po = float((x == y).mean())
    pe = sum(float((x == c).mean()) * float((y == c).mean()) for c in CATS)
    return None if pe >= 1 else round((po - pe) / (1 - pe), 3)


def fleiss_kappa(table: np.ndarray) -> float | None:
    """table : n_items × n_catégories, nombre d'annotateurs ayant choisi chaque catégorie."""
    n = table.sum(axis=1)
    table = table[n == n.max()]
    if len(table) == 0:
        return None
    r = table.sum(axis=1)[0]
    p_j = table.sum(axis=0) / table.sum()
    P_i = ((table * (table - 1)).sum(axis=1)) / (r * (r - 1))
    Pbar, Pe = P_i.mean(), (p_j ** 2).sum()
    return None if Pe >= 1 else round(float((Pbar - Pe) / (1 - Pe)), 3)


def verdict(k) -> str:
    if k is None:
        return "n/d"
    return "très bon" if k >= 0.8 else "correct" if k >= 0.6 else "moyen" if k >= 0.4 else "faible"


def cmd_essai() -> None:
    R = read_returns("*_1_essai*_annote*.csv")
    if len(R) < 2:
        sys.exit("Il faut au moins 2 fichiers d'essai dans retours/.")
    ids = sorted(set.intersection(*[set(d.index) for d in R.values()]))
    print(f"Essai : {len(R)} annotateurs ({', '.join(R)}), {len(ids)} avis annotés par tous.\n")
    print(f"{'aspect':<28} {'kappa Fleiss':>12}  {'accord total':>12}  verdict")
    res, rows = {}, []
    for a in ASPECTS:
        M = pd.DataFrame({p: d.loc[ids, a] for p, d in R.items()})
        table = np.stack([(M == c).sum(axis=1).values for c in CATS], axis=1)
        k = fleiss_kappa(table)
        unanimous = float((M.nunique(axis=1) == 1).mean())
        res[a] = {"fleiss_kappa": k, "unanimite": round(unanimous, 3)}
        print(f"{a:<28} {str(k):>12}  {unanimous:>11.0%}  {verdict(k)}")
        for rid, row in M[M.nunique(axis=1) > 1].iterrows():
            rows.append({"review_id": rid, "aspect": a, **row.to_dict()})
    first = next(iter(R.values()))
    dis = pd.DataFrame(rows)
    if len(dis):
        dis["texte_fr"] = dis.review_id.map(first["texte_fr"])
        dis["texte_pt"] = dis.review_id.map(first["texte_pt"])
    out = HERE / "coordination" / "desaccords_essai.csv"
    dis.to_csv(out, index=False, encoding="utf-8-sig")
    (HERE / "coordination" / "accord_essai.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    weak = [a for a, v in res.items() if v["fleiss_kappa"] is not None and v["fleiss_kappa"] < 0.6]
    print(f"\n{len(dis)} désaccords à discuter en réunion : {out.name}")
    print("Aspects à clarifier dans le guide (kappa < 0,6) : " + (", ".join(weak) if weak else "aucun"))


def load_assignment() -> pd.DataFrame:
    return pd.read_csv(HERE / "coordination" / "affectation_500.csv", encoding="utf-8-sig", dtype={"score": int})


def cmd_principal() -> None:
    A = load_assignment()
    R = read_returns("*_2_principal*_annote*.csv")
    missing_people = sorted(set("ABCDE") - set(R))
    if missing_people:
        print(f"  attention : fichiers manquants pour {', '.join(missing_people)}")
    pairs_k, pooled = {}, {a: ([], []) for a in ASPECTS}
    dis_rows, incomplete = [], 0
    for _, r in A.iterrows():
        p1, p2 = r.annotateur_1, r.annotateur_2
        if p1 not in R or p2 not in R or r.review_id not in R[p1].index or r.review_id not in R[p2].index:
            incomplete += 1
            continue
        x, y = R[p1].loc[r.review_id], R[p2].loc[r.review_id]
        for a in ASPECTS:
            pooled[a][0].append(x[a]); pooled[a][1].append(y[a])
            pairs_k.setdefault(f"{p1}-{p2}", {}).setdefault(a, ([], []))
            pairs_k[f"{p1}-{p2}"][a][0].append(x[a]); pairs_k[f"{p1}-{p2}"][a][1].append(y[a])
            if x[a] != y[a]:
                dis_rows.append({"arbitre": r.arbitre, "lot": r.lot, "review_id": r.review_id, "aspect": a,
                                 f"valeur_{p1}": x[a], f"valeur_{p2}": y[a], "annotateurs": f"{p1}-{p2}",
                                 "proposition_1": x[a], "proposition_2": y[a],
                                 "texte_fr": x.get("texte_fr", ""), "texte_pt": x.get("texte_pt", ""), "decision": ""})
    n_done = len(A) - incomplete
    print(f"Annotation principale : {n_done} avis sur {len(A)} annotés par leurs deux annotateurs.\n")
    print(f"{'aspect':<28} {'kappa Cohen':>11}  {'accord':>7}  verdict")
    res = {"avis_complets": n_done, "par_aspect": {}, "par_binome": {}}
    for a in ASPECTS:
        x, y = pooled[a]
        k = cohen_kappa(x, y)
        acc = float(np.mean(np.array(x) == np.array(y))) if x else 0.0
        res["par_aspect"][a] = {"cohen_kappa": k, "accord": round(acc, 3)}
        print(f"{a:<28} {str(k):>11}  {acc:>6.0%}  {verdict(k)}")
    print("\nKappa moyen par binôme (tous aspects) :")
    for pair, d in sorted(pairs_k.items()):
        ks = [cohen_kappa(*d[a]) for a in ASPECTS]
        ks = [k for k in ks if k is not None]
        res["par_binome"][pair] = round(float(np.mean(ks)), 3) if ks else None
        print(f"  {pair} : {res['par_binome'][pair]}")
    (HERE / "coordination" / "accord_principal.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    dis = pd.DataFrame(dis_rows)
    cols = ["lot", "review_id", "aspect", "annotateurs", "proposition_1", "proposition_2", "texte_fr", "texte_pt", "decision"]
    for p in "ABCDE":
        part = dis[dis.arbitre == p][cols] if len(dis) else pd.DataFrame(columns=cols)
        part.sort_values(["lot", "review_id"]).to_csv(HERE / "coordination" / f"arbitrage_{p}.csv", index=False, encoding="utf-8-sig")
        print(f"  arbitrage_{p}.csv : {len(part)} désaccords à trancher")
    print("\nL'arbitre remplit la colonne `decision` (-1, 0, 1, ou x = non mentionné), puis : python analyse_annotations.py final")


def cmd_final(compare_ai: str | None) -> None:
    A = load_assignment().set_index("review_id")
    R = read_returns("*_2_principal*_annote*.csv")
    decisions = {}
    undecided = 0
    for f in glob.glob(str(HERE / "coordination" / "arbitrage_*.csv")):
        d = pd.read_csv(f, encoding="utf-8-sig", dtype=str)
        for _, r in d.iterrows():
            dec = "" if pd.isna(r.get("decision")) else str(r["decision"]).strip()
            if dec == "":
                undecided += 1
                continue
            decisions[(r.review_id, r.aspect)] = norm(dec)
    rows = []
    for rid, r in A.iterrows():
        p1, p2 = r.annotateur_1, r.annotateur_2
        if p1 not in R or p2 not in R or rid not in R[p1].index or rid not in R[p2].index:
            continue
        x, y = R[p1].loc[rid], R[p2].loc[rid]
        out = {"review_id": rid, "score": int(r.score), "text_pt": x.get("texte_pt", ""), "text_fr": x.get("texte_fr", ""), "partie": r.partie}
        ok = True
        for a in ASPECTS:
            v = x[a] if x[a] == y[a] else decisions.get((rid, a))
            if v is None:
                ok = False
                break
            out[a] = "" if v == "vide" else v
        if ok:
            rows.append(out)
    ref = pd.DataFrame(rows)
    if undecided:
        print(f"  attention : {undecided} désaccords sans décision ; les avis concernés sont exclus.")
    dest = HERE.parent / "quality" / "annotated_reviews.csv" if (HERE.parent / "quality").is_dir() else HERE / "annotated_reviews.csv"
    ref.to_csv(dest, index=False, encoding="utf-8-sig")
    print(f"Référence humaine : {len(ref)} avis -> {dest}")
    print(f"  partie A (réglage) : {(ref.partie == 'A').sum()} avis ; partie B (test final) : {(ref.partie == 'B').sum()} avis")
    for a in ASPECTS:
        s = ref[a].astype(str)
        print(f"  {a:<28} critiques {int((s == '-1').sum()):>4}   mentions {int((s != '').sum()):>4}")
    if compare_ai:
        ai = pd.read_csv(compare_ai, encoding="utf-8-sig", dtype=str).drop_duplicates("review_id").set_index("review_id")
        common = [rid for rid in ref.review_id if rid in ai.index]
        refi = ref.set_index("review_id")
        print(f"\nAccord IA / référence humaine sur {len(common)} avis (à comparer au kappa entre humains) :")
        res = {}
        for a in ASPECTS:
            k = cohen_kappa([norm(v) for v in refi.loc[common, a]], [norm(v) for v in ai.loc[common, a]])
            res[a] = k
            print(f"  {a:<28} kappa {k}  ({verdict(k)})")
        (HERE / "coordination" / "accord_ia_humains.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("etape", choices=["essai", "principal", "final"])
    ap.add_argument("--comparer-ia", default=None, help="CSV annoté par un modèle de langage (mêmes colonnes)")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    {"essai": cmd_essai, "principal": cmd_principal}.get(a.etape, lambda: cmd_final(a.comparer_ia))()


if __name__ == "__main__":
    main()
