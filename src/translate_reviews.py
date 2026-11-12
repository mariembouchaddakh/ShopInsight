"""Traduction locale des avis Olist (portugais -> français) pour REHEARSE.

- Entrée  : data/silver/reviews_text.jsonl.gz (produit par prepare_data.py, non modifié)
- Sortie  : data/silver/reviews_text_fr.jsonl.gz (originaux conservés + traductions)
- Cache   : data/silver/translation_cache_fr.jsonl (reprise possible si le script est interrompu)
- Contrôle: quality/translation_report.json et quality/translation_sample_for_review.csv

Traitement 100 % local : aucun avis n'est envoyé à un service en ligne. Les modèles sont
téléchargés une seule fois depuis Hugging Face, puis exécutés sur l'ordinateur.

Modèles (pivot par l'anglais, comme préparé dans la phase précédente) :
  portugais -> anglais : Helsinki-NLP/opus-mt-ROMANCE-en
  anglais  -> français : Helsinki-NLP/opus-mt-en-fr
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import random
import re
import time
from pathlib import Path
from typing import Protocol

PT_EN_MODEL = "Helsinki-NLP/opus-mt-ROMANCE-en"
EN_FR_MODEL = "Helsinki-NLP/opus-mt-en-fr"
MODEL_LABEL = f"{PT_EN_MODEL} + {EN_FR_MODEL} (pivot anglais)"


class Translator(Protocol):
    def translate(self, texts: list[str]) -> list[tuple[str, str]]:
        """Retourne (anglais, français) pour chaque texte portugais."""


class MarianPivotTranslator:
    def __init__(self, batch_size: int = 32, device: str = "auto") -> None:
        import torch
        from transformers import MarianMTModel, MarianTokenizer

        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        self.batch_size = batch_size
        self.torch = torch
        print(f"Chargement des modèles sur {device} (premier lancement : téléchargement ~600 Mo)…", flush=True)
        self.tok_pt_en = MarianTokenizer.from_pretrained(PT_EN_MODEL)
        self.mod_pt_en = MarianMTModel.from_pretrained(PT_EN_MODEL).to(device).eval()
        self.tok_en_fr = MarianTokenizer.from_pretrained(EN_FR_MODEL)
        self.mod_en_fr = MarianMTModel.from_pretrained(EN_FR_MODEL).to(device).eval()

    def _run(self, tokenizer, model, texts: list[str]) -> list[str]:
        out: list[str] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            enc = tokenizer(batch, return_tensors="pt", padding=True, truncation=True, max_length=256).to(self.device)
            with self.torch.inference_mode():
                gen = model.generate(**enc, num_beams=2, max_new_tokens=256)
            out.extend(tokenizer.batch_decode(gen, skip_special_tokens=True))
        return out

    def translate(self, texts: list[str]) -> list[tuple[str, str]]:
        english = self._run(self.tok_pt_en, self.mod_pt_en, texts)
        french = self._run(self.tok_en_fr, self.mod_en_fr, english)
        return list(zip(english, french))


def key(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def check_translation(source: str, french: str) -> list[str]:
    """Signale les traductions suspectes ; ne les corrige pas."""
    flags = []
    if not french.strip():
        flags.append("traduction_vide")
        return flags
    letters = re.sub(r"[^a-zA-ZÀ-ÿ]", "", source)
    if len(letters) > 12 and french.strip().lower() == source.strip().lower():
        flags.append("non_traduit")
    if len(source) >= 20:
        ratio = len(french) / len(source)
        if ratio > 3 or ratio < 0.3:
            flags.append(f"longueur_anormale_{ratio:.1f}")
    if re.search(r"\b(\w+)(?:\W+\1\b){3,}", french.lower()):
        flags.append("repetition")
    return flags


def load_cache(path: Path) -> dict[str, dict[str, str]]:
    cache: dict[str, dict[str, str]] = {}
    if path.exists():
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                line = line.strip()
                if line:
                    record = json.loads(line)
                    cache[record["key"]] = record
    return cache


def run(project_dir: Path, translator: Translator | None, limit: int | None = None, chunk: int = 256) -> dict:
    silver = project_dir / "data" / "silver"
    quality = project_dir / "quality"
    quality.mkdir(parents=True, exist_ok=True)
    source_path = silver / "reviews_text.jsonl.gz"
    cache_path = silver / "translation_cache_fr.jsonl"
    output_path = silver / "reviews_text_fr.jsonl.gz"

    with gzip.open(source_path, "rt", encoding="utf-8") as stream:
        docs = [json.loads(line) for line in stream]
    if limit:
        docs = docs[:limit]

    segments = {clean(d.get(f)) for d in docs for f in ("text", "title")} - {""}
    cache = load_cache(cache_path)
    todo = sorted((s for s in segments if key(s) not in cache), key=len)
    print(f"{len(docs)} avis, {len(segments)} textes uniques, {len(segments) - len(todo)} déjà en cache, {len(todo)} à traduire.", flush=True)

    started = time.time()
    if todo:
        if translator is None:
            raise RuntimeError("Aucun traducteur fourni.")
        with cache_path.open("a", encoding="utf-8") as stream:
            for i in range(0, len(todo), chunk):
                batch = todo[i : i + chunk]
                for source, (english, french) in zip(batch, translator.translate(batch)):
                    record = {"key": key(source), "pt": source, "en": english, "fr": french}
                    cache[record["key"]] = record
                    stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                stream.flush()
                done = min(i + chunk, len(todo))
                elapsed = time.time() - started
                eta = elapsed / done * (len(todo) - done)
                print(f"  {done}/{len(todo)} traduits — {elapsed / 60:.1f} min écoulées, ~{eta / 60:.0f} min restantes", flush=True)

    status_counts = {"traduit": 0, "vide": 0, "à vérifier": 0}
    flag_counts: dict[str, int] = {}
    out_docs = []
    for d in docs:
        record = dict(d)
        flags: list[str] = []
        translated_any = False
        for field in ("text", "title"):
            source = clean(d.get(field))
            record[f"{field}_original_pt"] = d.get(field)
            if not source:
                record[f"{field}_fr"] = None
                continue
            french = cache[key(source)]["fr"]
            record[f"{field}_fr"] = french
            translated_any = True
            flags += [f"{field}:{f}" for f in check_translation(source, french)]
        status = "à vérifier" if flags else ("traduit" if translated_any else "vide")
        record["translation_status"] = status
        record["translation_flags"] = flags
        record["translation_model"] = MODEL_LABEL
        status_counts[status] += 1
        for f in flags:
            name = f.split(":", 1)[1].split("_")[0] if f.split(":", 1)[1].startswith("longueur") else f.split(":", 1)[1]
            flag_counts[name] = flag_counts.get(name, 0) + 1
        out_docs.append(record)

    with gzip.open(output_path, "wt", encoding="utf-8") as stream:
        for record in out_docs:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")

    rng = random.Random(42)
    sample = rng.sample(out_docs, min(200, len(out_docs)))
    with (quality / "translation_sample_for_review.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, delimiter=";")
        writer.writerow(["review_id", "review_score", "statut", "texte_pt", "texte_fr", "titre_pt", "titre_fr", "correct (oui/non)", "commentaire"])
        for r in sample:
            writer.writerow([r["review_id"], r["review_score"], r["translation_status"], r["text_original_pt"] or "", r["text_fr"] or "", r["title_original_pt"] or "", r["title_fr"] or "", "", ""])

    report = {
        "documents": len(out_docs),
        "unique_segments": len(segments),
        "translated_this_run": len(todo),
        "status": status_counts,
        "flags": flag_counts,
        "every_document_has_original": all(
            (r["text_original_pt"] == d.get("text")) and (r["title_original_pt"] == d.get("title")) for r, d in zip(out_docs, docs)
        ),
        "every_nonempty_text_translated": all(
            (r["text_fr"] is not None) == bool(clean(r["text_original_pt"])) and (r["title_fr"] is not None) == bool(clean(r["title_original_pt"]))
            for r in out_docs
        ),
        "model": MODEL_LABEL,
        "minutes": round((time.time() - started) / 60, 1),
        "manual_review_sample": "quality/translation_sample_for_review.csv (200 avis, graine 42)",
    }
    (quality / "translation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Traduction locale des avis Olist vers le français")
    parser.add_argument("--project-dir", type=Path, default=Path("."))
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--device", default="auto", help="auto, cpu ou cuda")
    parser.add_argument("--limit", type=int, help="Traduire seulement les N premiers avis (test rapide)")
    args = parser.parse_args()
    project_dir = args.project_dir.resolve()
    translator = MarianPivotTranslator(batch_size=args.batch_size, device=args.device)
    run(project_dir, translator, limit=args.limit)


if __name__ == "__main__":
    main()
