"""Briques NLP de l'agent BO2 (DS2.1 sentiment par aspect, DS2.2 plaintes émergentes, DS4.2-like recherche d'avis).

IMPORTANT — statut : c'est la BASELINE « mots-clés + note » annoncée dans le plan de modélisation (BO2). Elle est évaluée sur
500 avis stratifiés (100 par note) annotés à l'aveugle par un LLM selon le guide d'annotation (accord LLM–humain κ ≈ 0,63 sur
40 avis, contre 0,46 entre deux annotatrices). F1 de détection provisoire : 0,67 en moyenne sur les 9 aspects (objectif 0,70),
plus faible sur la qualité, les articles manquants et la conformité ; détail dans quality/bo2_aspect_f1.json. L'interface
`AspectModel` permet de brancher un transformeur multilingue sans toucher à l'agent.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Protocol

import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer


def norm_text(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s).lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9' ]+", " ", s)


# aspect -> (libellé FR, motif regex sur texte normalisé sans accents)
ASPECTS: dict[str, tuple[str, str]] = {
    "livraison": ("Livraison et délais", r"\b(entreg\w*|prazo\w*|atras\w*|demor\w*|chegou|chegar|chegada|correio\w*|transportadora|rastrei\w*|frete|envio|enviad\w*|despach\w*)\b"),
    "qualite_produit": ("Qualité et état du produit", r"\b(qualidade|defeit\w*|quebrad\w*|quebrou|danificad\w*|estragad\w*|funcion\w*|fragil|rasgad\w*|manchad\w*|material|amassad\w*|riscad\w*)\b"),
    "article_errone_ou_manquant": ("Article erroné, manquant ou incomplet", r"\b(errad\w*|diferente\w*|faltou|faltando|falta|incomplet\w*|trocad\w*|apenas um|so veio|veio so|nao veio|veio apenas|metade)\b"),
    "vendeur_service": ("Vendeur et service", r"\b(vendedor\w*|loja|lojista|atendimento|contato|resposta|respond\w*|sac|suporte|retorno)\b"),
    "emballage": ("Emballage", r"\b(embalagem|embalad\w*|caixa|lacrad\w*)\b"),
    "conformite_annonce": ("Conformité à l'annonce", r"\b(anuncio|descricao|descrito|foto\w*|imagem|cor|tamanho|medida\w*|original|falsific\w*|conforme|especifica\w*)\b"),
    "prix_valeur": ("Prix et rapport qualité-prix", r"\b(preco\w*|caro|barato|custo\w*|beneficio|valor)\b"),
    "retour_remboursement": ("Retour, échange, remboursement", r"\b(devol\w*|reembols\w*|estorn\w*|cancel\w*|troca\w*|trocar|reclam\w*|dinheiro de volta)\b"),
    "satisfaction_globale": ("Satisfaction globale", r"\b(recomend\w*|otim\w*|excelente\w*|perfeit\w*|parabens|satisfeit\w*|adorei|gostei|pessim\w*|horrivel|decepc\w*|lamentavel|nunca mais|pior|maravilh\w*)\b"),
}
ASPECT_RE = {a: re.compile(p) for a, (_, p) in ASPECTS.items()}

POS = set("otimo otima excelente perfeito perfeita bom boa adorei gostei recomendo recomendado parabens rapido rapida satisfeito satisfeita maravilhoso maravilhosa ideal lindo linda".split())
NEG = set("pessimo pessima horrivel ruim atrasou atrasado atrasada demorou demora defeito defeituoso quebrado quebrada errado errada faltou decepcionado decepcionada lamentavel falsificado fragil absurdo pior devolver reclamar".split())
NEG_PHRASES = ("nao chegou", "nao recebi", "nao veio", "nao funciona", "nao entreg", "nao foi entregue", "nao recomendo", "nunca chegou", "ainda nao",
               "nao gostei", "nao correspond", "nao atende", "sem resposta", "nao respond", "nunca mais")
NEGATORS = {"nao", "nunca", "jamais", "nem", "sem"}
STOP = set("""a o as os um uma uns umas de do da dos das em no na nos nas por para com sem sob sobre e ou mas que se ao aos ja so muito mais menos bem
foi ser sao era eu me meu minha meus minhas voce vc ele ela eles elas isso isto este esta esse essa aquele aquela como quando onde pois entao tambem
tem ter tinha comprei recebi produto produtos pedido compra loja lojas super mto q pra pro nao sim ate la aqui ainda s""".split())


def _sentences(text: str) -> list[str]:
    parts = re.split(r"[.!?;\n]+|\bmas\b|\bporem\b|\bcontudo\b|\bentretanto\b", norm_text_keep_sep(text))
    return [p.strip() for p in parts if p and p.strip()]


def norm_text_keep_sep(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s).lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9'.!?;\n ]+", " ", s)


def sentence_polarity(sent: str) -> int:
    """+1 / -1 / 0 par lexique avec négation locale. 0 = pas de signal (on retombe sur la note)."""
    if any(p in sent for p in NEG_PHRASES):
        return -1
    toks = sent.split()
    s = 0
    for i, t in enumerate(toks):
        neg_ctx = any(x in NEGATORS for x in toks[max(0, i - 2):i])
        if t in POS:
            s += -1 if neg_ctx else 1
        elif t in NEG:
            s += 1 if neg_ctx else -1
    return int(np.sign(s))


def score_polarity(score: int) -> int:
    return -1 if score <= 2 else (1 if score >= 4 else 0)


class AspectModel(Protocol):
    def predict(self, text: str, score: int) -> dict[str, int]: ...


@dataclass
class LexiconAspectModel:
    """Baseline DS2.1 : un aspect est détecté par mot-clé ; sa polarité est celle de la phrase (lexique + négation),
    sinon celle de la note de l'avis. Retourne {aspect: -1|0|1}."""
    def predict(self, text: str, score: int) -> dict[str, int]:
        out: dict[str, int] = {}
        fallback = score_polarity(int(score))
        for sent in _sentences(text):
            pol = sentence_polarity(sent)
            for a, rx in ASPECT_RE.items():
                if rx.search(sent):
                    p = pol if pol != 0 else fallback
                    # priorité au négatif : une seule phrase négative suffit à signaler le problème
                    out[a] = -1 if (out.get(a) == -1 or p == -1) else max(out.get(a, -2), p)
        return out


