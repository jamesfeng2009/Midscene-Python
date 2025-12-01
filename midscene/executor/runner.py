"""
Concurrent Runner.

Coordinates multiple device workers to execute test cases in parallel.
Provides high-level API for running test suites with automatic device management.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from loguru import logger

from midscene.executor.errors import DevicePoolError
from midscene.executor.executor import TaskExecutor, ExecutorConfig
from midscene.executor.isolation import (
    ExecutionScope,
    IsolatedTestConfig,
    IsolatedTestRunner,
    ParallelTestDataManager,
    TestDataFactory,
    get_current_scope,
    isolated_scope,
)
from midscene.executor.pool import DevicePool
from midscene.executor.types import (
    ConsolidatedReport,
    DeviceCapability,
    DeviceInfo,
    ExecutionResult,
    PoolConfig,
    RunnerConfig,
    TestTask,
)


@dataclass
class TestSuite:
    """
    Collection of test cases to run together.
    
    Attributes:
        name: Suite name for reporting.
        tests: List of test tasks in this suite.
        setup: Optional async setup function called before suite.
        teardown: Optional async teardown function called after suite.
        capability: Default capability requirements for tests in this suite.
    """
    name: str
    tests: List[TestTask] = field(default_factory=list)
    setup: Optional[Callable[[], Any]] = None
    teardown: Optional[Callable[[], Any]] = None
    capability: Optional[DeviceCapability] = None
    
    def add_test(
        self,
        name: str,
        test_func: Callable,
        capability: Optional[DeviceCapability] = None,
        timeout_ms: int = 60000,
        priority: int = 0,
        **metadata,
    ) -> "TestSuite":
        """
        Add a test to the suite.
        
        Args:
            name: Test name.
            test_func: Async test function that takes an Agent.
            capability: Device capability requirements (uses suite default if not specified).
            timeout_ms: Test timeout in milliseconds.
            priority: Test priority (higher = runs first).
            **metadata: Additional metadata for the test.
        
        Returns:
            Self for chaining.
        """
        task = TestTask(
            task_id=f"{self.name}:{name}",
            name=name,
            test_func=test_func,
            capability_requirements=capability or self.capability or DeviceCapability(platform="android"),
            timeout_ms=timeout_ms,
            priority=priority,
            metadata=metadata,
        )
        self.tests.append(task)
        return self


@dataclass
class RunnerResult:
    """
    Result of a test runner execution.
    
    Attributes:
        suites: Dict mapping suite name to its report.
        total_passed: Total passed tests across all suites.
        total_failed: Total failed tests across all suites.
        total_duration_ms: Total execution time.
        start_time: When execution started.
        end_time: When execution ended.
    """
    suites: Dict[str, ConsolidatedReport] = field(default_factory=dict)
    total_passed: int = 0
    total_failed: int = 0
    total_duration_ms: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    @property
    def success(self) -> bool:
        """Check if all tests passed."""
        return self.total_failed == 0
    
    def summary(self) -> str:
        """Get a summary string of the results."""
        total = self.total_passed + self.total_failed
        return (
            f"Tests: {self.total_passed}/{total} passed, "
            f"{self.total_failed} failed, "
            f"Duration: {self.total_duration_ms}ms"
        )


class ConcurrentRunner:
    """
    High-level runner for executing test suites concurrently.
    
    Features:
    - Automatic device pool management
    - Test suite organization
    - Parallel execution across multiple devices
    - Test data isolation
    - Consolidated reporting
    
    Example:
        runner = ConcurrentRunner()
        
        # Create test suite
        suite = TestSuite(
            name="Login Tests",
            capability=DeviceCapability(platform="ios"),
        )
        suite.add_test("test_valid_login", test_valid_login)
        suite.add_test("test_invalid_password", test_invalid_password)
        
        # Run tests
        result = await runner.run(suite)
        print(result.summary())
    """
    
    def __init__(
        self,
        config: Optional[RunnerConfig] = None,
        pool_config: Optional[PoolConfig] = None,
    ) -> None:
        """
        Initialize the concurrent runner.
        
        Args:
            config: Runner configuration.
            pool_config: Device pool configuration.
        """
        self.config = config or RunnerConfig()
        self.pool_config = pool_config or PoolConfig()
        self._pool: Optional[DevicePool] = None
        self._executor: Optional[TaskExecutor] = None
        self._data_manager = ParallelTestDataManager()
    
    async def initialize(self) -> None:
        """
        Initialize the runner by setting up the device pool.
        
        Discovers connected devices and prepares for test execution.
        """
        logger.info("Initializing concurrent runner")
        
        self._pool = DevicePool(self.pool_config)
        
        if self.pool_config.auto_discovery:
            summary = await self._pool.auto_discover()
            logger.info(
                f"Discovered {len(summary.android_devices)} Android devices, "
                f"{len(summary.ios_devices)} iOS devices"
            )
        
        # Create executor
        executor_config = ExecutorConfig(
            max_concurrent_tasks=self.config.max_concurrency,
            task_timeout_ms=self.config.task_timeout_ms,
            retry_failed_tasks=self.config.retry_failed_tasks,
            stop_on_first_failure=self.config.stop_on_failure,
            enable_isolation=True,
        )
        self._executor = TaskExecutor(self._pool, executor_config)
        
        logger.info("Concurrent runner initialized")
    
    async def run(
        self,
        *suites: TestSuite,
        on_test_complete: Optional[Callable[[ExecutionResult], None]] = None,
    ) -> RunnerResult:
        """
        Run one or more test suites.
        
        Args:
            *suites: Test suites to run.
            on_test_complete: Optional callback for each completed test.
        
        Returns:
            RunnerResult with all suite results.
        """
        if not self._pool or not self._executor:
            await self.initialize()
        
        result = RunnerResult(start_time=datetime.now())
        
        for suite in suites:
            logger.info(f"Running suite: {suite.name}")
            
            # Run suite setup
            if suite.setup:
                try:
                    if asyncio.iscoroutinefunction(suite.setup):
                        await suite.setup()
                    else:
                        suite.setup()
                except Exception as e:
                    logger.error(f"Suite setup failed: {e}")
                    continue
            
            # Execute tests
            report = await self._executor.execute_all(
                suite.tests,
                on_task_complete=on_test_complete,
            )
            
            result.suites[suite.name] = report
            result.total_passed += report.successful_tasks
            result.total_failed += report.failed_tasks
            result.total_duration_ms += report.total_duration_ms
            
            # Run suite teardown
            if suite.teardown:
                try:
                    if asyncio.iscoroutinefunction(suite.teardown):
                        await suite.teardown()
                    else:
                        suite.teardown()
                except Exception as e:
                    logger.error(f"Suite teardown failed: {e}")
        
        result.end_time = datetime.now()
        
        logger.info(f"All suites completed: {result.summary()}")
        return result
    
    async def run_tests(
        self,
        tests: List[Callable],
        capability: DeviceCapability,
        suite_name: str = "Default Suite",
    ) -> RunnerResult:
        """
        Convenience method to run a list of test functions.
        
        Args:
            tests: List of async test functions.
            capability: Device capability requirements.
            suite_name: Name for the test suite.
        
        Returns:
            RunnerResult with test results.
        """
        suite = TestSuite(name=suite_name, capability=capability)
        
        for i, test_func in enumerate(tests):
            name = getattr(test_func, "__name__", f"test_{i}")
            suite.add_test(name, test_func)
        
        return await self.run(suite)
    
    async def cleanup(self) -> None:
        """Cleanup runner resources."""
        logger.info("Cleaning up concurrent runner")
        
        if self._executor:
            await self._executor.stop()
        
        self._pool = None
        self._executor = None
    
    async def __aenter__(self) -> "ConcurrentRunner":
        """Enter async context manager."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context manager."""
        await self.cleanup()
    
    @property
    def pool(self) -> Optional[DevicePool]:
        """Get the device pool."""
        return self._pool


