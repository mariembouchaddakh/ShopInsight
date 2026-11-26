"""BO3 — compléments propres à l'agent vendeur, SANS modifier core.py (partagé avec BO1/BO2).

  BO3Report              rapport avec titres de sections adaptés aux vendeurs (sous-classe de core.Report)
  verify_bo3_narrative   vérification d'un résumé LLM : core.verify_narrative + identifiants de preuve BO3 (sel:, peer:, alr:)
                         et préfixes d'identifiant vendeur (8 caractères hexadécimaux), qui ne sont pas des chiffres
  load_multi_seller_links  lecture de silver/multi_seller_order_links.csv.gz (dates converties)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .core import EvidenceLog, Report, verify_narrative

_BO3_REF = re.compile(r"\b(?:sel|peer|alr):[\w:.\-]+")
_HEX_PREFIX = re.compile(r"\b[0-9a-f]{8,31}\b")
# Date en toutes lettres (« fin juin 2018 ») : une date, pas une mesure ; l'année n'est donc pas vérifiée comme un chiffre.
_MONTH_YEAR = re.compile(r"\b(?:janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+20\d{2}\b", re.I)

DEFAULT_TITLES = {"facts": "Faits observés (données)", "estimates": "Estimations du modèle", "similar": "Expériences d'autres clients",
                  "actions": "Actions suggérées (hypothèses à valider)"}


@dataclass
class BO3Report(Report):
    section_titles: dict = field(default_factory=dict)

    def to_markdown(self) -> str:
        def block(name, lines):
            if not lines:
                return ""
            body = "\n".join(f"- {l.text}" + (f"  `[{', '.join(l.evidence)}]`" if l.evidence else "") for l in lines)
            return f"\n## {name}\n{body}\n"

        t = {**DEFAULT_TITLES, **self.section_titles}
        md = f"# {self.title}\n"
        if self.narrative:
            md += f"\n{self.narrative}\n"
        md += block(t["facts"], self.facts) + block(t["estimates"], self.estimates) + block(t["similar"], self.similar) + block(t["actions"], self.actions)
        if self.caveats:
            md += "\n## Limites\n" + "\n".join(f"- {c}" for c in self.caveats) + "\n"
        return md

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["section_titles"] = {**DEFAULT_TITLES, **self.section_titles}
        return d


def verify_bo3_narrative(text: str, log: EvidenceLog) -> tuple[bool, list[str]]:
    """Comme core.verify_narrative, en reconnaissant aussi les preuves BO3 et les préfixes d'identifiant vendeur."""
    problems = [f"preuve inconnue : {r}" for r in _BO3_REF.findall(text) if r not in log.ids()]
    cleaned = _MONTH_YEAR.sub(" ", _HEX_PREFIX.sub(" ", _BO3_REF.sub(" ", text)))
    ok, more = verify_narrative(cleaned, log)
    return (ok and not problems), problems + more


def load_multi_seller_links(project_dir: str | Path) -> pd.DataFrame:
    path = Path(project_dir) / "data/silver/multi_seller_order_links.csv.gz"
    if not path.exists():
        return pd.DataFrame(columns=["order_id", "seller_id", "purchase_month", "seller_price_share"])
    df = pd.read_csv(path)
    if "seller_shipping_limit_max" in df.columns:
        df["seller_shipping_limit_max"] = pd.to_datetime(df["seller_shipping_limit_max"], errors="coerce", format="mixed")
    return df
