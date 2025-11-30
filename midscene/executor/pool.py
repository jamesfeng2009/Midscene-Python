"""
Device Pool Management.

Manages all available test devices (Android/iOS/Web), providing device registration,
allocation, recycling, and status monitoring.
"""

import asyncio
import threading
from datetime import datetime
from typing import Callable, Dict, List, Optional, TYPE_CHECKING

from loguru import logger

from midscene.executor.types import (
    DeviceCapability,
    DeviceEvent,
    DeviceEventType,
    DeviceHandle,
    DeviceInfo,
    DeviceState,
    PoolConfig,
    PoolStatus,
)
from midscene.executor.errors import (
    DeviceAcquisitionTimeoutError,
    DeviceNotFoundError,
    NoMatchingDeviceError,
)

if TYPE_CHECKING:
    from midscene.executor.discovery import DiscoverySummary


class ResourceLock:
    """
    Resource lock for ensuring exclusive device access.
    
    Provides thread-safe locking mechanism with timeout support to prevent
    concurrent access to the same device from multiple tasks.
    
    Implements the async context manager protocol for convenient usage:
        async with lock:
            # exclusive access to resource
    """
    
    def __init__(self) -> None:
        """Initialize the resource lock."""
        self._lock = asyncio.Lock()
        self._is_locked = False
    
    async def acquire(self, timeout_ms: int = 5000) -> bool:
        """
        Acquire the lock with timeout support.
        
        Args:
            timeout_ms: Maximum time to wait for lock acquisition in milliseconds.
                       Must be positive.
        
        Returns:
            True if lock was acquired successfully, False if timeout occurred.
        
        Raises:
            ValueError: If timeout_ms is not positive.
        """
        if timeout_ms <= 0:
            raise ValueError(f"timeout_ms must be positive, got {timeout_ms}")
        
        timeout_seconds = timeout_ms / 1000.0
        
        try:
            await asyncio.wait_for(self._lock.acquire(), timeout=timeout_seconds)
            self._is_locked = True
            return True
        except asyncio.TimeoutError:
            return False
    
    async def release(self) -> None:
        """
        Release the lock.
        
        Makes the resource available for other tasks to acquire.
        
        Raises:
            RuntimeError: If the lock is not currently held.
        """
        if not self._is_locked:
            raise RuntimeError("Cannot release a lock that is not held")
        
        self._is_locked = False
        self._lock.release()
    
    @property
    def is_locked(self) -> bool:
        """
        Check if the lock is currently held.
        
        Returns:
            True if the lock is currently acquired, False otherwise.
        """
        return self._is_locked
    
    async def __aenter__(self) -> "ResourceLock":
        """
        Enter the async context manager, acquiring the lock.
        
        Returns:
            The ResourceLock instance.
        
        Raises:
            asyncio.TimeoutError: If lock acquisition times out (default 5 seconds).
        """
        acquired = await self.acquire()
        if not acquired:
            raise asyncio.TimeoutError("Failed to acquire lock within timeout")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Exit the async context manager, releasing the lock.
        
        Args:
            exc_type: Exception type if an exception was raised.
            exc_val: Exception value if an exception was raised.
            exc_tb: Exception traceback if an exception was raised.
        """
        await self.release()


class DevicePool:
    """
    Device pool manager.
    
    Manages all available test devices (Android/iOS/Web), providing device
    registration, allocation, recycling, and status monitoring.
    
    Thread-safe implementation using threading.Lock for synchronization.
    """
    
    def __init__(self, config: Optional[PoolConfig] = None) -> None:
        """
        Initialize the device pool.
        
        Args:
            config: Pool configuration. Uses defaults if not provided.
        """
        self._config = config or PoolConfig()
        self._devices: Dict[str, DeviceInfo] = {}
        self._device_locks: Dict[str, ResourceLock] = {}
        self._lock = threading.Lock()
        self._event_subscribers: List[Callable[[DeviceEvent], None]] = []
        self._async_lock = asyncio.Lock()
    
    def _emit_event(self, event: DeviceEvent) -> None:
        """
        Emit a device event to all subscribers.
        
        Args:
            event: The device event to emit.
        """
        for subscriber in self._event_subscribers:
            try:
                subscriber(event)
            except Exception:
                # Don't let subscriber errors affect pool operations
                pass
    
    def subscribe(self, callback: Callable[[DeviceEvent], None]) -> None:
        """
        Subscribe to device events.
        
        Args:
            callback: Function to call when device events occur.
        """
        with self._lock:
            self._event_subscribers.append(callback)
    
    def unsubscribe(self, callback: Callable[[DeviceEvent], None]) -> None:
        """
        Unsubscribe from device events.
        
        Args:
            callback: The callback function to remove.
        """
        with self._lock:
            if callback in self._event_subscribers:
                self._event_subscribers.remove(callback)
    
    async def register(self, device_info: DeviceInfo) -> str:
        """
        Register a device to the pool.
        
        Args:
            device_info: Information about the device to register.
        
        Returns:
            The device ID of the registered device.
        
        Raises:
            ValueError: If a device with the same ID is already registered.
        """
        async with self._async_lock:
            with self._lock:
                if device_info.device_id in self._devices:
                    raise ValueError(
                        f"Device already registered: {device_info.device_id}"
                    )
                
                # Set initial state to IDLE
                device_info.state = DeviceState.IDLE
                device_info.last_used = None
                device_info.current_task = None
                
                self._devices[device_info.device_id] = device_info
                self._device_locks[device_info.device_id] = ResourceLock()
        
        # Emit registration event
        event = DeviceEvent(
            event_type=DeviceEventType.REGISTERED,
            device_id=device_info.device_id,
            timestamp=datetime.now(),
            new_state=DeviceState.IDLE,
        )
        self._emit_event(event)
        
        return device_info.device_id
    
    async def unregister(self, device_id: str) -> None:
        """
        Unregister a device from the pool.
        
        Args:
            device_id: The ID of the device to unregister.
        
        Raises:
            DeviceNotFoundError: If the device is not found in the pool.
        """
        async with self._async_lock:
            with self._lock:
                if device_id not in self._devices:
                    raise DeviceNotFoundError(device_id)
                
                old_state = self._devices[device_id].state
                del self._devices[device_id]
                
                if device_id in self._device_locks:
                    del self._device_locks[device_id]
        
        # Emit unregistration event
        event = DeviceEvent(
            event_type=DeviceEventType.UNREGISTERED,
            device_id=device_id,
            timestamp=datetime.now(),
            old_state=old_state,
        )
        self._emit_event(event)
    
    def _matches_capability(
        self, device: DeviceInfo, required: DeviceCapability
    ) -> bool:
        """
        Check if a device matches the required capability.
        
        Args:
            device: The device to check.
            required: The required capability.
        
        Returns:
            True if the device matches, False otherwise.
        """
        # Platform must match
        if device.capability.platform != required.platform:
            return False
        
        # OS version check (if specified)
        if required.os_version is not None:
            if device.capability.os_version is None:
                return False
            # Simple version comparison - device version should be >= required
            if device.capability.os_version < required.os_version:
                return False
        
        # Device model check (if specified)
        if required.device_model is not None:
            if device.capability.device_model is None:
                return False
            if device.capability.device_model != required.device_model:
                return False
        
        # Screen size check (if specified)
        if required.screen_size is not None:
            if device.capability.screen_size is None:
                return False
            # Device screen should be at least as large as required
            if (device.capability.screen_size[0] < required.screen_size[0] or
                device.capability.screen_size[1] < required.screen_size[1]):
                return False
        
        # Tags check - device must have all required tags
        if required.tags:
            device_tags = set(device.capability.tags)
            required_tags = set(required.tags)
            if not required_tags.issubset(device_tags):
                return False
        
        return True
    
    def _find_matching_device(
        self, capability: DeviceCapability
    ) -> Optional[DeviceInfo]:
        """
        Find a matching device using longest-idle selection.
        
        Args:
            capability: The required device capability.
        
        Returns:
            The matching device info, or None if no match found.
        """
        matching_devices = []
        
        for device in self._devices.values():
            if device.state != DeviceState.IDLE:
                continue
            if not self._matches_capability(device, capability):
                continue
            matching_devices.append(device)
        
        if not matching_devices:
            return None
        
        # Select the device with the longest idle time (earliest last_used)
        # Devices that have never been used (last_used=None) are prioritized
        def sort_key(d: DeviceInfo):
            if d.last_used is None:
                return datetime.min
            return d.last_used
        
        matching_devices.sort(key=sort_key)
        return matching_devices[0]
    
    async def acquire(
        self,
        capability: DeviceCapability,
        timeout_ms: Optional[int] = None,
    ) -> DeviceHandle:
        """
        Acquire a device matching the specified capability.
        
        Args:
            capability: The required device capability.
            timeout_ms: Maximum time to wait for a device. Uses config default if not specified.
        
        Returns:
            A DeviceHandle for the acquired device.
        
        Raises:
            DeviceAcquisitionTimeoutError: If no matching device becomes available within timeout.
            NoMatchingDeviceError: If no devices match the capability requirements.
        """
        if timeout_ms is None:
            timeout_ms = self._config.acquisition_timeout_ms
        
        start_time = datetime.now()
        timeout_seconds = timeout_ms / 1000.0
        poll_interval = 0.1  # 100ms polling interval
        
        while True:
            async with self._async_lock:
                with self._lock:
                    device = self._find_matching_device(capability)
                    
                    if device is not None:
                        # Found a matching device, acquire it
                        old_state = device.state
                        device.state = DeviceState.BUSY
                        device.last_used = datetime.now()
                        
                        lock = self._device_locks[device.device_id]
                        
                        # Create device handle
                        handle = DeviceHandle(
                            device_id=device.device_id,
                            device_info=device,
                            lock=lock,
                            acquired_at=datetime.now(),
                            timeout_at=None,
                        )
                        
                        # Emit state change event
                        event = DeviceEvent(
                            event_type=DeviceEventType.ACQUIRED,
                            device_id=device.device_id,
                            timestamp=datetime.now(),
                            old_state=old_state,
                            new_state=DeviceState.BUSY,
                        )
                        self._emit_event(event)
                        
                        return handle
            
            # Check timeout
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed >= timeout_seconds:
                # Check if any devices could potentially match
                with self._lock:
                    any_matching = any(
                        self._matches_capability(d, capability)
                        for d in self._devices.values()
                    )
                
                if not any_matching:
                    raise NoMatchingDeviceError(str(capability))
                else:
                    raise DeviceAcquisitionTimeoutError(
                        timeout_ms, str(capability)
                    )
            
            # Wait before polling again
            await asyncio.sleep(poll_interval)
    
    async def release(self, handle: DeviceHandle) -> None:
        """
        Release a device back to the pool.
        
        Args:
            handle: The device handle to release.
        
        Raises:
            DeviceNotFoundError: If the device is not found in the pool.
        """
        async with self._async_lock:
            with self._lock:
                if handle.device_id not in self._devices:
                    raise DeviceNotFoundError(handle.device_id)
                
                device = self._devices[handle.device_id]
                old_state = device.state
                device.state = DeviceState.IDLE
                device.current_task = None
                device.last_used = datetime.now()
        
        # Emit release event
        event = DeviceEvent(
            event_type=DeviceEventType.RELEASED,
            device_id=handle.device_id,
            timestamp=datetime.now(),
            old_state=old_state,
            new_state=DeviceState.IDLE,
        )
        self._emit_event(event)
    
    async def get_available_devices(self) -> List[DeviceInfo]:
        """
        Get all available (IDLE) devices.
        
        Returns:
            List of device info for all IDLE devices.
        """
        with self._lock:
            return [
                device for device in self._devices.values()
                if device.state == DeviceState.IDLE
            ]
    
    async def get_status(self) -> PoolStatus:
        """
        Get the current pool status.
        
        Returns:
            PoolStatus containing all device states and counts.
        """
        with self._lock:
            devices = list(self._devices.values())
            
            idle_count = sum(1 for d in devices if d.state == DeviceState.IDLE)
            busy_count = sum(1 for d in devices if d.state == DeviceState.BUSY)
            offline_count = sum(1 for d in devices if d.state == DeviceState.OFFLINE)
            error_count = sum(1 for d in devices if d.state == DeviceState.ERROR)
            
            return PoolStatus(
                total_devices=len(devices),
                idle_devices=idle_count,
                busy_devices=busy_count,
                offline_devices=offline_count,
                error_devices=error_count,
                devices=devices,
            )
    
    async def get_device(self, device_id: str) -> DeviceInfo:
        """
        Get a specific device by ID.
        
        Args:
            device_id: The ID of the device to get.
        
        Returns:
            The device info.
        
        Raises:
            DeviceNotFoundError: If the device is not found.
        """
        with self._lock:
            if device_id not in self._devices:
                raise DeviceNotFoundError(device_id)
            return self._devices[device_id]

    async def auto_discover(self) -> "DiscoverySummary":
        """
        Automatically discover and register connected devices.
        
        Scans for all connected Android and iOS devices, extracts their
        capabilities, and registers them to the pool.
        
        Returns:
            DiscoverySummary containing all discovered devices grouped by platform.
        """
        from midscene.executor.discovery import DeviceDiscovery

        discovery = DeviceDiscovery()
        summary = await discovery.discover_all()

        # Register discovered devices
        registered_count = 0
        for device_info in summary.android_devices + summary.ios_devices:
            try:
                # Skip if device already registered
                if device_info.device_id in self._devices:
                    logger.debug(f"Device already registered: {device_info.device_id}")
                    continue

                await self.register(device_info)
                registered_count += 1
            except Exception as e:
                logger.warning(
                    f"Failed to register discovered device {device_info.device_id}: {e}"
                )
                summary.errors.append(
                    f"Failed to register {device_info.device_id}: {e}"
                )

        logger.info(f"Auto-discovery registered {registered_count} new devices")
        return summary

    async def health_check(self) -> Dict[str, DeviceState]:
        """
        Perform health check on all registered devices.
        
        Checks connectivity for each device and updates state to OFFLINE
        if the device is no longer connected.
        
        Returns:
            Dict mapping device_id to current DeviceState after health check.
        """
        from midscene.executor.discovery import DeviceDiscovery

        discovery = DeviceDiscovery()
        results: Dict[str, DeviceState] = {}

        # Get currently connected device IDs
        try:
            android_ids = await discovery._get_android_device_ids()
        except Exception:
            android_ids = []

        try:
            ios_ids = await discovery._get_ios_device_ids()
        except Exception:
            ios_ids = []

        connected_ids = set(android_ids + ios_ids)

        # Check each registered device
        with self._lock:
            device_ids = list(self._devices.keys())

        for device_id in device_ids:
            async with self._async_lock:
                with self._lock:
                    if device_id not in self._devices:
                        continue

                    device = self._devices[device_id]
                    old_state = device.state

                    if device_id not in connected_ids:
                        # Device disconnected
                        if device.state != DeviceState.OFFLINE:
                            device.state = DeviceState.OFFLINE
                            logger.warning(f"Device went offline: {device_id}")

                            # Emit state change event
                            event = DeviceEvent(
                                event_type=DeviceEventType.STATE_CHANGED,
                                device_id=device_id,
                                timestamp=datetime.now(),
                                old_state=old_state,
                                new_state=DeviceState.OFFLINE,
                            )
                            self._emit_event(event)
                    else:
                        # Device is connected
                        if device.state == DeviceState.OFFLINE:
                            # Device came back online
                            device.state = DeviceState.IDLE
                            logger.info(f"Device came back online: {device_id}")

                            event = DeviceEvent(
                                event_type=DeviceEventType.STATE_CHANGED,
                                device_id=device_id,
                                timestamp=datetime.now(),
                                old_state=old_state,
                                new_state=DeviceState.IDLE,
                            )
                            self._emit_event(event)

                    results[device_id] = device.state

        return results

    async def start_health_check_loop(self) -> asyncio.Task:
        """
        Start periodic health check loop.
        
        Runs health checks at the interval specified in pool config.
        
        Returns:
            The asyncio Task running the health check loop.
        """
        async def _health_check_loop():
            interval_seconds = self._config.health_check_interval_ms / 1000.0
            while True:
                try:
                    await asyncio.sleep(interval_seconds)
                    await self.health_check()
                except asyncio.CancelledError:
                    logger.debug("Health check loop cancelled")
                    break
                except Exception as e:
                    logger.error(f"Health check failed: {e}")

        task = asyncio.create_task(_health_check_loop())
        logger.info(
            f"Started health check loop with interval "
            f"{self._config.health_check_interval_ms}ms"
        )
        return task

    async def update_device_state(
        self, device_id: str, new_state: DeviceState
    ) -> None:
        """
        Update the state of a device.
        
        Args:
            device_id: The ID of the device to update.
            new_state: The new state to set.
        
        Raises:
            DeviceNotFoundError: If the device is not found.
        """
        async with self._async_lock:
            with self._lock:
                if device_id not in self._devices:
                    raise DeviceNotFoundError(device_id)

                device = self._devices[device_id]
                old_state = device.state
                device.state = new_state

        # Emit state change event
        event = DeviceEvent(
            event_type=DeviceEventType.STATE_CHANGED,
            device_id=device_id,
            timestamp=datetime.now(),
            old_state=old_state,
            new_state=new_state,
        )
        self._emit_event(event)