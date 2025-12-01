"""
Test Data Isolation Module.

Provides mechanisms for isolating test data across concurrent test executions,
ensuring that tests running on different devices/threads do not interfere
with each other.
"""

import asyncio
import copy
import threading
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, Generic, Optional, TypeVar

from loguru import logger

T = TypeVar("T")


# =============================================================================
# 1. Thread-Local Storage - 线程本地存储
# =============================================================================

class ThreadLocalData:
    """
    Thread-local storage for test data.
    
    Each thread/coroutine gets its own isolated copy of data.
    This prevents data pollution between concurrent tests.
    
    Example:
        local_data = ThreadLocalData()
        local_data.user_id = "user_001"  # Only visible in current thread
    """
    
    def __init__(self):
        self._local = threading.local()
    
    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            return super().__getattribute__(name)
        return getattr(self._local, name, None)
    
    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            setattr(self._local, name, value)
    
    def clear(self) -> None:
        """Clear all thread-local data."""
        self._local.__dict__.clear()
    
    def get_all(self) -> Dict[str, Any]:
        """Get all thread-local data as dict."""
        return dict(self._local.__dict__)


# =============================================================================
# 2. Execution Scope - 执行作用域
# =============================================================================

@dataclass
class ExecutionScope:
    """
    Isolated execution scope for a single test.
    
    Contains all test-specific data that should not be shared
    between concurrent tests.
    
    Attributes:
        scope_id: Unique identifier for this scope
        device_id: Device this scope is bound to
        test_name: Name of the test being executed
        data: Isolated test data dictionary
        created_at: When this scope was created
    """
    scope_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    device_id: Optional[str] = None
    test_name: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get data from scope."""
        return self.data.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Set data in scope."""
        self.data[key] = value
    
    def update(self, data: Dict[str, Any]) -> None:
        """Update scope with multiple values."""
        self.data.update(data)
    
    def clear(self) -> None:
        """Clear all scope data."""
        self.data.clear()
    
    def generate_unique_id(self, prefix: str = "") -> str:
        """
        Generate a unique ID scoped to this execution.
        
        Useful for creating unique test data that won't conflict
        with other concurrent tests.
        
        Args:
            prefix: Optional prefix for the ID
            
        Returns:
            Unique ID like "prefix_abc123_1"
        """
        counter = self.data.get("_id_counter", 0) + 1
        self.data["_id_counter"] = counter
        
        if prefix:
            return f"{prefix}_{self.scope_id}_{counter}"
        return f"{self.scope_id}_{counter}"


# =============================================================================
# 3. Context Variable based isolation (for asyncio)
# =============================================================================

import contextvars

# Context variable for current execution scope
_current_scope: contextvars.ContextVar[Optional[ExecutionScope]] = \
    contextvars.ContextVar("current_scope", default=None)


def get_current_scope() -> Optional[ExecutionScope]:
    """Get the current execution scope."""
    return _current_scope.get()


def set_current_scope(scope: ExecutionScope) -> contextvars.Token:
    """Set the current execution scope."""
    return _current_scope.set(scope)


@asynccontextmanager
async def isolated_scope(
    device_id: Optional[str] = None,
    test_name: Optional[str] = None,
    initial_data: Optional[Dict[str, Any]] = None,
):
    """
    Context manager for creating an isolated execution scope.
    
    All code within this context has access to an isolated data scope
    that won't interfere with other concurrent executions.
    
    Example:
        async with isolated_scope(device_id="device1", test_name="test_login") as scope:
            # Generate unique test data
            user_id = scope.generate_unique_id("user")  # "user_abc123_1"
            scope.set("user_id", user_id)
            
            # Run test with isolated data
            await agent.ai_action(f"Login as {user_id}")
    
    Args:
        device_id: Device ID for this scope
        test_name: Test name for this scope
        initial_data: Initial data to populate the scope
        
    Yields:
        ExecutionScope instance
    """
    scope = ExecutionScope(
        device_id=device_id,
        test_name=test_name,
        data=initial_data.copy() if initial_data else {},
    )
    
    token = set_current_scope(scope)
    
    try:
        logger.debug(f"Created isolated scope {scope.scope_id} for {test_name}")
        yield scope
    finally:
        _current_scope.reset(token)
        logger.debug(f"Closed isolated scope {scope.scope_id}")


