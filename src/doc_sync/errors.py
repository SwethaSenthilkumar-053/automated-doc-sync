"""Domain errors used by the documentation synchronization tool."""


class SyncError(Exception):
    """Base class for expected synchronization failures."""


class ConfigurationError(SyncError):
    """Raised when the mapping configuration is invalid."""


class PathSafetyError(ConfigurationError):
    """Raised when a configured path escapes the repository."""


class GeneratorError(SyncError):
    """Raised when a generator is missing or returns invalid output."""


class TransientSyncError(SyncError):
    """Raised for an operation that can reasonably be retried."""


class ConcurrentUpdateError(TransientSyncError):
    """Raised when the repository changes while a sync is running."""


class StateConflictError(TransientSyncError):
    """Raised when durable state changed since it was read."""
