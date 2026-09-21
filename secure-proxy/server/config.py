import os
from dataclasses import dataclass

from shared.exceptions import ConfigError


@dataclass(frozen=True)
class ServerConfig:
    listen_host: str
    listen_port: int
    auth_token: str
    connect_timeout_seconds: float
    idle_timeout_seconds: float
    max_connections: int
    use_tls: bool
    tls_cert_path: str | None
    tls_key_path: str | None
    allowed_ports: set[int]
    blocked_hosts: set[str]

    @classmethod
    def from_env(cls) -> "ServerConfig":
        token = os.getenv("PROXY_AUTH_TOKEN", "").strip()
        if not token:
            raise ConfigError("PROXY_AUTH_TOKEN must be set")

        use_tls = os.getenv("CLIENT_SERVER_TLS", "false").lower() == "true"
        cert_path = os.getenv("PROXY_TLS_CERT_PATH") or None
        key_path = os.getenv("PROXY_TLS_KEY_PATH") or None
        if use_tls and (not cert_path or not key_path):
            raise ConfigError("TLS is enabled, but certificate/key paths are missing")

        allowed_ports = {
            int(port.strip())
            for port in os.getenv("ALLOWED_TARGET_PORTS", "80,443").split(",")
            if port.strip()
        }

        blocked_hosts = {
            host.strip().lower()
            for host in os.getenv("BLOCKED_TARGET_HOSTS", "localhost,127.0.0.1,0.0.0.0").split(",")
            if host.strip()
        }

        return cls(
            listen_host=os.getenv("SERVER_LISTEN_HOST", "0.0.0.0"),
            listen_port=int(os.getenv("PROXY_SERVER_PORT", "9000")),
            auth_token=token,
            connect_timeout_seconds=float(os.getenv("CONNECT_TIMEOUT_SECONDS", "10")),
            idle_timeout_seconds=float(os.getenv("IDLE_TIMEOUT_SECONDS", "120")),
            max_connections=int(os.getenv("MAX_CONNECTIONS", "200")),
            use_tls=use_tls,
            tls_cert_path=cert_path,
            tls_key_path=key_path,
            allowed_ports=allowed_ports,
            blocked_hosts=blocked_hosts,
        )
