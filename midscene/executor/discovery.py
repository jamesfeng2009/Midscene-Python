"""
Device Discovery Module.

Provides automatic detection of connected Android and iOS devices,
capability extraction, and integration with DevicePool.
"""

import asyncio
import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from loguru import logger

from midscene.executor.types import (
    DeviceCapability,
    DeviceInfo,
    DeviceState,
)


@dataclass
class DiscoverySummary:
    """Summary of device discovery results."""
    android_devices: List[DeviceInfo]
    ios_devices: List[DeviceInfo]
    total_discovered: int
    discovery_time_ms: int
    errors: List[str]

    @property
    def by_platform(self) -> Dict[str, List[DeviceInfo]]:
        """Get devices grouped by platform."""
        return {
            "android": self.android_devices,
            "ios": self.ios_devices,
        }


class DeviceDiscovery:
    """
    Device discovery service for auto-detecting connected devices.
    
    Supports:
    - Android devices via ADB
    - iOS devices via pymobiledevice3
    
    Extracts device capabilities including OS version, model, and screen size.
    """

    def __init__(self, adb_path: str = "adb") -> None:
        """
        Initialize the device discovery service.
        
        Args:
            adb_path: Path to ADB executable (default: "adb").
        """
        self._adb_path = adb_path

    async def discover_all(self) -> DiscoverySummary:
        """
        Discover all connected devices across all platforms.
        
        Scans for both Android and iOS devices concurrently.
        
        Returns:
            DiscoverySummary containing all discovered devices grouped by platform.
        """
        start_time = datetime.now()
        errors: List[str] = []

        # Discover Android and iOS devices concurrently
        android_task = self.discover_android_devices()
        ios_task = self.discover_ios_devices()

        android_results, ios_results = await asyncio.gather(
            android_task, ios_task, return_exceptions=True
        )

        # Handle Android results
        android_devices: List[DeviceInfo] = []
        if isinstance(android_results, Exception):
            errors.append(f"Android discovery failed: {android_results}")
            logger.error(f"Android discovery failed: {android_results}")
        else:
            android_devices = android_results

        # Handle iOS results
        ios_devices: List[DeviceInfo] = []
        if isinstance(ios_results, Exception):
            errors.append(f"iOS discovery failed: {ios_results}")
            logger.error(f"iOS discovery failed: {ios_results}")
        else:
            ios_devices = ios_results

        end_time = datetime.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        total = len(android_devices) + len(ios_devices)
        logger.info(
            f"Discovery completed: {len(android_devices)} Android, "
            f"{len(ios_devices)} iOS devices in {duration_ms}ms"
        )

        return DiscoverySummary(
            android_devices=android_devices,
            ios_devices=ios_devices,
            total_discovered=total,
            discovery_time_ms=duration_ms,
            errors=errors,
        )

    async def discover_android_devices(self) -> List[DeviceInfo]:
        """
        Discover connected Android devices using ADB.
        
        Returns:
            List of DeviceInfo for all connected Android devices.
        """
        devices: List[DeviceInfo] = []

        try:
            # Get list of connected devices
            device_ids = await self._get_android_device_ids()

            # Get capability for each device concurrently
            tasks = [
                self._get_android_capability(device_id)
                for device_id in device_ids
            ]
            capabilities = await asyncio.gather(*tasks, return_exceptions=True)

            for device_id, cap_result in zip(device_ids, capabilities):
                if isinstance(cap_result, Exception):
                    logger.warning(
                        f"Failed to get capability for Android device {device_id}: {cap_result}"
                    )
                    # Create device with minimal capability
                    capability = DeviceCapability(platform="android")
                else:
                    capability = cap_result

                device_info = DeviceInfo(
                    device_id=device_id,
                    platform="android",
                    capability=capability,
                    state=DeviceState.IDLE,
                    metadata={"discovered_at": datetime.now().isoformat()},
                )
                devices.append(device_info)

            logger.debug(f"Discovered {len(devices)} Android devices")

        except Exception as e:
            logger.error(f"Android device discovery failed: {e}")
            raise

        return devices

    async def discover_ios_devices(self) -> List[DeviceInfo]:
        """
        Discover connected iOS devices using pymobiledevice3.
        
        Returns:
            List of DeviceInfo for all connected iOS devices.
        """
        devices: List[DeviceInfo] = []

        try:
            # Get list of connected devices
            device_ids = await self._get_ios_device_ids()

            # Get capability for each device concurrently
            tasks = [
                self._get_ios_capability(udid)
                for udid in device_ids
            ]
            capabilities = await asyncio.gather(*tasks, return_exceptions=True)

            for udid, cap_result in zip(device_ids, capabilities):
                if isinstance(cap_result, Exception):
                    logger.warning(
                        f"Failed to get capability for iOS device {udid}: {cap_result}"
                    )
                    # Create device with minimal capability
                    capability = DeviceCapability(platform="ios")
                else:
                    capability = cap_result

                device_info = DeviceInfo(
                    device_id=udid,
                    platform="ios",
                    capability=capability,
                    state=DeviceState.IDLE,
                    metadata={"discovered_at": datetime.now().isoformat()},
                )
                devices.append(device_info)

            logger.debug(f"Discovered {len(devices)} iOS devices")

        except Exception as e:
            logger.error(f"iOS device discovery failed: {e}")
            raise

        return devices

    async def _get_android_device_ids(self) -> List[str]:
        """Get list of connected Android device IDs via ADB."""
        try:
            result = await asyncio.create_subprocess_exec(
                self._adb_path, "devices",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                result.communicate(), timeout=10
            )

            if result.returncode != 0:
                raise RuntimeError(f"ADB devices failed: {stderr.decode()}")

            lines = stdout.decode().strip().split('\n')[1:]  # Skip header
            device_ids = []

            for line in lines:
                if '\t' in line:
                    parts = line.split('\t')
                    device_id = parts[0].strip()
                    status = parts[1].strip() if len(parts) > 1 else ""
                    # Only include devices that are online
                    if device_id and status == "device":
                        device_ids.append(device_id)

            return device_ids

        except asyncio.TimeoutError:
            logger.error("ADB devices command timed out")
            return []
        except FileNotFoundError:
            logger.error(f"ADB not found at: {self._adb_path}")
            return []

    async def _get_ios_device_ids(self) -> List[str]:
        """Get list of connected iOS device UDIDs via pymobiledevice3."""
        try:
            from pymobiledevice3.usbmux import list_devices

            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            devices = await loop.run_in_executor(None, list_devices)
            return [d.serial for d in devices]

        except ImportError:
            logger.warning("pymobiledevice3 not installed, skipping iOS discovery")
            return []
        except Exception as e:
            logger.error(f"Failed to list iOS devices: {e}")
            return []

    async def _get_android_capability(self, device_id: str) -> DeviceCapability:
        """
        Extract capability information for an Android device.
        
        Args:
            device_id: The Android device ID.
            
        Returns:
            DeviceCapability with OS version, model, and screen size.
        """
        os_version = await self._get_android_property(device_id, "ro.build.version.release")
        model = await self._get_android_property(device_id, "ro.product.model")
        screen_size = await self._get_android_screen_size(device_id)

        return DeviceCapability(
            platform="android",
            os_version=os_version,
            device_model=model,
            screen_size=screen_size,
        )

    async def _get_ios_capability(self, udid: str) -> DeviceCapability:
        """
        Extract capability information for an iOS device.
        
        Args:
            udid: The iOS device UDID.
            
        Returns:
            DeviceCapability with OS version, model, and screen size.
        """
        try:
            from pymobiledevice3.lockdown import create_using_usbmux

            loop = asyncio.get_event_loop()

            def get_device_info():
                lockdown = create_using_usbmux(serial=udid)
                return {
                    "os_version": lockdown.product_version,
                    "model": lockdown.product_type,
                    "display_info": lockdown.display_info if hasattr(lockdown, 'display_info') else None,
                }

            info = await loop.run_in_executor(None, get_device_info)

            # Extract screen size from display info if available
            screen_size: Optional[Tuple[int, int]] = None
            if info.get("display_info"):
                display = info["display_info"]
                if "Width" in display and "Height" in display:
                    screen_size = (display["Width"], display["Height"])

            # If screen size not available, use known device dimensions
            if screen_size is None:
                screen_size = self._get_ios_screen_size_by_model(info.get("model"))

            return DeviceCapability(
                platform="ios",
                os_version=info.get("os_version"),
                device_model=info.get("model"),
                screen_size=screen_size,
            )

        except ImportError:
            logger.warning("pymobiledevice3 not installed")
            return DeviceCapability(platform="ios")
        except Exception as e:
            logger.warning(f"Failed to get iOS capability for {udid}: {e}")
            return DeviceCapability(platform="ios")

    async def _get_android_property(self, device_id: str, prop: str) -> Optional[str]:
        """Get a system property from an Android device."""
        try:
            result = await asyncio.create_subprocess_exec(
                self._adb_path, "-s", device_id, "shell", "getprop", prop,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(result.communicate(), timeout=5)
            value = stdout.decode().strip()
            return value if value else None
        except Exception as e:
            logger.debug(f"Failed to get property {prop} for {device_id}: {e}")
            return None

    async def _get_android_screen_size(self, device_id: str) -> Optional[Tuple[int, int]]:
        """Get screen size from an Android device."""
        try:
            result = await asyncio.create_subprocess_exec(
                self._adb_path, "-s", device_id, "shell", "wm", "size",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(result.communicate(), timeout=5)
            output = stdout.decode().strip()

            # Parse "Physical size: 1080x1920"
            if ":" in output:
                size_str = output.split(":")[-1].strip()
                if "x" in size_str:
                    width, height = map(int, size_str.split("x"))
                    return (width, height)

            return None
        except Exception as e:
            logger.debug(f"Failed to get screen size for {device_id}: {e}")
            return None

    def _get_ios_screen_size_by_model(self, model: Optional[str]) -> Optional[Tuple[int, int]]:
        """Get iOS screen size based on device model identifier."""
        if not model:
            return None

        # Common iOS device screen sizes (logical points)
        screen_sizes = {
            # iPhone 15 series
            "iPhone16,1": (393, 852),  # iPhone 15 Pro
            "iPhone16,2": (430, 932),  # iPhone 15 Pro Max
            "iPhone15,4": (393, 852),  # iPhone 15
            "iPhone15,5": (430, 932),  # iPhone 15 Plus
            # iPhone 14 series
            "iPhone15,2": (393, 852),  # iPhone 14 Pro
            "iPhone15,3": (430, 932),  # iPhone 14 Pro Max
            "iPhone14,7": (390, 844),  # iPhone 14
            "iPhone14,8": (428, 926),  # iPhone 14 Plus
            # iPhone 13 series
            "iPhone14,2": (390, 844),  # iPhone 13 Pro
            "iPhone14,3": (428, 926),  # iPhone 13 Pro Max
            "iPhone14,4": (375, 812),  # iPhone 13 mini
            "iPhone14,5": (390, 844),  # iPhone 13
            # iPhone 12 series
            "iPhone13,1": (375, 812),  # iPhone 12 mini
            "iPhone13,2": (390, 844),  # iPhone 12
            "iPhone13,3": (390, 844),  # iPhone 12 Pro
            "iPhone13,4": (428, 926),  # iPhone 12 Pro Max
            # iPhone SE
            "iPhone14,6": (375, 667),  # iPhone SE 3rd gen
            "iPhone12,8": (375, 667),  # iPhone SE 2nd gen
            # iPad models (common ones)
            "iPad13,18": (1024, 1366),  # iPad Pro 12.9"
            "iPad13,16": (834, 1194),   # iPad Pro 11"
        }

        return screen_sizes.get(model)
