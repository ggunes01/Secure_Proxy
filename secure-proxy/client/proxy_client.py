import logging
import select
import socket
import ssl
import threading
from contextlib import closing

from shared.protocol import ClientServerProtocol

from .config import ClientConfig

LOGGER = logging.getLogger(__name__)


class AwsConnectionFactory:
    """Creates one upstream connection to the AWS proxy for each browser socket."""

    def __init__(self, config: ClientConfig):
        self._config = config

    def create(self) -> socket.socket:
        raw_socket = socket.create_connection(
            (self._config.server_host, self._config.server_port),
            timeout=self._config.connect_timeout_seconds,
        )
        raw_socket.settimeout(self._config.idle_timeout_seconds)

        if not self._config.use_tls:
            return raw_socket

        context = ssl.create_default_context()
        if self._config.ca_cert_path:
            context.load_verify_locations(self._config.ca_cert_path)
        return context.wrap_socket(raw_socket, server_hostname=self._config.server_host)


class BidirectionalRelay:
    """Moves bytes between browser and AWS proxy until either side closes."""

    BUFFER_SIZE = 64 * 1024

    def __init__(self, idle_timeout_seconds: float):
        self._idle_timeout_seconds = idle_timeout_seconds

    def relay(self, left: socket.socket, right: socket.socket) -> None:
        sockets = [left, right]
        while True:
            readable, _, errored = select.select(sockets, [], sockets, self._idle_timeout_seconds)
            if errored or not readable:
                return

            for source in readable:
                target = right if source is left else left
                data = source.recv(self.BUFFER_SIZE)
                if not data:
                    return
                target.sendall(data)


class BrowserConnectionHandler:
    """Handles one accepted browser connection."""

    def __init__(
        self,
        config: ClientConfig,
        aws_factory: AwsConnectionFactory,
        relay: BidirectionalRelay,
    ):
        self._config = config
        self._aws_factory = aws_factory
        self._relay = relay

    def handle(self, browser_socket: socket.socket, browser_address: tuple[str, int]) -> None:
        LOGGER.info("browser_connected address=%s:%s", browser_address[0], browser_address[1])
        with closing(browser_socket):
            try:
                with closing(self._aws_factory.create()) as aws_socket:
                    auth_frame = ClientServerProtocol.build_auth_frame(self._config.auth_token)
                    aws_socket.sendall(auth_frame)
                    self._relay.relay(browser_socket, aws_socket)
            except OSError as exc:
                LOGGER.warning("client_connection_error address=%s:%s error=%s", *browser_address, exc)
            finally:
                LOGGER.info("browser_disconnected address=%s:%s", browser_address[0], browser_address[1])


class LocalProxyClient:
    """Listens on localhost and forwards browser proxy traffic to AWS."""

    def __init__(self, config: ClientConfig):
        self._config = config
        self._aws_factory = AwsConnectionFactory(config)
        self._relay = BidirectionalRelay(config.idle_timeout_seconds)
        self._handler = BrowserConnectionHandler(config, self._aws_factory, self._relay)
        self._stop_event = threading.Event()

    def start(self) -> None:
        LOGGER.info("local_proxy_starting host=%s port=%s", self._config.listen_host, self._config.listen_port)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((self._config.listen_host, self._config.listen_port))
            server_socket.listen()
            server_socket.settimeout(1)
            LOGGER.info("local_proxy_ready")

            while not self._stop_event.is_set():
                try:
                    browser_socket, browser_address = server_socket.accept()
                except socket.timeout:
                    continue

                thread = threading.Thread(
                    target=self._handler.handle,
                    args=(browser_socket, browser_address),
                    daemon=True,
                )
                thread.start()

    def stop(self) -> None:
        self._stop_event.set()
