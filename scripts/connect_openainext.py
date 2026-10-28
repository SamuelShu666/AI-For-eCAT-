"""Test the supplied key, then merge Codex config without changing auth.json."""
from __future__ import annotations

import argparse
import ctypes
import getpass
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.model_gateway import ModelGateway, text_reply

BASE_URL = "https://api.openai-next.com/v1"
MODEL = "claude-opus-5-5"
PROVIDER = "openai-next"


def merged_config(source: str) -> str:
    parsed = tomllib.loads(source)
    if PROVIDER in parsed.get("model_providers", {}):
        raise RuntimeError("An openai-next provider already exists; review it before replacing.")
    # Only edit root keys, leaving every existing table and auth setting intact.
    first_table = re.search(r"(?m)^\s*\[", source)
    split_at = first_table.start() if first_table else len(source)
    root, tables = source[:split_at], source[split_at:]
    for key, value in {"model": MODEL, "model_provider": PROVIDER}.items():
        pattern = rf"(?m)^{key}\s*=.*$"
        replacement = f'{key} = "{value}"'
        if re.search(pattern, root):
            root = re.sub(pattern, lambda _: replacement, root)
        else:
            root += "\n" + replacement + "\n"
    section = (f'\n[model_providers.{PROVIDER}]\n'
               f'name = "OpenAINext"\nbase_url = "{BASE_URL}"\n'
               'wire_api = "responses"\nenv_key = "OPENAINEXT_API_KEY"\n'
               'requires_openai_auth = false\n')
    result = root.rstrip() + "\n\n" + tables.rstrip() + "\n" + section
    check = tomllib.loads(result)
    if check.get("model_provider") != PROVIDER:
        raise RuntimeError("Provider configuration verification failed.")
    original_other = {k: v for k, v in parsed.items()
                      if k not in {"model", "model_provider", "model_providers"}}
    actual_other = {k: v for k, v in check.items()
                    if k not in {"model", "model_provider", "model_providers"}}
    if original_other != actual_other:
        raise RuntimeError("Unrelated settings changed; activation cancelled.")
    if check["model_providers"].get(PROVIDER, {}).get("base_url") != BASE_URL:
        raise RuntimeError("Provider URL verification failed.")
    for name, value in parsed.get("model_providers", {}).items():
        if check["model_providers"].get(name) != value:
            raise RuntimeError("An existing provider changed; activation cancelled.")
    return result


def write_status(path: Path, **values):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def test_tool_loop(gateway):
    prompt = {"role": "user", "content": [{"type": "input_text",
              "text": "Call connection_ping once, then reply exactly with its returned value."}]}
    tool = {"type": "function", "name": "connection_ping",
            "description": "A harmless local connection check returning OK.",
            "parameters": {"type": "object", "properties": {},
                           "required": [], "additionalProperties": False}, "strict": True}
    body = {"model": MODEL, "input": [prompt], "stream": True, "store": False,
            "max_output_tokens": 256, "tools": [tool],
            "tool_choice": {"type": "function", "name": "connection_ping"}}
    first = gateway.request_response(body)
    calls = [x for x in first.get("output", []) if x.get("type") == "function_call"]
    if len(calls) != 1 or calls[0].get("name") != "connection_ping" or not calls[0].get("call_id"):
        write_status(ROOT / ".local" / "tool-probe.json", model=first.get("model"),
                     output_types=[x.get("type") for x in first.get("output", [])],
                     output_keys=[list(x) for x in first.get("output", [])],
                     usage=first.get("usage") or {})
        raise RuntimeError("The requested model did not return the expected tool call.")
    if json.loads(calls[0].get("arguments", "null")) != {}:
        raise RuntimeError("The model returned invalid tool arguments.")
    body["input"] = [prompt] + first["output"] + [
        {"type": "function_call_output", "call_id": calls[0]["call_id"], "output": "OK"}]
    body["tool_choice"] = "none"
    second = gateway.request_response(body)
    reply = text_reply(second)
    if reply.text != "OK":
        raise RuntimeError("Tool continuation did not return OK; desktop activation cancelled.")
    return reply, [first.get("usage") or {}, second.get("usage") or {}]


def activate(key: str, status_path: Path):
    if os.name != "nt":
        raise RuntimeError("This desktop configuration helper requires Windows.")
    config_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    config = config_home / "config.toml"
    original = config.read_text(encoding="utf-8-sig")
    replacement = merged_config(original)
    write_status(status_path, status="testing", model=MODEL, base_url=BASE_URL)
    reply, usages = test_tool_loop(ModelGateway(key, MODEL, BASE_URL))
    if config.read_text(encoding="utf-8-sig") != original:
        raise RuntimeError("Codex configuration changed during testing; activation cancelled.")
    backup = config_home / "backups" / ("openainext-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    backup.mkdir(parents=True, exist_ok=False)
    shutil.copy2(config, backup / "config.toml")

    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, "Environment") as handle:
        try:
            previous, previous_type = winreg.QueryValueEx(handle, "OPENAINEXT_API_KEY")
        except FileNotFoundError:
            previous, previous_type = None, winreg.REG_SZ
        try:
            winreg.SetValueEx(handle, "OPENAINEXT_API_KEY", 0, winreg.REG_SZ, key)
            temporary = config.with_name("config.toml.openainext.tmp")
            temporary.write_text(replacement, encoding="utf-8")
            temporary.replace(config)
        except Exception:
            if previous is None:
                try:
                    winreg.DeleteValue(handle, "OPENAINEXT_API_KEY")
                except FileNotFoundError:
                    pass
            else:
                winreg.SetValueEx(handle, "OPENAINEXT_API_KEY", 0, previous_type, previous)
            raise
    # Notify desktop launchers that the user's environment changed.
    try:
        result = ctypes.c_size_t()
        ctypes.windll.user32.SendMessageTimeoutW(
            0xFFFF, 0x001A, 0, ctypes.c_wchar_p("Environment"),
            2, 3000, ctypes.byref(result))
    except Exception:
        pass
    write_status(status_path, status="configured_restart_required", model=MODEL,
                 base_url=BASE_URL, response_test="passed", tool_loop_test="passed", usage=usages,
                 backup=str(backup / "config.toml"),
                 project_adapter="backend/model_gateway.py", auth_json_modified=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", type=Path, default=ROOT / ".local" / "connection-status.json")
    parser.add_argument("--stdin-key", action="store_true")
    args = parser.parse_args()
    key = (getpass.getpass("API key (hidden): ").strip() if args.stdin_key
           else os.environ.get("OPENAINEXT_SETUP_KEY", "").strip())
    try:
        if not key:
            raise RuntimeError("No key was entered; no configuration was changed.")
        activate(key, args.status)
        print("Connection test passed. Project adapter ready. Restart Codex to activate desktop routing.")
    except Exception as error:
        # Known messages contain no credentials or response bodies. Unknown details stay private.
        message = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        if key:
            message = message.replace(key, "[redacted]")
        write_status(args.status, status="failed", error=message)
        print("Connection setup failed: " + message)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

