"""
iOS Agent implementation

Enhanced features:
1. Test Isolation - Reset device state between test cases
2. Enhanced Element Location - Better accuracy with context hints and retry
3. Improved Wait/Retry Mechanisms - Robust waiting and automatic retry
"""

import asyncio
from typing import Optional, Generic, Callable, Any, List, Dict, Tuple
from dataclasses import dataclass, field
from enum import Enum
from contextlib import asynccontextmanager

from loguru import logger

from ..core.agent import Agent
from ..core.types import AgentOptions, LocateOption, LocateResult, ExtractOption
from .device import iOSDevice


class RetryStrategy(Enum):
    """重试策略枚举"""
    FIXED = "fixed"  # 固定间隔
    EXPONENTIAL = "exponential"  # 指数退避
    LINEAR = "linear"  # 线性增长


@dataclass
class RetryConfig:
    """重试配置"""
    max_retries: int = 3  # 最大重试次数
    retry_delay_ms: int = 500  # 重试间隔（毫秒）
    exponential_backoff: bool = True  # 是否使用指数退避
    retry_on_exceptions: tuple = (Exception,)  # 需要重试的异常类型
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL  # 重试策略
    max_delay_ms: int = 10000  # 最大延迟时间
    jitter: bool = True  # 是否添加随机抖动


@dataclass
class LocateConfig:
    """元素定位增强配置"""
    confidence_threshold: float = 0.7  # 置信度阈值
    use_context_hints: bool = True  # 使用上下文提示
    prefer_visible: bool = True  # 优先选择可见元素
    prefer_interactable: bool = True  # 优先选择可交互元素
    max_candidates: int = 5  # 最大候选元素数量
    use_relative_position: bool = True  # 使用相对位置描述
    screenshot_before_locate: bool = True  # 定位前刷新截图


@dataclass
class TestIsolationConfig:
    """用例隔离配置"""
    reset_to_home: bool = True  # 重置到主屏幕
    close_all_apps: bool = False  # 关闭所有后台应用
    clear_notifications: bool = False  # 清除通知
    wait_after_reset_ms: int = 1000  # 重置后等待时间
    target_app_bundle_id: Optional[str] = None  # 目标应用 Bundle ID
    clear_app_data: bool = False  # 清除应用数据（需要重新安装）
    dismiss_alerts: bool = True  # 自动关闭系统弹窗
    wait_for_idle: bool = True  # 等待设备空闲


@dataclass
class WaitConfig:
    """等待配置"""
    default_timeout_ms: int = 10000  # 默认超时时间
    default_interval_ms: int = 500  # 默认检查间隔
    stable_count: int = 2  # 稳定性检查次数
    page_load_timeout_ms: int = 30000  # 页面加载超时


