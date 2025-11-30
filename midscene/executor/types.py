"""
Type definitions for the Concurrent Execution Engine.

Contains enums, dataclasses, and type definitions used throughout the executor module.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from midscene.executor.pool import ResourceLock


class DeviceState(str, Enum):
    """Device state enumeration."""
    IDLE = "idle"                   # Available for assignment
    BUSY = "busy"                   # Currently executing a task
    OFFLINE = "offline"             # Cannot connect
    ERROR = "error"                 # Requires manual intervention
    INITIALIZING = "initializing"  # Being initialized


@dataclass
class DeviceCapability:
    """Device capability description."""
    platform: str                                    # "android" | "ios" | "web"
    os_version: Optional[str] = None
    device_model: Optional[str] = None
    screen_size: Optional[Tuple[int, int]] = None
    tags: List[str] = field(default_factory=list)


@dataclass
class DeviceInfo:
    """Device information."""
    device_id: str                                   # UDID or device_id
    platform: str                                    # Platform type
    capability: DeviceCapability
    state: DeviceState = DeviceState.IDLE
    last_used: Optional[datetime] = None
    current_task: Optional[str] = None
    error_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DeviceHandle:
    """Device handle for acquired devices."""
    device_id: str
    device_info: DeviceInfo
    lock: "ResourceLock"
    acquired_at: datetime
    timeout_at: Optional[datetime] = None


@dataclass
class TestTask:
    """Test task definition."""
    task_id: str
    name: str
    test_func: Callable
    capability_requirements: DeviceCapability
    timeout_ms: int = 60000
    priority: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate task configuration."""
        if self.timeout_ms <= 0:
            raise ValueError(f"timeout_ms must be positive, got {self.timeout_ms}")


@dataclass
class ExecutionResult:
    """Execution result for a single task."""
    task_id: str
    device_id: str
    success: bool
    start_time: datetime
    end_time: datetime
    duration_ms: int
    error: Optional[str] = None
    error_traceback: Optional[str] = None
    screenshots: List[str] = field(default_factory=list)
    logs: List[str] = field(default_factory=list)


@dataclass
class DeviceStatistics:
    """Statistics for a single device."""
    device_id: str
    tasks_executed: int = 0
    tasks_succeeded: int = 0
    tasks_failed: int = 0
    total_execution_time_ms: int = 0
    utilization_percentage: float = 0.0


@dataclass
class ConsolidatedReport:
    """Consolidated report for all tasks."""
    total_tasks: int
    successful_tasks: int
    failed_tasks: int
    total_duration_ms: int
    parallel_efficiency: float  # Serial time / actual time
    device_statistics: Dict[str, DeviceStatistics]
    results: List[ExecutionResult]
    start_time: datetime
    end_time: datetime


@dataclass
class PoolConfig:
    """Device pool configuration."""
    auto_discovery: bool = True
    acquisition_timeout_ms: int = 30000
    auto_release_timeout_ms: int = 300000  # 5 minutes
    health_check_interval_ms: int = 10000
    max_error_count: int = 3  # Error count threshold

    def __post_init__(self) -> None:
        """Validate pool configuration."""
        if self.acquisition_timeout_ms <= 0:
            raise ValueError(
                f"acquisition_timeout_ms must be positive, got {self.acquisition_timeout_ms}"
            )
        if self.auto_release_timeout_ms <= 0:
            raise ValueError(
                f"auto_release_timeout_ms must be positive, got {self.auto_release_timeout_ms}"
            )
        if self.health_check_interval_ms <= 0:
            raise ValueError(
                f"health_check_interval_ms must be positive, got {self.health_check_interval_ms}"
            )
        if self.max_error_count <= 0:
            raise ValueError(
                f"max_error_count must be positive, got {self.max_error_count}"
            )


@dataclass
class RunnerConfig:
    """Concurrent runner configuration."""
    max_concurrency: int = 10
    task_timeout_ms: int = 60000
    retry_failed_tasks: bool = False
    stop_on_failure: bool = False

    def __post_init__(self) -> None:
        """Validate runner configuration."""
        if self.max_concurrency <= 0:
            raise ValueError(
                f"max_concurrency must be positive, got {self.max_concurrency}"
            )
        if self.task_timeout_ms <= 0:
            raise ValueError(
                f"task_timeout_ms must be positive, got {self.task_timeout_ms}"
            )


@dataclass
class WorkerConfig:
    """Device worker configuration."""
    setup_timeout_ms: int = 30000
    teardown_timeout_ms: int = 10000
    capture_screenshots: bool = True
    capture_logs: bool = True

    def __post_init__(self) -> None:
        """Validate worker configuration."""
        if self.setup_timeout_ms <= 0:
            raise ValueError(
                f"setup_timeout_ms must be positive, got {self.setup_timeout_ms}"
            )
        if self.teardown_timeout_ms <= 0:
            raise ValueError(
                f"teardown_timeout_ms must be positive, got {self.teardown_timeout_ms}"
            )


class DeviceEventType(str, Enum):
    """Device event type enumeration."""
    REGISTERED = "registered"
    UNREGISTERED = "unregistered"
    STATE_CHANGED = "state_changed"
    ACQUIRED = "acquired"
    RELEASED = "released"


@dataclass
class DeviceEvent:
    """Device event for notifications."""
    event_type: DeviceEventType
    device_id: str
    timestamp: datetime
    old_state: Optional[DeviceState] = None
    new_state: Optional[DeviceState] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PoolStatus:
    """Device pool status."""
    total_devices: int
    idle_devices: int
    busy_devices: int
    offline_devices: int
    error_devices: int
    devices: List[DeviceInfo]
