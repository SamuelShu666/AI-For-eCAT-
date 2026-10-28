# -*- coding: utf-8 -*-
"""v5：合并 pdf_input + new_refs，paper_id 固定映射，重新切块"""
import csv
import hashlib
import re
from pathlib import Path

from docling.document_converter import DocumentConverter

ROOT = Path(r"D:\her_agent_project")
PDF_DIRS = [ROOT / "pdf_input", ROOT / "new_refs"]
REGISTRY = ROOT / "paper_registry.csv"
OUT_CSV = ROOT / "her_chunks_v5.csv"

CHUNK_SIZE = 700
MIN_CHUNK = 120

SKIP_LABELS = {"page_header", "page_footer", "footnote", "reference"}
REF_HEAD = re.compile(r"^\s*(references?|bibliography|参考文献)\b", re.I)
CITE_A = re.compile(r"\b[A-Z]\.\s*[A-Z][a-z]+")
CITE_B = re.compile(r"\b[A-Z][a-z]+\s+[A-Z]\b")
YEAR = re.compile(r"\b(19|20)\d{2}\b")


def file_hash(p, buf=1 << 20):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(buf), b""):
            h.update(chunk)
    return h.hexdigest()


def load_registry():
    if not REGISTRY.exists():
        return {}
    return {
        r["source_file"]: r["paper_id"]
        for r in csv.DictReader(open(REGISTRY, encoding="utf-8-sig"))
    }


def save_registry(reg):
    with open(REGISTRY, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["source_file", "paper_id"])
        for name, pid in sorted(reg.items(), key=lambda kv: kv[1]):
            w.writerow([name, pid])


def split_long(text, limit):
    if len(text) <= limit:
        return [text]
    parts = re.split(r"(?<=[.!?])\s+", text)
    out, buf = [], ""
    for s in parts:
        if buf and len(buf) + len(s) + 1 > limit:
            out.append(buf.strip())
            buf = s
        else:
            buf = (buf + " " + s).strip()
    if buf:
        out.append(buf.strip())
    return out


def looks_like_references(text):
    if len(text) < 150:
        return False
    cites = len(CITE_A.findall(text)) + len(CITE_B.findall(text))
    return cites >= 6 and len(YEAR.findall(text)) >= 2


def build_chunks(doc):
    rows, buf, size = [], [], 0
    start_page = last_page = None
    in_refs = False

    for item, _ in doc.iterate_items():
        label = str(getattr(item, "label", ""))
        text = (getattr(item, "text", "") or "").strip()

        if len(text) < 40 and REF_HEAD.match(text):
            in_refs = True
        if in_refs or label in SKIP_LABELS or not text:
            continue

        prov = getattr(item, "prov", None)
        page = prov[0].page_no if prov else None

        for piece in split_long(text, CHUNK_SIZE):
            if buf and size + len(piece) > CHUNK_SIZE:
                if size >= MIN_CHUNK:
                    rows.append((start_page, last_page, " ".join(buf)))
                buf, size = [], 0
            if not buf:
                start_page = page
            buf.append(piece)
            size += len(piece)
            last_page = page

    if buf and size >= MIN_CHUNK:
        rows.append((start_page, last_page, " ".join(buf)))

    kept = []
    for p0, p1, text in rows:
        if not looks_like_references(text):
            kept.append((p0, p1, text))
    return kept


def main():
    files = []
    for d in PDF_DIRS:
        files.extend(sorted(d.glob("*.pdf")))

    seen = {}
    unique = []
    for p in files:
        h = file_hash(p)
        if h in seen:
            print("跳过重复:", p.name, "==", seen[h])
            continue
        seen[h] = p.name
        unique.append(p)

    reg = load_registry()
    next_id = max([int(v[1:]) for v in reg.values()], default=0) + 1
    for p in unique:
        if p.name not in reg:
            reg[p.name] = f"P{next_id:02d}"
            next_id += 1
    save_registry(reg)

    print(f"共 {len(unique)} 篇，registry 已更新\n")

    conv = DocumentConverter()
    all_rows = []
    total_dropped = 0

    for i, pdf in enumerate(unique, start=1):
        pid = reg[pdf.name]
        print(f"[{i}/{len(unique)}] {pid} {pdf.name[:60]}", flush=True)

        doc = conv.convert(str(pdf)).document
        chunks = build_chunks(doc)

        for k, (p0, p1, text) in enumerate(chunks):
            all_rows.append({
                "paper_id": pid,
                "paper_title": pdf.stem,
                "source_file": pdf.name,
                "page_start": p0,
                "page_end": p1,
                "chunk_id": f"{pid}_p{p0}_{k:03d}",
                "original_chunk_text": text,
            })
        print(f"        -> {len(chunks)} 块", flush=True)

    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        w.writeheader()
        w.writerows(all_rows)

    lens = [len(r["original_chunk_text"]) for r in all_rows]
    print("\n写入:", OUT_CSV)
    print("总块数:", len(all_rows))
    print("有页码的块:", sum(1 for r in all_rows if r["page_start"]))
    print("块长 最短/平均/最长:", min(lens), round(sum(lens) / len(lens)), max(lens))
    print("论文数:", len(set(r["paper_id"] for r in all_rows)))

    print("\n开头 3 块：")
    for r in all_rows[:3]:
        print(f"  {r['chunk_id']} | {r['original_chunk_text'][:70]}")


if __name__ == "__main__":
    main()