class BotError(Exception):
    """Base class for domain errors."""


class PermissionDenied(BotError):
    """Raised when user has insufficient permissions."""


class ValidationError(BotError):
    """Raised when input fails validation."""

