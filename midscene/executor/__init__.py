"""
Concurrent Execution Engine for Midscene.

This module provides device pool management and concurrent test execution capabilities
with built-in test data isolation for parallel test execution.
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
from midscene.executor.executor import (
    TaskExecutor,
    ExecutorConfig,
    execute_tests,
)
from midscene.executor.isolation import (
    ExecutionScope,
    IsolatedTestConfig,
    IsolatedTestContext,
    IsolatedTestRunner,
    ParallelTestDataManager,
    TestDataFactory,
    ThreadLocalData,
    get_current_scope,
    isolated_scope,
    set_current_scope,
)
from midscene.executor.pool import DevicePool, ResourceLock
from midscene.executor.runner import (
    ConcurrentRunner,
    RunnerResult,
    TestSuite,
    get_registered_tests,
    get_test_factory,
    get_test_scope,
    run_registered_tests,
    test,
)
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
    # Executor
    "TaskExecutor",
    "ExecutorConfig",
    "execute_tests",
    # Runner
    "ConcurrentRunner",
    "RunnerResult",
    "TestSuite",
    "test",
    "get_registered_tests",
    "run_registered_tests",
    "get_test_scope",
    "get_test_factory",
    # Isolation
    "ExecutionScope",
    "IsolatedTestConfig",
    "IsolatedTestContext",
    "IsolatedTestRunner",
    "ParallelTestDataManager",
    "TestDataFactory",
    "ThreadLocalData",
    "get_current_scope",
    "set_current_scope",
    "isolated_scope",
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
