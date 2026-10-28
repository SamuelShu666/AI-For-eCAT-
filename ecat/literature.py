"""Literature evidence base: PDF -> page-level chunks -> lightweight TF-IDF retrieval.

Every chunk keeps (file, page) so any claim the agent makes can be traced back.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

from .space import ROOT

LIT_DIR = ROOT / "相关文献"
CACHE = ROOT / "data" / "lit_chunks.json"
TOKEN = re.compile(r"[A-Za-z][A-Za-z\-]+|[A-Z][a-z]?(?=\b)")

ELEMENT_ALIASES = {
    "Pd": ["palladium", "Pd"], "Rh": ["rhodium", "Rh"], "Ni": ["nickel", "Ni"],
    "Au": ["gold", "Au"], "Ag": ["silver", "Ag"], "Cu": ["copper", "Cu"],
    "Zn": ["zinc", "Zn"], "Cd": ["cadmium", "Cd"], "Ga": ["gallium", "Ga"],
    "In": ["indium"], "Tl": ["thallium", "Tl"], "Hg": ["mercury", "Hg"],
    "Sn": ["tin", "Sn"],
}


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in TOKEN.findall(text)]


def build_chunks(chunk_chars: int = 900) -> list[dict]:
    import pypdfium2 as pdfium

    chunks = []
    for pdf in sorted(LIT_DIR.rglob("*.pdf")):
        doc = pdfium.PdfDocument(str(pdf))
        for page_no in range(len(doc)):
            text = re.sub(r"\s+", " ", doc[page_no].get_textpage().get_text_range()).strip()
            for start in range(0, len(text), chunk_chars):
                piece = text[start:start + chunk_chars]
                if len(piece) < 200:
                    continue
                chunks.append({"id": f"L{len(chunks):04d}",
                               "file": str(pdf.relative_to(LIT_DIR)).replace("\\", "/"),
                               "topic": pdf.parent.name, "page": page_no + 1,
                               "text": piece})
        doc.close()
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(chunks, ensure_ascii=False), encoding="utf-8")
    return chunks


class LiteratureIndex:
    def __init__(self, chunks: list[dict] | None = None):
        if chunks is None:
            chunks = (json.loads(CACHE.read_text(encoding="utf-8"))
                      if CACHE.exists() else build_chunks())
        self.chunks = chunks
        self._tf = [Counter(_tokens(c["text"])) for c in chunks]
        df = Counter()
        for tf in self._tf:
            df.update(tf.keys())
        n = len(chunks)
        self._idf = {t: math.log((n + 1) / (d + 0.5)) for t, d in df.items()}

    def search(self, query: str, k: int = 5) -> list[dict]:
        q = _tokens(query)
        scored = []
        for chunk, tf in zip(self.chunks, self._tf):
            total = sum(tf.values()) or 1
            s = sum((tf[t] / total) * self._idf.get(t, 0.0) for t in q)
            if s > 0:
                scored.append((s, chunk))
        scored.sort(key=lambda x: -x[0])
        return [dict(c, score=round(s, 5)) for s, c in scored[:k]]

    def get(self, chunk_id: str) -> dict | None:
        return next((c for c in self.chunks if c["id"] == chunk_id), None)
