"""Hidden result interface (black-box experiment).

The full table is read here and nowhere else on the decision side.
The agent can only call `run(cid)` and gets back one voltage at a time.
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

from .space import ROOT, parse_composition

FULL_TABLE = ROOT / "HER实验数据-212条.xlsx"


class BudgetExceeded(RuntimeError):
    pass


class HiddenOracle:
    def __init__(self, budget: int, path: Path = FULL_TABLE):
        frame = pd.read_excel(path)
        self.__results = {}
        for i, row in frame.iterrows():
            parse_composition(str(row["composition"]))  # same validation as decision side
            self.__results[f"C{i:03d}"] = float(row["voltage"])
        self.budget = budget
        self.log: list[dict] = []

    @property
    def used(self) -> int:
        return len(self.log)

    def run(self, cid: str) -> float:
        if cid not in self.__results:
            raise KeyError(f"Unknown candidate {cid}")
        if any(x["cid"] == cid for x in self.log):
            raise ValueError(f"Candidate {cid} already tested")
        if self.used >= self.budget:
            raise BudgetExceeded("Experiment budget exhausted")
        value = self.__results[cid]
        self.log.append({"cid": cid, "voltage": value, "t": time.time()})
        return value


class Evaluator:
    """Evaluation-only view of ground truth. Never handed to a policy."""

    def __init__(self, path: Path = FULL_TABLE, top_fraction: float = 0.10):
        frame = pd.read_excel(path)
        self.truth = {f"C{i:03d}": float(v) for i, v in enumerate(frame["voltage"])}
        ranked = sorted(self.truth.values())
        self.top_k = max(1, round(len(ranked) * top_fraction))
        self.top_threshold = ranked[self.top_k - 1]
        self.global_best = ranked[0]
        self.rank = {cid: sorted(self.truth, key=self.truth.get).index(cid) + 1
                     for cid in self.truth}
