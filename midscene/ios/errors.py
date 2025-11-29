"""
iOS-specific exception classes
"""


class iOSConnectionError(Exception):
    """iOS device connection error"""
    pass


class iOSDeviceNotFoundError(iOSConnectionError):
    """Device not found error"""
    
    def __init__(self, udid: str):
        super().__init__(f"iOS device not found: {udid}")
        self.udid = udid


class iOSOperationError(Exception):
    """iOS operation error"""
    pass


class iOSScreenshotError(iOSOperationError):
    """Screenshot capture failed"""
    pass


class iOSTouchError(iOSOperationError):
    """Touch operation failed"""
    pass


class iOSCoordinateError(iOSOperationError):
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
