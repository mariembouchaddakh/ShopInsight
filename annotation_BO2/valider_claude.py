"""Compare la validation humaine (60 avis) aux étiquettes produites par Claude.

Usage (depuis le dossier du projet) :
    python annotation_BO2/valider_claude.py annotation_BO2/retours/A_validation_60_avis.csv

Écrit quality/validation_claude.json et affiche, par aspect :
  - kappa de Cohen sur 4 classes (vide / -1 / 0 / +1)
  - kappa sur la présence (aspect mentionné ou non)
  - accord brut
"""
import json
import sys
from pathlib import Path

import pandas as pd

ASPECTS = ["livraison", "qualite_produit", "article_errone_ou_manquant",
           "vendeur_service", "emballage", "conformite_annonce", "prix_valeur",
           "retour_remboursement", "satisfaction_globale"]
ROOT = Path(__file__).resolve().parents[1]


def norm(x):
    s = str(x).strip().replace("+", "")
    if s in ("", "nan", "None"):
        return "vide"
    try:
        return str(int(float(s)))
    except ValueError:
        return "vide"


def kappa(a, b):
    a, b = list(a), list(b)
    n = len(a)
    if n == 0:
        return float("nan")
    po = sum(x == y for x, y in zip(a, b)) / n
    cats = set(a) | set(b)
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in cats)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    hum = pd.read_csv(sys.argv[1], dtype=str, encoding="utf-8-sig", sep=None, engine="python")
    ia = pd.read_csv(ROOT / "quality" / "annotated_reviews.csv", dtype=str, encoding="utf-8-sig")
    ia = ia.drop_duplicates("review_id").set_index("review_id")
    hum = hum[hum.review_id.isin(ia.index)].drop_duplicates("review_id")
    rempli = hum[ASPECTS].apply(lambda c: c.map(norm)).ne("vide").any(axis=1)
    print(f"{len(hum)} avis dans le fichier, {int(rempli.sum())} avec au moins un aspect rempli")
    res, all_h, all_c = {}, [], []
    print(f"\n{'aspect':30s} {'kappa 4cl':>9s} {'kappa prés.':>11s} {'accord':>7s}")
    for a in ASPECTS:
        h = hum[a].map(norm).tolist()
        c = [norm(ia.at[r, a]) for r in hum.review_id]
        k4, kp = kappa(h, c), kappa([x != "vide" for x in h], [x != "vide" for x in c])
        acc = sum(x == y for x, y in zip(h, c)) / len(h)
        res[a] = {"kappa_4classes": round(k4, 3), "kappa_presence": round(kp, 3),
                  "accord": round(acc, 3), "n_humain": sum(x != "vide" for x in h),
                  "n_claude": sum(x != "vide" for x in c)}
        all_h += h; all_c += c
        print(f"{a:30s} {k4:9.2f} {kp:11.2f} {acc:7.0%}")
    glob = round(kappa(all_h, all_c), 3)
    print(f"\nKappa global (toutes cellules) : {glob:.2f}  (>= 0.61 = accord substantiel)")
    out = {"n_avis": len(hum), "kappa_global": glob, "par_aspect": res,
           "note": "Étiquettes produites par Claude (LLM), validées par un annotateur humain sur cet échantillon."}
    (ROOT / "quality" / "validation_claude.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Écrit : quality/validation_claude.json")


if __name__ == "__main__":
    main()
