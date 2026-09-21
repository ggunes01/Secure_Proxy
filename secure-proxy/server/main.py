import logging

from .config import ServerConfig
from .proxy_server import ProxyServer


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def main() -> None:
    configure_logging()
    config = ServerConfig.from_env()
    ProxyServer(config).start()


if __name__ == "__main__":
    main()
