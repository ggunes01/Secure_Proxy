class ProxyError(Exception):
    """Base exception for expected proxy errors."""


class ConfigError(ProxyError):
    """Raised when configuration is missing or invalid."""


class AuthenticationError(ProxyError):
    """Raised when a client cannot be authenticated."""


class InvalidRequestError(ProxyError):
    """Raised when the browser/client sent an invalid proxy request."""


class DestinationRejectedError(ProxyError):
    """Raised when destination validation rejects a target."""


class TargetConnectionError(ProxyError):
    """Raised when the proxy cannot connect to the target server."""


class ForwardingError(ProxyError):
    """Raised when bidirectional data forwarding fails."""
