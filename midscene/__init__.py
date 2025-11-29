"""
Midscene Python - AI-powered automation framework

A Python implementation of Midscene, providing AI-driven automation
capabilities for Web, Android, and iOS platforms.
"""

from .core.agent import Agent
from .core.insight import Insight
from .core.types import UIContext, LocateResult, ExecutionResult

# iOS module exports for convenience
from .ios import (
    iOSDevice,
    iOSAgent,
    iOSElement,
    iOSDeviceConfig,
    iOSConnectionError,
    iOSDeviceNotFoundError,
    iOSOperationError,
    iOSScreenshotError,
    iOSTouchError,
    iOSCoordinateError,
)

__version__ = "0.1.0"

__all__ = [
    # Core classes
    "Agent",
    "Insight", 
    "UIContext",
    "LocateResult",
    "ExecutionResult",
    # iOS classes
    "iOSDevice",
    "iOSAgent",
    "iOSElement",
    "iOSDeviceConfig",
    "iOSConnectionError",
    "iOSDeviceNotFoundError",
    "iOSOperationError",
    "iOSScreenshotError",
    "iOSTouchError",
    "iOSCoordinateError",
]