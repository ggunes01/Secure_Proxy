from typing import Tuple

from .exceptions import AuthenticationError, InvalidRequestError
from .models import AuthEnvelope


class ClientServerProtocol:
    """Small framing protocol between local client and AWS proxy server."""

    VERSION_LINE = "SECURE_PROXY/1"
    END_OF_HEADERS = b"\n\n"
    MAX_AUTH_BYTES = 4096

    @classmethod
    def build_auth_frame(cls, token: str) -> bytes:
        return (
            f"{cls.VERSION_LINE}\n"
            f"Authorization: Bearer {token}\n"
            "\n"
        ).encode("utf-8")

    @classmethod
    def parse_auth_frame(cls, data: bytes) -> AuthEnvelope:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AuthenticationError("Authentication frame is not valid UTF-8") from exc

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines or lines[0] != cls.VERSION_LINE:
            raise AuthenticationError("Unsupported proxy protocol version")

        auth_line = next((line for line in lines[1:] if line.lower().startswith("authorization:")), None)
        if not auth_line:
            raise AuthenticationError("Missing authorization header")

        _, value = auth_line.split(":", 1)
        value = value.strip()
        prefix = "Bearer "
        if not value.startswith(prefix):
            raise AuthenticationError("Unsupported authorization scheme")

        token = value[len(prefix):].strip()
        if not token:
            raise AuthenticationError("Empty authorization token")
        return AuthEnvelope(token=token)

    @classmethod
    def split_auth_frame(cls, buffer: bytes) -> Tuple[bytes, bytes]:
        marker = cls.END_OF_HEADERS
        index = buffer.find(marker)
        if index == -1:
            if len(buffer) > cls.MAX_AUTH_BYTES:
                raise InvalidRequestError("Authentication frame is too large")
            return b"", buffer
        frame_end = index + len(marker)
        return buffer[:frame_end], buffer[frame_end:]
