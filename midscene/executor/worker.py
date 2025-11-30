"""
Device Worker.

Encapsulates the execution environment for a single device, responsible for
executing test tasks on that device.
"""

import asyncio
import traceback
from datetime import datetime
from typing import Any, Optional, TYPE_CHECKING

from loguru import logger

from midscene.executor.errors import (
    TaskExecutionError,
    WorkerInitializationError,
)
from midscene.executor.types import (
    DeviceHandle,
    ExecutionResult,
    TestTask,
    WorkerConfig,
)

if TYPE_CHECKING:
    from midscene.core.agent import Agent


class ExecutionContext:
    """
    Execution context for a task.
    
    Contains all information needed for task execution including device,
    configuration, and state tracking.
    """
    
    def __init__(
        self,
        task: TestTask,
        device_handle: DeviceHandle,
        worker_config: WorkerConfig,
    ) -> None:
        """
        Initialize execution context.
        
        Args:
            task: The test task to execute.
            device_handle: Handle to the device for execution.
            worker_config: Worker configuration.
        """
        self.task = task
        self.device_handle = device_handle
        self.worker_config = worker_config
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.screenshots: list[str] = []
        self.logs: list[str] = []
        self.error: Optional[str] = None
        self.error_traceback: Optional[str] = None
    
    def start(self) -> None:
        """Mark the start of execution."""
        self.start_time = datetime.now()
    
    def finish(self, error: Optional[Exception] = None) -> None:
        """
        Mark the end of execution.
        
        Args:
            error: Optional exception if execution failed.
        """
        self.end_time = datetime.now()
        if error:
            self.error = str(error)
            self.error_traceback = traceback.format_exc()
    
    def add_screenshot(self, screenshot: str) -> None:
        """Add a screenshot to the context."""
        self.screenshots.append(screenshot)
    
    def add_log(self, log: str) -> None:
        """Add a log entry to the context."""
        self.logs.append(log)
    
    @property
    def duration_ms(self) -> int:
        """Get execution duration in milliseconds."""
        if self.start_time is None or self.end_time is None:
            return 0
        delta = self.end_time - self.start_time
        return int(delta.total_seconds() * 1000)
    
    @property
    def success(self) -> bool:
        """Check if execution was successful."""
        return self.error is None


