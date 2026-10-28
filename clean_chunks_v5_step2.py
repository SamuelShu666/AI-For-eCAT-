# -*- coding: utf-8 -*-
"""v5 二次清理：剔除元数据/作者单位/致谢等垃圾块"""
import csv
import re
import shutil
from collections import Counter
from pathlib import Path

ROOT = Path(r"D:\her_agent_project")
CSV = ROOT / "her_chunks_v5.csv"
BAK = ROOT / "her_chunks_v5_raw2.csv"

PATTERNS = [
    re.compile(r"^\s*contents lists available", re.I),
    re.compile(r"^\s*article\s+published online", re.I),
    re.compile(r"supporting information is available", re.I),
    re.compile(r"^\s*(original research|research article)\b", re.I),
    re.compile(r"^\s*[a-e]\s+(Graduate|Department|Institute|School|University|College)\b"),
    re.compile(r"^\s*[a-e]\s+\S+.*(Ltd\.?|Corp\.?|Co\.)", re.I),
    re.compile(r"\s-\sDepartment of\b"),
    re.compile(r"^\s*acknowledg", re.I),
]


def is_junk(text):
    return any(p.search(text) for p in PATTERNS)


def main():
    rows = list(csv.DictReader(open(CSV, encoding="utf-8-sig")))
    if not BAK.exists():
        shutil.copyfile(CSV, BAK)

    flags = [is_junk(r["original_chunk_text"]) for r in rows]
    kept = [r for r, bad in zip(rows, flags) if not bad]

    with open(CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(kept)

    print("原始:", len(rows), "| 删除:", len(rows) - len(kept), "| 保留:", len(kept))
    print("删除分布:", dict(Counter(r["paper_id"] for r, bad in zip(rows, flags) if bad)))
    print("备份:", BAK)


if __name__ == "__main__":
    main()