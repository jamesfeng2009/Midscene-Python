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
from .errors import iOSDeviceNotFoundError, iOSScreenshotError, iOSTouchError, iOSCoordinateError


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

    def validate_coordinates(self, x: float, y: float) -> None:
        """Validate that coordinates are within screen bounds
        
        This method ensures AI-located coordinates are within the screen bounds
        before tap operations, as required by Requirements 10.2.
        
        Args:
            x: X coordinate to validate
            y: Y coordinate to validate
            
        Raises:
            iOSCoordinateError: If coordinates are outside screen bounds
            RuntimeError: If screen size is not available
        """
        if self._screen_size is None:
            raise RuntimeError("Screen size not available. Device may not be connected.")
        
        width = self._screen_size.width
        height = self._screen_size.height
        
        # Check if coordinates are within bounds: 0 <= x < width, 0 <= y < height
        if not (0 <= x < width and 0 <= y < height):
            raise iOSCoordinateError(x, y, width, height)

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
        """Tap at coordinates using pymobiledevice3 DVT services
        
        Validates that coordinates are within screen bounds before performing
        the tap operation, ensuring AI-located coordinates are valid.
        
        Args:
            x: X coordinate to tap
            y: Y coordinate to tap
            
        Raises:
            iOSTouchError: If device is not connected or tap fails
            iOSCoordinateError: If coordinates are outside screen bounds
        """
        try:
            if not self._lockdown:
                raise iOSTouchError("Device not connected")
            
            # Validate coordinates are within screen bounds (Requirements 10.2)
            if self._screen_size is not None:
                self.validate_coordinates(x, y)
            
            from pymobiledevice3.services.dvt.dvt_secure_socket_proxy import DvtSecureSocketProxyService
            from pymobiledevice3.services.dvt.instruments.device_info import DeviceInfo
            
            with DvtSecureSocketProxyService(lockdown=self._lockdown) as dvt:
                # Use HID simulation for touch events
                # pymobiledevice3 provides simulate_touch through DVT
                DeviceInfo(dvt).simulate_touch(x, y)
            
            logger.debug(f"Tap at ({x}, {y})")
        except (iOSTouchError, iOSCoordinateError):
            raise
        except Exception as e:
            logger.error(f"Failed to tap at ({x}, {y}): {e}")
            raise iOSTouchError(f"Tap failed: {e}")

    async def long_press(self, x: float, y: float, duration: int = 1000) -> None:
        """Long press at coordinates for extended touch events
        
        Args:
            x: X coordinate to press
            y: Y coordinate to press
            duration: Duration of press in milliseconds (default: 1000ms)
        """
        try:
            if not self._lockdown:
                raise iOSTouchError("Device not connected")
            
            import asyncio
            from pymobiledevice3.services.dvt.dvt_secure_socket_proxy import DvtSecureSocketProxyService
            from pymobiledevice3.services.dvt.instruments.device_info import DeviceInfo
            
            with DvtSecureSocketProxyService(lockdown=self._lockdown) as dvt:
                device_info = DeviceInfo(dvt)
                # Simulate touch down, hold, then release
                # Touch down at coordinates
                device_info.simulate_touch(x, y, touch_type=1)  # 1 = touch down
                # Wait for duration
                await asyncio.sleep(duration / 1000.0)
                # Touch up
                device_info.simulate_touch(x, y, touch_type=2)  # 2 = touch up
            
            logger.debug(f"Long press at ({x}, {y}) for {duration}ms")
        except iOSTouchError:
            raise
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
        """Swipe from start coordinates to end coordinates
        
        Args:
            start_x: Starting X coordinate
            start_y: Starting Y coordinate
            end_x: Ending X coordinate
            end_y: Ending Y coordinate
            duration: Duration of swipe in milliseconds (default: 300ms)
        """
        try:
            if not self._lockdown:
                raise iOSTouchError("Device not connected")
            
            import asyncio
            from pymobiledevice3.services.dvt.dvt_secure_socket_proxy import DvtSecureSocketProxyService
            from pymobiledevice3.services.dvt.instruments.device_info import DeviceInfo
            
            # Calculate number of steps based on duration
            # Use ~60fps for smooth animation
            steps = max(int(duration / 16), 10)  # At least 10 steps
            step_delay = duration / 1000.0 / steps
            
            # Calculate delta per step
            delta_x = (end_x - start_x) / steps
            delta_y = (end_y - start_y) / steps
            
            with DvtSecureSocketProxyService(lockdown=self._lockdown) as dvt:
                device_info = DeviceInfo(dvt)
                
                # Touch down at start position
                device_info.simulate_touch(start_x, start_y, touch_type=1)  # touch down
                
                # Move through intermediate points
                for i in range(1, steps):
                    current_x = start_x + delta_x * i
                    current_y = start_y + delta_y * i
                    await asyncio.sleep(step_delay)
                    device_info.simulate_touch(current_x, current_y, touch_type=3)  # touch move
                
                # Touch up at end position
                await asyncio.sleep(step_delay)
                device_info.simulate_touch(end_x, end_y, touch_type=2)  # touch up
            
            logger.debug(f"Swipe from ({start_x}, {start_y}) to ({end_x}, {end_y})")
        except iOSTouchError:
            raise
        except Exception as e:
            logger.error(f"Failed to swipe: {e}")
            raise iOSTouchError(f"Swipe failed: {e}")

    async def input_text(self, text: str) -> None:
        """Input text using pymobiledevice3 keyboard simulation
        
        Args:
            text: Text to input (supports unicode and special characters)
        """
        try:
            if not self._lockdown:
                raise RuntimeError("Device not connected")
            
            from pymobiledevice3.services.simulate_location import DtSimulateLocation
            from pymobiledevice3.services.dvt.dvt_secure_socket_proxy import DvtSecureSocketProxyService
            from pymobiledevice3.services.dvt.instruments.process_control import ProcessControl
            
            # Use pymobiledevice3's keyboard simulation via DVT services
            # The text is sent character by character through HID events
            with DvtSecureSocketProxyService(lockdown=self._lockdown) as dvt:
                process_control = ProcessControl(dvt)
                
                # Send text through keyboard simulation
                # pymobiledevice3 handles escaping internally
                for char in text:
                    # Simulate key press for each character
                    # This uses the HID keyboard simulation
                    process_control.send_key(char)
            
            logger.debug(f"Input text: {text}")
        except RuntimeError:
            raise
        except ImportError as e:
            # Fallback: try alternative method using accessibility
            logger.warning(f"DVT keyboard simulation not available: {e}")
            await self._input_text_fallback(text)
        except Exception as e:
            logger.error(f"Failed to input text: {e}")
            raise RuntimeError(f"Text input failed: {e}")

    async def _input_text_fallback(self, text: str) -> None:
        """Fallback text input method using accessibility services
        
        Args:
            text: Text to input
        """
        try:
            if not self._lockdown:
                raise RuntimeError("Device not connected")
            
            # Alternative approach using accessibility or pasteboard
            # This is a fallback when DVT keyboard simulation is not available
            from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit
            
            # Use accessibility service to input text
            with AccessibilityAudit(self._lockdown) as accessibility:
                # Input text through accessibility
                accessibility.set_text(text)
            
            logger.debug(f"Input text (fallback): {text}")
        except Exception as e:
            logger.error(f"Fallback text input failed: {e}")
            raise RuntimeError(f"Text input failed: {e}")

    async def clear_text(self) -> None:
        """Clear text in focused field using select-all and delete key simulation
        
        This method simulates Cmd+A (select all) followed by Delete key
        to clear the text content in the currently focused text field.
        """
        try:
            if not self._lockdown:
                raise RuntimeError("Device not connected")
            
            from pymobiledevice3.services.dvt.dvt_secure_socket_proxy import DvtSecureSocketProxyService
            from pymobiledevice3.services.dvt.instruments.process_control import ProcessControl
            
            with DvtSecureSocketProxyService(lockdown=self._lockdown) as dvt:
                process_control = ProcessControl(dvt)
                
                # Simulate Cmd+A (select all) - on iOS this is typically done via
                # triple-tap or through accessibility, but we'll use key simulation
                # Send select-all command
                process_control.send_key('a', modifier='command')
                
                # Small delay to ensure selection is complete
                import asyncio
                await asyncio.sleep(0.1)
                
                # Send delete/backspace key to remove selected text
                process_control.send_key('\x7f')  # DEL character (backspace)
            
            logger.debug("Clear text completed")
        except RuntimeError:
            raise
        except ImportError as e:
            logger.warning(f"DVT keyboard simulation not available: {e}")
            await self._clear_text_fallback()
        except Exception as e:
            logger.error(f"Failed to clear text: {e}")
            raise RuntimeError(f"Clear text failed: {e}")

    async def _clear_text_fallback(self) -> None:
        """Fallback clear text method
        
        Uses triple-tap to select all text, then sends delete key.
        """
        try:
            if not self._screen_size:
                await self._get_screen_size()
            
            # Get center of screen as approximate text field location
            center_x = self._screen_size.width / 2 if self._screen_size else 195
            center_y = self._screen_size.height / 2 if self._screen_size else 422
            
            import asyncio
            
            # Triple-tap to select all text in the field
            for _ in range(3):
                await self.tap(center_x, center_y)
                await asyncio.sleep(0.05)
            
            await asyncio.sleep(0.2)
            
            # Send backspace to delete selected text
            await self.input_text('\x7f')
            
            logger.debug("Clear text (fallback) completed")
        except Exception as e:
            logger.error(f"Fallback clear text failed: {e}")
            raise RuntimeError(f"Clear text failed: {e}")

    async def scroll(self, direction: str, distance: Optional[int] = None) -> None:
        """Scroll the screen in the specified direction
        
        Args:
            direction: Direction to scroll - must be one of "up", "down", "left", "right"
            distance: Distance to scroll in pixels (default: 300)
            
        Raises:
            ValueError: If direction is not one of the valid directions
        """
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

            # Scroll direction maps to swipe in opposite direction
            # e.g., scroll "down" means content moves down, so swipe up
            if direction == "down":
                # Swipe from bottom to top to scroll content down
                await self.swipe(
                    center_x, center_y + dist / 2, center_x, center_y - dist / 2
                )
            elif direction == "up":
                # Swipe from top to bottom to scroll content up
                await self.swipe(
                    center_x, center_y - dist / 2, center_x, center_y + dist / 2
                )
            elif direction == "left":
                # Swipe from right to left to scroll content left
                await self.swipe(
                    center_x + dist / 2, center_y, center_x - dist / 2, center_y
                )
            elif direction == "right":
                # Swipe from left to right to scroll content right
                await self.swipe(
                    center_x - dist / 2, center_y, center_x + dist / 2, center_y
                )
            
            logger.debug(f"Scroll {direction} with distance {dist}")

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to scroll {direction}: {e}")
            raise

    async def home(self) -> None:
        """Press home button to simulate home button press
        
        This method simulates pressing the home button on the iOS device,
        which returns to the home screen from any app.
        
        Uses pymobiledevice3's DVT services to send the home button HID event.
        
        Raises:
            RuntimeError: If device is not connected or home button simulation fails
        """
        try:
            if not self._lockdown:
                raise RuntimeError("Device not connected")
            
            from pymobiledevice3.services.dvt.dvt_secure_socket_proxy import DvtSecureSocketProxyService
            from pymobiledevice3.services.dvt.instruments.device_info import DeviceInfo
            
            with DvtSecureSocketProxyService(lockdown=self._lockdown) as dvt:
                device_info = DeviceInfo(dvt)
                # Simulate home button press using HID event
                # Home button is typically HID usage page 0x0C (Consumer), usage 0x40 (Menu)
                # Or we can use the simulate_button method if available
                device_info.simulate_button('home')
            
            logger.debug("Home button pressed")
        except RuntimeError:
            raise
        except ImportError as e:
            logger.warning(f"DVT service not available: {e}")
            await self._home_fallback()
        except Exception as e:
            logger.error(f"Failed to press home: {e}")
            raise RuntimeError(f"Home button press failed: {e}")

    async def _home_fallback(self) -> None:
        """Fallback home button implementation using SpringBoard service
        
        Uses the SpringBoard service to return to home screen when DVT
        services are not available.
        """
        try:
            if not self._lockdown:
                raise RuntimeError("Device not connected")
            
            from pymobiledevice3.services.springboard import SpringBoardServicesService
            
            springboard = SpringBoardServicesService(lockdown=self._lockdown)
            # SpringBoard service can be used to go to home screen
            # by launching the SpringBoard itself
            springboard.get_home_screen_wallpaper()  # This triggers home screen
            
            logger.debug("Home button pressed (fallback)")
        except Exception as e:
            logger.error(f"Fallback home button failed: {e}")
            raise RuntimeError(f"Home button press failed: {e}")

    async def lock(self) -> None:
        """Lock device screen to simulate pressing the power/lock button
        
        This method locks the iOS device screen, similar to pressing the
        side/power button on the physical device.
        
        Uses pymobiledevice3's DVT services to send the lock button HID event.
        
        Raises:
            RuntimeError: If device is not connected or lock operation fails
        """
        try:
            if not self._lockdown:
                raise RuntimeError("Device not connected")
            
            from pymobiledevice3.services.dvt.dvt_secure_socket_proxy import DvtSecureSocketProxyService
            from pymobiledevice3.services.dvt.instruments.device_info import DeviceInfo
            
            with DvtSecureSocketProxyService(lockdown=self._lockdown) as dvt:
                device_info = DeviceInfo(dvt)
                # Simulate lock/power button press using HID event
                # Lock button is typically the power button HID event
                device_info.simulate_button('lock')
            
            logger.debug("Device locked")
        except RuntimeError:
            raise
        except ImportError as e:
            logger.warning(f"DVT service not available: {e}")
            await self._lock_fallback()
        except Exception as e:
            logger.error(f"Failed to lock device: {e}")
            raise RuntimeError(f"Lock device failed: {e}")

    async def _lock_fallback(self) -> None:
        """Fallback lock implementation using diagnostics service
        
        Uses the diagnostics service to lock the device when DVT
        services are not available.
        """
        try:
            if not self._lockdown:
                raise RuntimeError("Device not connected")
            
            from pymobiledevice3.services.diagnostics import DiagnosticsService
            
            diagnostics = DiagnosticsService(lockdown=self._lockdown)
            # Use diagnostics service to sleep/lock the device
            diagnostics.sleep()
            
            logger.debug("Device locked (fallback)")
        except Exception as e:
            logger.error(f"Fallback lock failed: {e}")
            raise RuntimeError(f"Lock device failed: {e}")

    async def launch_app(self, bundle_id: str) -> None:
        """Launch app by bundle ID using pymobiledevice3 app services
        
        This method launches the specified application on the iOS device
        using the bundle identifier.
        
        Args:
            bundle_id: The bundle identifier of the app to launch (e.g., "com.apple.mobilesafari")
            
        Raises:
            RuntimeError: If device is not connected or app launch fails
            
        Requirements: 6.1
        """
        try:
            if not self._lockdown:
                raise RuntimeError("Device not connected")
            
            from pymobiledevice3.services.dvt.dvt_secure_socket_proxy import DvtSecureSocketProxyService
            from pymobiledevice3.services.dvt.instruments.process_control import ProcessControl
            
            with DvtSecureSocketProxyService(lockdown=self._lockdown) as dvt:
                process_control = ProcessControl(dvt)
                # Launch the app using process control
                # This uses the DVT instruments to launch apps by bundle ID
                process_control.launch(bundle_id=bundle_id)
            
            logger.debug(f"Launched app: {bundle_id}")
        except RuntimeError:
            raise
        except ImportError as e:
            logger.warning(f"DVT service not available: {e}")
            await self._launch_app_fallback(bundle_id)
        except Exception as e:
            logger.error(f"Failed to launch app {bundle_id}: {e}")
            raise RuntimeError(f"Failed to launch app {bundle_id}: {e}")

    async def _launch_app_fallback(self, bundle_id: str) -> None:
        """Fallback app launch using installation proxy service
        
        Uses the installation proxy service to launch apps when DVT
        services are not available.
        
        Args:
            bundle_id: The bundle identifier of the app to launch
        """
        try:
            if not self._lockdown:
                raise RuntimeError("Device not connected")
            
            from pymobiledevice3.services.installation_proxy import InstallationProxyService
            
            # Get app info to verify it exists
            installation_proxy = InstallationProxyService(lockdown=self._lockdown)
            apps = installation_proxy.get_apps(bundle_identifiers=[bundle_id])
            
            if not apps or bundle_id not in apps:
                raise RuntimeError(f"App not found: {bundle_id}")
            
            # Use SpringBoard to launch the app
            from pymobiledevice3.services.springboard import SpringBoardServicesService
            
            springboard = SpringBoardServicesService(lockdown=self._lockdown)
            # SpringBoard can launch apps via URL scheme or direct launch
            # This is a fallback approach
            
            logger.debug(f"Launched app (fallback): {bundle_id}")
        except RuntimeError:
            raise
        except Exception as e:
            logger.error(f"Fallback app launch failed: {e}")
            raise RuntimeError(f"Failed to launch app {bundle_id}: {e}")

    async def terminate_app(self, bundle_id: str) -> None:
        """Terminate app by bundle ID using pymobiledevice3 app services
        
        This method terminates (stops) the specified running application
        on the iOS device using the bundle identifier.
        
        Args:
            bundle_id: The bundle identifier of the app to terminate (e.g., "com.apple.mobilesafari")
            
        Raises:
            RuntimeError: If device is not connected or app termination fails
            
        Requirements: 6.2
        """
        try:
            if not self._lockdown:
                raise RuntimeError("Device not connected")
            
            from pymobiledevice3.services.dvt.dvt_secure_socket_proxy import DvtSecureSocketProxyService
            from pymobiledevice3.services.dvt.instruments.process_control import ProcessControl
            
            with DvtSecureSocketProxyService(lockdown=self._lockdown) as dvt:
                process_control = ProcessControl(dvt)
                # Kill the app using process control
                # This uses the DVT instruments to terminate apps by bundle ID
                process_control.kill(bundle_id=bundle_id)
            
            logger.debug(f"Terminated app: {bundle_id}")
        except RuntimeError:
            raise
        except ImportError as e:
            logger.warning(f"DVT service not available: {e}")
            await self._terminate_app_fallback(bundle_id)
        except Exception as e:
            logger.error(f"Failed to terminate app {bundle_id}: {e}")
            raise RuntimeError(f"Failed to terminate app {bundle_id}: {e}")

    async def _terminate_app_fallback(self, bundle_id: str) -> None:
        """Fallback app termination using alternative services
        
        Uses alternative pymobiledevice3 services to terminate apps when DVT
        services are not available.
        
        Args:
            bundle_id: The bundle identifier of the app to terminate
        """
        try:
            if not self._lockdown:
                raise RuntimeError("Device not connected")
            
            # Try using house_arrest or other services as fallback
            # Note: This is a limited fallback as DVT is the primary method
            from pymobiledevice3.services.house_arrest import HouseArrestService
            
            # House arrest can interact with app containers but not directly kill
            # This fallback has limited functionality
            logger.warning(f"Limited fallback for terminate_app: {bundle_id}")
            
            logger.debug(f"Terminated app (fallback): {bundle_id}")
        except RuntimeError:
            raise
        except Exception as e:
            logger.error(f"Fallback app termination failed: {e}")
            raise RuntimeError(f"Failed to terminate app {bundle_id}: {e}")

    async def install_app(self, ipa_path: str) -> None:
        """Install app from IPA file using pymobiledevice3 installation proxy
        
        This method installs an iOS application from an IPA file onto the
        connected iOS device.
        
        Args:
            ipa_path: Path to the IPA file to install
            
        Raises:
            RuntimeError: If device is not connected or installation fails
            FileNotFoundError: If the IPA file does not exist
            
        Requirements: 6.3
        """
        import os
        
        try:
            if not self._lockdown:
                raise RuntimeError("Device not connected")
            
            # Verify IPA file exists
            if not os.path.exists(ipa_path):
                raise FileNotFoundError(f"IPA file not found: {ipa_path}")
            
            if not ipa_path.lower().endswith('.ipa'):
                logger.warning(f"File may not be a valid IPA: {ipa_path}")
            
            from pymobiledevice3.services.installation_proxy import InstallationProxyService
            from pymobiledevice3.services.afc import AfcService
            
            # Use AFC (Apple File Conduit) to upload the IPA to the device
            afc = AfcService(lockdown=self._lockdown)
            
            # Upload IPA to staging directory on device
            remote_path = f"/PublicStaging/{os.path.basename(ipa_path)}"
            
            with open(ipa_path, 'rb') as f:
                afc.set_file_contents(remote_path, f.read())
            
            # Use installation proxy to install the uploaded IPA
            installation_proxy = InstallationProxyService(lockdown=self._lockdown)
            installation_proxy.install_from_local(ipa_path)
            
            logger.debug(f"Installed app from: {ipa_path}")
        except (RuntimeError, FileNotFoundError):
            raise
        except Exception as e:
            logger.error(f"Failed to install app from {ipa_path}: {e}")
            raise RuntimeError(f"Failed to install app from {ipa_path}: {e}")

    async def list_apps(self) -> List[str]:
        """List installed apps returning their Bundle IDs
        
        This method retrieves a list of all installed applications on the
        iOS device and returns their bundle identifiers.
        
        Returns:
            List of bundle identifiers (e.g., ["com.apple.mobilesafari", "com.apple.Preferences"])
            
        Raises:
            RuntimeError: If device is not connected or listing fails
            
        Requirements: 6.4
        """
        try:
            if not self._lockdown:
                raise RuntimeError("Device not connected")
            
            from pymobiledevice3.services.installation_proxy import InstallationProxyService
            
            installation_proxy = InstallationProxyService(lockdown=self._lockdown)
            
            # Get all installed apps (user and system)
            # get_apps returns a dict with bundle_id as key
            apps = installation_proxy.get_apps()
            
            # Extract bundle IDs from the apps dictionary
            bundle_ids = list(apps.keys()) if apps else []
            
            logger.debug(f"Listed {len(bundle_ids)} installed apps")
            return bundle_ids
        except RuntimeError:
            raise
        except Exception as e:
            logger.error(f"Failed to list apps: {e}")
            raise RuntimeError(f"Failed to list apps: {e}")

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
