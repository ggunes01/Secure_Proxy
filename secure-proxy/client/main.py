import logging

from .config import ClientConfig
from .proxy_client import LocalProxyClient


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def main() -> None:
    configure_logging()
    config = ClientConfig.from_env()
    LocalProxyClient(config).start()


if __name__ == "__main__":
    main()
