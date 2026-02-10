from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class McpCallResult:
    content: list[dict[str, Any]]
    structured: dict[str, Any] | None


class McpClientError(RuntimeError):
    pass


def _read_exact(stream, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = stream.read(n - len(buf))
        if not chunk:
            raise McpClientError("mcp_eof")
        buf.extend(chunk)
    return bytes(buf)


def _recv_message(stdout) -> dict[str, Any]:
    headers: dict[str, str] = {}
    while True:
        line = stdout.readline()
        if not line:
            raise McpClientError("mcp_eof")
        line_s = line.decode("utf-8", errors="replace").strip()
        if not line_s:
            break
        if ":" in line_s:
            k, v = line_s.split(":", 1)
            headers[k.strip().lower()] = v.strip()

    length_s = headers.get("content-length")
    if not length_s:
        raise McpClientError("mcp_missing_content_length")
    length = int(length_s)
    body = _read_exact(stdout, length)
    return json.loads(body.decode("utf-8"))


def _send_message(stdin, obj: dict[str, Any]) -> None:
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    stdin.write(f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8"))
    stdin.write(body)
    stdin.flush()


class McpStdioClient:
    def __init__(self, *, module_name: str, env: dict[str, str] | None = None):
        cmd = [sys.executable, "-X", "utf8", "-m", module_name]
        self._proc = subprocess.Popen(  # noqa: S603
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
        )
        if self._proc.stdin is None or self._proc.stdout is None:
            raise McpClientError("mcp_popen_failed")
        self._stdin = self._proc.stdin
        self._stdout = self._proc.stdout
        self._next_id = 0

        self._request("initialize", {})

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._next_id += 1
        msg_id = self._next_id
        _send_message(self._stdin, {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params})

        while True:
            resp = _recv_message(self._stdout)
            if resp.get("id") != msg_id:
                continue
            if "error" in resp:
                raise McpClientError(f"mcp_error:{resp['error']}")
            if "result" not in resp:
                raise McpClientError("mcp_missing_result")
            result = resp.get("result")
            if not isinstance(result, dict):
                raise McpClientError("mcp_invalid_result")
            return result

    def call_tool(self, *, name: str, arguments: dict[str, Any]) -> McpCallResult:
        result = self._request("tools/call", {"name": name, "arguments": arguments})
        content = result.get("content")
        if not isinstance(content, list):
            content = []
        structured = result.get("structuredContent")
        if structured is not None and not isinstance(structured, dict):
            structured = None
        return McpCallResult(content=content, structured=structured)

    def close(self) -> None:
        try:
            self._proc.terminate()
            self._proc.wait(timeout=2)
        except Exception:
            try:
                self._proc.kill()
            except Exception:
                pass

