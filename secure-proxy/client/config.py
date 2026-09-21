from __future__ import annotations

import os
from dataclasses import dataclass

from shared.exceptions import ConfigError


@dataclass(frozen=True)
class ClientConfig:
    listen_host: str
    listen_port: int
    server_host: str
    server_port: int
    auth_token: str
    connect_timeout_seconds: float
    idle_timeout_seconds: float
    use_tls: bool
    ca_cert_path: str | None

    @classmethod
    def from_env(cls) -> "ClientConfig":
        token = os.getenv("PROXY_AUTH_TOKEN", "").strip()
        if not token:
            raise ConfigError("PROXY_AUTH_TOKEN must be set")

        return cls(
            listen_host=os.getenv("CLIENT_LISTEN_HOST", "127.0.0.1"),
            listen_port=int(os.getenv("CLIENT_LISTEN_PORT", "8080")),
            server_host=os.getenv("PROXY_SERVER_HOST", "127.0.0.1"),
            server_port=int(os.getenv("PROXY_SERVER_PORT", "9000")),
            auth_token=token,
            connect_timeout_seconds=float(os.getenv("CONNECT_TIMEOUT_SECONDS", "10")),
            idle_timeout_seconds=float(os.getenv("IDLE_TIMEOUT_SECONDS", "120")),
            use_tls=os.getenv("CLIENT_SERVER_TLS", "false").lower() == "true",
            ca_cert_path=os.getenv("PROXY_CA_CERT_PATH") or None,
        )
