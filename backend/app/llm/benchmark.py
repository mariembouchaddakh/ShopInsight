"""Banc d'essai des modèles gratuits + juge LLM, sur les cas de référence (docs/reference_cases/cases.json).

    python -m backend.app.llm.benchmark --max-calls 40          # reprend là où il s'est arrêté (résultats et cache sur disque)
    python -m backend.app.llm.benchmark --report-only           # régénère le rapport à partir des résultats déjà obtenus
    python -m backend.app.llm.benchmark --compare-human docs/reference_cases/review_form.csv

Pour chaque cas × modèle (A, B) : même paquet de preuves, même consigne, même schéma, même validateur. Mesures déterministes :
taux d'éléments validés, rejets par motif, conformité du schéma, latence, jetons, échecs (dont limites de débit). Puis un JUGE
(troisième modèle, famille différente) note la qualité rédactionnelle de la sortie VALIDÉE (8 critères, 1–5). Le juge ne vérifie
ni les chiffres, ni les alertes : ils sont contrôlés de façon déterministe. Budget : 0 $ (modèles « :free » vérifiés avant chaque appel).
Sorties : quality/llm_benchmark.json, quality/llm_benchmark.md, quality/llm_benchmark_runs/*.json.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics as st
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
from agents.bo3_agent import SellerAuditAgent  # noqa: E402
from backend.app.config import load_settings  # noqa: E402
from backend.app.llm.analyst import analyse, build_package, parse_json, with_caveats  # noqa: E402
from backend.app.llm.provider import LLMError, OpenRouterFreeProvider  # noqa: E402
from backend.app.llm.reference_cases import CRITERIA  # noqa: E402
from backend.app.serialization import evidence_snapshot, jsonable  # noqa: E402

JUDGE_SYSTEM = """Tu es un évaluateur exigeant de rapports d'analyse de vendeurs. Tu reçois (1) les preuves déterministes d'un vendeur et
(2) une analyse rédigée par une IA, déjà filtrée par un contrôle automatique des chiffres et des identifiants de preuve.
Tu NE juges PAS l'exactitude des chiffres ni la justesse des alertes (contrôlées ailleurs). Tu juges la qualité de l'analyse :
adherence_preuves, coherence_factuelle (fidélité au rapport déterministe), profondeur_analytique, separation_faits_hypotheses,
pertinence_recommandations, actionnabilite, completude, clarte : chacun de 1 (très insuffisant) à 5 (excellent).
Signale aussi toute affirmation causale non étayée et toute hallucination (fait inventé ou contredit par les preuves).
Réponds UNIQUEMENT en JSON : {"scores": {"adherence_preuves": n, ...}, "affirmation_causale_non_etayee": true|false,
"hallucination": true|false, "commentaire": "2 phrases maximum"}"""


def provider(settings, model_id: str) -> OpenRouterFreeProvider:
    base = Path(settings.project_dir) / "data/model"
    return OpenRouterFreeProvider(settings.openrouter_api_key, model_id, cache_dir=base / "llm_cache", call_log=base / "llm_calls.jsonl")


def judge(prov: OpenRouterFreeProvider, report: dict, evidence: list[dict], analysis: dict) -> dict:
    shown = {k: analysis[k] for k in ("resume", "sections", "actions")}
    msgs = [{"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": "PREUVES :\n" + build_package(report, with_caveats(report, evidence), max_chars=20000)
             + "\n\nANALYSE IA À ÉVALUER :\n" + json.dumps(shown, ensure_ascii=False)}]
    out = prov.complete(msgs, max_tokens=1200)
    data = parse_json(out.content) or {}
    scores = data.get("scores") if isinstance(data.get("scores"), dict) else {}
    clean = {c: int(scores[c]) for c in CRITERIA if isinstance(scores.get(c), (int, float)) and 1 <= scores[c] <= 5}
    return {"scores": clean, "complete": len(clean) == len(CRITERIA), "causal": bool(data.get("affirmation_causale_non_etayee")),
            "hallucination": bool(data.get("hallucination")), "comment": str(data.get("commentaire") or "")[:400],
            "call": {"latency_s": out.latency_s, "usage": out.usage, "cost": out.cost, "cached": out.cached}}


def models_used(s, override: dict | None = None) -> dict:
    cfg = ROOT / "quality/llm_benchmark_config.json"
    m = {"a": s.llm_model_a, "b": s.llm_model_b, "judge": s.llm_judge_model}
    if cfg.exists():
        m.update(json.loads(cfg.read_text(encoding="utf-8")))
    m.update({k: v for k, v in (override or {}).items() if v})
    return m


def run(max_calls: int, pause_s: float, override: dict | None = None) -> None:
    s = load_settings()
    used = models_used(s, override)
    (ROOT / "quality/llm_benchmark_config.json").write_text(json.dumps(used, indent=2), encoding="utf-8")
    cases = json.loads((ROOT / "docs/reference_cases/cases.json").read_text(encoding="utf-8"))["cases"]
    runs = ROOT / "quality/llm_benchmark_runs"
    runs.mkdir(parents=True, exist_ok=True)
    slots = {"a": used["a"], "b": used["b"]}
    judge_prov = provider(s, used["judge"]) if used.get("judge") else None
    ag = SellerAuditAgent(ROOT)
    calls = 0
    for c in cases:
        rep_obj = ag.audit(c["seller_id"], c["month"], use_llm=False)
        report, evidence = jsonable(rep_obj.to_dict()), evidence_snapshot(ag.log)
        for slot, mid in slots.items():
            f = runs / f"{c['case_id']}_{slot}.json"
            rec = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"case_id": c["case_id"], "category": c["category"], "slot": slot, "model": mid}
            if rec.get("model") != mid:
                rec = {"case_id": c["case_id"], "category": c["category"], "slot": slot, "model": mid}
            if rec.get("analysis") is None:
                if calls >= max_calls:
                    continue
                calls += 1
                try:
                    res = analyse(provider(s, mid), report, evidence).to_dict()
                    rec.update({"analysis": res, "error": None})
                    calls -= res["call"]["cached"]
                except LLMError as e:
                    rec.update({"analysis": None, "error": {"kind": e.kind, "message": str(e)[:300], "at": time.time()}})
                f.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"{c['case_id']} {slot}: {'ok' if rec.get('analysis') else rec['error']['kind']}", flush=True)
                time.sleep(pause_s)
            if rec.get("analysis") and judge_prov and not (rec.get("judge") or {}).get("complete"):
                if calls >= max_calls:
                    continue
                calls += 1
                try:
                    rec["judge"] = judge(judge_prov, report, evidence, rec["analysis"])
                    calls -= rec["judge"]["call"]["cached"]
                    rec["judge_error"] = None
                except LLMError as e:
                    rec["judge_error"] = {"kind": e.kind, "message": str(e)[:300]}
                f.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"{c['case_id']} {slot} juge: {'ok' if rec.get('judge') and not rec.get('judge_error') else rec['judge_error']['kind']}", flush=True)
                time.sleep(pause_s)
    print(f"appels non mis en cache utilisés : {calls} (budget {max_calls})")


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return round(st.mean(xs), 3) if xs else None


def report() -> dict:
    s = load_settings()
    cases = json.loads((ROOT / "docs/reference_cases/cases.json").read_text(encoding="utf-8"))["cases"]
    runs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "quality/llm_benchmark_runs").glob("*.json"))]
    out = {"models": models_used(s), "n_cases": len(cases), "budget_usd": 0, "per_model": {}, "configured_in_env": {"a": s.llm_model_a, "b": s.llm_model_b, "judge": s.llm_judge_model}}
    calls_log = ROOT / "data/model/llm_calls.jsonl"
    statuses: dict = {}
    if calls_log.exists():
        for line in calls_log.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            statuses.setdefault(e.get("model"), Counter())[str(e.get("status"))] += 1
    out["call_statuses_by_model"] = {k: dict(v) for k, v in statuses.items()}
    for slot in ("a", "b"):
        rs = [r for r in runs if r["slot"] == slot and r.get("model") == out["models"][slot]]
        ok = [r for r in rs if r.get("analysis")]
        an = [r["analysis"] for r in ok]
        reasons = Counter(p.split(" :")[0] for a in an for x in a["rejected"] for p in x["problems"])
        js = [r["judge"] for r in ok if r.get("judge") and r["judge"].get("complete")]
        out["per_model"][slot] = {
            "model": out["models"][slot], "cases_attempted": len(rs), "cases_ok": len(ok),
            "failures": dict(Counter(r["error"]["kind"] for r in rs if r.get("error"))),
            "schema_ok_rate": _mean([1.0 if a["schema_ok"] else 0.0 for a in an]),
            "grounding_rate_mean": _mean([a["stats"]["grounding_rate"] for a in an]),
            "items_valid_mean": _mean([a["stats"]["items_valid"] for a in an]), "items_rejected_mean": _mean([a["stats"]["items_rejected"] for a in an]),
            "rejection_reasons": dict(reasons.most_common(8)),
            "hypotheses_mean": _mean([len(a["sections"].get("hypotheses", [])) for a in an]), "actions_mean": _mean([len(a["actions"]) for a in an]),
            "latency_s_median": round(st.median([a["call"]["latency_s"] for a in an if not a["call"]["cached"]]), 1) if any(not a["call"]["cached"] for a in an) else None,
            "tokens_mean": _mean([(a["call"]["usage"] or {}).get("total_tokens") for a in an]),
            "cost_total_usd": round(sum(a["call"]["cost"] for a in an), 6),
            "judge_cases": len(js), "judge_scores_mean": {c: _mean([j["scores"][c] for j in js]) for c in CRITERIA},
            "judge_overall_mean": _mean([st.mean(j["scores"].values()) for j in js]),
            "judge_causal_flags": sum(j["causal"] for j in js), "judge_hallucination_flags": sum(j["hallucination"] for j in js),
            "by_category": {cat: {"ok": sum(1 for r in ok if r["category"] == cat),
                                  "grounding": _mean([r["analysis"]["stats"]["grounding_rate"] for r in ok if r["category"] == cat])}
                            for cat in sorted({c["category"] for c in cases})},
        }
    pa, pb = out["per_model"]["a"], out["per_model"]["b"]
    enough = min(pa["cases_ok"], pb["cases_ok"]) >= 5 and min(pa["judge_cases"], pb["judge_cases"]) >= 5
    if enough:
        key = lambda p: (p["grounding_rate_mean"] or 0, p["judge_overall_mean"] or 0, -sum(p["failures"].values()))  # noqa: E731
        best = "a" if key(pa) >= key(pb) else "b"
        out["selection"] = {"selected_slot": best, "model": out["models"][best],
                            "rule": "taux d'éléments validés moyen, puis note moyenne du juge, puis moins d'échecs (mesures sur les mêmes cas)"}
    else:
        out["selection"] = {"selected_slot": None, "rule": "au moins 5 cas analysés ET jugés par modèle requis ; relancer le banc d'essai (quota gratuit journalier)"}
    (ROOT / "quality/llm_benchmark.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(out)
    return out


def write_markdown(o: dict) -> None:
    pm = o["per_model"]
    rows = [("Modèle", pm["a"]["model"], pm["b"]["model"]),
            ("Cas analysés / tentés", f"{pm['a']['cases_ok']} / {pm['a']['cases_attempted']}", f"{pm['b']['cases_ok']} / {pm['b']['cases_attempted']}"),
            ("Échecs (motif)", json.dumps(pm["a"]["failures"], ensure_ascii=False) or "—", json.dumps(pm["b"]["failures"], ensure_ascii=False) or "—"),
            ("JSON conforme", pm["a"]["schema_ok_rate"], pm["b"]["schema_ok_rate"]),
            ("Taux d'éléments validés (moyenne)", pm["a"]["grounding_rate_mean"], pm["b"]["grounding_rate_mean"]),
            ("Éléments validés / rejetés (moyenne)", f"{pm['a']['items_valid_mean']} / {pm['a']['items_rejected_mean']}", f"{pm['b']['items_valid_mean']} / {pm['b']['items_rejected_mean']}"),
            ("Hypothèses / actions (moyenne)", f"{pm['a']['hypotheses_mean']} / {pm['a']['actions_mean']}", f"{pm['b']['hypotheses_mean']} / {pm['b']['actions_mean']}"),
            ("Latence médiane (s)", pm["a"]["latency_s_median"], pm["b"]["latency_s_median"]),
            ("Jetons par analyse (moyenne)", pm["a"]["tokens_mean"], pm["b"]["tokens_mean"]),
            ("Coût total ($)", pm["a"]["cost_total_usd"], pm["b"]["cost_total_usd"]),
            ("Cas jugés", pm["a"]["judge_cases"], pm["b"]["judge_cases"]),
            ("Note moyenne du juge (1–5)", pm["a"]["judge_overall_mean"], pm["b"]["judge_overall_mean"]),
            *[(f"— {c}", pm["a"]["judge_scores_mean"][c], pm["b"]["judge_scores_mean"][c]) for c in CRITERIA],
            ("Signalements juge : causalité / hallucination", f"{pm['a']['judge_causal_flags']} / {pm['a']['judge_hallucination_flags']}",
             f"{pm['b']['judge_causal_flags']} / {pm['b']['judge_hallucination_flags']}")]
    sel = o["selection"]
    md = ["# Banc d'essai des modèles gratuits (analyse vendeur BO3)", "",
          f"Cas de référence : {o['n_cases']} (`docs/reference_cases/`). Juge : `{o['models']['judge']}` (famille différente). Budget : 0 $ (modèles « :free » vérifiés avant chaque appel).",
          "Le juge évalue la qualité rédactionnelle de la sortie **validée** ; il ne juge ni les chiffres ni les alertes, contrôlés de façon déterministe.", "",
          "| Mesure | Modèle A | Modèle B |", "|---|---|---|", *[f"| {a} | {b} | {c} |" for a, b, c in rows], "",
          "**Rejets les plus fréquents** — A : " + json.dumps(pm["a"]["rejection_reasons"], ensure_ascii=False) + " ; B : " + json.dumps(pm["b"]["rejection_reasons"], ensure_ascii=False), "",
          "## Disponibilité mesurée des modèles gratuits (journal des appels)", "",
          *[f"- `{m}` : " + ", ".join(f"HTTP {k} × {v}" for k, v in sorted(c.items())) for m, c in o.get("call_statuses_by_model", {}).items()], "",
          (f"Modèles configurés dans `.env` : {o['configured_in_env']}. " if o.get("configured_in_env") != {k: o['models'].get(k) for k in ("a", "b", "judge")} else "")
          + "Un modèle limité en amont (HTTP 429) sur tous les essais est remplacé pour le banc d'essai par un autre modèle gratuit d'une famille différente, "
            "de façon explicite (`--model-a` / `--model-b`), jamais automatiquement.", "",
          "## Sélection", "",
          (f"Modèle retenu : **{sel['model']}** (règle : {sel['rule']})." if sel.get("selected_slot") else f"Pas de sélection : {sel['rule']}."), "",
          "## Limites", "",
          "- Modèles gratuits : quotas journaliers et limitations de débit en amont ; les échecs sont comptés tels quels, sans substitution de modèle.",
          "- Le juge est lui-même un LLM (biais possibles) ; ses notes doivent être comparées à la revue humaine (`review_form.csv`, en attente).",
          "- Les cas sont choisis par règles déterministes sur une seule période (TEST avr.–juin 2018)."]
    (ROOT / "quality/llm_benchmark.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def compare_human(path: Path) -> None:
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig"), delimiter=";"))
    filled = [r for r in rows if any((r.get(c) or "").strip() for c in CRITERIA)]
    if not filled:
        print("Formulaire non rempli : comparaison juge / humain en attente.")
        return
    runs = {(p.stem.split("_")[0], p.stem.split("_")[1]): json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "quality/llm_benchmark_runs").glob("*.json")}
    diffs = {c: [] for c in CRITERIA}
    for r in filled:
        j = (runs.get((r["case_id"], r["model"])) or {}).get("judge") or {}
        for c in CRITERIA:
            if (r.get(c) or "").strip() and c in j.get("scores", {}):
                diffs[c].append(abs(int(r[c]) - j["scores"][c]))
    res = {c: {"n": len(v), "mae": round(st.mean(v), 2) if v else None, "exact_agreement": round(sum(x == 0 for x in v) / len(v), 2) if v else None} for c, v in diffs.items()}
    (ROOT / "quality/llm_judge_vs_human.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--max-calls", type=int, default=40, help="appels non mis en cache autorisés pour cette exécution (quota gratuit)")
    ap.add_argument("--pause", type=float, default=4.0, help="pause entre appels (limite par minute)")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--compare-human", type=Path)
    ap.add_argument("--model-a", help="remplace LLM_MODEL_A pour ce banc d'essai (modèle :free)")
    ap.add_argument("--model-b", help="remplace LLM_MODEL_B pour ce banc d'essai (modèle :free)")
    ap.add_argument("--judge", help="remplace LLM_JUDGE_MODEL pour ce banc d'essai (modèle :free)")
    a = ap.parse_args()
    if a.compare_human:
        compare_human(a.compare_human)
        return
    if not a.report_only:
        run(a.max_calls, a.pause, {"a": a.model_a, "b": a.model_b, "judge": a.judge})
    o = report()
    print(json.dumps({k: {x: o["per_model"][k][x] for x in ("cases_ok", "failures", "grounding_rate_mean", "judge_overall_mean")} for k in ("a", "b")},
                     ensure_ascii=False), o["selection"])


if __name__ == "__main__":
    main()
