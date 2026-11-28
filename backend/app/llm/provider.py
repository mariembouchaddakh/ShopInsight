"""Fournisseur LLM : OpenRouter, modèles GRATUITS uniquement (budget d'inférence strictement 0 $).

Garde-fous appliqués à CHAQUE appel :
  * identifiant de modèle explicite, suffixe « :free » obligatoire ; pas de routage automatique côté OpenRouter
    (`provider.allow_fallbacks = false`, aucun champ `models`) : le repli éventuel est fait ICI, en Python (FailoverFreeProvider),
    sur une liste ordonnée de modèles « :free », chacun repassant tous les contrôles ci-dessous avant d'être appelé ;
  * vérification EN DIRECT dans le catalogue OpenRouter que les prix (entrée, sortie, requête) valent exactement 0 ;
  * le modèle renvoyé doit être celui demandé, et le coût déclaré dans `usage.cost` doit valoir 0 ; sinon la réponse est rejetée ;
  * nouvelles tentatives bornées (429 / 5xx), cache disque (une requête identique ne consomme pas de quota), journal des appels sans secret.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol

import httpx

log = logging.getLogger("shopinsight.llm")
CATALOG_URL = "https://openrouter.ai/api/v1/models"
CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"


class LLMError(RuntimeError):
    """kind : no_key | not_free | rate_limited | quota_exhausted | unavailable | bad_response | substituted | not_zero_cost"""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass
class LLMResult:
    content: str
    model_requested: str
    model_returned: str
    latency_s: float
    usage: dict = field(default_factory=dict)
    cost: float = 0.0
    cached: bool = False
    attempts: int = 1
    model_used: str = ""                                  # modèle qui a réellement servi la réponse (repli compris)
    candidates_tried: list = field(default_factory=list)  # [{"model", "error" | "status"}] dans l'ordre d'essai
    tool_calls: list = field(default_factory=list)


class LLMProvider(Protocol):
    model: str

    def complete(self, messages: list[dict], *, max_tokens: int = 3000, temperature: float = 0.0, json_mode: bool = True,
                 tools: list[dict] | None = None, tool_choice: str | dict | None = None) -> LLMResult: ...


_CATALOG: dict = {"at": 0.0, "models": {}}


def fetch_catalog(client: httpx.Client, ttl: float = 600.0) -> dict[str, dict]:
    if time.time() - _CATALOG["at"] > ttl or not _CATALOG["models"]:
        r = client.get(CATALOG_URL, timeout=30)
        r.raise_for_status()
        _CATALOG["models"] = {m["id"]: m for m in r.json()["data"]}
        _CATALOG["at"] = time.time()
    return _CATALOG["models"]


def is_free(model: dict) -> bool:
    p = model.get("pricing") or {}
    try:
        return all(float(p.get(k) or 0) == 0.0 for k in ("prompt", "completion", "request", "image", "web_search", "internal_reasoning"))
    except (TypeError, ValueError):
        return False


class OpenRouterFreeProvider:
    def __init__(self, api_key: str | None, model: str, cache_dir: Path, call_log: Path | None = None, max_retries: int = 3,
                 timeout: float = 180.0, backoff_s: float = 4.0, client: httpx.Client | None = None) -> None:
        self._key = api_key
        self.model = model
        self.cache_dir = Path(cache_dir)
        self.call_log = call_log
        self.max_retries = max_retries
        self.timeout = timeout
        self.backoff_s = backoff_s
        self.client = client or httpx.Client()

    def __repr__(self) -> str:  # jamais la clé
        return f"OpenRouterFreeProvider(model={self.model!r}, key={'configurée' if self._key else 'absente'})"

    def verify_free(self) -> dict:
        if not self.model.endswith(":free"):
            raise LLMError("not_free", f"{self.model} n'est pas une variante « :free » : appel refusé (budget 0 $).")
        try:
            catalog = fetch_catalog(self.client)
        except httpx.HTTPError as e:
            raise LLMError("unavailable", f"catalogue OpenRouter injoignable : {e}") from e
        m = catalog.get(self.model)
        if m is None:
            raise LLMError("unavailable", f"{self.model} absent du catalogue OpenRouter.")
        if not is_free(m):
            raise LLMError("not_free", f"{self.model} n'est plus gratuit (prix {m.get('pricing')}) : appel refusé.")
        return m

    def _record(self, entry: dict) -> None:
        if self.call_log is None:
            return
        self.call_log.parent.mkdir(parents=True, exist_ok=True)
        with self.call_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def complete(self, messages: list[dict], *, max_tokens: int = 3000, temperature: float = 0.0, json_mode: bool = True,
                 tools: list[dict] | None = None, tool_choice: str | dict | None = None) -> LLMResult:
        if not self._key:
            raise LLMError("no_key", "OPENROUTER_API_KEY absente : couche IA désactivée (l'audit déterministe reste disponible).")
        body = {"model": self.model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature,
                "provider": {"allow_fallbacks": False},
                # raisonnement interne désactivé : sinon il consomme tout le budget de jetons (contenu vide, mesuré sur Nemotron)
                "reasoning": {"enabled": False}}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = tool_choice or "auto"
        if json_mode and not tools:
            body["response_format"] = {"type": "json_object"}
        h = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:32]
        cache_file = self.cache_dir / f"{h}.json"
        if cache_file.exists():
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            res = LLMResult(**{**data, "cached": True})
            res.model_used = res.model_used or res.model_returned
            return res
        self.verify_free()
        attempts, t0, last = 0, time.time(), ""
        while attempts <= self.max_retries:
            attempts += 1
            try:
                r = self.client.post(CHAT_URL, json=body, timeout=self.timeout,
                                     headers={"Authorization": f"Bearer {self._key}", "Content-Type": "application/json", "X-Title": "ShopInsight"})
            except httpx.HTTPError as e:
                last = f"réseau : {type(e).__name__}"
                time.sleep(self.backoff_s * attempts)
                continue
            if r.status_code == 429 and "per-day" in r.text.lower():
                # quota quotidien du COMPTE (tous modèles gratuits confondus) : ni réessai ni repli n'y changeraient rien
                self._record({"ts": time.time(), "model": self.model, "status": 429, "attempt": attempts, "note": "quota quotidien gratuit épuisé"})
                raise LLMError("quota_exhausted", "quota quotidien des modèles gratuits OpenRouter épuisé pour ce compte.")
            if r.status_code in (429, 500, 502, 503, 504):
                last = f"HTTP {r.status_code}"
                self._record({"ts": time.time(), "model": self.model, "status": r.status_code, "attempt": attempts})
                if attempts <= self.max_retries:
                    time.sleep(self.backoff_s * (2 ** (attempts - 1)))
                continue
            if r.status_code == 400 and "reasoning is mandatory" in r.text.lower() and body["reasoning"].get("enabled") is False:
                # même modèle (pas de repli) : ce point d'accès impose le raisonnement → on l'active, masqué, avec plus de jetons
                body = {**body, "reasoning": {"enabled": True, "exclude": True}, "max_tokens": min(int(body["max_tokens"]) * 2, 16000)}
                self._record({"ts": time.time(), "model": self.model, "status": 400, "attempt": attempts, "note": "raisonnement obligatoire : réessai"})
                attempts -= 1
                continue
            if r.status_code >= 400:
                self._record({"ts": time.time(), "model": self.model, "status": r.status_code, "attempt": attempts})
                raise LLMError("unavailable", f"OpenRouter HTTP {r.status_code} : {r.text[:200]}")
            data = r.json()
            returned = data.get("model") or ""
            usage = data.get("usage") or {}
            cost = float(usage.get("cost") or 0.0)
            if returned and returned != self.model:
                raise LLMError("substituted", f"modèle renvoyé {returned} ≠ demandé {self.model} : réponse rejetée.")
            if cost != 0.0:
                raise LLMError("not_zero_cost", f"coût déclaré {cost} ≠ 0 : réponse rejetée.")
            message = ((data.get("choices") or [{}])[0].get("message") or {})
            content = message.get("content") or ""
            tool_calls = message.get("tool_calls") or []
            if not content.strip() and not tool_calls:
                raise LLMError("bad_response", "réponse vide du modèle.")
            res = LLMResult(content=content, model_requested=self.model, model_returned=returned or self.model, latency_s=round(time.time() - t0, 2),
                            usage={k: usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens")}, cost=cost, attempts=attempts,
                            model_used=returned or self.model, tool_calls=tool_calls)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps({k: v for k, v in asdict(res).items() if k not in ("cached", "candidates_tried")}, ensure_ascii=False),
                                  encoding="utf-8")
            self._record({"ts": time.time(), "model": self.model, "returned": res.model_returned, "status": 200, "attempts": attempts,
                          "latency_s": res.latency_s, "usage": res.usage, "cost": cost})
            return res
        raise LLMError("rate_limited" if "429" in last else "unavailable", f"{self.model} indisponible après {attempts} tentatives ({last}).")


# Erreurs qui font passer au candidat suivant : limite du MODÈLE (429), erreur amont transitoire (5xx), modèle indisponible
# (400 / 404, absent du catalogue), modèle devenu payant, réponse vide, substitution ou coût ≠ 0 (réponse rejetée, rien n'est utilisé).
ROTATE_ON = {"rate_limited", "unavailable", "not_free", "bad_response", "substituted", "not_zero_cost"}


class FailoverFreeProvider:
    """Repli DÉTERMINISTE sur une liste ordonnée de modèles gratuits : [modèle principal] + LLM_FALLBACK_MODELS (sans doublon, ordre conservé).

    Chaque candidat passe par OpenRouterFreeProvider, donc par TOUS les garde-fous (suffixe « :free », prix 0 vérifié en direct dans le
    catalogue AVANT l'appel, `allow_fallbacks = false`, modèle renvoyé = modèle demandé, coût 0). Un candidat en échec est abandonné
    aussitôt (une tentative, aucune longue attente) au profit du suivant. Arrêt immédiat si la clé manque ou si le quota quotidien
    du compte est épuisé (aucun autre modèle gratuit ne répondrait). Chaque essai et le modèle retenu sont journalisés (sans secret).
    """

    def __init__(self, api_key: str | None, models: list[str], cache_dir: Path, call_log: Path | None = None, timeout: float = 180.0,
                 retries_per_model: int = 0, backoff_s: float = 0.5, client: httpx.Client | None = None) -> None:
        self.candidates = list(dict.fromkeys(m.strip() for m in models if m and m.strip()))
        if not self.candidates:
            raise ValueError("aucun modèle configuré")
        self.primary = self.candidates[0]
        self.model = self.primary  # devient le modèle qui a servi la dernière réponse
        self.client = client or httpx.Client()
        self._providers = [OpenRouterFreeProvider(api_key, m, cache_dir, call_log, max_retries=retries_per_model, timeout=timeout,
                                                  backoff_s=backoff_s, client=self.client) for m in self.candidates]

    def __repr__(self) -> str:  # jamais la clé
        return f"FailoverFreeProvider(candidates={self.candidates!r})"

    def _record(self, entry: dict) -> None:
        self._providers[0]._record(entry)

    def complete(self, messages: list[dict], *, max_tokens: int = 3000, temperature: float = 0.0, json_mode: bool = True,
                 tools: list[dict] | None = None, tool_choice: str | dict | None = None) -> LLMResult:
        tried: list[dict] = []
        for p in self._providers:
            try:
                res = p.complete(messages, max_tokens=max_tokens, temperature=temperature, json_mode=json_mode,
                                 tools=tools, tool_choice=tool_choice)
            except LLMError as e:
                tried.append({"model": p.model, "error": e.kind})
                if e.kind not in ROTATE_ON:  # no_key, quota_exhausted : inutile d'essayer un autre modèle
                    if e.kind != "no_key":  # sans clé, aucun appel n'a été tenté : rien à journaliser
                        self._record({"ts": time.time(), "event": "failover_stop", "model": p.model, "reason": e.kind, "candidates_tried": tried})
                    raise
                log.warning("modèle %s indisponible (%s) : repli sur le candidat suivant", p.model, e.kind)
                self._record({"ts": time.time(), "event": "failover", "from": p.model, "reason": e.kind})
                continue
            res.model_used = res.model_used or res.model_returned
            res.candidates_tried = [*tried, {"model": p.model, "status": "cache" if res.cached else "ok"}]
            self.model = res.model_used
            self._record({"ts": time.time(), "event": "served", "model_used": res.model_used, "primary": self.primary, "cached": res.cached,
                          "fallback": res.model_used != self.primary, "candidates_tried": res.candidates_tried})
            return res
        kinds = [t["error"] for t in tried]
        kind = "rate_limited" if "rate_limited" in kinds else "not_free" if all(k == "not_free" for k in kinds) else "unavailable"
        self._record({"ts": time.time(), "event": "failover_exhausted", "reason": kind, "candidates_tried": tried})
        raise LLMError(kind, f"aucun des {len(tried)} modèles gratuits n'a répondu ("
                             + ", ".join(f"{t['model']} : {t['error']}" for t in tried) + ").")
