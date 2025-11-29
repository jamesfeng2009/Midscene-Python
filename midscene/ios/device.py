"""
iOS device management using pymobiledevice3
"""

from typing import List, Optional

from loguru import logger
from pydantic import BaseModel

from ..core.types import (
    AbstractInterface,
    InterfaceType,
    UIContext,
    UINode,
    UITree,
    Size,
    Rect,
    NodeType,
    BaseElement,
)
from .errors import iOSDeviceNotFoundError, iOSScreenshotError, iOSTouchError


class iOSElement(BaseElement):
    """iOS UI element wrapper"""

    _device: Optional["iOSDevice"] = None

    def __init__(self, device: "iOSDevice", **kwargs):
        super().__init__(**kwargs)
        self._device = device

    async def tap(self) -> None:
        """Tap this element"""
        if self._device is None:
            raise RuntimeError("Device not set for element")
        center = self.center
        await self._device.tap(center[0], center[1])

    async def input_text(self, text: str) -> None:
        """Input text to this element"""
        if self._device is None:
            raise RuntimeError("Device not set for element")
        await self.tap()
        await self._device.input_text(text)


class iOSDeviceConfig(BaseModel):
    """iOS device configuration"""

    udid: str
    timeout: int = 30
    screenshot_quality: int = 100


