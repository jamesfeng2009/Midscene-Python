"""
Android integration module for Midscene Python

This module provides Android device automation capabilities using ADB.
It exports the main classes for Android automation:
- AndroidDevice: Device interface for Android automation
- AndroidAgent: AI-driven agent for Android automation
- AndroidElement: UI element wrapper for Android
- AndroidDeviceConfig: Configuration for Android device connection
- Error classes for Android-specific exceptions

Enhanced features (v2.0):

1. Test Isolation (用例隔离):
   - TestIsolationConfig: 配置用例隔离行为
   - agent.reset_state(): 重置设备状态
   - agent.setup_test() / teardown_test(): 测试生命周期管理
   - agent.test_case(): 上下文管理器，自动处理 setup/teardown

2. Enhanced Element Location (增强元素定位):
   - LocateConfig: 配置定位行为
   - agent.ai_locate_enhanced(): 带重试和上下文提示的定位
   - agent.ai_tap(): 智能点击，支持相对位置
   - agent.ai_input(): 智能输入
   - agent.build_element_description(): 构建精确的元素描述

3. Wait/Retry Mechanisms (等待和重试):
   - RetryConfig: 配置重试策略
   - WaitConfig: 配置等待行为
   - agent.with_retry(): 带重试执行操作
   - agent.with_timeout(): 带超时执行操作
   - agent.wait_for_element(): 等待元素出现
   - agent.wait_for_element_gone(): 等待元素消失
   - agent.wait_for_page_load(): 等待页面加载完成
   - agent.safe_action(): 安全执行，不抛异常
   - agent.conditional_action(): 条件执行

Usage Example:
    ```python
    from midscene.android import AndroidAgent, TestIsolationConfig, RetryConfig
    
    # 创建 agent
    agent = await AndroidAgent.create(
        retry_config=RetryConfig(max_retries=3),
        isolation_config=TestIsolationConfig(reset_to_home=True)
    )
    
    # 使用测试用例上下文管理器
    async with agent.test_case("登录测试", app_package="com.example.app"):
        await agent.ai_tap("用户名输入框")
        await agent.ai_input("用户名输入框", "testuser")
        await agent.ai_tap("登录按钮", context_hints=["蓝色", "底部"])
        await agent.wait_for_page_load()
    ```
"""

from .device import AndroidDevice, AndroidElement, AndroidDeviceConfig
from .agent import (
    AndroidAgent, 
    RetryConfig, 
    LocateConfig, 
    TestIsolationConfig,
    WaitConfig,
    RetryStrategy,
)
from .errors import (
    AndroidConnectionError,
    AndroidDeviceNotFoundError,
    AndroidOperationError,
    AndroidScreenshotError,
    AndroidTouchError,
    AndroidCoordinateError,
    AndroidADBError,
)

__all__ = [
    # Core classes
    "AndroidDevice",
    "AndroidElement",
    "AndroidDeviceConfig",
    "AndroidAgent",
    # Configuration classes
    "RetryConfig",
    "LocateConfig",
    "TestIsolationConfig",
    "WaitConfig",
    "RetryStrategy",
    # Error classes
    "AndroidConnectionError",
    "AndroidDeviceNotFoundError",
    "AndroidOperationError",
    "AndroidScreenshotError",
    "AndroidTouchError",
    "AndroidCoordinateError",
    "AndroidADBError",
]
