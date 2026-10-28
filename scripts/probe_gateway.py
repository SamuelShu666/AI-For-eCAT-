"""Read-only diagnostics. No credentials or raw response bodies are printed."""
import getpass
import json
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.request import Request, build_opener
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.model_gateway import ModelGateway, _NoCredentialRedirect
key = getpass.getpass("API key (hidden): ").strip()
gateway = ModelGateway(key, "claude-opus-5-5")
req = Request(gateway.base_url + "/models", headers={"Authorization": "Bearer " + key, "User-Agent": "eCAT/0.1"})
try:
    with build_opener(_NoCredentialRedirect()).open(req, timeout=30) as response:
        data = json.load(response)
    matches = [m for m in data.get("data", []) if m.get("id") == "claude-opus-5-5"]
    print(json.dumps({"listed_model": bool(matches), "model_fields": list(matches[0]) if matches else []}))
except HTTPError as error:
    print(json.dumps({"models_status": error.code}))
try:
    reply = gateway.respond("Reply exactly OK.", max_output_tokens=64)
    print(json.dumps({"text_test": reply.text == "OK", "returned_model": reply.model, "usage": reply.usage}))
except RuntimeError as error:
    print(str(error).replace(key, "[redacted]"))
tool = {"type": "function", "name": "connection_ping", "description": "Return OK to check connection.", "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False}}
try:
    response = gateway.request_response({"model":gateway.model,"input":"Use connection_ping now. Do not answer without calling it.","tools":[tool],"tool_choice":"required","max_output_tokens":256,"stream":True,"store":False})
    print(json.dumps({"returned_model":response.get("model"),"output_types":[x.get("type") for x in response.get("output",[])],"output_keys":[list(x) for x in response.get("output",[])],"usage":response.get("usage")}))
except RuntimeError as error:
    print(str(error).replace(key, "[redacted]"))
