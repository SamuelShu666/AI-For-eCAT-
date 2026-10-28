# -*- coding: utf-8 -*-
"""用 her_chunks_v5.csv 重建 chroma_her_db_v5"""
import os

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

import csv
import shutil
from pathlib import Path

from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings

ROOT = Path(r"D:\her_agent_project")
CSV_PATH = ROOT / "her_chunks_v5.csv"
PERSIST_DIR = ROOT / "chroma_her_db_v5"
CACHE_DIR = r"D:\her_agent_project\model_cache"


def main():
    docs = []
    for r in csv.DictReader(open(CSV_PATH, encoding="utf-8-sig")):
        text = (r.get("original_chunk_text") or "").strip()
        if not text:
            continue
        docs.append(Document(
            page_content=text,
            metadata={
                "paper_id": r["paper_id"],
                "paper_title": r["paper_title"],
                "source_file": r["source_file"],
                "page_start": r["page_start"],
                "page_end": r["page_end"],
                "chunk_id": r["chunk_id"],
            },
        ))

    print("待入库:", len(docs))
    if PERSIST_DIR.exists():
        shutil.rmtree(PERSIST_DIR)

    emb = HuggingFaceEmbeddings(
        model_name="all-MiniLM-L6-v2",
        cache_folder=CACHE_DIR,
        encode_kwargs={"normalize_embeddings": True},
    )
    vs = Chroma.from_documents(docs, emb, persist_directory=str(PERSIST_DIR))
    print("入库完成:", PERSIST_DIR)

    tests = [
        "Ni Mo alloy hydrogen evolution alkaline",
        "cathode potential above 0.6 V irreversible hydroxide",
        "Co alloy hydrogen evolution reaction",
    ]
    for q in tests:
        print(f"\n[{q}]")
        for d, dist in vs.similarity_search_with_score(q, k=3):
            print(f"  dist={dist:.3f} | {d.metadata['chunk_id']} | {d.page_content[:60]!r}")


if __name__ == "__main__":
    main()