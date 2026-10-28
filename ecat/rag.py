"""Offline, reproducible RAG display adapter.

Member A delivered Chroma + MiniLM + TF-IDF + RRF, but not the Chroma database
or model cache.  This module keeps the RRF fusion idea while providing a fully
local TF-IDF + BM25 fallback for replay.  Results are always labelled as replay;
they are not represented as the vector rankings seen by the original runs.
"""
from __future__ import annotations

import math
import re
from collections import Counter

from .literature import LiteratureIndex

TOKEN = re.compile(r"[A-Za-z][A-Za-z\-]+|[A-Z][a-z]?(?=\b)")


def tokens(text: str) -> list[str]:
    return [t.lower() for t in TOKEN.findall(text)]


class OfflineHybridRetriever:
    """TF-IDF and BM25 rankings fused with member A's reciprocal-rank method."""

    method = "TF-IDF + BM25 + RRF（离线重放）"

    def __init__(self, chunks: list[dict]):
        self.chunks = chunks
        self.tfidf = LiteratureIndex(chunks)
        self._tf = [Counter(tokens(c["text"])) for c in chunks]
        self._len = [sum(tf.values()) or 1 for tf in self._tf]
        self._avg_len = sum(self._len) / max(1, len(self._len))
        df = Counter()
        for tf in self._tf:
            df.update(tf.keys())
        n = len(chunks)
        self._idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def bm25_search(self, query: str, k: int = 5) -> list[dict]:
        q = tokens(query)
        scored = []
        for chunk, tf, doc_len in zip(self.chunks, self._tf, self._len):
            score = 0.0
            for term in q:
                f = tf.get(term, 0)
                if not f:
                    continue
                denom = f + 1.5 * (1 - 0.75 + 0.75 * doc_len / self._avg_len)
                score += self._idf.get(term, 0.0) * f * 2.5 / denom
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda x: -x[0])
        return [dict(c, score=round(s, 5)) for s, c in scored[:k]]

    @staticmethod
    def rrf_merge(rankings: list[list[dict]], k: int = 60) -> list[dict]:
        fused: dict[str, dict] = {}
        for ranking in rankings:
            for rank, item in enumerate(ranking, start=1):
                key = item["id"]
                if key not in fused:
                    fused[key] = {"item": dict(item), "score": 0.0, "rankings": []}
                fused[key]["score"] += 1.0 / (k + rank)
                fused[key]["rankings"].append({"source": item["source"], "rank": rank})
        return sorted(fused.values(), key=lambda x: -x["score"])

    def search(self, query: str, k: int = 4) -> list[dict]:
        lexical = [dict(c, source="tfidf") for c in self.tfidf.search(query, k=5)]
        bm25 = [dict(c, source="bm25") for c in self.bm25_search(query, k=5)]
        out = []
        for item in self.rrf_merge([lexical, bm25])[:k]:
            chunk = item["item"]
            chunk["rrf_score"] = round(item["score"], 6)
            chunk["rankings"] = item["rankings"]
            chunk["retrieval_method"] = self.method
            out.append(chunk)
        return out
