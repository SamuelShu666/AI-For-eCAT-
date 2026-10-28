"""Retry the documented desktop auth path in an isolated Codex home first."""
from pathlib import Path
from datetime import datetime
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.model_gateway import local_api_key

CODEX_HOME = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).resolve()
POINTER = ROOT / ".local" / "desktop-rollback.json"
MODEL = "claude-opus-5-5"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot():
    folder = CODEX_HOME / "backups" / ("openainext-retry-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    folder.mkdir(parents=True, exist_ok=False)
    records = []
    for name in ("config.toml", "auth.json"):
        source = CODEX_HOME / name
        if not source.is_file():
            raise RuntimeError("A required desktop configuration file is missing.")
        shutil.copy2(source, folder / name)
        records.append({"name": name, "sha256": digest(folder / name)})
    manifest = {"codex_home": str(CODEX_HOME), "files": records,
                "scope": "Desktop config.toml and auth.json. Project settings and chat history are not modified."}
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    POINTER.parent.mkdir(parents=True, exist_ok=True)
    POINTER.write_text(json.dumps({"snapshot": str(folder)}, indent=2), encoding="utf-8")
    return folder


def verify_snapshot(folder):
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if Path(manifest["codex_home"]).resolve() != CODEX_HOME:
        raise RuntimeError("Snapshot target does not match this Codex home.")
    if {x["name"] for x in manifest["files"]} != {"config.toml", "auth.json"}:
        raise RuntimeError("Snapshot has unexpected filenames.")
    for record in manifest["files"]:
        if digest(folder / record["name"]) != record["sha256"]:
            raise RuntimeError("Snapshot integrity check failed.")
    return manifest


def restore(verify_only=False):
    folder = Path(json.loads(POINTER.read_text(encoding="utf-8"))["snapshot"]).resolve()
    manifest = verify_snapshot(folder)
    if verify_only:
        print(json.dumps({"snapshot_integrity": "passed", "snapshot": str(folder)}))
        return
    safety = CODEX_HOME / "backups" / ("before-restore-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    safety.mkdir(parents=True, exist_ok=False)
    for record in manifest["files"]:
        target = CODEX_HOME / record["name"]
        if target.exists():
            shutil.copy2(target, safety / record["name"])
    for record in manifest["files"]:
        target = CODEX_HOME / record["name"]
        temporary = target.with_name(target.name + ".restore.tmp")
        shutil.copy2(folder / record["name"], temporary)
        temporary.replace(target)
        if digest(target) != record["sha256"]:
            raise RuntimeError("Restored file verification failed.")
    print("Desktop configuration and login restored. Restart Codex to activate.")


def retry():
    key = local_api_key()
    folder = snapshot()
    verify_snapshot(folder)
    before = {name: digest(CODEX_HOME / name) for name in ("config.toml", "auth.json")}
    print(json.dumps({"backup_created": str(folder), "backup_integrity": "passed"}), flush=True)
    cli = shutil.which("codex")
    if not cli:
        raise RuntimeError("Codex executable was not found.")
    with tempfile.TemporaryDirectory(prefix="ecat-codex-probe-") as temporary:
        isolated = Path(temporary)
        (isolated / "config.toml").write_text(
            f'model = "{MODEL}"\nmodel_provider = "openai-next"\n'
            'model_reasoning_effort = "medium"\nweb_search = "disabled"\n'
            '[model_providers.openai-next]\nname = "openai-next"\n'
            'base_url = "https://api.openai-next.com/v1"\n'
            'requires_openai_auth = true\nwire_api = "responses"\n'
            'request_max_retries = 0\nstream_max_retries = 0\nstream_idle_timeout_ms = 20000\n', encoding="utf-8")
        (isolated / "auth.json").write_text(json.dumps({"OPENAI_API_KEY": key}), encoding="utf-8")
        workspace = isolated / "empty-workspace"
        workspace.mkdir()
        environment = os.environ.copy()
        environment["CODEX_HOME"] = str(isolated)
        for name in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAINEXT_API_KEY"):
            environment.pop(name, None)
        output = isolated / "last-message.txt"
        command = [cli, "exec", "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only",
                   "--color", "never", "--output-last-message", str(output),
                   "--cd", str(workspace), "Reply exactly OK. Do not use any tools."]
        try:
            result = subprocess.run(command, env=environment, capture_output=True,
                                    text=True, encoding="utf-8", errors="replace", timeout=55,
                                    stdin=subprocess.DEVNULL)
            final = output.read_text(encoding="utf-8").strip() if output.exists() else ""
            passed = result.returncode == 0 and final == "OK"
            diagnostic = (result.stderr + "\n" + result.stdout).replace(key, "[redacted]")
            # Save diagnostics from the empty isolated test only; never output credentials.
            (ROOT / ".local" / "desktop-retry-diagnostic.txt").write_text(diagnostic, encoding="utf-8")
            report = {"desktop_cli_test": "passed" if passed else "failed",
                      "exit_code": result.returncode, "exact_ok": final == "OK"}
        except subprocess.TimeoutExpired:
            passed = False
            report = {"desktop_cli_test": "timed_out", "timeout_seconds": 55}
    report.update(model=MODEL, backup=str(folder),
                  actual_desktop_unchanged=all(digest(CODEX_HOME / name) == h for name, h in before.items()))
    (ROOT / ".local" / "desktop-retry-result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report), flush=True)
    if passed:
        print("Isolated text test passed; tool compatibility must be checked before activation.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--restore", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.restore or args.verify_only:
        restore(args.verify_only)
    else:
        retry()

