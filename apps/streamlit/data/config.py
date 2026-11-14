"""Server-side connection preparation; does not open a ClickHouse connection."""
from dataclasses import dataclass, field
from ipaddress import ip_address
import math
import os
import re
from typing import Mapping


@dataclass(frozen=True)
class ClickHouseConfig:
    host: str
    port: int = 8443
    username: str = "default"
    password: str = field(default="", repr=False)
    database: str = "gold"
    secure: bool = True
    connect_timeout: float = 5.0
    query_timeout: float = 30.0

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "ClickHouseConfig":
        env = os.environ if environ is None else environ
        host = env.get("APP_CLICKHOUSE_HOST", "").strip()
        try:
            ip_address(host)
            valid_host = True
        except ValueError:
            labels = host.removesuffix(".").split(".")
            valid_host = bool(host) and len(host) <= 253 and all(
                re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                for label in labels
            )
        if not valid_host:
            raise ValueError("APP_CLICKHOUSE_HOST must be a hostname or IP, without URL or credentials")
        secure = env.get("APP_CLICKHOUSE_SECURE", "true").strip().lower()
        if secure not in {"true", "false"}:
            raise ValueError("APP_CLICKHOUSE_SECURE must be true or false")
        try:
            port = int(env.get("APP_CLICKHOUSE_PORT", "8443" if secure == "true" else "8123"))
        except ValueError:
            raise ValueError("APP_CLICKHOUSE_PORT must be an integer from 1 to 65535") from None
        if not 1 <= port <= 65535:
            raise ValueError("APP_CLICKHOUSE_PORT must be an integer from 1 to 65535")
        timeouts = {}
        for suffix, default in [("CONNECT_TIMEOUT", "5"), ("QUERY_TIMEOUT", "30")]:
            try:
                value = float(env.get("APP_CLICKHOUSE_" + suffix, default))
            except ValueError:
                raise ValueError(f"APP_CLICKHOUSE_{suffix} must be a positive finite number") from None
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"APP_CLICKHOUSE_{suffix} must be a positive finite number")
            timeouts[suffix] = value
        username = env.get("APP_CLICKHOUSE_USER", "default").strip()
        database = env.get("APP_CLICKHOUSE_DATABASE", "gold").strip()
        if not username or not database:
            raise ValueError("APP_CLICKHOUSE_USER and APP_CLICKHOUSE_DATABASE must be nonempty")
        return cls(host=host, port=port, secure=secure == "true", username=username,
                   password=env.get("APP_CLICKHOUSE_PASSWORD", ""), database=database,
                   connect_timeout=timeouts["CONNECT_TIMEOUT"], query_timeout=timeouts["QUERY_TIMEOUT"])
