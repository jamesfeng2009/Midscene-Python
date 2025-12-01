"""
Task Executor.

Responsible for distributing and scheduling test tasks to available device workers.
Integrates with the isolation module to ensure test data isolation across concurrent executions.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional, Any

from loguru import logger

from midscene.executor.errors import (
    DeviceAcquisitionTimeoutError,
    NoMatchingDeviceError,
    TaskExecutionError,
)
from midscene.executor.isolation import (
    ExecutionScope,
    IsolatedTestRunner,
    IsolatedTestConfig,
    ParallelTestDataManager,
    TestDataFactory,
    isolated_scope,
    get_current_scope,
)
from midscene.executor.pool import DevicePool
from midscene.executor.types import (
    ConsolidatedReport,
    DeviceCapability,
    DeviceStatistics,
    ExecutionResult,
    PoolConfig,
    TestTask,
)
from midscene.executor.worker import DeviceWorker, ExecutionContext


@dataclass
class ExecutorConfig:
    """Configuration for the task executor."""
    max_concurrent_tasks: int = 10
    task_timeout_ms: int = 60000
    retry_failed_tasks: bool = False
    max_retries: int = 2
    stop_on_first_failure: bool = False
    enable_isolation: bool = True  # Enable test data isolation
    isolation_config: Optional[IsolatedTestConfig] = None
    
    def __post_init__(self) -> None:
        if self.max_concurrent_tasks <= 0:
            raise ValueError(
                f"max_concurrent_tasks must be positive, got {self.max_concurrent_tasks}"
            )
        if self.task_timeout_ms <= 0:
            raise ValueError(
                f"task_timeout_ms must be positive, got {self.task_timeout_ms}"
            )


@dataclass
class TaskQueueItem:
    """Item in the task queue with priority support."""
    task: TestTask
    priority: int = 0
    retry_count: int = 0
    queued_at: datetime = field(default_factory=datetime.now)
    
    def __lt__(self, other: "TaskQueueItem") -> bool:
        """Higher priority tasks come first."""
        return self.priority > other.priority


class TaskExecutor:
    """
    Distributes and schedules test tasks to available device workers.
    
    Features:
    - Priority-based task scheduling
    - Automatic device allocation from pool
    - Test data isolation via ExecutionScope
    - Retry support for failed tasks
    - Consolidated reporting
    
    Example:
        pool = DevicePool()
        await pool.auto_discover()
        
        executor = TaskExecutor(pool)
        
        tasks = [
            TestTask(
                task_id="test_1",
                name="Login Test",
                test_func=test_login,
                capability_requirements=DeviceCapability(platform="ios"),
            ),
            TestTask(
                task_id="test_2", 
                name="Checkout Test",
                test_func=test_checkout,
                capability_requirements=DeviceCapability(platform="android"),
            ),
        ]
        
        report = await executor.execute_all(tasks)
        print(f"Passed: {report.successful_tasks}/{report.total_tasks}")
    """
    
    def __init__(
        self,
        pool: DevicePool,
        config: Optional[ExecutorConfig] = None,
    ) -> None:
        """
        Initialize the task executor.
        
        Args:
            pool: Device pool for device allocation.
            config: Executor configuration.
        """
        self.pool = pool
        self.config = config or ExecutorConfig()
        self._data_manager = ParallelTestDataManager()
        self._task_queue: asyncio.PriorityQueue[TaskQueueItem] = asyncio.PriorityQueue()
        self._results: List[ExecutionResult] = []
        self._active_workers: Dict[str, DeviceWorker] = {}
        self._stop_flag = False
        self._lock = asyncio.Lock()
    
    async def execute_all(
        self,
        tasks: List[TestTask],
        on_task_complete: Optional[Callable[[ExecutionResult], None]] = None,
    ) -> ConsolidatedReport:
        """
        Execute all tasks with automatic device allocation and isolation.
        
        Args:
            tasks: List of test tasks to execute.
            on_task_complete: Optional callback for each completed task.
        
        Returns:
            ConsolidatedReport with all results and statistics.
        """
        if not tasks:
            return self._create_empty_report()
        
        start_time = datetime.now()
        self._results = []
        self._stop_flag = False
        
        # Queue all tasks
        for task in tasks:
            item = TaskQueueItem(task=task, priority=task.priority)
            await self._task_queue.put(item)
        
        logger.info(f"Starting execution of {len(tasks)} tasks")
        
        # Create worker tasks up to max concurrency
        worker_tasks = []
        for _ in range(min(self.config.max_concurrent_tasks, len(tasks))):
            worker_task = asyncio.create_task(
                self._worker_loop(on_task_complete)
            )
            worker_tasks.append(worker_task)
        
        # Wait for all workers to complete
        await asyncio.gather(*worker_tasks, return_exceptions=True)
        
        end_time = datetime.now()
        
        # Build consolidated report
        return self._build_report(tasks, start_time, end_time)
    
    async def _worker_loop(
        self,
        on_task_complete: Optional[Callable[[ExecutionResult], None]] = None,
    ) -> None:
        """
        Worker loop that processes tasks from the queue.
        
        Each iteration:
        1. Gets a task from the queue
        2. Acquires a matching device
        3. Executes the task with isolation
        4. Releases the device
        """
        while not self._stop_flag:
            try:
                # Get next task (with timeout to check stop flag)
                try:
                    item = await asyncio.wait_for(
                        self._task_queue.get(),
                        timeout=1.0,
                    )
                except asyncio.TimeoutError:
                    # Check if queue is empty and no more tasks
                    if self._task_queue.empty():
                        break
                    continue
                
                task = item.task
                
                # Execute task with isolation
                result = await self._execute_task_isolated(task, item.retry_count)
                
                # Handle result
                async with self._lock:
                    self._results.append(result)
                
                if on_task_complete:
                    on_task_complete(result)
                
                # Handle failure
                if not result.success:
                    if self.config.stop_on_first_failure:
                        self._stop_flag = True
                        break
                    
                    # Retry if configured
                    if (self.config.retry_failed_tasks and 
                        item.retry_count < self.config.max_retries):
                        retry_item = TaskQueueItem(
                            task=task,
                            priority=item.priority,
                            retry_count=item.retry_count + 1,
                        )
                        await self._task_queue.put(retry_item)
                        logger.info(
                            f"Retrying task {task.task_id} "
                            f"(attempt {item.retry_count + 2})"
                        )
                
                self._task_queue.task_done()
                
            except Exception as e:
                logger.error(f"Worker loop error: {e}")
    
    async def _execute_task_isolated(
        self,
        task: TestTask,
        retry_count: int = 0,
    ) -> ExecutionResult:
        """
        Execute a single task with test data isolation.
        
        Args:
            task: The task to execute.
            retry_count: Current retry attempt number.
        
        Returns:
            ExecutionResult for the task.
        """
        device_handle = None
        worker = None
        
        try:
            # Acquire device
            device_handle = await self.pool.acquire(
                task.capability_requirements,
                timeout_ms=self.config.task_timeout_ms,
            )
            
            logger.info(
                f"Acquired device {device_handle.device_id} for task {task.task_id}"
            )
            
            # Create worker
            worker = DeviceWorker(device_handle)
            await worker.initialize()
            
            # Execute with isolation
            if self.config.enable_isolation:
                result = await self._execute_with_isolation(
                    worker, task, device_handle.device_id
                )
            else:
                result = await worker.execute(task)
            
            return result
            
        except DeviceAcquisitionTimeoutError as e:
            logger.error(f"Device acquisition timeout for task {task.task_id}: {e}")
            return ExecutionResult(
                task_id=task.task_id,
                device_id="",
                success=False,
                start_time=datetime.now(),
                end_time=datetime.now(),
                duration_ms=0,
                error=f"Device acquisition timeout: {e}",
            )
            
        except NoMatchingDeviceError as e:
            logger.error(f"No matching device for task {task.task_id}: {e}")
            return ExecutionResult(
                task_id=task.task_id,
                device_id="",
                success=False,
                start_time=datetime.now(),
                end_time=datetime.now(),
                duration_ms=0,
                error=f"No matching device: {e}",
            )
            
        except Exception as e:
            logger.error(f"Task {task.task_id} failed: {e}")
            return ExecutionResult(
                task_id=task.task_id,
                device_id=device_handle.device_id if device_handle else "",
                success=False,
                start_time=datetime.now(),
                end_time=datetime.now(),
                duration_ms=0,
                error=str(e),
            )
            
        finally:
            # Cleanup
            if worker:
                await worker.cleanup()
            if device_handle:
                await self.pool.release(device_handle)
    
    async def _execute_with_isolation(
        self,
        worker: DeviceWorker,
        task: TestTask,
        device_id: str,
    ) -> ExecutionResult:
        """
        Execute task within an isolated scope.
        
        Creates an ExecutionScope for the task, providing:
        - Isolated test data that won't conflict with other tasks
        - Unique ID generation scoped to this execution
        - Test data factory for creating test fixtures
        
        Args:
            worker: The device worker to use.
            task: The task to execute.
            device_id: The device ID.
        
        Returns:
            ExecutionResult for the task.
        """
        async with self._data_manager.acquire_scope(
            test_name=task.name,
            device_id=device_id,
            initial_data=task.metadata,
        ) as scope:
            # Create test data factory
            factory = TestDataFactory(scope)
            
            # Inject scope and factory into task metadata
            task.metadata["_scope"] = scope
            task.metadata["_factory"] = factory
            
            # Execute the task
            result = await worker.execute(task)
            
            # Log isolation info
            logger.debug(
                f"Task {task.task_id} executed in scope {scope.scope_id} "
                f"on device {device_id}"
            )
            
            return result
    
    def _build_report(
        self,
        tasks: List[TestTask],
        start_time: datetime,
        end_time: datetime,
    ) -> ConsolidatedReport:
        """Build consolidated report from results."""
        total_duration_ms = int((end_time - start_time).total_seconds() * 1000)
        
        successful = sum(1 for r in self._results if r.success)
        failed = len(self._results) - successful
        
        # Calculate device statistics
        device_stats: Dict[str, DeviceStatistics] = {}
        for result in self._results:
            if result.device_id not in device_stats:
                device_stats[result.device_id] = DeviceStatistics(
                    device_id=result.device_id
                )
            
            stats = device_stats[result.device_id]
            stats.tasks_executed += 1
            stats.total_execution_time_ms += result.duration_ms
            if result.success:
                stats.tasks_succeeded += 1
            else:
                stats.tasks_failed += 1
        
        # Calculate parallel efficiency
        serial_time = sum(r.duration_ms for r in self._results)
        parallel_efficiency = serial_time / total_duration_ms if total_duration_ms > 0 else 1.0
        
        return ConsolidatedReport(
            total_tasks=len(tasks),
            successful_tasks=successful,
            failed_tasks=failed,
            total_duration_ms=total_duration_ms,
            parallel_efficiency=parallel_efficiency,
            device_statistics=device_stats,
            results=self._results,
            start_time=start_time,
            end_time=end_time,
        )
    
    def _create_empty_report(self) -> ConsolidatedReport:
        """Create an empty report for when no tasks are provided."""
        now = datetime.now()
        return ConsolidatedReport(
            total_tasks=0,
            successful_tasks=0,
            failed_tasks=0,
            total_duration_ms=0,
            parallel_efficiency=1.0,
            device_statistics={},
            results=[],
            start_time=now,
            end_time=now,
        )
    
    async def stop(self) -> None:
        """Stop the executor gracefully."""
        logger.info("Stopping task executor")
        self._stop_flag = True


# Convenience function for simple usage
async def execute_tests(
    tasks: List[TestTask],
    pool: Optional[DevicePool] = None,
    config: Optional[ExecutorConfig] = None,
) -> ConsolidatedReport:
    """
    Convenience function to execute tests with automatic pool management.
    
    Args:
        tasks: List of test tasks to execute.
        pool: Optional device pool. If not provided, creates one with auto-discovery.
        config: Optional executor configuration.
    
    Returns:
        ConsolidatedReport with all results.
    
    Example:
        tasks = [
            TestTask(
                task_id="test_1",
                name="Login Test",
                test_func=test_login,
                capability_requirements=DeviceCapability(platform="ios"),
            ),
        ]
        
        report = await execute_tests(tasks)
        print(f"Passed: {report.successful_tasks}/{report.total_tasks}")
    """
    if pool is None:
        pool = DevicePool()
        await pool.auto_discover()
    
    executor = TaskExecutor(pool, config)
    return await executor.execute_all(tasks)
