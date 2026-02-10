from __future__ import annotations

from dataclasses import dataclass

import tomlkit

from ..settings import SETTINGS


BASE_CONFIG_TOML = """\
approval_policy = "never"
sandbox_mode = "danger-full-access"
forced_login_method = "api"
cli_auth_credentials_store = "file"

[history]
persistence = "none"

[notice]
hide_full_access_warning = true

[mcp_servers.realmoi-status]
command = "python3"
args = ["-X", "utf8", "-m", "realmoi_status_mcp"]
startup_timeout_sec = 10
tool_timeout_sec = 180
"""


@dataclass(frozen=True)
class CodexConfigResult:
    user_overrides_toml: str
    effective_config_toml: str
    allowed_keys: list[str]


def _validate_overrides(doc: tomlkit.TOMLDocument) -> None:
    # Only allow a flat dict of whitelisted keys at root.
    for key, value in doc.items():
        if key not in SETTINGS.codex_user_allowed_keys:
            raise ValueError(f"disallowed_key:{key}")
        if isinstance(value, (tomlkit.items.Table, tomlkit.items.AoT)):
            raise ValueError(f"disallowed_key:{key}")


def build_effective_config(*, user_overrides_toml: str) -> CodexConfigResult:
    allowed = list(SETTINGS.codex_user_allowed_keys)

    base = tomlkit.parse(BASE_CONFIG_TOML)
    overrides = tomlkit.parse(user_overrides_toml or "")
    _validate_overrides(overrides)

    for key in allowed:
        if key in overrides:
            base[key] = overrides[key]

    return CodexConfigResult(
        user_overrides_toml=user_overrides_toml,
        effective_config_toml=tomlkit.dumps(base),
        allowed_keys=allowed,
    )
