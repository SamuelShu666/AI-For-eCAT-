"""Check the documented native protocol; persist credentials only after success."""
import getpass
import json
import sys
from pathlib import Path
from urllib.request import Request, build_opener
from urllib.error import HTTPError
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.model_gateway import _NoCredentialRedirect
key = getpass.getpass("API key (hidden): ").strip()
body = {"model":"claude-opus-5-5", "max_tokens":64,
        "messages":[{"role":"user","content":"Reply exactly OK."}]}
headers = {"x-api-key":key, "anthropic-version":"2023-06-01",
           "Content-Type":"application/json", "User-Agent":"eCAT/0.1"}
request = Request("https://api.openai-next.com/v1/messages",
                  data=json.dumps(body).encode(), headers=headers, method="POST")
try:
    with build_opener(_NoCredentialRedirect()).open(request,timeout=90) as response:
        reply=json.load(response)
    text="".join(x.get("text","") for x in reply.get("content",[]) if x.get("type")=="text").strip()
    summary={"native_text_test":text=="OK","returned_model":reply.get("model"),
             "content_types":[x.get("type") for x in reply.get("content",[])],"usage":reply.get("usage")}
    print(json.dumps(summary))
    if text != "OK":raise RuntimeError("Native endpoint did not return OK.")
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,"Environment") as handle:
        for name,value in {"OPENAINEXT_API_KEY":key,"OPENAINEXT_MODEL":"claude-opus-5-5","OPENAINEXT_PROTOCOL":"anthropic"}.items():
            winreg.SetValueEx(handle,name,0,winreg.REG_SZ,value)
    status=Path(__file__).resolve().parents[1]/'.local'/'connection-status.json'
    summary.update(status="project_configured_desktop_responses_incompatible",model="claude-opus-5-5",codex_config_changed=False,protocol="anthropic")
    status.write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print('Project credential and model saved; desktop configuration has not been changed.')
except HTTPError as error:
    payload=error.read(8192).decode('utf-8',errors='replace')
    message=''
    try:message=str(json.loads(payload).get('error',{}).get('message',''))[:400]
    except (ValueError,AttributeError):pass
    print(json.dumps({'native_http_status':error.code,'message':message.replace(key,'[redacted]')}))
    raise SystemExit(1)
except RuntimeError as error:
    print(str(error).replace(key,'[redacted]'));raise SystemExit(1)