# =============================================================================
# 4. Test Data Factory - 测试数据工厂
# =============================================================================

class TestDataFactory:
    """
    Factory for generating isolated test data.
    
    Ensures that each test execution gets unique test data
    that won't conflict with other concurrent tests.
    
    Example:
        factory = TestDataFactory(scope)
        
        # Generate unique user
        user = factory.create_user()  # {"id": "user_abc123_1", "name": "Test User 1"}
        
        # Generate unique email
        email = factory.unique_email()  # "test_abc123_1@example.com"
    """
    
    def __init__(self, scope: ExecutionScope):
        self.scope = scope
    
    def unique_string(self, prefix: str = "test") -> str:
        """Generate a unique string."""
        return self.scope.generate_unique_id(prefix)
    
    def unique_email(self, domain: str = "example.com") -> str:
        """Generate a unique email address."""
        unique_id = self.scope.generate_unique_id("test")
        return f"{unique_id}@{domain}"
    
    def unique_phone(self, prefix: str = "1380000") -> str:
        """Generate a unique phone number."""
        counter = self.scope.data.get("_phone_counter", 0) + 1
        self.scope.data["_phone_counter"] = counter
        return f"{prefix}{counter:04d}"
    
    def create_user(
        self,
        name_prefix: str = "Test User",
        **extra_fields,
    ) -> Dict[str, Any]:
        """
        Create a unique test user.
        
        Args:
            name_prefix: Prefix for user name
            **extra_fields: Additional fields to include
            
        Returns:
            Dict with user data
        """
        user_id = self.scope.generate_unique_id("user")
        counter = int(user_id.split("_")[-1])
        
        user = {
            "id": user_id,
            "name": f"{name_prefix} {counter}",
            "email": self.unique_email(),
            "phone": self.unique_phone(),
            "created_at": datetime.now().isoformat(),
            **extra_fields,
        }
        
        # Store in scope for later reference
        users = self.scope.get("_created_users", [])
        users.append(user)
        self.scope.set("_created_users", users)
        
        return user
    
    def get_created_users(self) -> list:
        """Get all users created in this scope."""
        return self.scope.get("_created_users", [])


# =============================================================================
# 5. Isolated Test Runner - 隔离测试运行器
# =============================================================================

@dataclass
class IsolatedTestConfig:
    """Configuration for isolated test execution."""
    reset_app_state: bool = True          # Reset app to clean state before test
    clear_app_data: bool = False          # Clear app data (more aggressive)
    use_unique_account: bool = True       # Use unique test account
    cleanup_after_test: bool = True       # Cleanup test data after test
    isolation_timeout_ms: int = 5000      # Timeout for isolation operations


