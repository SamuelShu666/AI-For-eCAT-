"""Small Responses API adapter. Keys and response bodies are never logged."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, HTTPRedirectHandler, build_opener


class _NoCredentialRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def local_setting(name: str, default: str = "") -> str:
    value = os.environ.get(name, "").strip()
    if not value and os.name == "nt":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as handle:
                value = winreg.QueryValueEx(handle, name)[0].strip()
        except FileNotFoundError:
            pass
    return value or default


def local_api_key() -> str:
    value = local_setting("OPENAINEXT_API_KEY")
    if not value:
        raise RuntimeError("OPENAINEXT_API_KEY is missing. Run the local connection helper.")
    return value


@dataclass(frozen=True)
class ModelReply:
    text: str
    model: str
    usage: dict
    response_id: str


def read_completed_stream(lines) -> dict:
    """Require a completed response; never treat truncated output as success."""
    completed = None
    for line in lines:
        if isinstance(line, bytes):
            line = line.decode("utf-8")
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            raise RuntimeError("Gateway returned an invalid SSE event.") from None
        event_type = event.get("type", "")
        if event_type in {"error", "response.failed", "response.incomplete"}:
            raise RuntimeError("Gateway response failed or exceeded the output limit.")
        if event_type == "response.completed":
            completed = event.get("response", {})
    if not completed or completed.get("status") != "completed":
        raise RuntimeError("Gateway stream ended without a completed response.")
    return completed


def text_reply(completed: dict) -> ModelReply:
    text_parts = []
    for item in completed.get("output", []):
        if item.get("type") == "message":
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    text_parts.append(content.get("text", ""))
    text = "".join(text_parts).strip()
    if not text:
        raise RuntimeError("Gateway completed without text output.")
    return ModelReply(text, completed.get("model", ""),
                      completed.get("usage") or {}, completed.get("id", ""))


def read_response_stream(lines) -> ModelReply:
    return text_reply(read_completed_stream(lines))


class ModelGateway:
    def __init__(self, api_key: str | None = None, model: str | None = None,
                 base_url: str | None = None, protocol: str | None = None):
        self._api_key = api_key or local_api_key()
        self.model = model or local_setting("OPENAINEXT_MODEL", "claude-opus-5-5")
        self.protocol = protocol or local_setting("OPENAINEXT_PROTOCOL",
            "anthropic" if self.model.startswith("claude-") else "responses")
        self.base_url = (base_url or local_setting(
            "OPENAINEXT_BASE_URL", "https://api.openai-next.com/v1")).rstrip("/")
        if not self.base_url.startswith("https://"):
            raise ValueError("The model gateway must use HTTPS.")

    def respond(self, prompt: str, *, max_output_tokens: int = 1024,
                timeout: int = 90) -> ModelReply:
        if not 1 <= max_output_tokens <= 4096:
            raise ValueError("max_output_tokens must be between 1 and 4096.")
        if self.protocol == "anthropic":
            return self._anthropic_reply(prompt, max_output_tokens, timeout)
        body = {"model": self.model, "input": [{"role": "user", "content": [
                    {"type": "input_text", "text": prompt}]}], "stream": True,
                "store": False, "max_output_tokens": max_output_tokens}
        if self.model == "gpt-6.1-sol":
            body["reasoning"] = {"effort": "low"}
        return text_reply(self.request_response(body, timeout=timeout))

    def _anthropic_reply(self, prompt: str, max_tokens: int, timeout: int) -> ModelReply:
        body = {"model": self.model, "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}]}
        request = Request(self.base_url + "/messages", data=json.dumps(body).encode("utf-8"),
                          headers={"x-api-key": self._api_key, "anthropic-version": "2023-06-01",
                                   "Content-Type": "application/json", "User-Agent": "eCAT/0.1"},
                          method="POST")
        try:
            with build_opener(_NoCredentialRedirect()).open(request, timeout=timeout) as response:
                result = json.load(response)
        except HTTPError as error:
            raise RuntimeError(f"Native model endpoint HTTP {error.code}.") from None
        except (URLError, TimeoutError):
            raise RuntimeError("Native model connection failed or timed out.") from None
        except json.JSONDecodeError:
            raise RuntimeError("Native model endpoint returned invalid JSON.") from None
        if result.get("stop_reason") != "end_turn":
            raise RuntimeError("Native model response did not finish normally.")
        text = "".join(x.get("text", "") for x in result.get("content", [])
                       if x.get("type") == "text").strip()
        if not text:
            raise RuntimeError("Native model endpoint returned no text.")
        return ModelReply(text, result.get("model", ""), result.get("usage") or {}, result.get("id", ""))

    def request_response(self, body: dict, *, timeout: int = 90) -> dict:
        request = Request(self.base_url + "/responses",
                          data=json.dumps(body).encode("utf-8"),
                          headers={"Authorization": "Bearer " + self._api_key,
                                   "Content-Type": "application/json",
                                   "User-Agent": "eCAT/0.1",
                                   "Accept": "text/event-stream"}, method="POST")
        try:
            with build_opener(_NoCredentialRedirect()).open(request, timeout=timeout) as response:
                if "text/event-stream" not in response.headers.get("Content-Type", ""):
                    raise RuntimeError("Gateway did not return a Responses SSE stream.")
                return read_completed_stream(response)
        except HTTPError as error:
            detail = ""
            payload = error.read(8192).decode("utf-8", errors="replace")
            try:
                problem = json.loads(payload).get("error", {})
                if isinstance(problem, dict):
                    detail = str(problem.get("message", problem.get("code", "")))[:400]
            except (json.JSONDecodeError, AttributeError):
                if "cloudflare" in payload.lower() or "error code: 1010" in payload.lower():
                    detail = "Request rejected by gateway edge filtering."
            detail = detail.replace(self._api_key, "[redacted]")
            raise RuntimeError(f"Gateway HTTP {error.code}: {detail or 'check key, credit and model access.'}") from None
        except (URLError, TimeoutError):
            raise RuntimeError("Gateway connection failed or timed out.") from None

