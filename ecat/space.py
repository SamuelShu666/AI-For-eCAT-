"""Candidate space. Reads ONLY the masked table (no voltage column)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
MASKED_TABLE = ROOT / "HER实验数据-212条 - 结果已掩盖.xlsx"

# Fixed element order used for feature vectors.
ELEMENTS = ["Pd", "Rh", "Ni", "Au", "Ag", "Cu", "Zn", "Cd", "Ga", "In", "Tl", "Hg", "Sn"]
FRACTION_TOLERANCE = 0.002


@dataclass(frozen=True)
class Candidate:
    cid: str            # stable id, e.g. "C017"
    composition: str    # raw string, e.g. "Au-0.25-Cu-0.75"
    fractions: tuple    # ((element, fraction), ...) sorted by element order

    @property
    def elements(self) -> tuple:
        return tuple(e for e, _ in self.fractions)

    @property
    def system(self) -> str:
        return "-".join(sorted(self.elements))

    def vector(self) -> list[float]:
        d = dict(self.fractions)
        return [d.get(e, 0.0) for e in ELEMENTS]

    def to_public(self) -> dict:
        return {"id": self.cid, "composition": self.composition,
                "system": self.system, "fractions": dict(self.fractions)}


def parse_composition(text: str) -> tuple:
    parts = text.strip().split("-")
    if len(parts) % 2:
        raise ValueError(f"Malformed composition: {text!r}")
    pairs = [(parts[i], float(parts[i + 1])) for i in range(0, len(parts), 2)]
    unknown = [e for e, _ in pairs if e not in ELEMENTS]
    if unknown:
        raise ValueError(f"Unknown element(s) {unknown} in {text!r}")
    if abs(sum(f for _, f in pairs) - 1.0) > FRACTION_TOLERANCE:
        raise ValueError(f"Fractions do not sum to 1: {text!r}")
    return tuple(sorted(pairs, key=lambda p: ELEMENTS.index(p[0])))


def load_candidates(path: Path = MASKED_TABLE) -> list[Candidate]:
    frame = pd.read_excel(path)
    if list(frame.columns) != ["composition"]:
        raise RuntimeError("Decision side must read the masked table only.")
    return [Candidate(f"C{i:03d}", str(c), parse_composition(str(c)))
            for i, c in enumerate(frame["composition"])]
