"""
Concurrent Execution Engine for Midscene.

This module provides device pool management and concurrent test execution capabilities.
"""

from midscene.executor.discovery import DeviceDiscovery, DiscoverySummary
from midscene.executor.errors import (
    DeviceAcquisitionTimeoutError,
    DeviceAlreadyAcquiredError,
    DeviceNotFoundError,
    DevicePoolError,
    NoMatchingDeviceError,
    TaskExecutionError,
    WorkerInitializationError,
)
from midscene.executor.pool import DevicePool, ResourceLock
from midscene.executor.types import (
    ConsolidatedReport,
    DeviceCapability,
    DeviceEvent,
    DeviceEventType,
    DeviceHandle,
    DeviceInfo,
    DeviceState,
    DeviceStatistics,
    ExecutionResult,
    PoolConfig,
    PoolStatus,
    RunnerConfig,
    TestTask,
    WorkerConfig,
)
from midscene.executor.worker import DeviceWorker, ExecutionContext

__all__ = [
    # Discovery
    "DeviceDiscovery",
    "DiscoverySummary",
    # Pool
    "DevicePool",
    "ResourceLock",
    # Worker
    "DeviceWorker",
    "ExecutionContext",
    # Types
    "DeviceCapability",
    "DeviceEvent",
    "DeviceEventType",
    "DeviceHandle",
    "DeviceInfo",
    "DeviceState",
    "DeviceStatistics",
    "ConsolidatedReport",
    "ExecutionResult",
    "PoolConfig",
    "PoolStatus",
    "RunnerConfig",
    "TestTask",
    "WorkerConfig",
    # Errors
    "DevicePoolError",
    "DeviceNotFoundError",
    "DeviceAcquisitionTimeoutError",
    "DeviceAlreadyAcquiredError",
    "NoMatchingDeviceError",
    "TaskExecutionError",
    "WorkerInitializationError",
]
