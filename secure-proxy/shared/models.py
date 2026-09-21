from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class ProxyRequest:
    method: str
    host: str
    port: int
    http_version: str
    raw_target: str
    headers: Dict[str, str] = field(default_factory=dict)
    is_connect: bool = False

    @property
    def destination(self) -> Tuple[str, int]:
        return self.host, self.port


@dataclass(frozen=True)
class AuthEnvelope:
    token: str


@dataclass
class ConnectionContext:
    client_address: str
    client_port: int
    request: Optional[ProxyRequest] = None

    @property
    def label(self) -> str:
        return f"{self.client_address}:{self.client_port}"
