"""Traduction À LA DEMANDE des extraits d'avis affichés par BO3 (portugais → français), 100 % locale.

La traduction complète du corpus (src/translate_reviews.py) prend des heures sur CPU ; l'interface n'affiche pourtant que quelques
extraits par vendeur. Ce module ne traduit donc que les extraits demandés, avec les MÊMES modèles (MarianMT, pivot anglais), la MÊME clé
et le MÊME cache (data/silver/translation_cache_fr.jsonl) que le script complet : tout ce qui est traduit ici est réutilisé par lui,
et inversement. Si les bibliothèques ou les modèles manquent, rien n'est traduit et l'original portugais reste affiché (étiqueté).
Aucun avis n'est envoyé à un service en ligne.
"""
from __future__ import annotations

import json
import logging
import sys
import threading
from pathlib import Path

log = logging.getLogger("shopinsight.translation")


class OnDemandTranslator:
    def __init__(self, project_dir: str | Path) -> None:
        self.dir = Path(project_dir)
        self.cache_path = self.dir / "data/silver/translation_cache_fr.jsonl"
        self._cache: dict[str, dict] | None = None
        self._model = None
        self._unavailable = False
        self._lock = threading.Lock()
        if str(self.dir / "src") not in sys.path:
            sys.path.insert(0, str(self.dir / "src"))

    def _tools(self):
        import translate_reviews as tr  # même clé, même nettoyage, mêmes modèles que le script complet
        return tr

    @property
    def cache(self) -> dict[str, dict]:
        if self._cache is None:
            self._cache = self._tools().load_cache(self.cache_path)
        return self._cache

    def load(self) -> bool:
        """Charge les modèles (une fois) ; False si impossible (bibliothèques ou modèles absents)."""
        if self._model is not None or self._unavailable:
            return self._model is not None
        with self._lock:
            if self._model is None and not self._unavailable:
                try:
                    from transformers.utils import logging as hf_logging
                    hf_logging.set_verbosity_error()  # pas d'avertissements de génération dans les journaux de l'API
                    self._model = self._tools().MarianPivotTranslator(batch_size=8)
                except Exception as e:  # noqa: BLE001 — traduction facultative : l'original reste affiché
                    log.warning("traduction locale indisponible (%s) : extraits affichés en portugais", type(e).__name__)
                    self._unavailable = True
        return self._model is not None

    def translate(self, texts: list[str], allow_model: bool = True) -> dict[str, str]:
        """{texte portugais nettoyé : français} ; traduit (et met en cache) les segments manquants si le modèle est disponible."""
        tr = self._tools()
        segs = list(dict.fromkeys(t for t in (tr.clean(x) for x in texts) if t))
        out = {s: self.cache[tr.key(s)]["fr"] for s in segs if tr.key(s) in self.cache}
        todo = [s for s in segs if s not in out]
        if todo and allow_model and self.load():
            with self._lock:
                pairs = self._model.translate(todo)
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                with self.cache_path.open("a", encoding="utf-8") as f:
                    for src, (en, fr) in zip(todo, pairs):
                        rec = {"key": tr.key(src), "pt": src, "en": en, "fr": fr}
                        self.cache[rec["key"]] = rec
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        out[src] = fr
        return out

    def review(self, title: str | None, text: str | None, allow_model: bool = True) -> str | None:
        """Titre et texte traduits séparément (comme le script complet), réunis comme dans l'original ; None si non traduit."""
        tr = self._tools()
        parts = [tr.clean(title), tr.clean(text)]
        parts = [p for p in parts if p]
        if not parts:
            return None
        fr = self.translate(parts, allow_model=allow_model)
        if not all(p in fr and fr[p].strip() for p in parts):
            return None
        return ". ".join(fr[p].rstrip(". ") for p in parts)