class iOSAgent(Agent):
    """iOS-specific agent implementation
    
    Inherits all AI-driven capabilities from the base Agent class:
    - ai_action: Execute AI-driven actions
    - ai_locate: Locate UI elements using AI
    - ai_extract: Extract data from UI using AI
    - ai_assert: Assert conditions using AI
    - ai_wait_for: Wait for conditions to be true
    - tap: Tap at coordinates
    - input_text: Input text
    - scroll: Scroll page
    
    Additionally provides iOS-specific convenience methods:
    - launch_app: Launch iOS app by bundle ID
    - terminate_app: Terminate iOS app by bundle ID
    - home: Press home button
    - swipe: Perform swipe gesture
    - long_press: Perform long press gesture
    
    Enhanced features (v2.0):
    
    1. Test Isolation (用例隔离):
       - reset_state(): Reset device to clean state
       - setup_test(): Test case setup with app launch
       - teardown_test(): Test case cleanup
       - test_case(): Context manager for automatic setup/teardown
    
    2. Enhanced Element Location (增强元素定位):
       - ai_locate_enhanced(): Location with retry and context hints
       - ai_tap(): Smart tap with enhanced location
       - ai_input(): Smart input with enhanced location
       - build_element_description(): Build precise element descriptions
    
    3. Wait/Retry Mechanisms (等待和重试):
       - with_retry(): Execute action with automatic retry
       - ai_wait_for_enhanced(): Enhanced wait with stability check
       - wait_for_element(): Wait for element to appear
       - wait_for_element_gone(): Wait for element to disappear
       - wait_for_page_load(): Wait for page to fully load
    """

    # Type hint for the interface to be iOSDevice
    interface: iOSDevice

    def __init__(
        self, 
        device: iOSDevice, 
        options: Optional[AgentOptions] = None,
        retry_config: Optional[RetryConfig] = None,
        locate_config: Optional[LocateConfig] = None,
        isolation_config: Optional[TestIsolationConfig] = None,
        wait_config: Optional[WaitConfig] = None,
    ):
        """Initialize iOS agent

        Args:
            device: iOSDevice instance
            options: Agent options (optional)
            retry_config: Retry configuration for operations
            locate_config: Enhanced locate configuration
            isolation_config: Test isolation configuration
            wait_config: Wait configuration
            
        Requirements: 8.1, 8.2
        """
        super().__init__(device, options)
        # Store typed reference to device for iOS-specific operations
        self._ios_device = device
        
        # Enhanced configurations
        self.retry_config = retry_config or RetryConfig()
        self.locate_config = locate_config or LocateConfig()
        self.isolation_config = isolation_config or TestIsolationConfig()
        self.wait_config = wait_config or WaitConfig()
        
        # Test execution state
        self._current_test_name: Optional[str] = None
        self._test_start_time: Optional[float] = None
        self._action_history: List[Dict[str, Any]] = []

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

    # ==================== 用例隔离/状态重置功能 ====================

    async def reset_state(
        self, 
        config: Optional[TestIsolationConfig] = None
    ) -> None:
        """重置设备状态，用于用例隔离
        
        在每个测试用例开始前调用，确保设备处于干净的初始状态。
        
        Args:
            config: 隔离配置，如果为 None 则使用默认配置
            
        Example:
            # 在每个测试用例开始前
            await agent.reset_state()
            
            # 使用自定义配置
            await agent.reset_state(TestIsolationConfig(
                reset_to_home=True,
                close_all_apps=True,
                target_app_bundle_id="com.example.app"
            ))
        """
        cfg = config or self.isolation_config
        
        logger.info("Resetting device state for test isolation")
        
        try:
            # 1. 返回主屏幕
            if cfg.reset_to_home:
                await self.home()
                await asyncio.sleep(0.3)
            
            # 2. 关闭所有后台应用（可选）
            if cfg.close_all_apps:
                await self._close_all_background_apps()
            
            # 3. 清除通知（可选）
            if cfg.clear_notifications:
                await self._clear_notifications()
            
            # 4. 如果指定了目标应用，启动它
            if cfg.target_app_bundle_id:
                await self.launch_app(cfg.target_app_bundle_id)
            
            # 5. 等待状态稳定
            if cfg.wait_after_reset_ms > 0:
                await asyncio.sleep(cfg.wait_after_reset_ms / 1000.0)
            
            logger.info("Device state reset completed")
            
        except Exception as e:
            logger.error(f"Failed to reset device state: {e}")
            raise

    async def _close_all_background_apps(self) -> None:
        """关闭所有后台应用
        
        通过双击 Home 键进入多任务界面，然后上滑关闭所有应用。
        """
        try:
            # 双击 Home 键进入多任务界面
            await self.home()
            await asyncio.sleep(0.1)
            await self.home()
            await asyncio.sleep(0.5)
            
            # 上滑关闭应用（重复多次以确保关闭所有）
            screen_size = self._ios_device._screen_size
            if screen_size:
                center_x = screen_size.width / 2
                center_y = screen_size.height / 2
                
                for _ in range(5):  # 最多关闭 5 个应用
                    await self.swipe(
                        center_x, center_y,
                        center_x, center_y - 300,
                        duration=200
                    )
                    await asyncio.sleep(0.3)
            
            # 返回主屏幕
            await self.home()
            
        except Exception as e:
            logger.warning(f"Failed to close background apps: {e}")

    async def _clear_notifications(self) -> None:
        """清除通知中心的通知"""
        try:
            # 从顶部下滑打开通知中心
            screen_size = self._ios_device._screen_size
            if screen_size:
                center_x = screen_size.width / 2
                await self.swipe(center_x, 0, center_x, 300, duration=300)
                await asyncio.sleep(0.5)
                
                # 尝试清除通知（点击清除按钮）
                # 这里使用 AI 定位更可靠
                try:
                    await self.ai_action("点击清除所有通知按钮")
                except Exception:
                    pass  # 可能没有通知需要清除
                
                # 返回主屏幕
                await self.home()
                
        except Exception as e:
            logger.warning(f"Failed to clear notifications: {e}")

    async def setup_test(
        self, 
        app_bundle_id: Optional[str] = None,
        reset: bool = True
    ) -> None:
        """测试用例 setup 方法
        
        在每个测试用例开始时调用，执行状态重置和应用启动。
        
        Args:
            app_bundle_id: 要启动的应用 Bundle ID
            reset: 是否执行状态重置
            
        Example:
            async def test_login():
                await agent.setup_test(app_bundle_id="com.example.app")
                # 执行测试步骤...
                await agent.teardown_test()
        """
        if reset:
            await self.reset_state(TestIsolationConfig(
                reset_to_home=True,
                target_app_bundle_id=app_bundle_id
            ))
        elif app_bundle_id:
            await self.launch_app(app_bundle_id)

    async def teardown_test(self, close_app: bool = True) -> None:
        """测试用例 teardown 方法
        
        在每个测试用例结束时调用，执行清理操作。
        
        Args:
            close_app: 是否关闭当前应用
        """
        try:
            if close_app:
                await self.home()
            
            # 记录测试执行时间
            if self._test_start_time:
                duration = asyncio.get_event_loop().time() - self._test_start_time
                logger.info(f"Test '{self._current_test_name}' completed in {duration:.2f}s")
            
            self._current_test_name = None
            self._test_start_time = None
            logger.info("Test teardown completed")
        except Exception as e:
            logger.warning(f"Teardown failed: {e}")

    @asynccontextmanager
    async def test_case(
        self,
        name: str,
        app_bundle_id: Optional[str] = None,
        reset: bool = True,
        close_app_after: bool = True
    ):
        """测试用例上下文管理器
        
        自动处理 setup 和 teardown，确保用例隔离。
        
        Args:
            name: 测试用例名称
            app_bundle_id: 要启动的应用 Bundle ID
            reset: 是否执行状态重置
            close_app_after: 测试后是否关闭应用
            
        Example:
            async with agent.test_case("登录测试", app_bundle_id="com.example.app"):
                await agent.ai_tap("用户名输入框")
                await agent.ai_input("用户名输入框", "testuser")
                await agent.ai_tap("登录按钮")
        """
        self._current_test_name = name
        self._test_start_time = asyncio.get_event_loop().time()
        self._action_history = []
        
        logger.info(f"Starting test case: {name}")
        
        try:
            await self.setup_test(app_bundle_id=app_bundle_id, reset=reset)
            yield self
        except Exception as e:
            logger.error(f"Test case '{name}' failed: {e}")
            # 记录失败时的截图
            try:
                await self._capture_failure_screenshot(name)
            except Exception:
                pass
            raise
        finally:
            await self.teardown_test(close_app=close_app_after)

    async def _capture_failure_screenshot(self, test_name: str) -> None:
        """捕获失败时的截图用于调试"""
        try:
            context = await self.get_context()
            logger.info(f"Captured failure screenshot for test: {test_name}")
            # 可以保存到文件或报告系统
        except Exception as e:
            logger.warning(f"Failed to capture failure screenshot: {e}")

    async def dismiss_system_alert(self) -> bool:
        """尝试关闭系统弹窗
        
        Returns:
            是否成功关闭了弹窗
        """
        try:
            # 尝试点击常见的关闭按钮
            common_dismiss_buttons = [
                "允许", "Allow", "好", "OK", "确定", "Done",
                "不允许", "Don't Allow", "取消", "Cancel",
                "稍后", "Later", "跳过", "Skip"
            ]
            
            for button_text in common_dismiss_buttons:
                try:
                    result = await self.ai_locate(button_text)
                    if result.element:
                        await result.element.tap()
                        await asyncio.sleep(0.3)
                        return True
                except Exception:
                    continue
            
            return False
        except Exception as e:
            logger.debug(f"No system alert to dismiss: {e}")
            return False

    # ==================== 增强元素定位功能 ====================

    def build_element_description(
        self,
        element_type: str,
        text: Optional[str] = None,
        position: Optional[str] = None,
        color: Optional[str] = None,
        size: Optional[str] = None,
        near_element: Optional[str] = None,
        index: Optional[int] = None,
        additional_hints: Optional[List[str]] = None
    ) -> str:
        """构建精确的元素描述
        
        帮助用户构建更精确的元素描述，减少误点问题。
        
        Args:
            element_type: 元素类型（按钮、输入框、文本、图片等）
            text: 元素文本内容
            position: 位置描述（顶部、底部、左侧、右侧、中间等）
            color: 颜色描述（蓝色、红色、绿色等）
            size: 大小描述（大、小、中等）
            near_element: 附近的参照元素
            index: 第几个（当有多个相似元素时）
            additional_hints: 其他提示
            
        Returns:
            构建好的元素描述字符串
            
        Example:
            desc = agent.build_element_description(
                element_type="按钮",
                text="确认",
                position="底部",
                color="蓝色",
                near_element="取消按钮右侧"
            )
            # 返回: "底部的蓝色按钮，文字为'确认'，在取消按钮右侧"
        """
        parts = []
        
        # 位置
        if position:
            parts.append(f"{position}的")
        
        # 颜色
        if color:
            parts.append(f"{color}")
        
        # 大小
        if size:
            parts.append(f"{size}")
        
        # 元素类型
        parts.append(element_type)
        
        # 索引
        if index is not None:
            parts.append(f"（第{index}个）")
        
        # 文本
        if text:
            parts.append(f"，文字为'{text}'")
        
        # 附近元素
        if near_element:
            parts.append(f"，在{near_element}")
        
        # 其他提示
        if additional_hints:
            hints_str = "，".join(additional_hints)
            parts.append(f"，{hints_str}")
        
        return "".join(parts)

    async def ai_locate_enhanced(
        self,
        prompt: str,
        options: Optional[LocateOption] = None,
        config: Optional[LocateConfig] = None,
        context_hints: Optional[List[str]] = None,
        relative_to: Optional[str] = None,
        element_type: Optional[str] = None,
    ) -> LocateResult:
        """增强的 AI 元素定位
        
        相比基础的 ai_locate，提供以下增强功能：
        - 自动重试机制
        - 置信度过滤
        - 上下文提示增强
        - 相对位置定位
        - 更精确的元素描述
        
        Args:
            prompt: 元素描述
            options: 定位选项
            config: 定位配置
            context_hints: 上下文提示列表，帮助 AI 更准确定位
            relative_to: 相对于哪个元素定位（如"在用户名输入框下方"）
            element_type: 元素类型（按钮、输入框等）
            
        Returns:
            LocateResult 包含定位到的元素
            
        Example:
            # 基础用法
            result = await agent.ai_locate_enhanced("登录按钮")
            
            # 使用上下文提示
            result = await agent.ai_locate_enhanced(
                "提交按钮",
                context_hints=["在表单底部", "蓝色背景", "文字为'提交'"]
            )
            
            # 使用相对位置
            result = await agent.ai_locate_enhanced(
                "确认按钮",
                relative_to="取消按钮右侧"
            )
        """
        cfg = config or self.locate_config
        
        # 构建增强的 prompt
        enhanced_prompt = self._build_enhanced_prompt(
            prompt, context_hints, cfg, relative_to, element_type
        )
        
        # 记录定位尝试
        locate_attempt = {
            "action": "locate",
            "prompt": prompt,
            "enhanced_prompt": enhanced_prompt,
            "timestamp": asyncio.get_event_loop().time()
        }
        
        # 使用重试机制执行定位
        async def do_locate():
            # 如果配置了定位前刷新截图，先等待一小段时间
            if cfg.screenshot_before_locate:
                await asyncio.sleep(0.1)
            
            result = await self.ai_locate(enhanced_prompt, options)
            
            # 如果定位失败，抛出异常触发重试
            if result.element is None:
                raise ValueError(f"Element not found: {prompt}")
            
            return result
        
        try:
            result = await self.with_retry(
                do_locate,
                max_retries=self.retry_config.max_retries,
                retry_delay_ms=self.retry_config.retry_delay_ms
            )
            locate_attempt["success"] = True
            locate_attempt["element"] = str(result.element)
        except Exception as e:
            locate_attempt["success"] = False
            locate_attempt["error"] = str(e)
            raise
        finally:
            self._action_history.append(locate_attempt)
        
        return result

    def _build_enhanced_prompt(
        self,
        prompt: str,
        context_hints: Optional[List[str]],
        config: LocateConfig,
        relative_to: Optional[str] = None,
        element_type: Optional[str] = None
    ) -> str:
        """构建增强的定位 prompt
        
        通过添加上下文信息和约束条件，提高定位精确度。
        """
        parts = []
        
        # 元素类型前缀
        if element_type:
            parts.append(f"找到{element_type}：")
        
        # 主要描述
        parts.append(prompt)
        
        # 相对位置
        if relative_to and config.use_relative_position:
            parts.append(f"（位于{relative_to}）")
        
        # 添加上下文提示
        if context_hints and config.use_context_hints:
            hints_str = "，".join(context_hints)
            parts.append(f"（特征：{hints_str}）")
        
        # 添加可见性约束
        if config.prefer_visible:
            parts.append("（需要是当前屏幕上可见的元素）")
        
        # 添加可交互性约束
        if config.prefer_interactable:
            parts.append("（需要是可点击/可交互的元素）")
        
        return "".join(parts)

    async def ai_tap(
        self,
        prompt: str,
        context_hints: Optional[List[str]] = None,
        relative_to: Optional[str] = None,
        retry: bool = True,
        wait_after_tap_ms: int = 300,
        double_tap: bool = False
    ) -> None:
        """AI 驱动的点击操作，带增强定位和重试
        
        Args:
            prompt: 要点击的元素描述
            context_hints: 上下文提示
            relative_to: 相对于哪个元素
            retry: 是否启用重试
            wait_after_tap_ms: 点击后等待时间（毫秒）
            double_tap: 是否双击
            
        Example:
            # 简单用法
            await agent.ai_tap("登录按钮")
            
            # 带上下文提示
            await agent.ai_tap(
                "确认按钮",
                context_hints=["在弹窗中", "绿色按钮"]
            )
            
            # 使用相对位置避免误点
            await agent.ai_tap(
                "删除按钮",
                relative_to="第一条消息右侧"
            )
        """
        if retry:
            result = await self.ai_locate_enhanced(
                prompt, 
                context_hints=context_hints,
                relative_to=relative_to
            )
        else:
            result = await self.ai_locate(prompt)
        
        if result.element:
            await result.element.tap()
            if double_tap:
                await asyncio.sleep(0.1)
                await result.element.tap()
            
            # 点击后等待
            if wait_after_tap_ms > 0:
                await asyncio.sleep(wait_after_tap_ms / 1000.0)
        else:
            raise ValueError(f"Cannot tap: element not found - {prompt}")

    async def ai_input(
        self,
        prompt: str,
        text: str,
        context_hints: Optional[List[str]] = None,
        relative_to: Optional[str] = None,
        clear_first: bool = True,
        verify_input: bool = False,
        submit_after: bool = False
    ) -> None:
        """AI 驱动的输入操作，带增强定位
        
        Args:
            prompt: 输入框描述
            text: 要输入的文本
            context_hints: 上下文提示
            relative_to: 相对于哪个元素
            clear_first: 是否先清除现有文本
            verify_input: 是否验证输入成功
            submit_after: 输入后是否按回车提交
            
        Example:
            await agent.ai_input("用户名输入框", "testuser")
            await agent.ai_input(
                "密码输入框",
                "password123",
                context_hints=["在用户名下方", "带有密码图标"],
                submit_after=True
            )
        """
        result = await self.ai_locate_enhanced(
            prompt, 
            context_hints=context_hints,
            relative_to=relative_to,
            element_type="输入框"
        )
        
        if result.element:
            await result.element.tap()
            await asyncio.sleep(0.2)
            
            if clear_first:
                await self._ios_device.clear_text()
                await asyncio.sleep(0.1)
            
            await self._ios_device.input_text(text)
            
            # 验证输入
            if verify_input:
                await asyncio.sleep(0.2)
                # 可以通过 AI 验证输入框中是否包含预期文本
                try:
                    await self.ai_assert(f"输入框中显示'{text}'")
                except AssertionError:
                    logger.warning(f"Input verification failed for: {text}")
            
            # 提交
            if submit_after:
                await self._ios_device.input_text("\n")  # 发送回车键
        else:
            raise ValueError(f"Cannot input: element not found - {prompt}")

    async def ai_scroll_to_element(
        self,
        prompt: str,
        direction: str = "down",
        max_scrolls: int = 5,
        context_hints: Optional[List[str]] = None
    ) -> LocateResult:
        """滚动直到找到元素
        
        Args:
            prompt: 要找的元素描述
            direction: 滚动方向
            max_scrolls: 最大滚动次数
            context_hints: 上下文提示
            
        Returns:
            找到的元素
            
        Example:
            result = await agent.ai_scroll_to_element("底部的提交按钮")
        """
        for i in range(max_scrolls):
            try:
                result = await self.ai_locate_enhanced(
                    prompt, 
                    context_hints=context_hints
                )
                if result.element:
                    return result
            except ValueError:
                pass
            
            # 滚动
            await self._ios_device.scroll(direction)
            await asyncio.sleep(0.5)
        
        raise ValueError(f"Element not found after {max_scrolls} scrolls: {prompt}")

    # ==================== 等待和重试机制 ====================

    def _calculate_retry_delay(self, attempt: int, base_delay: int) -> int:
        """计算重试延迟时间
        
        Args:
            attempt: 当前尝试次数（从0开始）
            base_delay: 基础延迟时间（毫秒）
            
        Returns:
            实际延迟时间（毫秒）
        """
        import random
        
        if self.retry_config.strategy == RetryStrategy.FIXED:
            delay = base_delay
        elif self.retry_config.strategy == RetryStrategy.EXPONENTIAL:
            delay = base_delay * (2 ** attempt)
        elif self.retry_config.strategy == RetryStrategy.LINEAR:
            delay = base_delay * (attempt + 1)
        else:
            delay = base_delay
        
        # 限制最大延迟
        delay = min(delay, self.retry_config.max_delay_ms)
        
        # 添加随机抖动（±10%）
        if self.retry_config.jitter:
            jitter_range = delay * 0.1
            delay = delay + random.uniform(-jitter_range, jitter_range)
        
        return int(delay)

    async def with_retry(
        self,
        action: Callable[[], Any],
        max_retries: Optional[int] = None,
        retry_delay_ms: Optional[int] = None,
        on_retry: Optional[Callable[[int, Exception], None]] = None,
        retry_on: Optional[Tuple[type, ...]] = None,
    ) -> Any:
        """带重试机制执行操作
        
        支持多种重试策略：固定间隔、指数退避、线性增长。
        
        Args:
            action: 要执行的异步操作
            max_retries: 最大重试次数
            retry_delay_ms: 重试间隔（毫秒）
            on_retry: 重试时的回调函数
            retry_on: 需要重试的异常类型
            
        Returns:
            操作的返回值
            
        Example:
            result = await agent.with_retry(
                lambda: agent.ai_locate("按钮"),
                max_retries=3,
                retry_delay_ms=1000
            )
        """
        retries = max_retries if max_retries is not None else self.retry_config.max_retries
        delay = retry_delay_ms if retry_delay_ms is not None else self.retry_config.retry_delay_ms
        exceptions_to_retry = retry_on or self.retry_config.retry_on_exceptions
        
        last_exception = None
        
        for attempt in range(retries + 1):
            try:
                if asyncio.iscoroutinefunction(action):
                    return await action()
                else:
                    result = action()
                    # 如果返回的是协程，等待它
                    if asyncio.iscoroutine(result):
                        return await result
                    return result
            except exceptions_to_retry as e:
                last_exception = e
                
                if attempt < retries:
                    # 计算延迟时间
                    actual_delay = self._calculate_retry_delay(attempt, delay)
                    
                    logger.warning(
                        f"Retry {attempt + 1}/{retries} after {actual_delay}ms: {e}"
                    )
                    
                    if on_retry:
                        on_retry(attempt + 1, e)
                    
                    await asyncio.sleep(actual_delay / 1000.0)
        
        raise last_exception

    async def with_timeout(
        self,
        action: Callable[[], Any],
        timeout_ms: int,
        error_message: Optional[str] = None
    ) -> Any:
        """带超时执行操作
        
        Args:
            action: 要执行的异步操作
            timeout_ms: 超时时间（毫秒）
            error_message: 超时错误消息
            
        Returns:
            操作的返回值
            
        Example:
            result = await agent.with_timeout(
                lambda: agent.ai_locate("按钮"),
                timeout_ms=5000,
                error_message="定位按钮超时"
            )
        """
        try:
            if asyncio.iscoroutinefunction(action):
                return await asyncio.wait_for(
                    action(),
                    timeout=timeout_ms / 1000.0
                )
            else:
                result = action()
                if asyncio.iscoroutine(result):
                    return await asyncio.wait_for(
                        result,
                        timeout=timeout_ms / 1000.0
                    )
                return result
        except asyncio.TimeoutError:
            msg = error_message or f"Operation timed out after {timeout_ms}ms"
            raise TimeoutError(msg)

    async def ai_wait_for_enhanced(
        self,
        condition: str,
        timeout_ms: int = 10000,
        check_interval_ms: int = 500,
        stable_count: int = 1,
    ) -> bool:
        """增强的等待条件满足
        
        相比基础的 ai_wait_for，提供以下增强：
        - 稳定性检查：条件需要连续满足 N 次才算成功
        - 更细粒度的检查间隔
        - 返回布尔值而不是抛出异常
        
        Args:
            condition: 等待的条件描述
            timeout_ms: 超时时间（毫秒）
            check_interval_ms: 检查间隔（毫秒）
            stable_count: 条件需要连续满足的次数
            
        Returns:
            条件是否满足
            
        Example:
            # 等待页面加载完成
            success = await agent.ai_wait_for_enhanced(
                "页面加载完成，显示主界面",
                timeout_ms=15000
            )
            
            # 等待元素稳定出现
            success = await agent.ai_wait_for_enhanced(
                "登录按钮可见",
                stable_count=2  # 连续2次检查都满足
            )
        """
        start_time = asyncio.get_event_loop().time()
        timeout_seconds = timeout_ms / 1000.0
        check_interval_seconds = check_interval_ms / 1000.0
        
        consecutive_success = 0
        
        while True:
            try:
                result = await self.insight.assert_condition(condition)
                
                if result.passed:
                    consecutive_success += 1
                    if consecutive_success >= stable_count:
                        logger.info(f"Condition met: {condition}")
                        return True
                else:
                    consecutive_success = 0
                    
            except Exception as e:
                logger.debug(f"Wait condition check failed: {e}")
                consecutive_success = 0
            
            # 检查超时
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout_seconds:
                logger.warning(f"Timeout waiting for: {condition}")
                return False
            
            await asyncio.sleep(check_interval_seconds)

    async def wait_for_element(
        self,
        prompt: str,
        timeout_ms: int = 10000,
        check_interval_ms: int = 500,
    ) -> Optional[LocateResult]:
        """等待元素出现
        
        Args:
            prompt: 元素描述
            timeout_ms: 超时时间
            check_interval_ms: 检查间隔
            
        Returns:
            LocateResult 或 None（超时）
            
        Example:
            result = await agent.wait_for_element("加载完成提示")
            if result:
                await result.element.tap()
        """
        start_time = asyncio.get_event_loop().time()
        timeout_seconds = timeout_ms / 1000.0
        
        while True:
            try:
                result = await self.ai_locate(prompt)
                if result.element:
                    return result
            except Exception as e:
                logger.debug(f"Element not found yet: {e}")
            
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout_seconds:
                return None
            
            await asyncio.sleep(check_interval_ms / 1000.0)

    async def wait_for_element_gone(
        self,
        prompt: str,
        timeout_ms: int = 10000,
        check_interval_ms: int = 500,
    ) -> bool:
        """等待元素消失
        
        Args:
            prompt: 元素描述
            timeout_ms: 超时时间
            check_interval_ms: 检查间隔
            
        Returns:
            元素是否已消失
            
        Example:
            # 等待加载动画消失
            await agent.wait_for_element_gone("加载中动画")
        """
        start_time = asyncio.get_event_loop().time()
        timeout_seconds = timeout_ms / 1000.0
        
        while True:
            try:
                result = await self.ai_locate(prompt)
                if result.element is None:
                    return True
            except Exception:
                # 定位失败也认为元素消失了
                return True
            
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout_seconds:
                return False
            
            await asyncio.sleep(check_interval_ms / 1000.0)

    async def wait_for_page_load(
        self,
        indicators: Optional[List[str]] = None,
        timeout_ms: Optional[int] = None,
        wait_for_idle_ms: int = 500
    ) -> bool:
        """等待页面加载完成
        
        通过检查加载指示器消失和页面稳定来判断加载完成。
        
        Args:
            indicators: 加载指示器描述列表（如 ["加载中", "Loading", "转圈动画"]）
            timeout_ms: 超时时间
            wait_for_idle_ms: 页面稳定等待时间
            
        Returns:
            页面是否加载完成
            
        Example:
            await agent.wait_for_page_load(
                indicators=["加载中动画", "Loading..."],
                timeout_ms=15000
            )
        """
        timeout = timeout_ms or self.wait_config.page_load_timeout_ms
        default_indicators = ["加载中", "Loading", "正在加载", "请稍候"]
        check_indicators = indicators or default_indicators
        
        start_time = asyncio.get_event_loop().time()
        
        # 首先等待加载指示器消失
        for indicator in check_indicators:
            try:
                gone = await self.wait_for_element_gone(
                    indicator,
                    timeout_ms=timeout,
                    check_interval_ms=300
                )
                if gone:
                    logger.debug(f"Loading indicator gone: {indicator}")
            except Exception:
                pass
            
            # 检查是否超时
            elapsed = asyncio.get_event_loop().time() - start_time
            remaining = timeout - (elapsed * 1000)
            if remaining <= 0:
                return False
        
        # 等待页面稳定
        await asyncio.sleep(wait_for_idle_ms / 1000.0)
        
        return True

    async def wait_and_tap(
        self,
        prompt: str,
        timeout_ms: int = 10000,
        context_hints: Optional[List[str]] = None
    ) -> None:
        """等待元素出现并点击
        
        Args:
            prompt: 元素描述
            timeout_ms: 超时时间
            context_hints: 上下文提示
            
        Example:
            await agent.wait_and_tap("登录成功后的确认按钮", timeout_ms=15000)
        """
        result = await self.wait_for_element(prompt, timeout_ms=timeout_ms)
        if result and result.element:
            await result.element.tap()
        else:
            raise TimeoutError(f"Element not found within {timeout_ms}ms: {prompt}")

    async def safe_action(
        self,
        action: Callable[[], Any],
        fallback: Optional[Callable[[], Any]] = None,
        error_handler: Optional[Callable[[Exception], None]] = None
    ) -> Tuple[bool, Any]:
        """安全执行操作，不抛出异常
        
        Args:
            action: 要执行的操作
            fallback: 失败时的备选操作
            error_handler: 错误处理函数
            
        Returns:
            (是否成功, 结果或错误)
            
        Example:
            success, result = await agent.safe_action(
                lambda: agent.ai_tap("可能不存在的按钮"),
                fallback=lambda: agent.ai_tap("备选按钮")
            )
        """
        try:
            if asyncio.iscoroutinefunction(action):
                result = await action()
            else:
                result = action()
                if asyncio.iscoroutine(result):
                    result = await result
            return (True, result)
        except Exception as e:
            if error_handler:
                error_handler(e)
            
            if fallback:
                try:
                    if asyncio.iscoroutinefunction(fallback):
                        result = await fallback()
                    else:
                        result = fallback()
                        if asyncio.iscoroutine(result):
                            result = await result
                    return (True, result)
                except Exception as fallback_error:
                    return (False, fallback_error)
            
            return (False, e)

    async def conditional_action(
        self,
        condition: str,
        if_true: Callable[[], Any],
        if_false: Optional[Callable[[], Any]] = None
    ) -> Any:
        """条件执行操作
        
        根据 AI 判断的条件执行不同的操作。
        
        Args:
            condition: 条件描述
            if_true: 条件为真时执行的操作
            if_false: 条件为假时执行的操作
            
        Returns:
            执行结果
            
        Example:
            await agent.conditional_action(
                "登录按钮存在",
                if_true=lambda: agent.ai_tap("登录按钮"),
                if_false=lambda: agent.ai_tap("注册按钮")
            )
        """
        try:
            result = await self.insight.assert_condition(condition)
            is_true = result.passed
        except Exception:
            is_true = False
        
        if is_true:
            if asyncio.iscoroutinefunction(if_true):
                return await if_true()
            else:
                result = if_true()
                if asyncio.iscoroutine(result):
                    return await result
                return result
        elif if_false:
            if asyncio.iscoroutinefunction(if_false):
                return await if_false()
            else:
                result = if_false()
                if asyncio.iscoroutine(result):
                    return await result
                return result
        
        return None
