import hmac
import logging
import re
import select
import socket
import ssl
import threading
from contextlib import closing
from urllib.parse import urlsplit

from shared.exceptions import (
    AuthenticationError,
    DestinationRejectedError,
    InvalidRequestError,
    TargetConnectionError,
)
from shared.models import ConnectionContext, ProxyRequest
from shared.protocol import ClientServerProtocol

from .config import ServerConfig

LOGGER = logging.getLogger(__name__)


class SocketReader:
    """Reads framed data without accidentally consuming bytes from the next phase."""

    def __init__(self, timeout_seconds: float):
        self._timeout_seconds = timeout_seconds

    def read_until(self, sock: socket.socket, separator: bytes, initial: bytes = b"", max_bytes: int = 65536) -> tuple[bytes, bytes]:
        buffer = initial
        sock.settimeout(self._timeout_seconds)
        while separator not in buffer:
            if len(buffer) > max_bytes:
                raise InvalidRequestError("Incoming frame is too large")
            chunk = sock.recv(8192)
            if not chunk:
                raise InvalidRequestError("Connection closed before frame was complete")
            buffer += chunk

        index = buffer.index(separator) + len(separator)
        return buffer[:index], buffer[index:]


class TokenAuthenticator:
    """Validates client identity before any proxy request is processed."""

    def __init__(self, expected_token: str):
        self._expected_token = expected_token

    def authenticate(self, frame: bytes) -> None:
        envelope = ClientServerProtocol.parse_auth_frame(frame)
        if not hmac.compare_digest(envelope.token, self._expected_token):
            raise AuthenticationError("Invalid authentication token")


class ProxyRequestParser:
    """Converts raw HTTP proxy bytes into a validated request model."""

    HEADER_END = b"\r\n\r\n"
    CONNECT_TARGET_RE = re.compile(r"^[A-Za-z0-9.-]+:\d{1,5}$")

    def parse(self, header_frame: bytes, body_prefix: bytes = b"") -> tuple[ProxyRequest, bytes]:
        try:
            header_text = header_frame.decode("iso-8859-1")
        except UnicodeDecodeError as exc:
            raise InvalidRequestError("HTTP header cannot be decoded") from exc

        lines = header_text.split("\r\n")
        request_line = lines[0].strip()
        parts = request_line.split()
        if len(parts) != 3:
            raise InvalidRequestError("Invalid HTTP request line")

        method, raw_target, http_version = parts
        method = method.upper()
        headers = self._parse_headers(lines[1:])

        if method == "CONNECT":
            request = self._parse_connect(raw_target, http_version, headers)
            return request, body_prefix

        request, rewritten_header = self._parse_http(method, raw_target, http_version, headers, lines[1:])
        return request, rewritten_header + body_prefix

    def _parse_headers(self, lines: list[str]) -> dict[str, str]:
        headers: dict[str, str] = {}
        for line in lines:
            if not line:
                continue
            if ":" not in line:
                raise InvalidRequestError("Invalid HTTP header")
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
        return headers

    def _parse_connect(self, raw_target: str, http_version: str, headers: dict[str, str]) -> ProxyRequest:
        if not self.CONNECT_TARGET_RE.match(raw_target):
            raise InvalidRequestError("Invalid CONNECT target")
        host, port_text = raw_target.rsplit(":", 1)
        port = self._parse_port(port_text)
        return ProxyRequest(
            method="CONNECT",
            host=host.lower(),
            port=port,
            http_version=http_version,
            raw_target=raw_target,
            headers=headers,
            is_connect=True,
        )

    def _parse_http(
        self,
        method: str,
        raw_target: str,
        http_version: str,
        headers: dict[str, str],
        original_header_lines: list[str],
    ) -> tuple[ProxyRequest, bytes]:
        host = ""
        port = 80
        origin_target = raw_target

        parsed = urlsplit(raw_target)
        if parsed.scheme and parsed.netloc:
            if parsed.scheme.lower() != "http":
                raise InvalidRequestError("Only HTTP requests and HTTPS CONNECT are supported")
            host = parsed.hostname or ""
            port = parsed.port or 80
            path = parsed.path or "/"
            if parsed.query:
                path += f"?{parsed.query}"
            origin_target = path
        else:
            host_header = headers.get("host", "")
            if not host_header:
                raise InvalidRequestError("HTTP request is missing Host header")
            host, port = self._split_host_header(host_header)

        if not host:
            raise InvalidRequestError("Target host is missing")

        rewritten_lines = [f"{method} {origin_target} {http_version}"]
        rewritten_lines.extend(line for line in original_header_lines if line)
        rewritten_header = ("\r\n".join(rewritten_lines) + "\r\n\r\n").encode("iso-8859-1")

        return (
            ProxyRequest(
                method=method,
                host=host.lower(),
                port=port,
                http_version=http_version,
                raw_target=raw_target,
                headers=headers,
                is_connect=False,
            ),
            rewritten_header,
        )

    def _split_host_header(self, value: str) -> tuple[str, int]:
        if ":" not in value:
            return value.lower(), 80
        host, port_text = value.rsplit(":", 1)
        return host.lower(), self._parse_port(port_text)

    def _parse_port(self, value: str) -> int:
        try:
            port = int(value)
        except ValueError as exc:
            raise InvalidRequestError("Port is not numeric") from exc
        if port < 1 or port > 65535:
            raise InvalidRequestError("Port is out of range")
        return port