def analyse_reviews(reviews: pd.DataFrame, model: AspectModel | None = None) -> pd.DataFrame:
    """Ajoute une colonne a_<aspect> (−1, 0, 1 ou NaN si non mentionné) et `text_norm` aux avis ayant du texte."""
    model = model or LexiconAspectModel()
    df = reviews[(reviews["full_pt"].str.len() > 0)].copy()
    cols = {a: [] for a in ASPECTS}
    for text, sc in zip(df["full_pt"], df["score"]):
        res = model.predict(text, sc)
        for a in ASPECTS:
            cols[a].append(res.get(a, np.nan))
    for a in ASPECTS:
        df[f"a_{a}"] = cols[a]
    df["text_norm"] = df["full_pt"].map(norm_text)
    return df


# ----------------------------------------------------------------------------- plaintes émergentes (DS2.2)
def _bh(p: np.ndarray) -> np.ndarray:
    n = len(p)
    order = np.argsort(p)
    q = np.empty(n)
    prev = 1.0
    for rank, i in zip(range(n, 0, -1), order[::-1]):
        prev = min(prev, p[i] * n / rank)
        q[i] = prev
    return q


def baseline_months(an: pd.DataFrame, month: str, n_base: int = 12, min_reviews: int = 150) -> list[str]:
    counts = an.groupby("month").size()
    ok = [m for m in sorted(counts.index) if counts[m] >= min_reviews and m < month]
    return ok[-n_base:]


def emerging_aspects(an: pd.DataFrame, month: str, n_base: int = 12, min_base_months: int = 3, min_count: int = 15, q_max: float = 0.05,
                     min_abs_gain: float = 0.02, min_lift: float = 1.3, min_reviews: int = 150) -> dict:
    """Part des avis écrits qui critiquent un aspect, mois cible vs historique robuste.
    Référence = MÉDIANE des taux mensuels des 12 mois complets précédents (robuste à un mois déjà perturbé, ex. un pic de retards).
    Avec 6 mois, un seul pic (nov. 2017) gonflait la variabilité MAD et rendait l'agent aveugle aux crises suivantes (fév.–mars 2018) ;
    la variabilité naturelle d'un mois à l'autre (MAD) est ajoutée à l'erreur du test, sinon la saisonnalité produirait de fausses alertes.
    Test unilatéral, correction de Benjamini-Hochberg sur les aspects. Alerte si q ≤ 5 %, ≥ 15 avis, +2 points et ×1,3 au moins."""
    cur = an[an["month"] == month]
    base_m = baseline_months(an, month, n_base, min_reviews)
    base = an[an["month"].isin(base_m)]
    if len(cur) < min_reviews or len(base_m) < min_base_months:
        return {"month": month, "baseline_months": base_m, "n_current": int(len(cur)), "n_baseline": int(len(base)), "aspects": [],
                "note": "mois ou historique insuffisant pour un test fiable"}
    rows = []
    n1 = len(cur)
    for a in ASPECTS:
        if a == "satisfaction_globale":
            continue
        x1 = int((cur[f"a_{a}"] == -1).sum())
        monthly = np.array([(base[base["month"] == m][f"a_{a}"] == -1).mean() for m in base_m])
        p1, p0 = x1 / n1, float(np.median(monthly))
        mad = 1.4826 * float(np.median(np.abs(monthly - p0)))
        p0e = max(p0, 0.5 / n1)
        se = float(np.sqrt(p0e * (1 - p0e) / n1 + mad ** 2)) or 1e-9
        z = (p1 - p0) / se
        rows.append({"aspect": a, "label": ASPECTS[a][0], "count": x1, "rate": p1, "baseline_count": int((base[f"a_{a}"] == -1).sum()),
                     "baseline_rate": p0, "baseline_spread": mad, "lift": (p1 / p0) if p0 > 0 else None, "z": float(z), "p": float(norm.sf(z))})
    q = _bh(np.array([r["p"] for r in rows]))
    for r, qi in zip(rows, q):
        r["q"] = float(qi)
        r["alert"] = bool(qi <= q_max and r["count"] >= min_count and (r["rate"] - r["baseline_rate"]) >= min_abs_gain
                          and (r["lift"] is None or r["lift"] >= min_lift))
    rows.sort(key=lambda r: -r["z"])
    return {"month": month, "baseline_months": base_m, "n_current": int(n1), "n_baseline": int(len(base)), "aspects": rows}