class DeviceWorker:
    """
    Device worker for isolated task execution.
    
    Encapsulates the execution environment for a single device, responsible for
    executing test tasks on that device with proper isolation and error handling.
    
    Implements the async context manager protocol for convenient usage:
        async with DeviceWorker(handle, config) as worker:
            await worker.initialize()
            result = await worker.execute(task)
    
    Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
    """
    
    def __init__(
        self,
        device_handle: DeviceHandle,
        config: Optional[WorkerConfig] = None,
    ) -> None:
        """
        Initialize device worker.
        
        Args:
            device_handle: Handle to the device for this worker.
            config: Worker configuration. Uses defaults if not provided.
        
        Requirements: 4.1
        """
        self.device_handle = device_handle
        self.config = config or WorkerConfig()
        self.agent: Optional["Agent"] = None
        self._initialized = False
        self._current_context: Optional[ExecutionContext] = None
        
        logger.debug(
            f"DeviceWorker created for device {device_handle.device_id} "
            f"(platform: {device_handle.device_info.platform})"
        )
    
    async def initialize(self) -> None:
        """
        Initialize the worker by creating the platform-specific Agent.
        
        Creates the appropriate Agent (iOSAgent/AndroidAgent/WebAgent) based on
        the device platform type.
        
        Raises:
            WorkerInitializationError: If agent creation fails.
        
        Requirements: 4.1
        """
        if self._initialized:
            logger.warning(
                f"Worker for device {self.device_handle.device_id} already initialized"
            )
            return
        
        try:
            logger.info(
                f"Initializing worker for device {self.device_handle.device_id}"
            )
            
            # Create platform-specific agent with timeout
            self.agent = await asyncio.wait_for(
                self._create_agent(),
                timeout=self.config.setup_timeout_ms / 1000.0,
            )
            
            self._initialized = True
            logger.info(
                f"Worker initialized for device {self.device_handle.device_id}"
            )
            
        except asyncio.TimeoutError:
            raise WorkerInitializationError(
                self.device_handle.device_id,
                f"Initialization timed out after {self.config.setup_timeout_ms}ms",
            )
        except Exception as e:
            raise WorkerInitializationError(
                self.device_handle.device_id,
                str(e),
                cause=e,
            )
    
    async def _create_agent(self) -> "Agent":
        """
        Factory method to create platform-specific Agent.
        
        Creates the appropriate Agent based on the device platform:
        - android: AndroidAgent
        - ios: iOSAgent
        - web: WebAgent (via Playwright or Selenium)
        
        Returns:
            The created Agent instance.
        
        Raises:
            ValueError: If platform is not supported.
        
        Requirements: 4.1
        """
        platform = self.device_handle.device_info.platform.lower()
        device_id = self.device_handle.device_id
        
        if platform == "android":
            from midscene.android.agent import AndroidAgent
            return await AndroidAgent.create(device_id=device_id)
        
        elif platform == "ios":
            from midscene.ios.agent import iOSAgent
            return await iOSAgent.create(udid=device_id)
        
        elif platform == "web":
            # Web platform requires additional configuration
            # For now, raise an error indicating web needs special handling
            raise ValueError(
                f"Web platform requires explicit browser/page configuration. "
                f"Use WebAgent directly with Playwright or Selenium page."
            )
        
        else:
            raise ValueError(f"Unsupported platform: {platform}")
    
    async def execute(self, task: TestTask) -> ExecutionResult:
        """
        Execute a test task on this worker's device.
        
        Creates an isolated ExecutionContext for the task and runs it with
        proper timeout and error handling.
        
        Args:
            task: The test task to execute.
        
        Returns:
            ExecutionResult containing success status, timing, and any errors.
        
        Raises:
            RuntimeError: If worker is not initialized.
        
        Requirements: 4.2, 4.3
        """
        if not self._initialized or self.agent is None:
            raise RuntimeError(
                f"Worker for device {self.device_handle.device_id} not initialized. "
                f"Call initialize() first."
            )
        
        # Create execution context
        context = ExecutionContext(
            task=task,
            device_handle=self.device_handle,
            worker_config=self.config,
        )
        self._current_context = context
        
        logger.info(
            f"Executing task {task.task_id} on device {self.device_handle.device_id}"
        )
        
        try:
            # Run task with timeout
            await self._run_task(task, context)
            
        except Exception as e:
            logger.error(
                f"Task {task.task_id} failed on device {self.device_handle.device_id}: {e}"
            )
            context.finish(error=e)
            
            # Capture error state for debugging
            await self._capture_error_state(context)
        
        finally:
            self._current_context = None
        
        # Build execution result
        return ExecutionResult(
            task_id=task.task_id,
            device_id=self.device_handle.device_id,
            success=context.success,
            start_time=context.start_time or datetime.now(),
            end_time=context.end_time or datetime.now(),
            duration_ms=context.duration_ms,
            error=context.error,
            error_traceback=context.error_traceback,
            screenshots=context.screenshots,
            logs=context.logs,
        )
    
    async def _run_task(
        self,
        task: TestTask,
        context: ExecutionContext,
    ) -> None:
        """
        Run the task with timeout and error handling.
        
        Args:
            task: The test task to execute.
            context: The execution context.
        
        Raises:
            TaskExecutionError: If task execution fails.
            asyncio.TimeoutError: If task times out.
        
        Requirements: 4.2, 4.3
        """
        context.start()
        
        try:
            # Determine timeout (use task timeout or config default)
            timeout_ms = task.timeout_ms or self.config.setup_timeout_ms
            timeout_seconds = timeout_ms / 1000.0
            
            # Execute the test function
            test_func = task.test_func
            
            # Check if test function is async
            if asyncio.iscoroutinefunction(test_func):
                # Async function - pass agent and await with timeout
                await asyncio.wait_for(
                    test_func(self.agent),
                    timeout=timeout_seconds,
                )
            else:
                # Sync function - run in executor with timeout
                loop = asyncio.get_event_loop()
                await asyncio.wait_for(
                    loop.run_in_executor(None, test_func, self.agent),
                    timeout=timeout_seconds,
                )
            
            context.finish()
            logger.info(
                f"Task {task.task_id} completed successfully in {context.duration_ms}ms"
            )
            
        except asyncio.TimeoutError:
            error_msg = f"Task timed out after {task.timeout_ms}ms"
            context.finish(error=TimeoutError(error_msg))
            raise TaskExecutionError(task.task_id, error_msg)
        
        except Exception as e:
            context.finish(error=e)
            raise TaskExecutionError(task.task_id, str(e), cause=e)
    
    async def _capture_error_state(self, context: ExecutionContext) -> None:
        """
        Capture device state for debugging when an error occurs.
        
        Takes a screenshot and captures relevant logs to help diagnose
        the failure.
        
        Args:
            context: The execution context to store captured state.
        
        Requirements: 4.4
        """
        if not self.config.capture_screenshots and not self.config.capture_logs:
            return
        
        try:
            if self.agent is not None and self.config.capture_screenshots:
                # Try to capture screenshot
                try:
                    ui_context = await asyncio.wait_for(
                        self.agent.get_context(),
                        timeout=5.0,  # 5 second timeout for screenshot
                    )
                    if ui_context and ui_context.screenshot_base64:
                        context.add_screenshot(ui_context.screenshot_base64)
                        logger.debug(
                            f"Captured error screenshot for task {context.task.task_id}"
                        )
                except Exception as e:
                    logger.warning(f"Failed to capture error screenshot: {e}")
            
            if self.config.capture_logs:
                # Add error context to logs
                context.add_log(f"Error occurred at: {datetime.now().isoformat()}")
                context.add_log(f"Device: {self.device_handle.device_id}")
                context.add_log(f"Platform: {self.device_handle.device_info.platform}")
                if context.error:
                    context.add_log(f"Error: {context.error}")
                
        except Exception as e:
            logger.warning(f"Failed to capture error state: {e}")
    
    async def cleanup(self) -> None:
        """
        Cleanup worker resources.
        
        Destroys the Agent and releases any device resources.
        
        Requirements: 4.5
        """
        if not self._initialized:
            return
        
        logger.info(f"Cleaning up worker for device {self.device_handle.device_id}")
        
        try:
            if self.agent is not None:
                # Destroy agent with timeout
                await asyncio.wait_for(
                    self.agent.destroy(),
                    timeout=self.config.teardown_timeout_ms / 1000.0,
                )
                self.agent = None
            
            self._initialized = False
            logger.info(
                f"Worker cleanup completed for device {self.device_handle.device_id}"
            )
            
        except asyncio.TimeoutError:
            logger.warning(
                f"Worker cleanup timed out for device {self.device_handle.device_id}"
            )
            self.agent = None
            self._initialized = False
            
        except Exception as e:
            logger.error(
                f"Worker cleanup failed for device {self.device_handle.device_id}: {e}"
            )
            self.agent = None
            self._initialized = False
    
    async def __aenter__(self) -> "DeviceWorker":
        """
        Enter the async context manager.
        
        Returns:
            The DeviceWorker instance.
        
        Requirements: 4.5
        """
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Exit the async context manager, performing cleanup.
        
        Args:
            exc_type: Exception type if an exception was raised.
            exc_val: Exception value if an exception was raised.
            exc_tb: Exception traceback if an exception was raised.
        
        Requirements: 4.5
        """
        await self.cleanup()
    
    @property
    def is_initialized(self) -> bool:
        """Check if worker is initialized."""
        return self._initialized
    
    @property
    def device_id(self) -> str:
        """Get the device ID for this worker."""
        return self.device_handle.device_id
    
    @property
    def platform(self) -> str:
        """Get the platform type for this worker."""
        return self.device_handle.device_info.platform
