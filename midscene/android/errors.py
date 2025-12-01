"""
Android-specific exception classes
"""


class AndroidConnectionError(Exception):
    """Android device connection error"""
    pass


class AndroidDeviceNotFoundError(AndroidConnectionError):
    """Device not found error"""
    
    def __init__(self, device_id: str):
        super().__init__(f"Android device not found: {device_id}")
        self.device_id = device_id


class AndroidOperationError(Exception):
    """Android operation error"""
    pass


class AndroidScreenshotError(AndroidOperationError):
    """Screenshot capture failed"""
    pass


class AndroidTouchError(AndroidOperationError):
    """Touch operation failed"""
    pass


class AndroidCoordinateError(AndroidOperationError):
    """Coordinate out of bounds error
    
    Raised when AI-located coordinates are outside the screen bounds.
    """
    
    def __init__(self, x: float, y: float, width: float, height: float):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        super().__init__(
            f"Coordinates ({x}, {y}) are out of screen bounds "
            f"(0 <= x < {width}, 0 <= y < {height})"
        )


class AndroidADBError(AndroidOperationError):
    """ADB command execution error"""
    
    def __init__(self, command: str, error: str):
        self.command = command
        self.error = error
        super().__init__(f"ADB command failed: {command}, error: {error}")
