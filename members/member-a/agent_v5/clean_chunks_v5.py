# -*- coding: utf-8 -*-
"""二次过滤：清掉分号式参考文献块，原始备份为 her_chunks_v5_raw.csv"""
import csv
import re
import shutil
from collections import Counter
from pathlib import Path

ROOT = Path(r"D:\her_agent_project")
CSV = ROOT / "her_chunks_v5.csv"
RAW = ROOT / "her_chunks_v5_raw.csv"

A = re.compile(r"\b[A-Z]\.\s*[A-Z][a-z]+")
B = re.compile(r"\b[A-Z][a-z]+\s+[A-Z]\b")
S = re.compile(r"\b[A-Z][a-z]+,\s*[A-Z]\.")
Y = re.compile(r"\b(19|20)\d{2}\b")
START = re.compile(r"^\s*[A-Z][a-z]+,\s*[A-Z]\.")


def is_ref(text):
    if len(text) <= 150:
        return False
    n = len(A.findall(text)) + len(B.findall(text)) + len(S.findall(text))
    y = len(Y.findall(text))
    return (bool(START.match(text)) and n >= 3) or (n >= 10 and y >= 2)


def main():
    rows = list(csv.DictReader(open(CSV, encoding="utf-8-sig")))
    if not RAW.exists():
        shutil.copyfile(CSV, RAW)

    flags = [is_ref(r["original_chunk_text"]) for r in rows]
    kept = [r for r, bad in zip(rows, flags) if not bad]

    with open(CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(kept)

    print("原始:", len(rows), "| 删除:", len(rows) - len(kept), "| 保留:", len(kept))
    print("删除分布:", dict(Counter(r["paper_id"] for r, bad in zip(rows, flags) if bad)))
    print("原始备份:", RAW)


if __name__ == "__main__":
    main()