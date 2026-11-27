"""Configuration de l'API ShopInsight.

Sources, par ordre de priorité : variables d'environnement, puis fichier `.env` à la racine du projet (ignoré par Git).
La clé OpenRouter n'est JAMAIS affichée : `repr()` la masque et `public()` n'indique que sa présence.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        values[k.strip()] = v.strip().strip('"').strip("'")
    return values


@dataclass(frozen=True)
class Settings:
    project_dir: Path
    warmup: bool = True
    llm_budget_usd: float = 0.0
    llm_free_only: bool = True
    llm_model_a: str | None = None
    llm_model_b: str | None = None
    llm_judge_model: str | None = None
    llm_fallback_models: tuple[str, ...] = ()  # repli ordonné, modèles « :free » uniquement (vérifiés à chaque appel)
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    _openrouter_api_key: str | None = field(default=None, repr=False)
    om5_llm_enabled: bool = False
    om5_llm_provider: str = "groq"
    groq_model: str = "openai/gpt-oss-120b"
    _groq_api_key: str | None = field(default=None, repr=False)
    gemini_model: str = "gemini-2.5-flash"
    _gemini_api_key: str | None = field(default=None, repr=False)

    @property
    def openrouter_api_key(self) -> str | None:
        return self._openrouter_api_key

    @property
    def gemini_api_key(self) -> str | None:
        return self._gemini_api_key

    @property
    def groq_api_key(self) -> str | None:
        return self._groq_api_key

    def public(self) -> dict:
        """Configuration montrable (aucun secret)."""
        return {"project_dir": str(self.project_dir), "warmup": self.warmup, "llm_budget_usd": self.llm_budget_usd,
                "llm_free_only": self.llm_free_only, "llm_models": {"a": self.llm_model_a, "b": self.llm_model_b, "judge": self.llm_judge_model},
                "llm_fallback_models": list(self.llm_fallback_models),
                "openrouter_key_configured": bool(self._openrouter_api_key),
                "om5_llm_enabled": self.om5_llm_enabled, "om5_llm_provider": self.om5_llm_provider,
                "groq_model": self.groq_model, "groq_key_configured": bool(self._groq_api_key), "gemini_model": self.gemini_model,
                "gemini_key_configured": bool(self._gemini_api_key)}


def load_settings() -> Settings:
    env = {**_read_dotenv(ROOT / ".env"), **os.environ}
    project = Path(env.get("SHOPINSIGHT_PROJECT_DIR", str(ROOT)))
    origins = tuple(o.strip() for o in env.get("SHOPINSIGHT_CORS_ORIGINS", "").split(",") if o.strip()) or Settings.cors_origins
    return Settings(project_dir=project, warmup=env.get("SHOPINSIGHT_WARMUP", "1") not in ("0", "false", "False"),
                    llm_budget_usd=float(env.get("LLM_BUDGET_USD", "0") or 0), llm_free_only=env.get("LLM_FREE_ONLY", "true").lower() != "false",
                    llm_model_a=env.get("LLM_MODEL_A") or None, llm_model_b=env.get("LLM_MODEL_B") or None,
                    llm_judge_model=env.get("LLM_JUDGE_MODEL") or None, cors_origins=origins,
                    llm_fallback_models=tuple(dict.fromkeys(m.strip() for m in env.get("LLM_FALLBACK_MODELS", "").split(",") if m.strip())),
                    _openrouter_api_key=env.get("OPENROUTER_API_KEY") or None,
                    om5_llm_enabled=env.get("OM5_LLM_ENABLED", "false").lower() in {"1", "true", "yes"},
                    om5_llm_provider=env.get("OM5_LLM_PROVIDER", "groq"),
                    groq_model=env.get("GROQ_MODEL", "openai/gpt-oss-120b"),
                    _groq_api_key=env.get("GROQ_API_KEY") or None,
                    gemini_model=env.get("GEMINI_MODEL", "gemini-2.5-flash"),
                    _gemini_api_key=env.get("GEMINI_API_KEY") or None)
