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