class IsolatedTestRunner:
    """
    Runner that ensures complete test isolation.
    
    Handles:
    1. Test data isolation via ExecutionScope
    2. App state isolation via device reset
    3. Account isolation via unique test accounts
    4. Cleanup after test completion
    
    Example:
        runner = IsolatedTestRunner(agent, config)
        
        async with runner.isolated_test("test_login") as ctx:
            # ctx.scope - isolated data scope
            # ctx.factory - test data factory
            # ctx.agent - the agent to use
            
            user = ctx.factory.create_user()
            await ctx.agent.ai_action(f"Register user {user['email']}")
    """
    
    def __init__(
        self,
        agent: Any,  # Agent instance
        config: Optional[IsolatedTestConfig] = None,
    ):
        self.agent = agent
        self.config = config or IsolatedTestConfig()
    
    @asynccontextmanager
    async def isolated_test(
        self,
        test_name: str,
        initial_data: Optional[Dict[str, Any]] = None,
    ):
        """
        Run a test in complete isolation.
        
        Args:
            test_name: Name of the test
            initial_data: Initial test data
            
        Yields:
            IsolatedTestContext with scope, factory, and agent
        """
        device_id = getattr(self.agent, "device_id", None) or \
                   getattr(getattr(self.agent, "interface", None), "device_id", None)
        
        async with isolated_scope(
            device_id=device_id,
            test_name=test_name,
            initial_data=initial_data,
        ) as scope:
            factory = TestDataFactory(scope)
            
            # Pre-test isolation
            if self.config.reset_app_state:
                await self._reset_app_state()
            
            context = IsolatedTestContext(
                scope=scope,
                factory=factory,
                agent=self.agent,
            )
            
            try:
                yield context
            finally:
                # Post-test cleanup
                if self.config.cleanup_after_test:
                    await self._cleanup_test_data(scope)
    
    async def _reset_app_state(self) -> None:
        """Reset app to clean state."""
        try:
            # Check if agent has reset_state method (iOS Agent)
            if hasattr(self.agent, "reset_state"):
                await self.agent.reset_state()
            elif hasattr(self.agent, "home"):
                await self.agent.home()
        except Exception as e:
            logger.warning(f"Failed to reset app state: {e}")
    
    async def _cleanup_test_data(self, scope: ExecutionScope) -> None:
        """Cleanup test data created during the test."""
        try:
            # Log what was created
            created_users = scope.get("_created_users", [])
            if created_users:
                logger.debug(
                    f"Test {scope.test_name} created {len(created_users)} users"
                )
            
            # In a real implementation, you might:
            # - Delete created users from backend
            # - Clear local storage
            # - Reset database state
            
        except Exception as e:
            logger.warning(f"Failed to cleanup test data: {e}")


@dataclass
class IsolatedTestContext:
    """Context provided to isolated tests."""
    scope: ExecutionScope
    factory: TestDataFactory
    agent: Any


# =============================================================================
# 6. Parallel Test Data Manager - 并行测试数据管理器
# =============================================================================

class ParallelTestDataManager:
    """
    Manages test data across multiple parallel test executions.
    
    Ensures that:
    1. Each parallel execution has isolated data
    2. Shared resources are properly locked
    3. Test data doesn't leak between executions
    
    Example:
        manager = ParallelTestDataManager()
        
        # In parallel test 1
        async with manager.acquire_scope("test1", "device1") as scope:
            user = scope.generate_unique_id("user")
            
        # In parallel test 2 (concurrent)
        async with manager.acquire_scope("test2", "device2") as scope:
            user = scope.generate_unique_id("user")  # Different from test1!
    """
    
    def __init__(self):
        self._scopes: Dict[str, ExecutionScope] = {}
        self._lock = asyncio.Lock()
        self._shared_resources: Dict[str, asyncio.Lock] = {}
    
    @asynccontextmanager
    async def acquire_scope(
        self,
        test_name: str,
        device_id: str,
        initial_data: Optional[Dict[str, Any]] = None,
    ):
        """
        Acquire an isolated scope for a test.
        
        Args:
            test_name: Name of the test
            device_id: Device ID
            initial_data: Initial data
            
        Yields:
            ExecutionScope
        """
        scope_key = f"{device_id}:{test_name}"
        
        async with self._lock:
            scope = ExecutionScope(
                device_id=device_id,
                test_name=test_name,
                data=initial_data.copy() if initial_data else {},
            )
            self._scopes[scope_key] = scope
        
        token = set_current_scope(scope)
        
        try:
            yield scope
        finally:
            _current_scope.reset(token)
            async with self._lock:
                self._scopes.pop(scope_key, None)
    
    @asynccontextmanager
    async def shared_resource(self, resource_name: str):
        """
        Acquire exclusive access to a shared resource.
        
        Use this when tests need to access a shared resource
        that can't be parallelized (e.g., a specific test account).
        
        Args:
            resource_name: Name of the shared resource
            
        Yields:
            None (just provides exclusive access)
        """
        async with self._lock:
            if resource_name not in self._shared_resources:
                self._shared_resources[resource_name] = asyncio.Lock()
            resource_lock = self._shared_resources[resource_name]
        
        async with resource_lock:
            logger.debug(f"Acquired shared resource: {resource_name}")
            yield
            logger.debug(f"Released shared resource: {resource_name}")
    
    def get_active_scopes(self) -> Dict[str, ExecutionScope]:
        """Get all currently active scopes."""
        return dict(self._scopes)
