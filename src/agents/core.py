"""Briques communes aux agents REHEARSE.

Principe de conception (exigence du projet) : chaque agent sépare
  1. les FAITS observés dans les données,
  2. les ESTIMATIONS produites par un modèle,
  3. les EXPÉRIENCES d'autres clients (commandes ou avis comparables),
et cite les enregistrements utilisés (identifiants de preuve).

Pour garantir cela même avec un LLM :
  - les outils (fonctions Python) sont la seule source de chiffres ;
  - chaque sortie d'outil est inscrite dans un `EvidenceLog` avec un identifiant ;
  - le rapport est assemblé de façon déterministe à partir de ce journal ;
  - le LLM (optionnel, serveur compatible OpenAI, ex. vLLM) ne sert qu'à choisir les outils et à rédiger
    un résumé, qui est VÉRIFIÉ (`verify_narrative`) : tout chiffre absent des preuves le fait rejeter.
"""
from __future__ import annotations

import gzip
import json
import re
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------------------
# Preuves et rapport
# --------------------------------------------------------------------------------------
FACT, ESTIMATE, SIMILAR = "fait", "estimation", "experience_autres_clients"


@dataclass
class Evidence:
    id: str
    kind: str          # FACT | ESTIMATE | SIMILAR
    source: str        # fichier / modèle d'où vient l'information
    payload: dict


class EvidenceLog:
    def __init__(self) -> None:
        self._items: dict[str, Evidence] = {}
        self.tool_calls: list[dict] = []

    def add(self, id: str, kind: str, source: str, payload: dict) -> str:
        self._items[id] = Evidence(id, kind, source, payload)
        return id

    def get(self, id: str) -> Evidence | None:
        return self._items.get(id)

    def by_kind(self, kind: str) -> list[Evidence]:
        return [e for e in self._items.values() if e.kind == kind]

    def with_prefix(self, prefix: str) -> list[Evidence]:
        return [e for e in self._items.values() if e.id.startswith(prefix)]

    def ids(self) -> set[str]:
        return set(self._items)

    def numbers(self) -> set[float]:
        out: set[float] = set()

        def walk(x: Any) -> None:
            if isinstance(x, bool) or x is None:
                return
            if isinstance(x, (int, float, np.integer, np.floating)):
                v = float(x)
                if np.isfinite(v):
                    out.update({v, v * 100, abs(v)})
            elif isinstance(x, dict):
                for v in x.values():
                    walk(v)
            elif isinstance(x, (list, tuple)):
                for v in x:
                    walk(v)
            elif isinstance(x, str):
                for m in _NUM.findall(_strip_ids(x)):
                    out.add(_to_float(m))

        for e in self._items.values():
            walk(e.payload)
        return out


@dataclass
class Line:
    text: str
    evidence: list[str] = field(default_factory=list)


@dataclass
class Report:
    title: str
    facts: list[Line] = field(default_factory=list)
    estimates: list[Line] = field(default_factory=list)
    similar: list[Line] = field(default_factory=list)
    actions: list[Line] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    narrative: str = ""
    narrative_source: str = "deterministe"
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"title": self.title, "narrative": self.narrative, "narrative_source": self.narrative_source,
                "facts": [vars(x) for x in self.facts], "estimates": [vars(x) for x in self.estimates],
                "similar_experiences": [vars(x) for x in self.similar], "actions": [vars(x) for x in self.actions],
                "caveats": self.caveats, "meta": self.meta}

    def to_markdown(self) -> str:
        def block(name: str, lines: list[Line]) -> str:
            if not lines:
                return ""
            body = "\n".join(f"- {l.text}" + (f"  `[{', '.join(l.evidence)}]`" if l.evidence else "") for l in lines)
            return f"\n## {name}\n{body}\n"

        md = f"# {self.title}\n"
        if self.narrative:
            md += f"\n{self.narrative}\n"
        md += block("Faits observés (données)", self.facts)
        md += block("Estimations du modèle", self.estimates)
        md += block("Expériences d'autres clients", self.similar)
        md += block("Actions suggérées (hypothèses à valider)", self.actions)
        if self.caveats:
            md += "\n## Limites\n" + "\n".join(f"- {c}" for c in self.caveats) + "\n"
        return md