def emerging_terms(an: pd.DataFrame, month: str, base_months: list[str], top: int = 10, z_min: float = 2.5, min_count: int = 8,
                   negative_only: bool = True) -> list[dict]:
    """Termes sur-représentés dans les avis négatifs du mois (log-odds avec a priori de Dirichlet informatif, Monroe et al. 2008).
    Détecte des plaintes que le lexique ne connaît pas. `new` = quasi absent du passé."""
    d = an[an["score"] <= 2] if negative_only else an
    cur, base = d[d["month"] == month], d[d["month"].isin(base_months)]
    if len(cur) < 30 or len(base) < 30:
        return []
    cv = CountVectorizer(ngram_range=(1, 2), min_df=5, stop_words=list(STOP), token_pattern=r"(?u)\b[a-z][a-z']{2,}\b")
    Xall = cv.fit_transform(d["text_norm"])
    vocab = np.array(cv.get_feature_names_out())
    idx_c = np.where((d["month"] == month).values)[0]
    idx_b = np.where(d["month"].isin(base_months).values)[0]
    y1 = np.asarray(Xall[idx_c].sum(0)).ravel().astype(float)
    y0 = np.asarray(Xall[idx_b].sum(0)).ravel().astype(float)
    tot = np.asarray(Xall.sum(0)).ravel().astype(float)
    a = 500 * tot / tot.sum()
    a0 = a.sum()
    n1, n0 = y1.sum(), y0.sum()
    delta = np.log((y1 + a) / (n1 + a0 - y1 - a)) - np.log((y0 + a) / (n0 + a0 - y0 - a))
    z = delta / np.sqrt(1 / (y1 + a) + 1 / (y0 + a))
    cand = []
    for i in np.argsort(-z):
        if z[i] < z_min or len(cand) >= top * 4:
            break
        if y1[i] >= min_count:
            cand.append({"term": vocab[i], "count_month": int(y1[i]), "count_baseline": int(y0[i]), "z": round(float(z[i]), 2),
                         "new": bool(y0[i] <= 1)})
    # on garde les bigrammes et on retire les mots seuls qu'ils contiennent (évite « golpe » + « golpe total » + « total »)
    bigrams = [c["term"] for c in cand if " " in c["term"]]
    out = [c for c in cand if " " in c["term"] or not any(c["term"] in b.split() for b in bigrams)]
    return out[:top]


# ----------------------------------------------------------------------------- recherche d'avis (type DS4.2)
class ReviewIndex:
    """TF-IDF sur portugais + français (traduction) : une requête en français ou en portugais retrouve les avis pertinents."""
    def __init__(self, an: pd.DataFrame) -> None:
        self.df = an.reset_index(drop=True)
        corpus = (self.df["text_norm"] + " " + self.df["full_fr"].map(norm_text)).values
        self.vec = TfidfVectorizer(sublinear_tf=True, ngram_range=(1, 2), min_df=2, max_df=0.5)
        self.X = self.vec.fit_transform(corpus)

    def search(self, query: str, mask: np.ndarray | None = None, k: int = 5) -> pd.DataFrame:
        q = self.vec.transform([norm_text(query)])
        sims = (self.X @ q.T).toarray().ravel()
        if mask is not None:
            sims = np.where(mask, sims, 0)
        order = np.argsort(-sims)
        seen, rows = set(), []
        for i in order:
            if sims[i] <= 0 or len(rows) >= k:
                break
            key = self.df.at[i, "text_norm"][:80]
            if key in seen:
                continue
            seen.add(key)
            r = self.df.iloc[i].copy()
            r["similarity"] = float(sims[i])
            rows.append(r)
        return pd.DataFrame(rows)
