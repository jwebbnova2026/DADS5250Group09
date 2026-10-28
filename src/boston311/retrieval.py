"""TF-IDF retrieval over the official request-type catalog (spec 4.6).

This is the "R" in RAG (retrieval-augmented generation): before the language
model sees a resident's message, we retrieve the few official request types
most similar to it, and the model may only choose among those candidates.

How the search works
--------------------
TF-IDF ("term frequency x inverse document frequency") turns each text into
a vector of word weights. Words that appear in many types (like "request")
get low weight; distinctive words (like "pothole") get high weight. The
similarity between a message and a type is the cosine of the angle between
their vectors: 1 means the same words in the same proportions, 0 means no
words in common.

We combine two TF-IDF views and average their cosine scores:

* **words** (single words and two-word phrases), which captures meaning;
* **character fragments** (3-5 letters inside words), which still matches
  when a resident misspells something ("strret light" still shares "str",
  "ligh", "ight" with "street light").

Each type's searchable text is its official name, its description, and its
reviewed aliases. Everything runs locally, with no network.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from boston311 import config
from boston311.catalog import CatalogEntry


@dataclass(frozen=True)
class Hit:
    """One retrieved candidate type and its similarity score (0..1)."""

    type_id: str
    score: float


class Retriever:
    """Finds the catalog types most similar to a message.

    Args:
        entries: catalog entries to index.
        with_aliases: index aliases too (True) or only names and
            descriptions (False). The evaluation compares both (spec 4.6).
    """

    def __init__(self, entries: list[CatalogEntry], *, with_aliases: bool = True):
        self.entries = list(entries)
        self.ids = [e.type_id for e in self.entries]
        docs = [e.search_text(with_aliases) for e in self.entries]
        self.word = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english", lowercase=True)
        self.char = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, lowercase=True)
        self.word_matrix = self.word.fit_transform(docs)
        self.char_matrix = self.char.fit_transform(docs)

    def scores(self, text: str) -> np.ndarray:
        """Similarity of ``text`` to every indexed type (same order as ``self.ids``).

        TfidfVectorizer normalises every vector to length 1, so the dot
        product of two vectors is their cosine similarity.
        """
        w = (self.word_matrix @ self.word.transform([text]).T).toarray().ravel()
        c = (self.char_matrix @ self.char.transform([text]).T).toarray().ravel()
        return (w + c) / 2

    def search(self, text: str, k: int = config.RETRIEVAL_TOP_K) -> list[Hit]:
        """The ``k`` most similar types, best first (ties broken by type ID)."""
        s = self.scores(text)
        order = sorted(range(len(s)), key=lambda i: (-s[i], self.ids[i]))[:k]
        return [Hit(self.ids[i], float(s[i])) for i in order]