class DestinationValidator:
    """Applies simple allow/deny rules before opening a target connection."""

    def __init__(self, config: ServerConfig):
        self._config = config

    def validate(self, request: ProxyRequest) -> None:
        if request.port not in self._config.allowed_ports:
            raise DestinationRejectedError("Target port is not allowed")
        if request.host in self._config.blocked_hosts:
            raise DestinationRejectedError("Target host is blocked")
        if request.host.endswith(".local"):
            raise DestinationRejectedError("Local network names are blocked")


class TargetConnector:
    """Owns DNS resolution and TCP connection creation for target websites."""

    def __init__(self, timeout_seconds: float):
        self._timeout_seconds = timeout_seconds

    def connect(self, request: ProxyRequest) -> socket.socket:
        try:
            target_socket = socket.create_connection(request.destination, timeout=self._timeout_seconds)
            target_socket.settimeout(self._timeout_seconds)
            return target_socket
        except OSError as exc:
            raise TargetConnectionError("Could not connect to target") from exc


class BidirectionalForwarder:
    """Copies bytes between client and target sockets."""

    BUFFER_SIZE = 64 * 1024

    def __init__(self, idle_timeout_seconds: float):
        self._idle_timeout_seconds = idle_timeout_seconds

    def forward(self, client_socket: socket.socket, target_socket: socket.socket) -> None:
        sockets = [client_socket, target_socket]
        while True:
            readable, _, errored = select.select(sockets, [], sockets, self._idle_timeout_seconds)
            if errored or not readable:
                return

            for source in readable:
                destination = target_socket if source is client_socket else client_socket
                data = source.recv(self.BUFFER_SIZE)
                if not data:
                    return
                destination.sendall(data)


