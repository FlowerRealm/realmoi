from __future__ import annotations

"""Terminal log streaming helpers for runner processes."""

from pathlib import Path


def redact_bytes(*, data: bytes, secrets: list[str]) -> bytes:
    output = data
    for secret in secrets:
        if secret:
            output = output.replace(secret.encode("utf-8"), b"***")
    return output


def stream_terminal_log(
    *,
    stdout,
    log_path: Path,
    max_bytes: int,
    redact_secrets: list[str],
) -> int:
    """Stream `stdout` bytes into `log_path` with redaction and size cap."""
    log_path.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    try:
        with log_path.open("ab") as log_file:
            while True:
                raw = stdout.read(4096)
                if not raw:
                    break
                safe = redact_bytes(data=raw, secrets=redact_secrets)
                if written >= max_bytes:
                    continue
                remaining = int(max_bytes) - int(written)
                out = safe[: max(0, remaining)]
                if not out:
                    continue
                log_file.write(out)
                log_file.flush()
                written += len(out)
    except Exception:
        return written
    return written

