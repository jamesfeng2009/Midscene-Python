"""
iOS Agent implementation
"""

from typing import Optional

from ..core.agent import Agent
from ..core.types import AgentOptions
from .device import iOSDevice


class iOSAgent(Agent):
    """iOS-specific agent implementation"""

    def __init__(self, device: iOSDevice, options: Optional[AgentOptions] = None):
        """Initialize iOS agent

        Args:
            device: iOSDevice instance
            options: Agent options
        """
        super().__init__(device, options)

    @classmethod
    async def create(
        cls,
        udid: Optional[str] = None,
        options: Optional[AgentOptions] = None,
    ) -> "iOSAgent":
        """Create iOS agent with device

        Args:
            udid: iOS device UDID, if None uses first available
            options: Agent options

        Returns:
            iOSAgent instance
        """
        device = await iOSDevice.create(udid)
        return cls(device, options)

    async def launch_app(self, bundle_id: str) -> None:
        """Launch iOS app

        Args:
            bundle_id: App bundle ID
        """
        await self.interface.launch_app(bundle_id)

    async def terminate_app(self, bundle_id: str) -> None:
        """Terminate iOS app

        Args:
            bundle_id: App bundle ID
        """
        await self.interface.terminate_app(bundle_id)

    async def home(self) -> None:
        """Press home button"""
        await self.interface.home()

    async def swipe(
        self,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        duration: int = 300,
    ) -> None:
        """Swipe gesture

        Args:
            start_x: Start X coordinate
            start_y: Start Y coordinate
            end_x: End X coordinate
            end_y: End Y coordinate
            duration: Swipe duration in milliseconds
        """
        await self.interface.swipe(start_x, start_y, end_x, end_y, duration)

    async def long_press(self, x: float, y: float, duration: int = 1000) -> None:
        """Long press gesture

        Args:
            x: X coordinate
            y: Y coordinate
            duration: Press duration in milliseconds
        """
        await self.interface.long_press(x, y, duration)
