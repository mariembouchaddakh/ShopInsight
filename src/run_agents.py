"""Lance les agents REHEARSE en ligne de commande.

  python src/run_agents.py bo1 --project-dir . --order <order_id> [--audit]
  python src/run_agents.py bo1 --project-dir . --triage 2018-06 [--target late|poor] [--audit]
  python src/run_agents.py bo2 --project-dir . --month 2018-03 [--state AL] [--category cama_mesa_banho]
  python src/run_agents.py bo2 --project-dir . --ask "Y a-t-il de nouvelles plaintes en juillet 2018 ?"
  python src/run_agents.py bo3 --project-dir . --seller <seller_id> [--month 2018-05] [--metric late|poor|handover]
  python src/run_agents.py bo3 --project-dir . --alerts 2018-06 [--metric handover]
  python src/run_agents.py bo3 --project-dir . --ask "Quels vendeurs se dégradent en juin 2018 ?"

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
from agents.bo3_agent import SellerAuditAgent  # noqa: E402
from agents.core import LLMClient  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("agent", choices=["bo1", "bo2", "bo3"])
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
    ap.add_argument("--seller", help="BO3 : identifiant vendeur (ou ses 8 premiers caractères)")
    ap.add_argument("--alerts", metavar="AAAA-MM", help="BO3 : liste des vendeurs en alerte à la fin de ce mois")
    ap.add_argument("--metric", choices=["late", "poor", "handover"], help="BO3 : limiter à un indicateur")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):  # console Windows (cp1252) : « ≈ », « → »… sinon UnicodeEncodeError
        sys.stdout.reconfigure(encoding="utf-8")
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
    elif a.agent == "bo2":
        ag = VoiceOfCustomerAgent(a.project_dir, llm)
        rep = ag.ask(a.ask) if a.ask else ag.report(a.month, a.state, a.category)
    else:
        ag = SellerAuditAgent(a.project_dir, llm)
        if a.seller:
            rep = ag.audit(a.seller, a.month, a.metric)
        elif a.alerts:
            rep = ag.alerts_report(a.alerts, a.metric, a.top_k)
        elif a.ask:
            rep = ag.ask(a.ask)
        else:
            ap.error("bo3 : --seller, --alerts ou --ask requis")
    print(rep.to_markdown())
    if a.json:
        a.json.write_text(json.dumps(rep.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
