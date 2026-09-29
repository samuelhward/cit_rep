"""Turn text into a comparable 'topic fingerprint'.

Simplest thing that works: TF-IDF bag of words with cosine similarity, on sparse dict
vectors. In production this module is the seam where a real embedding model (SPECTER2,
a sentence transformer) plugs in: keep the interface (`Vectorizer.vectorize`, `cosine`)
and swap the internals.

Why TF-IDF here and not just word overlap? Common words ("method", "results", "we show")
appear in every abstract and tell you nothing. IDF down-weights them so that the rare,
topic-specific words dominate the comparison.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable

Vector = dict[str, float]

_TOKEN = re.compile(r"[a-z][a-z0-9\-]+")

STOPWORDS = frozenset("""
a an the and or of to in on for with by from as at is are was were be been being this that these those
we our us it its they their them he she his her i you your not no nor but if then than so such which who whom
whose what when where why how all any both each few more most other some very can will just should may might
into over under again further here there also via using use used uses based show shows shown propose proposed
present presents presented paper study results result method methods approach approaches novel new
""".split())


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in STOPWORDS and len(t) > 2]


def cosine(a: Vector, b: Vector) -> float:
    if not a or not b:
        return 0.0
    # iterate over the smaller vector for speed
    if len(a) > len(b):
        a, b = b, a
    dot = sum(v * b.get(k, 0.0) for k, v in a.items())
    if dot == 0.0:
        return 0.0
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb)


def add_scaled(acc: Vector, v: Vector, scale: float) -> None:
    """acc += scale * v, in place."""
    for k, val in v.items():
        acc[k] = acc.get(k, 0.0) + scale * val


def normalise(v: Vector) -> Vector:
    n = math.sqrt(sum(x * x for x in v.values()))
    return {k: x / n for k, x in v.items()} if n else {}


class Vectorizer:
    """Fit IDF weights on a corpus once; then vectorize any text."""

    def __init__(self) -> None:
        self.idf: dict[str, float] = {}
        self.n_docs = 0

    def fit(self, texts: Iterable[str]) -> "Vectorizer":
        df: Counter[str] = Counter()
        n = 0
        for text in texts:
            n += 1
            df.update(set(tokenize(text)))
        self.n_docs = n
        # smoothed IDF: never zero, never infinite
        self.idf = {t: math.log((n + 1) / (c + 1)) + 1.0 for t, c in df.items()}
        return self

    def vectorize(self, text: str) -> Vector:
        counts = Counter(tokenize(text))
        total = sum(counts.values()) or 1
        default_idf = math.log(self.n_docs + 1) + 1.0  # unseen word: treat as rare
        vec = {t: (c / total) * self.idf.get(t, default_idf) for t, c in counts.items()}
        return normalise(vec)
