"""
Error definitions for the Concurrent Execution Engine.

Contains custom exception classes for device pool and task execution errors.
"""


class DevicePoolError(Exception):
    """Base exception for device pool errors."""
    pass


class DeviceNotFoundError(DevicePoolError):
    """Raised when a device is not found in the pool."""

    def __init__(self, device_id: str):
        self.device_id = device_id
        super().__init__(f"Device not found: {device_id}")


class DeviceAcquisitionTimeoutError(DevicePoolError):
    """Raised when device acquisition times out."""

    def __init__(self, timeout_ms: int, capability: str = None):
        self.timeout_ms = timeout_ms
        self.capability = capability
        msg = f"Device acquisition timed out after {timeout_ms}ms"
        if capability:
            msg += f" for capability: {capability}"
        super().__init__(msg)


class DeviceAlreadyAcquiredError(DevicePoolError):
    """Raised when attempting to acquire an already acquired device."""

    def __init__(self, device_id: str):
        self.device_id = device_id
        super().__init__(f"Device already acquired: {device_id}")


class NoMatchingDeviceError(DevicePoolError):
    """Raised when no device matches the specified requirements."""

    def __init__(self, requirements: str):
        self.requirements = requirements
        super().__init__(f"No device matches requirements: {requirements}")


class TaskExecutionError(Exception):
    """Raised when task execution fails."""

    def __init__(self, task_id: str, message: str, cause: Exception = None):
        self.task_id = task_id
        self.cause = cause
        super().__init__(f"Task {task_id} failed: {message}")


class WorkerInitializationError(Exception):
    """Raised when worker initialization fails."""

    def __init__(self, device_id: str, message: str, cause: Exception = None):
        self.device_id = device_id
        self.cause = cause
        super().__init__(f"Worker initialization failed for device {device_id}: {message}")