# =============================================================================
# Decorator-based test definition
# =============================================================================

_registered_tests: Dict[str, List[TestTask]] = {}


def test(
    name: Optional[str] = None,
    suite: str = "default",
    capability: Optional[DeviceCapability] = None,
    timeout_ms: int = 60000,
    priority: int = 0,
):
    """
    Decorator to register a test function.
    
    Args:
        name: Test name (uses function name if not specified).
        suite: Suite name to add the test to.
        capability: Device capability requirements.
        timeout_ms: Test timeout.
        priority: Test priority.
    
    Example:
        @test(suite="login", capability=DeviceCapability(platform="ios"))
        async def test_valid_login(agent):
            await agent.ai_action("Enter username 'testuser'")
            await agent.ai_action("Enter password 'password123'")
            await agent.ai_action("Tap login button")
            await agent.ai_assert("Login successful message is displayed")
    """
    def decorator(func: Callable) -> Callable:
        test_name = name or func.__name__
        task = TestTask(
            task_id=f"{suite}:{test_name}",
            name=test_name,
            test_func=func,
            capability_requirements=capability or DeviceCapability(platform="android"),
            timeout_ms=timeout_ms,
            priority=priority,
        )
        
        if suite not in _registered_tests:
            _registered_tests[suite] = []
        _registered_tests[suite].append(task)
        
        return func
    
    return decorator


def get_registered_tests(suite: Optional[str] = None) -> Dict[str, List[TestTask]]:
    """
    Get registered tests.
    
    Args:
        suite: Optional suite name to filter by.
    
    Returns:
        Dict mapping suite names to test tasks.
    """
    if suite:
        return {suite: _registered_tests.get(suite, [])}
    return dict(_registered_tests)


async def run_registered_tests(
    suite: Optional[str] = None,
    config: Optional[RunnerConfig] = None,
) -> RunnerResult:
    """
    Run all registered tests.
    
    Args:
        suite: Optional suite name to run (runs all if not specified).
        config: Optional runner configuration.
    
    Returns:
        RunnerResult with test results.
    """
    async with ConcurrentRunner(config) as runner:
        suites = []
        
        tests_to_run = get_registered_tests(suite)
        for suite_name, tasks in tests_to_run.items():
            if tasks:
                test_suite = TestSuite(name=suite_name)
                test_suite.tests = tasks
                suites.append(test_suite)
        
        return await runner.run(*suites)


# =============================================================================
# Helper functions for test isolation
# =============================================================================

def get_test_scope() -> Optional[ExecutionScope]:
    """
    Get the current test's execution scope.
    
    Use this within a test function to access isolated test data.
    
    Returns:
        The current ExecutionScope, or None if not in a test context.
    
    Example:
        async def test_create_user(agent):
            scope = get_test_scope()
            if scope:
                user_id = scope.generate_unique_id("user")
                await agent.ai_action(f"Create user with ID {user_id}")
    """
    return get_current_scope()


def get_test_factory() -> Optional[TestDataFactory]:
    """
    Get the test data factory for the current test.
    
    Returns:
        TestDataFactory for generating isolated test data, or None if not in test context.
    
    Example:
        async def test_register_user(agent):
            factory = get_test_factory()
            if factory:
                user = factory.create_user()
                await agent.ai_action(f"Register with email {user['email']}")
    """
    scope = get_current_scope()
    if scope:
        return TestDataFactory(scope)
    return None
