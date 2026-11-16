"""Lance les agents REHEARSE en ligne de commande.

  python src/run_agents.py bo1 --project-dir . --order <order_id> [--audit]
  python src/run_agents.py bo1 --project-dir . --triage 2018-06 [--target late|poor] [--audit]
  python src/run_agents.py bo2 --project-dir . --month 2018-03 [--state AL] [--category cama_mesa_banho]
  python src/run_agents.py bo2 --project-dir . --ask "Y a-t-il de nouvelles plaintes en juillet 2018 ?"

LLM optionnel (serveur compatible OpenAI, par ex. vLLM) : --llm-url http://localhost:8000/v1 --llm-model <nom>
Sans LLM, tout fonctionne en mode déterministe (mêmes outils, mêmes preuves).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agents.bo1_agent import PreventiveDiagnosisAgent  # noqa: E402
from agents.bo2_agent import VoiceOfCustomerAgent  # noqa: E402
from agents.core import LLMClient  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("agent", choices=["bo1", "bo2"])
    ap.add_argument("--project-dir", type=Path, default=Path("."))
    ap.add_argument("--llm-url")
    ap.add_argument("--llm-model")
    ap.add_argument("--json", type=Path, help="écrit aussi le rapport en JSON")
    ap.add_argument("--ask", help="question en langage naturel")
    ap.add_argument("--order")
    ap.add_argument("--triage", metavar="AAAA-MM")
    ap.add_argument("--target", choices=["late", "poor"], default="late")
    ap.add_argument("--audit", action="store_true", help="BO1 : affiche aussi l'issue réelle (évaluation rétrospective uniquement)")
    ap.add_argument("--top-k", type=int, default=20)
    ap.add_argument("--month")
    ap.add_argument("--state")
    ap.add_argument("--category")
    a = ap.parse_args()
    llm = LLMClient(a.llm_url, a.llm_model) if a.llm_url and a.llm_model else None

    if a.agent == "bo1":
        ag = PreventiveDiagnosisAgent(a.project_dir, llm)
        if a.order:
            rep = ag.diagnose(a.order, audit=a.audit)
        elif a.triage:
            rep = ag.triage(a.triage, a.top_k, a.target, audit=a.audit)
        elif a.ask:
            rep = ag.ask(a.ask, audit=a.audit)
        else:
            ap.error("bo1 : --order, --triage ou --ask requis")
    else:
        ag = VoiceOfCustomerAgent(a.project_dir, llm)
        rep = ag.ask(a.ask) if a.ask else ag.report(a.month, a.state, a.category)
    print(rep.to_markdown())
    if a.json:
        a.json.write_text(json.dumps(rep.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
