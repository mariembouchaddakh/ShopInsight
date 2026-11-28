"""Comparaison à l'aveugle de modèles de traduction sur un échantillon d'avis (portugais -> français).

1) Générer la grille (GPU conseillé pour nllb-1.3b, CPU possible pour 100 avis) :
     python src/compare_translations.py --project-dir .   # défaut : opus-split, nllb-1.3b, tower-2b, milmmt-4b
   -> quality/comparaison_traductions.csv : pour chaque avis, le portugais et une traduction par système dans un ordre mélangé
      (la traduction actuelle du corpus + chaque candidat), sans dire laquelle est laquelle.
   -> quality/comparaison_cle.json : la clé (quel numéro = quel modèle), à ne pas ouvrir avant d'avoir jugé.

2) Juger : dans le CSV, remplir `meilleure` (numéro, ou egal) et, pour chaque traduction, `correcte_i` (oui / non :
   le sens est-il fidèle ?). Idéalement deux personnes, chacune sur sa copie.

3) Résultat :
     python src/compare_translations.py --project-dir . --score quality/comparaison_traductions.csv [autre_copie.csv]
   -> part de victoires et part de traductions jugées correctes par modèle, dans quality/comparaison_resultats.json
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from translate_reviews import LLM_MODELS, NLLB_MODELS, check_translation, clean, make_translator, split_sentences  # noqa: E402

CANDIDATES = ["opus-split", *NLLB_MODELS, *LLM_MODELS]

CURRENT = "actuel (opus-mt, pivot anglais)"


def sample_reviews(project: Path, n: int, seed: int) -> list[dict]:
    with gzip.open(project / "data/silver/reviews_text_fr.jsonl.gz", "rt", encoding="utf-8") as f:
        docs = [json.loads(l) for l in f]
    docs = [d for d in docs if clean(d.get("text_original_pt")) and d.get("text_fr")]
    rng = random.Random(seed)
    per = n // 5
    out = []
    for s in range(1, 6):
        pool = [d for d in docs if int(d.get("review_score") or 0) == s]
        out += rng.sample(pool, min(per, len(pool)))
    rng.shuffle(out)
    return out


def generate(project: Path, models: list[str], n: int, seed: int, device: str, batch: int, engine: str = "hf") -> None:
    docs = sample_reviews(project, n, seed)
    texts = [clean(d["text_original_pt"]) for d in docs]
    systems = {CURRENT: [d["text_fr"] for d in docs]}
    timing = {}
    # traductions déjà produites pour ce même échantillon : réutilisées (un modèle n'est calculé qu'une fois)
    store = project / "quality" / "comparaison_systemes.json"
    saved = json.loads(store.read_text(encoding="utf-8")) if store.exists() else {}
    ids = [d["review_id"] for d in docs]
    for m in models:
        if m in saved and saved[m]["review_ids"] == ids:
            systems[m], timing[m] = saved[m]["traductions"], saved[m]["temps"]
            print(f"{m} : réutilisé", flush=True)
            continue
        tr = make_translator("opus" if m == "opus-split" else m, batch_size=batch, device=device, engine=engine)
        sents = sorted({p for t in texts for p in split_sentences(t)}, key=len)
        t0 = time.time()
        fr = dict(zip(sents, (f for _, f in tr.translate(sents))))
        timing[m] = {"secondes": round(time.time() - t0, 1), "phrases": len(sents), "device": tr.device}
        systems[m] = [" ".join(fr[p].strip() for p in split_sentences(t)) for t in texts]
        print(f"{m} : {len(sents)} phrases en {timing[m]['secondes']} s sur {tr.device}", flush=True)
        saved[m] = {"review_ids": ids, "traductions": systems[m], "temps": timing[m]}
        store.parent.mkdir(exist_ok=True)
        store.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
        del tr
        try:
            import gc, torch
            gc.collect()
            torch.cuda.empty_cache()
        except Exception:
            pass
    names = list(systems)
    rng = random.Random(seed + 1)
    q = project / "quality"
    q.mkdir(exist_ok=True)
    key_rows = []
    with (q / "comparaison_traductions.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["n", "review_id", "texte_pt"] + [f"traduction_{i+1}" for i in range(len(names))]
                   + ["meilleure (numero ou egal)"] + [f"correcte_{i+1} (oui/non)" for i in range(len(names))] + ["commentaire"])
        for i, d in enumerate(docs):
            order = names[:]
            rng.shuffle(order)
            key_rows.append({"review_id": d["review_id"], "ordre": order})
            w.writerow([i + 1, d["review_id"], texts[i]] + [systems[s][i] for s in order] + [""] * (1 + len(names)) + [""])
    auto = {}
    for s in names:
        flags = [check_translation(t, f) for t, f in zip(texts, systems[s])]
        auto[s] = {"traductions_signalees": sum(1 for x in flags if x),
                   "ratio_longueur_moyen": round(sum(len(f) / max(1, len(t)) for t, f in zip(texts, systems[s])) / len(texts), 2)}
    (q / "comparaison_cle.json").write_text(json.dumps({"systemes": names, "lignes": key_rows, "controles_automatiques": auto,
                                                        "temps": timing}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"controles_automatiques": auto, "temps": timing}, ensure_ascii=False, indent=2))
    print(f"\nGrille à juger : {q / 'comparaison_traductions.csv'} ({len(docs)} avis). Ne pas ouvrir comparaison_cle.json avant.")


def score(project: Path, files: list[str]) -> None:
    key = json.loads((project / "quality/comparaison_cle.json").read_text(encoding="utf-8"))
    order = {r["review_id"]: r["ordre"] for r in key["lignes"]}
    names = key["systemes"]
    wins = {s: 0.0 for s in names}
    correct = {s: [0, 0] for s in names}
    judged = 0
    for path in files:
        with open(path, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f, delimiter=";"))
        head = rows[0]
        ib = next(i for i, h in enumerate(head) if h.startswith("meilleure"))
        ic = [i for i, h in enumerate(head) if h.startswith("correcte_")]
        for r in rows[1:]:
            rid, best = r[1], r[ib].strip().lower()
            o = order[rid]
            if best:
                judged += 1
                if best.startswith("eg") or best.startswith("ég"):
                    for s in o:
                        wins[s] += 1 / len(o)
                elif best.isdigit() and 1 <= int(best) <= len(o):
                    wins[o[int(best) - 1]] += 1
            for j, col in enumerate(ic):
                v = r[col].strip().lower()
                if v in ("oui", "o", "non", "n"):
                    correct[o[j]][1] += 1
                    correct[o[j]][0] += v.startswith("o")
    res = {"avis_juges": judged,
           "victoires": {s: round(wins[s] / judged, 3) if judged else None for s in names},
           "part_correcte": {s: round(c / t, 3) if t else None for s, (c, t) in correct.items()},
           "controles_automatiques": key.get("controles_automatiques")}
    (project / "quality/comparaison_resultats.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project-dir", type=Path, default=Path("."))
    ap.add_argument("--models", nargs="+", default=["opus-split", "nllb-1.3b", "tower-2b", "milmmt-4b"], choices=CANDIDATES)
    ap.add_argument("--engine", choices=["hf", "vllm"], default="hf")
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--device", default="auto")
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--score", nargs="+", help="CSV jugés à dépouiller")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    p = a.project_dir.resolve()
    score(p, a.score) if a.score else generate(p, a.models, a.n, a.seed, a.device, a.batch_size, a.engine)


if __name__ == "__main__":
    main()
