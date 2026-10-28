"""Thin LLM wrapper: JSON-only replies, retry, and a cost ledger."""
from __future__ import annotations

import json
import re
import sys
import time

from .space import ROOT

sys.path.insert(0, str(ROOT))
from backend.model_gateway import ModelGateway  # noqa: E402

LEDGER = ROOT / "data" / "llm_ledger.jsonl"


def _extract_json(text: str):
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError("no JSON in reply")
    return json.JSONDecoder().raw_decode(text[start:])[0]


class LLM:
    def __init__(self, model: str = "claude-sonnet-5-5", tag: str = ""):
        self.model = model
        self.tag = tag
        self._gw = ModelGateway(model=model, protocol="anthropic")

    def json(self, prompt: str, *, max_tokens: int = 3000, retries: int = 2):
        last = None
        for attempt in range(retries + 1):
            try:
                reply = self._gw.respond(prompt, max_output_tokens=max_tokens, timeout=180)
                data = _extract_json(reply.text)
                self._log(reply.usage, ok=True)
                return data
            except Exception as err:  # noqa: BLE001
                last = err
                time.sleep(2 * (attempt + 1))
        self._log({}, ok=False, error=str(last)[:200])
        raise RuntimeError(f"LLM call failed after retries: {last}")

    def _log(self, usage: dict, **extra):
        LEDGER.parent.mkdir(exist_ok=True)
        row = {"t": round(time.time()), "model": self.model, "tag": self.tag,
               "in": usage.get("input_tokens", 0), "out": usage.get("output_tokens", 0),
               "credits": usage.get("official_credits", 0), **extra}
        with LEDGER.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