class ProxySession:
    """Coordinates auth, parsing, validation, target connection and forwarding."""

    def __init__(
        self,
        config: ServerConfig,
        reader: SocketReader,
        authenticator: TokenAuthenticator,
        parser: ProxyRequestParser,
        validator: DestinationValidator,
        connector: TargetConnector,
        forwarder: BidirectionalForwarder,
    ):
        self._config = config
        self._reader = reader
        self._authenticator = authenticator
        self._parser = parser
        self._validator = validator
        self._connector = connector
        self._forwarder = forwarder

    def handle(self, client_socket: socket.socket, address: tuple[str, int]) -> None:
        context = ConnectionContext(client_address=address[0], client_port=address[1])
        LOGGER.info("server_client_connected client=%s", context.label)

        with closing(client_socket):
            try:
                auth_frame, remaining = self._reader.read_until(
                    client_socket,
                    ClientServerProtocol.END_OF_HEADERS,
                    max_bytes=ClientServerProtocol.MAX_AUTH_BYTES,
                )
                self._authenticator.authenticate(auth_frame)
                LOGGER.info("authentication_success client=%s", context.label)

                header_frame, body_prefix = self._reader.read_until(
                    client_socket,
                    ProxyRequestParser.HEADER_END,
                    initial=remaining,
                )
                request, outbound_initial = self._parser.parse(header_frame, body_prefix)
                context.request = request
                self._validator.validate(request)

                with closing(self._connector.connect(request)) as target_socket:
                    LOGGER.info("target_connected client=%s host=%s port=%s", context.label, request.host, request.port)
                    if request.is_connect:
                        client_socket.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    elif outbound_initial:
                        target_socket.sendall(outbound_initial)

                    self._forwarder.forward(client_socket, target_socket)
            except AuthenticationError:
                LOGGER.warning("authentication_failed client=%s", context.label)
                self._safe_send(client_socket, b"HTTP/1.1 407 Proxy Authentication Required\r\n\r\n")
            except (InvalidRequestError, DestinationRejectedError) as exc:
                LOGGER.warning("request_rejected client=%s reason=%s", context.label, exc)
                self._safe_send(client_socket, b"HTTP/1.1 400 Bad Request\r\n\r\n")
            except TargetConnectionError:
                LOGGER.warning("target_unreachable client=%s", context.label)
                self._safe_send(client_socket, b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            except OSError as exc:
                LOGGER.warning("socket_error client=%s error=%s", context.label, exc)
            finally:
                LOGGER.info("server_client_disconnected client=%s", context.label)

    def _safe_send(self, sock: socket.socket, data: bytes) -> None:
        try:
            sock.sendall(data)
        except OSError:
            pass


class ProxyServer:
    """Accepts local-client connections on AWS and starts isolated sessions."""

    def __init__(self, config: ServerConfig):
        self._config = config
        self._reader = SocketReader(config.idle_timeout_seconds)
        self._authenticator = TokenAuthenticator(config.auth_token)
        self._parser = ProxyRequestParser()
        self._validator = DestinationValidator(config)
        self._connector = TargetConnector(config.connect_timeout_seconds)
        self._forwarder = BidirectionalForwarder(config.idle_timeout_seconds)
        self._semaphore = threading.BoundedSemaphore(config.max_connections)
        self._stop_event = threading.Event()

    def start(self) -> None:
        LOGGER.info("proxy_server_starting host=%s port=%s", self._config.listen_host, self._config.listen_port)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((self._config.listen_host, self._config.listen_port))
            server_socket.listen()
            server_socket.settimeout(1)

            listen_socket: socket.socket = server_socket
            ssl_context = self._build_ssl_context()
            LOGGER.info("proxy_server_ready")

            while not self._stop_event.is_set():
                try:
                    client_socket, address = listen_socket.accept()
                except socket.timeout:
                    continue

                if ssl_context:
                    try:
                        client_socket = ssl_context.wrap_socket(client_socket, server_side=True)
                    except ssl.SSLError as exc:
                        LOGGER.warning("tls_handshake_failed address=%s:%s error=%s", address[0], address[1], exc)
                        client_socket.close()
                        continue

                if not self._semaphore.acquire(blocking=False):
                    LOGGER.warning("connection_limit_reached address=%s:%s", address[0], address[1])
                    client_socket.close()
                    continue

                thread = threading.Thread(target=self._run_session, args=(client_socket, address), daemon=True)
                thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _run_session(self, client_socket: socket.socket, address: tuple[str, int]) -> None:
        try:
            session = ProxySession(
                self._config,
                self._reader,
                self._authenticator,
                self._parser,
                self._validator,
                self._connector,
                self._forwarder,
            )
            session.handle(client_socket, address)
        finally:
            self._semaphore.release()

    def _build_ssl_context(self) -> ssl.SSLContext | None:
        if not self._config.use_tls:
            return None
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(self._config.tls_cert_path, self._config.tls_key_path)
        return context