# --------------------------------------------------------------------------------------
# Vérification du résumé rédigé par un LLM
# --------------------------------------------------------------------------------------
_NUM = re.compile(r"\d+(?:[.,]\d+)?")
_ID = re.compile(r"\b[0-9a-f]{32}\b|\b\d{4}-\d{2}(?:-\d{2})?\b|\b(?:ord|rev|kpi|mdl|ctx):[\w:.\-]+")


def _strip_ids(s: str) -> str:
    return _ID.sub(" ", s)


def _to_float(m: str) -> float:
    return float(m.replace(",", "."))


def verify_narrative(text: str, log: EvidenceLog, rel_tol: float = 0.011, small_ints: int = 10) -> tuple[bool, list[str]]:
    """Tout nombre du résumé doit exister dans les preuves (arrondi toléré) ; tout identifiant cité doit exister."""
    problems: list[str] = []
    allowed = log.numbers()
    for m in _NUM.findall(_strip_ids(text)):
        v = _to_float(m)
        if v <= small_ints and float(v).is_integer():
            continue
        if not any(abs(v - a) <= max(0.051, rel_tol * abs(a)) for a in allowed):
            problems.append(f"chiffre non sourcé : {m}")
    for ref in re.findall(r"\b(?:ord|rev|kpi|mdl|ctx):[\w:.\-]+", text):
        if ref not in log.ids():
            problems.append(f"preuve inconnue : {ref}")
    return (not problems), problems


# --------------------------------------------------------------------------------------
# Accès aux données (fichiers produits par prepare_data.py / build_model_features.py / translate_reviews.py)
# --------------------------------------------------------------------------------------
class DataStore:
    def __init__(self, project_dir: str | Path = ".") -> None:
        self.dir = Path(project_dir).resolve()
        self._cache: dict[str, Any] = {}

    def _p(self, rel: str) -> Path:
        return self.dir / rel

    def _csv(self, key: str, rel: str, **kw) -> pd.DataFrame:
        if key not in self._cache:
            path = self._p(rel)
            if not path.exists():
                raise FileNotFoundError(f"{rel} introuvable : lancez d'abord le pipeline (prepare_data.py, build_model_features.py).")
            self._cache[key] = pd.read_csv(path, **kw)
        return self._cache[key]

    @property
    def orders(self) -> pd.DataFrame:
        if "orders" not in self._cache:
            df = self._csv("orders_raw", "data/silver/orders_analysis.csv.gz", low_memory=False,
                           parse_dates=["order_purchase_timestamp", "order_estimated_delivery_date", "order_delivered_customer_date",
                                       "review_answer_timestamp"])
            # conversion explicite : selon la version de pandas, parse_dates peut laisser une colonne en texte (formats mixtes)
            for c in ("order_purchase_timestamp", "order_approved_at", "order_estimated_delivery_date", "order_delivered_customer_date",
                      "review_answer_timestamp"):
                if c in df.columns:
                    df[c] = pd.to_datetime(df[c], errors="coerce", format="mixed")
            self._cache["orders"] = df.set_index("order_id", drop=False)
        return self._cache["orders"]

    def features(self, split: str) -> pd.DataFrame:
        return self._csv(f"feat_{split}", f"data/model/features_{split}.csv.gz", parse_dates=["order_purchase_timestamp"])

    @property
    def all_features(self) -> pd.DataFrame:
        if "feat_all" not in self._cache:
            parts = []
            for s in ("train", "valid", "test"):
                f = self.features(s).copy()
                f["split"] = s
                parts.append(f)
            df = pd.concat(parts, ignore_index=True)
            self._cache["feat_all"] = df.set_index("order_id", drop=False)
        return self._cache["feat_all"]

    @property
    def monthly(self) -> pd.DataFrame:
        return self._csv("monthly", "data/gold/monthly_business_kpis.csv")

    @property
    def state_monthly(self) -> pd.DataFrame:
        return self._csv("state_monthly", "data/gold/state_monthly_kpis.csv.gz")

    @property
    def category_monthly(self) -> pd.DataFrame:
        return self._csv("category_monthly", "data/gold/category_monthly_kpis.csv.gz")

    @property
    def seller_monthly(self) -> pd.DataFrame:
        return self._csv("seller_monthly", "data/silver/seller_monthly_kpis.csv.gz")

    def reviews(self) -> pd.DataFrame:
        """Avis texte à plat. Utilise la version traduite si elle existe (originaux conservés)."""
        if "reviews" in self._cache:
            return self._cache["reviews"]
        fr = self._p("data/silver/reviews_text_fr.jsonl.gz")
        pt = self._p("data/silver/reviews_text.jsonl.gz")
        path = fr if fr.exists() else pt
        if not path.exists():
            raise FileNotFoundError("reviews_text(.fr).jsonl.gz introuvable.")
        rows = []
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                meta = d.get("metadata") or {}
                rows.append({
                    "review_id": d["review_id"], "order_id": d["order_id"], "score": d["review_score"],
                    "title_pt": d.get("title_original_pt", d.get("title")) or "",
                    "text_pt": d.get("text_original_pt", d.get("text")) or "",
                    "title_fr": d.get("title_fr") or "", "text_fr": d.get("text_fr") or "",
                    "translation_status": d.get("translation_status", "absent"),
                    "month": meta.get("purchase_month"), "state": meta.get("customer_state"),
                    "category": meta.get("primary_category"), "is_late": meta.get("is_late"),
                    "has_message": d.get("has_message", bool(d.get("text"))),
                    # BO4 point-in-time retrieval needs the timestamp of each
                    # individual review, not the order-level selected review.
                    "review_created_at": d.get("review_created_at") or meta.get("review_created_at"),
                    "review_answered_at": d.get("review_answered_at") or meta.get("review_answered_at"),
                })
        df = pd.DataFrame(rows)
        for c in ("review_created_at", "review_answered_at"):
            df[c] = pd.to_datetime(df[c], errors="coerce", utc=True).dt.tz_localize(None)
        df["full_pt"] = (df["title_pt"].str.strip() + ". " + df["text_pt"].str.strip()).str.strip(". ").str.strip()
        df["full_fr"] = (df["title_fr"].str.strip() + ". " + df["text_fr"].str.strip()).str.strip(". ").str.strip()
        self._cache["reviews"] = df
        return df