class iOSDevice(AbstractInterface):
    """iOS device interface using pymobiledevice3"""

    def __init__(self, udid: str, config: Optional[iOSDeviceConfig] = None):
        """Initialize iOS device

        Args:
            udid: iOS device UDID
            config: Device configuration
        """
        self.udid = udid
        self.config = config or iOSDeviceConfig(udid=udid)
        self._connected = False
        self._screen_size: Optional[Size] = None
        self._lockdown = None

    @classmethod
    async def create(cls, udid: Optional[str] = None) -> "iOSDevice":
        """Create iOS device instance

        Args:
            udid: Device UDID, if None will use first available device

        Returns:
            iOSDevice instance
        """
        if not udid:
            devices = await cls.list_devices()
            if not devices:
                raise RuntimeError("No iOS devices found")
            udid = devices[0]

        device = cls(udid)
        await device.connect()
        return device

    @classmethod
    async def list_devices(cls) -> List[str]:
        """List available iOS devices"""
        try:
            from pymobiledevice3.usbmux import list_devices

            devices = list_devices()
            return [d.serial for d in devices]
        except ImportError:
            logger.error("pymobiledevice3 not installed")
            return []
        except Exception as e:
            logger.error(f"Failed to list devices: {e}")
            return []

    async def connect(self) -> None:
        """Connect to iOS device"""
        try:
            from pymobiledevice3.lockdown import create_using_usbmux

            devices = await self.list_devices()
            if self.udid not in devices:
                raise iOSDeviceNotFoundError(self.udid)

            self._lockdown = create_using_usbmux(serial=self.udid)
            await self._get_screen_size()
            self._connected = True
            logger.info(f"Connected to iOS device: {self.udid}")

        except iOSDeviceNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to connect to device: {e}")
            raise RuntimeError(f"iOS device not found: {self.udid}")

    async def disconnect(self) -> None:
        """Disconnect from device"""
        self._connected = False
        self._lockdown = None
        logger.info(f"Disconnected from device: {self.udid}")

    @property
    def interface_type(self) -> InterfaceType:
        """Get interface type"""
        return InterfaceType.IOS

    async def get_context(self) -> UIContext:
        """Get current UI context"""
        try:
            screenshot_base64 = await self._take_screenshot()

            root_node = UINode(
                id="root",
                content="",
                rect=Rect(
                    left=0,
                    top=0,
                    width=self._screen_size.width if self._screen_size else 390,
                    height=self._screen_size.height if self._screen_size else 844,
                ),
                center=(
                    (self._screen_size.width if self._screen_size else 390) / 2,
                    (self._screen_size.height if self._screen_size else 844) / 2,
                ),
                node_type=NodeType.CONTAINER,
                attributes={},
                is_visible=True,
                children=[],
            )

            return UIContext(
                screenshot_base64=screenshot_base64,
                size=self._screen_size or Size(width=390, height=844),
                content=[],
                tree=UITree(node=root_node, children=[]),
            )

        except Exception as e:
            logger.error(f"Failed to get context: {e}")
            raise

    async def action_space(self) -> List[str]:
        """Get available actions"""
        return [
            "tap",
            "long_press",
            "swipe",
            "scroll",
            "input_text",
            "clear_text",
            "home",
            "lock",
            "launch_app",
            "terminate_app",
            "install_app",
            "list_apps",
        ]

    async def tap(self, x: float, y: float) -> None:
        """Tap at coordinates"""
        try:
            # TODO: Implement using pymobiledevice3 DVT services
            logger.debug(f"Tap at ({x}, {y})")
        except Exception as e:
            logger.error(f"Failed to tap at ({x}, {y}): {e}")
            raise iOSTouchError(f"Tap failed: {e}")

    async def long_press(self, x: float, y: float, duration: int = 1000) -> None:
        """Long press at coordinates"""
        try:
            # TODO: Implement using pymobiledevice3 DVT services
            logger.debug(f"Long press at ({x}, {y}) for {duration}ms")
        except Exception as e:
            logger.error(f"Failed to long press at ({x}, {y}): {e}")
            raise iOSTouchError(f"Long press failed: {e}")

    async def swipe(
        self,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        duration: int = 300,
    ) -> None:
        """Swipe between coordinates"""
        try:
            # TODO: Implement using pymobiledevice3 DVT services
            logger.debug(f"Swipe from ({start_x}, {start_y}) to ({end_x}, {end_y})")
        except Exception as e:
            logger.error(f"Failed to swipe: {e}")
            raise iOSTouchError(f"Swipe failed: {e}")

    async def input_text(self, text: str) -> None:
        """Input text"""
        try:
            # TODO: Implement using pymobiledevice3 keyboard simulation
            logger.debug(f"Input text: {text}")
        except Exception as e:
            logger.error(f"Failed to input text: {e}")
            raise

    async def clear_text(self) -> None:
        """Clear text in focused field"""
        try:
            # TODO: Implement select-all and delete
            logger.debug("Clear text")
        except Exception as e:
            logger.error(f"Failed to clear text: {e}")
            raise

    async def scroll(self, direction: str, distance: Optional[int] = None) -> None:
        """Scroll in direction"""
        valid_directions = ["up", "down", "left", "right"]
        if direction not in valid_directions:
            raise ValueError(
                f"Invalid scroll direction: {direction}. Must be one of {valid_directions}"
            )

        try:
            if not self._screen_size:
                await self._get_screen_size()

            center_x = self._screen_size.width / 2 if self._screen_size else 195
            center_y = self._screen_size.height / 2 if self._screen_size else 422
            dist = distance or 300

            if direction == "down":
                await self.swipe(
                    center_x, center_y + dist / 2, center_x, center_y - dist / 2
                )
            elif direction == "up":
                await self.swipe(
                    center_x, center_y - dist / 2, center_x, center_y + dist / 2
                )
            elif direction == "left":
                await self.swipe(
                    center_x + dist / 2, center_y, center_x - dist / 2, center_y
                )
            elif direction == "right":
                await self.swipe(
                    center_x - dist / 2, center_y, center_x + dist / 2, center_y
                )

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to scroll {direction}: {e}")
            raise

    async def home(self) -> None:
        """Press home button"""
        try:
            # TODO: Implement using pymobiledevice3
            logger.debug("Home button pressed")
        except Exception as e:
            logger.error(f"Failed to press home: {e}")
            raise

    async def lock(self) -> None:
        """Lock device screen"""
        try:
            # TODO: Implement using pymobiledevice3
            logger.debug("Device locked")
        except Exception as e:
            logger.error(f"Failed to lock device: {e}")
            raise

    async def launch_app(self, bundle_id: str) -> None:
        """Launch app by bundle ID"""
        try:
            # TODO: Implement using pymobiledevice3 app services
            logger.debug(f"Launch app: {bundle_id}")
        except Exception as e:
            logger.error(f"Failed to launch app: {e}")
            raise

    async def terminate_app(self, bundle_id: str) -> None:
        """Terminate app by bundle ID"""
        try:
            # TODO: Implement using pymobiledevice3 app services
            logger.debug(f"Terminate app: {bundle_id}")
        except Exception as e:
            logger.error(f"Failed to terminate app: {e}")
            raise

    async def install_app(self, ipa_path: str) -> None:
        """Install app from IPA file"""
        try:
            # TODO: Implement using pymobiledevice3
            logger.debug(f"Install app: {ipa_path}")
        except Exception as e:
            logger.error(f"Failed to install app: {e}")
            raise

    async def list_apps(self) -> List[str]:
        """List installed apps"""
        try:
            # TODO: Implement using pymobiledevice3
            logger.debug("List apps")
            return []
        except Exception as e:
            logger.error(f"Failed to list apps: {e}")
            raise

    async def _take_screenshot(self) -> str:
        """Take screenshot and return base64 string"""
        try:
            import base64
            from io import BytesIO

            if not self._lockdown:
                raise iOSScreenshotError("Device not connected")

            logger.debug("Taking screenshot")
            
            # Use pymobiledevice3 ScreenshotService
            from pymobiledevice3.services.screenshot import ScreenshotService
            
            screenshot_service = ScreenshotService(lockdown=self._lockdown)
            screenshot_data = screenshot_service.take_screenshot()
            
            # screenshot_data is PNG bytes
            screenshot_base64 = base64.b64encode(screenshot_data).decode('utf-8')
            
            return screenshot_base64

        except iOSScreenshotError:
            raise
        except Exception as e:
            logger.error(f"Failed to take screenshot: {e}")
            raise iOSScreenshotError(f"Screenshot failed: {e}")

    async def _get_screen_size(self) -> None:
        """Get device screen size"""
        try:
            # TODO: Get actual screen size from device
            # Default to iPhone 14 dimensions
            self._screen_size = Size(width=390, height=844)
        except Exception as e:
            logger.warning(f"Failed to get screen size: {e}")
            self._screen_size = Size(width=390, height=844)
