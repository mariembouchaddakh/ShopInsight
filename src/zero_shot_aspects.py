"""BO2 — détection des aspects par un modèle multilingue en zero-shot (NLI), comparée à la baseline mots-clés.

Principe : un modèle d'inférence en langage naturel (NLI) multilingue lit l'avis en PORTUGAIS (le texte original) et juge,
pour chaque aspect, si deux hypothèses rédigées en portugais en découlent : « le client critique X » et « le client apprécie X ».
Aucun entraînement : le modèle n'a jamais vu nos avis ni nos étiquettes.

Décision par aspect : p = max(P(critique), P(éloge)) ; aspect mentionné si p >= seuil ; polarité = l'hypothèse la plus probable.
Tout réglage se fait sur la moitié A des 500 avis annotés ; les résultats sont donnés sur la moitié B, jamais utilisée pour
régler quoi que ce soit (A/B : parité du crc32 de review_id). Trois variantes sont comparées à la baseline mots-clés :
  zero_shot          un seuil unique (choisi sur A) ;
  zero_shot_aspect   un seuil par aspect (choisi sur A) ;
  hybride            par aspect, on garde sur A le meilleur de : mots-clés seuls, zero-shot seul, ou union (mots-clés,
                     complétés par le zero-shot quand les mots-clés ne trouvent rien).

Entrées : quality/annotated_reviews.csv (500 avis annotés), et optionnellement des fichiers annotés par des humains (--human).
Sorties : quality/bo2_zero_shot_predictions.csv, quality/bo2_zero_shot.json

  python src/zero_shot_aspects.py --project-dir .                         # CPU : ~15 min ; GPU (Colab) : ~1 min
  python src/zero_shot_aspects.py --project-dir . --human annotation_BO2/retours/B_1_essai_40_avis_annote.csv
  python src/zero_shot_aspects.py --project-dir . --reuse      # réévalue à partir des probabilités déjà calculées
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

ASPECTS = ["livraison", "qualite_produit", "article_errone_ou_manquant", "vendeur_service", "emballage",
           "conformite_annonce", "prix_valeur", "retour_remboursement", "satisfaction_globale"]

# Hypothèses en portugais : (critique, éloge). Formulées à partir des définitions du guide d'annotation.
HYPOTHESES = {
    "livraison": ("O cliente reclama da entrega, do atraso ou de não ter recebido o pedido.",
                  "O cliente elogia a entrega ou o prazo de entrega."),
    "qualite_produit": ("O cliente reclama da qualidade do produto ou de defeito.",
                        "O cliente elogia a qualidade do produto."),
    "article_errone_ou_manquant": ("O cliente recebeu um produto errado ou faltaram itens no pedido.",
                                   "O cliente recebeu exatamente os itens que pediu, completos."),
    "vendeur_service": ("O cliente reclama da loja, do vendedor ou do atendimento.",
                        "O cliente elogia a loja, o vendedor ou o atendimento."),
    "emballage": ("O cliente reclama da embalagem.",
                  "O cliente elogia a embalagem."),
    "conformite_annonce": ("O produto é diferente do anúncio, da descrição ou da foto.",
                           "O produto é igual ao anúncio e à descrição."),
    "prix_valeur": ("O cliente reclama do preço ou do frete caro.",
                    "O cliente elogia o preço ou o custo-benefício."),
    "retour_remboursement": ("O cliente pede devolução, troca, reembolso ou cancelamento.",
                             "O cliente ficou satisfeito com a troca ou o reembolso."),
    "satisfaction_globale": ("O cliente está insatisfeito com a compra em geral.",
                             "O cliente está satisfeito com a compra e recomenda."),
}
MODEL = "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7"


def part_of(review_id: str) -> str:
    return "A" if zlib.crc32(review_id.encode()) % 2 == 0 else "B"


def nli_scores(texts: list[str], model_name: str, batch: int, device: str) -> np.ndarray:
    """Renvoie un tableau (n_textes, 9 aspects, 2) : P(entailment) pour (critique, éloge)."""
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name).to(device).eval()
    ent = {v.lower(): k for k, v in model.config.id2label.items()}
    i_ent, i_con = ent["entailment"], ent["contradiction"]
    hyps = [h for a in ASPECTS for h in HYPOTHESES[a]]
    pairs = [(t, h) for t in texts for h in hyps]
    out = np.zeros(len(pairs), dtype=np.float32)
    t0 = time.time()
    with torch.inference_mode():
        for s in range(0, len(pairs), batch):
            p, h = zip(*pairs[s:s + batch])
            enc = tok(list(p), list(h), truncation="only_first", max_length=256, padding=True, return_tensors="pt").to(device)
            logits = model(**enc).logits
            # entailment contre contradiction (convention du zero-shot multi-label)
            out[s:s + len(p)] = torch.softmax(logits[:, [i_ent, i_con]], dim=-1)[:, 0].float().cpu().numpy()
            if (s // batch) % 50 == 0:
                done = s + len(p)
                print(f"  {done}/{len(pairs)} paires ({time.time() - t0:.0f} s)", file=sys.stderr, flush=True)
    return out.reshape(len(texts), len(ASPECTS), 2)


def decide(p: np.ndarray, threshold) -> np.ndarray:
    """p (n, 9, 2) -> étiquettes (n, 9) : -1 critique, 1 éloge, NaN non mentionné. threshold : un nombre ou un seuil par aspect."""
    best = p.max(axis=2)
    lab = np.where(p[:, :, 0] >= p[:, :, 1], -1.0, 1.0)
    th = np.array([threshold[a] for a in ASPECTS]) if isinstance(threshold, dict) else threshold
    return np.where(best >= th, lab, np.nan)


def union(kw: pd.DataFrame, zs: pd.DataFrame) -> pd.DataFrame:
    """Mots-clés d'abord ; le zero-shot ne complète que les aspects que les mots-clés n'ont pas trouvés."""
    return pd.DataFrame({a: np.where(kw[a].notna(), kw[a].astype(float), zs[a].astype(float)) for a in ASPECTS}, index=kw.index)


def prf(g: np.ndarray, p: np.ndarray) -> dict:
    tp, fp, fn = int((g & p).sum()), int((~g & p).sum()), int((g & ~p).sum())
    pr = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(pr, 3), "recall": round(rc, 3), "f1": round(2 * pr * rc / (pr + rc), 3) if pr + rc else 0.0, "support": int(g.sum())}


def evaluate(gold: pd.DataFrame, pred: pd.DataFrame) -> dict:
    res = {}
    for a in ASPECTS:
        g = pd.to_numeric(gold[a], errors="coerce").values
        p = pd.to_numeric(pred[a], errors="coerce").values
        res[a] = {"detection": prf(~np.isnan(g), ~np.isnan(p)), "negative": prf(g == -1, p == -1)}
    res["macro"] = {k: round(float(np.mean([res[a][k]["f1"] for a in ASPECTS])), 3) for k in ("detection", "negative")}
    return res


def baseline_predictions(project: Path, ids: list[str]) -> pd.DataFrame | None:
    """Prédictions de la baseline mots-clés + note de l'agent BO2, pour les mêmes avis."""
    try:
        sys.path.insert(0, str(project / "src"))
        from agents.bo2_agent import VoiceOfCustomerAgent
        an = VoiceOfCustomerAgent(project).an.drop_duplicates("review_id").set_index("review_id")
    except Exception as e:  # données absentes : on compare seulement le zero-shot
        print(f"baseline indisponible : {e}", file=sys.stderr)
        return None
    keep = [i for i in ids if i in an.index]
    return pd.DataFrame({a: an.loc[keep, f"a_{a}"].values for a in ASPECTS}, index=keep)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-dir", type=Path, default=Path("."))
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--device", default=None, help="cpu ou cuda (défaut : cuda si disponible)")
    ap.add_argument("--reuse", action="store_true", help="réutilise quality/bo2_zero_shot_predictions.csv au lieu de relancer le modèle")
    ap.add_argument("--human", type=Path, nargs="*", default=[], help="fichiers d'essai annotés par des humains (format outil d'annotation)")
    args = ap.parse_args()
    project = args.project_dir.resolve()
    import torch
    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")

    gold = pd.read_csv(project / "quality/annotated_reviews.csv", dtype={"review_id": str}).drop_duplicates("review_id").reset_index(drop=True)
    gold["partie"] = gold["review_id"].map(part_of)
    humans = []
    for f in args.human:
        h = pd.read_csv(f, dtype={"review_id": str}).rename(columns={"texte_pt": "text_pt"})
        humans.append((f.stem, h))
    texts = {r: t for r, t in zip(gold["review_id"], gold["text_pt"].fillna(""))}
    for _, h in humans:
        texts.update({r: t for r, t in zip(h["review_id"], h["text_pt"].fillna("")) if r not in texts})
    ids = list(texts)
    pred_path = project / "quality/bo2_zero_shot_predictions.csv"
    if args.reuse and pred_path.exists():
        old = pd.read_csv(pred_path, dtype={"review_id": str}).set_index("review_id")
        ids = [i for i in ids if i in old.index]
        P = np.stack([np.stack([old.loc[ids, f"p_neg_{a}"].values, old.loc[ids, f"p_pos_{a}"].values], axis=1) for a in ASPECTS], axis=1)
        elapsed = 0.0
    else:
        print(f"{len(ids)} avis, modèle {args.model}, {device}", file=sys.stderr)
        t0 = time.time()
        P = nli_scores([texts[i] for i in ids], args.model, args.batch, device)
        elapsed = time.time() - t0
    pos = {r: k for k, r in enumerate(ids)}
    base = baseline_predictions(project, ids)

    # ---- Réglages, sur la moitié A uniquement
    A = gold[gold["partie"] == "A"].reset_index(drop=True)
    PA = P[[pos[r] for r in A["review_id"]]]
    grid = [0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 0.97, 0.98, 0.99, 0.995, 0.998]
    macro_A = [evaluate(A, pd.DataFrame(decide(PA, g), columns=ASPECTS))["macro"]["detection"] for g in grid]
    th = float(grid[int(np.argmax(macro_A))])
    th_aspect = {a: float(max(grid, key=lambda g, a=a: evaluate(A, pd.DataFrame(decide(PA, g), columns=ASPECTS))[a]["detection"]["f1"]))
                 for a in ASPECTS}

    pred = pd.DataFrame(decide(P, th_aspect), columns=ASPECTS)
    pred.insert(0, "review_id", ids)
    for k, a in enumerate(ASPECTS):
        pred[f"p_neg_{a}"] = P[:, k, 0].round(4)
        pred[f"p_pos_{a}"] = P[:, k, 1].round(4)
    pred.to_csv(pred_path, index=False)
    zs1 = pd.DataFrame(decide(P, th), columns=ASPECTS, index=ids)
    zs = pred.set_index("review_id")[ASPECTS]

    choice = {}
    if base is not None:
        a_ids = [r for r in A["review_id"] if r in base.index]
        A2 = A[A["review_id"].isin(a_ids)].reset_index(drop=True)
        kwA, zsA = base.loc[A2["review_id"]].reset_index(drop=True), zs.loc[A2["review_id"]].reset_index(drop=True)
        cand = {"mots_cles": evaluate(A2, kwA), "zero_shot": evaluate(A2, zsA), "union": evaluate(A2, union(kwA, zsA))}
        choice = {a: max(cand, key=lambda c, a=a: cand[c][a]["detection"]["f1"]) for a in ASPECTS}

    def hybrid(rids: list[str]) -> pd.DataFrame:
        kw, z = base.loc[rids], zs.loc[rids]
        u = union(kw, z)
        return pd.DataFrame({a: {"mots_cles": kw, "zero_shot": z, "union": u}[choice[a]][a].values for a in ASPECTS}).reset_index(drop=True)

    out = {"model": args.model, "device": device, "seconds": round(elapsed), "threshold_global": th, "threshold_per_aspect": th_aspect,
           "macro_detection_on_A_by_global_threshold": dict(zip(map(str, grid), macro_A)), "hybrid_choice_on_A": choice, "hypotheses_pt": HYPOTHESES,
           "note": "Zero-shot : aucun entraînement. Seuils et choix de l'hybride réglés sur la moitié A ; résultats à présenter = moitié B. "
                   "Référence = étiquettes LLM (provisoires) et, à part, annotations humaines (40 avis d'essai)."}

    def compare(sub: pd.DataFrame) -> dict:
        sub = sub.drop_duplicates("review_id").reset_index(drop=True)
        rids = list(sub["review_id"])
        r = {"n": len(sub), "zero_shot": evaluate(sub, zs1.loc[rids].reset_index(drop=True)),
             "zero_shot_aspect": evaluate(sub, zs.loc[rids].reset_index(drop=True))}
        if base is not None:
            s2 = sub[sub["review_id"].isin(base.index)].reset_index(drop=True)
            r["n_baseline"] = len(s2)
            r["baseline_mots_cles"] = evaluate(s2, base.loc[s2["review_id"]].reset_index(drop=True))
            r["hybride"] = evaluate(s2, hybrid(list(s2["review_id"])))
        return r

    out["reference_llm_B"] = compare(gold[gold["partie"] == "B"])
    out["reference_llm_tous_500"] = compare(gold)
    for stem, h in humans:
        out[f"reference_humaine_{stem}"] = compare(h)
    (project / "quality/bo2_zero_shot.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nSeuil global (A) : {th} ; seuils par aspect (A) : {th_aspect}\nHybride (A) : {choice}\n")
    for key in [k for k in out if k.startswith("reference_")]:
        r = out[key]
        cells = "  ".join(f"{m} {r[m]['macro']['detection']:.2f}/{r[m]['macro']['negative']:.2f}"
                          for m in ("baseline_mots_cles", "zero_shot", "zero_shot_aspect", "hybride") if m in r)
        print(f"{key:45s} n={r['n']:3d}  (F1 détection / critiques)  {cells}")


if __name__ == "__main__":
    main()