# --------------------------------------------------------------------------------------
# Client LLM optionnel (API compatible OpenAI : vLLM, etc.) — sans dépendance externe
# --------------------------------------------------------------------------------------
class LLMClient:
    def __init__(self, base_url: str, model: str, api_key: str = "EMPTY", timeout: int = 120, temperature: float = 0.0) -> None:
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model, self.key, self.timeout, self.temperature = model, api_key, timeout, temperature

    def chat(self, messages: list[dict], tools: list[dict] | None = None, max_tokens: int = 700) -> dict:
        body: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": self.temperature, "max_tokens": max_tokens}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        req = urllib.request.Request(self.url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.key}"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read())["choices"][0]["message"]


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    fn: Callable[..., Any]

    def schema(self) -> dict:
        return {"type": "function", "function": {"name": self.name, "description": self.description, "parameters": self.parameters}}


def run_tool_loop(llm: LLMClient, system: str, user: str, tools: list[Tool], log: EvidenceLog, max_steps: int = 6) -> str | None:
    """Boucle outils : le LLM choisit les outils ; chaque appel est journalisé. Retourne le texte final du LLM."""
    by_name = {t.name: t for t in tools}
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    for _ in range(max_steps):
        msg = llm.chat(messages, [t.schema() for t in tools])
        calls = msg.get("tool_calls") or []
        if not calls:
            return msg.get("content")
        messages.append(msg)
        for c in calls:
            name = c["function"]["name"]
            try:
                args = json.loads(c["function"].get("arguments") or "{}")
                out = by_name[name].fn(**args)
                log.tool_calls.append({"tool": name, "args": args, "ok": True})
                content = json.dumps(out, ensure_ascii=False, default=str)[:6000]
            except Exception as exc:  # l'erreur est renvoyée au LLM, jamais masquée
                log.tool_calls.append({"tool": name, "args": c["function"].get("arguments"), "ok": False, "error": str(exc)})
                content = json.dumps({"error": str(exc)})
            messages.append({"role": "tool", "tool_call_id": c.get("id", name), "content": content})
    return None


def month_label(m: str) -> str:
    return m


def pct(x: float, nd: int = 1) -> str:
    return f"{100 * x:.{nd}f} %"


def to_native(o: Any) -> Any:
    if isinstance(o, dict):
        return {k: to_native(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [to_native(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, (pd.Timestamp,)):
        return o.isoformat()
    if isinstance(o, float) and np.isnan(o):
        return None
    return o
