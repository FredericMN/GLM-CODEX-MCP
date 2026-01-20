"""Coder 工具实现

调用 claude-glm (GLM-4.7) 执行代码生成或修改任务。
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Dict, Generator, Iterator, Literal, Optional

from pydantic import Field


# ============================================================================
# 错误类型定义
# ============================================================================

class CommandNotFoundError(Exception):
    """命令不存在错误"""
    pass


class CommandTimeoutError(Exception):
    """命令执行超时错误"""
    def __init__(self, message: str, is_idle: bool = False):
        super().__init__(message)
        self.is_idle = is_idle  # 标记是否为空闲超时


# ============================================================================
# 错误类型枚举
# ============================================================================

class ErrorKind:
    """结构化错误类型枚举"""
    TIMEOUT = "timeout"  # 总时长超时
    IDLE_TIMEOUT = "idle_timeout"  # 空闲超时（无输出）
    COMMAND_NOT_FOUND = "command_not_found"
    UPSTREAM_ERROR = "upstream_error"
    JSON_DECODE = "json_decode"
    PROTOCOL_MISSING_SESSION = "protocol_missing_session"
    EMPTY_RESULT = "empty_result"
    SUBPROCESS_ERROR = "subprocess_error"
    CONFIG_ERROR = "config_error"
    UNEXPECTED_EXCEPTION = "unexpected_exception"


# ============================================================================
# 指标收集
# ============================================================================

class MetricsCollector:
    """指标收集器"""

    def __init__(self, tool: str, prompt: str, sandbox: str):
        self.tool = tool
        self.sandbox = sandbox
        self.prompt_chars = len(prompt)
        self.prompt_lines = prompt.count('\n') + 1
        self.ts_start = datetime.now(timezone.utc)
        self.ts_end: Optional[datetime] = None
        self.duration_ms: int = 0
        self.success: bool = False
        self.error_kind: Optional[str] = None
        self.retries: int = 0
        self.exit_code: Optional[int] = None
        self.result_chars: int = 0
        self.result_lines: int = 0
        self.raw_output_lines: int = 0
        self.json_decode_errors: int = 0

    def finish(
        self,
        success: bool,
        error_kind: Optional[str] = None,
        result: str = "",
        exit_code: Optional[int] = None,
        raw_output_lines: int = 0,
        json_decode_errors: int = 0,
        retries: int = 0,
    ) -> None:
        """完成指标收集"""
        self.ts_end = datetime.now(timezone.utc)
        self.duration_ms = int((self.ts_end - self.ts_start).total_seconds() * 1000)
        self.success = success
        self.error_kind = error_kind
        self.result_chars = len(result)
        self.result_lines = result.count('\n') + 1 if result else 0
        self.exit_code = exit_code
        self.raw_output_lines = raw_output_lines
        self.json_decode_errors = json_decode_errors
        self.retries = retries

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "ts_start": self.ts_start.isoformat() if self.ts_start else None,
            "ts_end": self.ts_end.isoformat() if self.ts_end else None,
            "duration_ms": self.duration_ms,
            "tool": self.tool,
            "sandbox": self.sandbox,
            "success": self.success,
            "error_kind": self.error_kind,
            "retries": self.retries,
            "exit_code": self.exit_code,
            "prompt_chars": self.prompt_chars,
            "prompt_lines": self.prompt_lines,
            "result_chars": self.result_chars,
            "result_lines": self.result_lines,
            "raw_output_lines": self.raw_output_lines,
            "json_decode_errors": self.json_decode_errors,
        }

    def format_duration(self) -> str:
        """格式化耗时为 "xmxs" 格式"""
        total_seconds = self.duration_ms // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}m{seconds}s"

    def log_to_stderr(self) -> None:
        """将指标输出到 stderr（JSONL 格式）"""
        metrics = self.to_dict()
        # 移除 None 值以减少输出
        metrics = {k: v for k, v in metrics.items() if v is not None}
        try:
            print(json.dumps(metrics, ensure_ascii=False), file=sys.stderr)
        except Exception:
            pass  # 静默失败，不影响主流程


# ============================================================================
# 命令执行
# ============================================================================

def run_coder_command(
    cmd: list[str],
    env: dict[str, str],
    cwd: Path | None = None,
    timeout: int = 300,
    max_duration: int = 1800,
    prompt: str = "",
) -> Generator[str, None, tuple[Optional[int], int]]:
    """执行 Coder 命令并流式返回输出

    Args:
        cmd: 命令和参数列表
        env: 环境变量字典
        cwd: 工作目录
        timeout: 空闲超时（秒），无输出超过此时间触发超时，默认 300 秒（5 分钟）
        max_duration: 总时长硬上限（秒），默认 1800 秒（30 分钟），0 表示无限制
        prompt: 通过 stdin 传递的对话 prompt

    Yields:
        输出行

    Returns:
        (exit_code, raw_output_lines) 元组

    Raises:
        CommandNotFoundError: claude CLI 未安装时抛出
        CommandTimeoutError: 命令执行超时时抛出
    """
    # 查找 claude-glm CLI 路径
    claude_glm_path = shutil.which('claude-glm')
    if not claude_glm_path:
        raise CommandNotFoundError(
            "未找到 claude-glm CLI。请确保已安装 claude-glm 并添加到 PATH。\n"
            "安装方式：参考你的 claude-glm 封装项目"
        )
    popen_cmd = cmd.copy()
    popen_cmd[0] = claude_glm_path

    process = subprocess.Popen(
        popen_cmd,
        shell=False,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        encoding='utf-8',
        errors='replace',  # 处理非 UTF-8 字符，避免 UnicodeDecodeError
        env=env,
        cwd=cwd,
    )

    # 通过 stdin 传递对话 prompt，然后关闭 stdin
    if process.stdin:
        try:
            if prompt:
                process.stdin.write(prompt)
        except (BrokenPipeError, OSError):
            pass
        finally:
            try:
                process.stdin.close()
            except (BrokenPipeError, OSError):
                pass

    output_queue: queue.Queue[str | None] = queue.Queue()
    raw_output_lines = 0
    GRACEFUL_SHUTDOWN_DELAY = 0.3

    def is_session_completed(line: str) -> bool:
        """检查是否会话完成（stream-json 格式）"""
        try:
            data = json.loads(line)
            # stream-json 格式：result 或 error 类型表示会话结束
            return data.get("type") in ("result", "error")
        except (json.JSONDecodeError, AttributeError, TypeError):
            return False

    def read_output() -> None:
        """在单独线程中读取进程输出"""
        nonlocal raw_output_lines
        if process.stdout:
            for line in iter(process.stdout.readline, ""):
                stripped = line.strip()
                # 任意行都入队（触发活动判定），但只计数非空行
                output_queue.put(stripped)
                if stripped:
                    raw_output_lines += 1
                if is_session_completed(stripped):
                    time.sleep(GRACEFUL_SHUTDOWN_DELAY)
                    break
            process.stdout.close()
        output_queue.put(None)

    thread = threading.Thread(target=read_output)
    thread.start()

    # 持续读取输出，带双重超时保障
    start_time = time.time()
    last_activity_time = time.time()
    timeout_error: CommandTimeoutError | None = None

    while True:
        now = time.time()

        # 检查总时长硬上限（优先级高）
        if max_duration > 0 and (now - start_time) >= max_duration:
            timeout_error = CommandTimeoutError(
                f"coder 执行超时（总时长超过 {max_duration}s），进程已终止。",
                is_idle=False
            )
            break

        # 检查空闲超时
        if (now - last_activity_time) >= timeout:
            timeout_error = CommandTimeoutError(
                f"coder 空闲超时（{timeout}s 无输出），进程已终止。",
                is_idle=True
            )
            break

        try:
            line = output_queue.get(timeout=0.5)
            if line is None:
                break
            # 有输出（包括空行），重置空闲计时器
            last_activity_time = time.time()
            if line:  # 非空行才 yield
                yield line
        except queue.Empty:
            if process.poll() is not None and not thread.is_alive():
                break

    # 如果超时，终止进程
    if timeout_error is not None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        thread.join(timeout=5)
        raise timeout_error

    exit_code: Optional[int] = None
    try:
        exit_code = process.wait(timeout=5)  # 此时进程应已结束，短超时即可
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        # 进程等待超时（罕见情况），视为总时长超时
        timeout_error = CommandTimeoutError(
            f"coder 进程等待超时，进程已终止。",
            is_idle=False
        )
    finally:
        thread.join(timeout=5)

    if timeout_error is not None:
        raise timeout_error

    # 读取剩余输出（不再累加 raw_output_lines，避免重复计数）
    while not output_queue.empty():
        try:
            line = output_queue.get_nowait()
            if line is not None:
                yield line
        except queue.Empty:
            break

    # 返回退出码和原始输出行数
    return (exit_code, raw_output_lines)


@contextmanager
def safe_coder_command(
    cmd: list[str],
    env: dict[str, str],
    cwd: Path | None = None,
    timeout: int = 300,
    max_duration: int = 1800,
    prompt: str = "",
) -> Iterator[Generator[str, None, tuple[Optional[int], int]]]:
    """安全执行 Coder 命令的上下文管理器

    确保在任何情况下（包括异常）都能正确清理子进程。

    用法:
        with safe_coder_command(cmd, env, cwd, timeout, max_duration, prompt) as gen:
            for line in gen:
                process_line(line)
    """
    # 查找 claude-glm CLI 路径
    claude_glm_path = shutil.which('claude-glm')
    if not claude_glm_path:
        raise CommandNotFoundError(
            "未找到 claude-glm CLI。请确保已安装 claude-glm 并添加到 PATH。\n"
            "安装方式：参考你的 claude-glm 封装项目"
        )
    popen_cmd = cmd.copy()
    popen_cmd[0] = claude_glm_path

    process = subprocess.Popen(
        popen_cmd,
        shell=False,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        encoding='utf-8',
        errors='replace',  # 处理非 UTF-8 字符，避免 UnicodeDecodeError
        env=env,
        cwd=cwd,
    )

    thread: Optional[threading.Thread] = None

    def cleanup() -> None:
        """清理子进程和线程（best-effort，不抛异常）"""
        nonlocal thread
        # 1. 先关闭 stdout 以解除读取线程的阻塞
        try:
            if process.stdout and not process.stdout.closed:
                process.stdout.close()
        except (OSError, IOError):
            pass
        # 2. 终止进程
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    try:
                        process.wait(timeout=2)  # kill 后也设超时
                    except subprocess.TimeoutExpired:
                        pass  # 极端情况：进程无法终止，放弃
        except (ProcessLookupError, OSError):
            pass  # 进程已退出，忽略
        # 3. 等待线程结束
        if thread is not None and thread.is_alive():
            thread.join(timeout=5)

    try:
        # 通过 stdin 传递对话 prompt，然后关闭 stdin
        if process.stdin:
            try:
                if prompt:
                    process.stdin.write(prompt)
            except (BrokenPipeError, OSError):
                pass
            finally:
                try:
                    process.stdin.close()
                except (BrokenPipeError, OSError):
                    pass

        output_queue: queue.Queue[str | None] = queue.Queue()
        raw_output_lines_holder = [0]  # 使用列表以便在嵌套函数中修改
        GRACEFUL_SHUTDOWN_DELAY = 0.3

        def is_session_completed(line: str) -> bool:
            """检查是否会话完成（stream-json 格式）"""
            try:
                data = json.loads(line)
                # stream-json 格式：result 或 error 类型表示会话结束
                return data.get("type") in ("result", "error")
            except (json.JSONDecodeError, AttributeError, TypeError):
                return False

        def read_output() -> None:
            """在单独线程中读取进程输出"""
            try:
                if process.stdout:
                    for line in iter(process.stdout.readline, ""):
                        stripped = line.strip()
                        output_queue.put(stripped)
                        if stripped:
                            raw_output_lines_holder[0] += 1
                        if is_session_completed(stripped):
                            time.sleep(GRACEFUL_SHUTDOWN_DELAY)
                            break
                    process.stdout.close()
            except (OSError, IOError, ValueError):
                pass  # stdout 被关闭，正常退出
            finally:
                output_queue.put(None)  # 确保投递哨兵

        thread = threading.Thread(target=read_output, daemon=True)
        thread.start()

        def generator() -> Generator[str, None, tuple[Optional[int], int]]:
            """生成器：读取输出并处理超时"""
            nonlocal thread
            start_time = time.time()
            last_activity_time = time.time()
            timeout_error: CommandTimeoutError | None = None

            while True:
                now = time.time()

                if max_duration > 0 and (now - start_time) >= max_duration:
                    timeout_error = CommandTimeoutError(
                        f"coder 执行超时（总时长超过 {max_duration}s），进程已终止。",
                        is_idle=False
                    )
                    break

                if (now - last_activity_time) >= timeout:
                    timeout_error = CommandTimeoutError(
                        f"coder 空闲超时（{timeout}s 无输出），进程已终止。",
                        is_idle=True
                    )
                    break

                try:
                    line = output_queue.get(timeout=0.5)
                    if line is None:
                        break
                    last_activity_time = time.time()
                    if line:
                        yield line
                except queue.Empty:
                    if process.poll() is not None and not thread.is_alive():
                        break

            if timeout_error is not None:
                cleanup()
                raise timeout_error

            exit_code: Optional[int] = None
            try:
                exit_code = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                timeout_error = CommandTimeoutError(
                    f"coder 进程等待超时，进程已终止。",
                    is_idle=False
                )
            finally:
                if thread is not None:
                    thread.join(timeout=5)

            if timeout_error is not None:
                raise timeout_error

            while not output_queue.empty():
                try:
                    line = output_queue.get_nowait()
                    if line is not None:
                        yield line
                except queue.Empty:
                    break

            return (exit_code, raw_output_lines_holder[0])

        yield generator()

    except Exception:
        cleanup()
        raise
    finally:
        # 确保在退出上下文时清理
        cleanup()


def _filter_last_lines(lines: list[str], max_lines: int = 50) -> list[str]:
    """过滤 last_lines，脱敏 tool_result 中的大内容

    stream-json 格式的 user 消息通常包含 tool_result，其中可能有大量文件内容。
    这里只脱敏 tool_result 的 content 字段，保留消息结构和所有其他上下文。
    """
    import copy
    filtered = []
    for line in lines:
        try:
            data = json.loads(line)
            msg_type = data.get("type", "")

            # 脱敏 user 消息中的 tool_result 内容（就地修改，保留完整结构）
            if msg_type == "user":
                message = data.get("message", {})
                content = message.get("content")
                # 类型防御：只处理 list 类型的 content
                if isinstance(content, list):
                    # 深拷贝以避免修改原始数据
                    data = copy.deepcopy(data)
                    for block in data["message"]["content"]:
                        if isinstance(block, dict) and block.get("type") == "tool_result":
                            # 只替换 content 字段，保留其他所有字段
                            block["content"] = "[truncated]"
                    filtered.append(json.dumps(data, ensure_ascii=False))
                else:
                    # content 不是 list，原样保留（可能格式异常）
                    filtered.append(line)
                continue

            # 其他消息类型正常保留
            filtered.append(line)
        except (json.JSONDecodeError, TypeError, AttributeError):
            # 非 JSON 行正常保留
            filtered.append(line)

    return filtered[-max_lines:]


def _build_error_detail(
    message: str,
    exit_code: Optional[int] = None,
    last_lines: Optional[list[str]] = None,
    json_decode_errors: int = 0,
    idle_timeout_s: Optional[int] = None,
    max_duration_s: Optional[int] = None,
    retries: int = 0,
) -> Dict[str, Any]:
    """构建结构化错误详情"""
    detail: Dict[str, Any] = {"message": message}
    if exit_code is not None:
        detail["exit_code"] = exit_code
    if last_lines:
        detail["last_lines"] = _filter_last_lines(last_lines, max_lines=50)
    if json_decode_errors > 0:
        detail["json_decode_errors"] = json_decode_errors
    if idle_timeout_s is not None:
        detail["idle_timeout_s"] = idle_timeout_s
        detail["suggestion"] = (
            "任务空闲超时（无输出）。建议：1) 增加 timeout 参数 "
            "2) 检查任务是否卡住 3) 拆分为更小的子任务"
        )
    if max_duration_s is not None:
        detail["max_duration_s"] = max_duration_s
        detail["suggestion"] = (
            "任务总时长超时。建议：1) 增加 max_duration 参数 "
            "2) 拆分为更小的子任务 3) 检查是否存在死循环"
        )
    if retries > 0:
        detail["retries"] = retries
    return detail


# ============================================================================
# Coder System Prompt
# ============================================================================

CODER_SYSTEM_PROMPT = "你是一个专注高效的代码执行助手。【执行原则】- 直接执行任务，不闲聊、不反问需求 - 遵循代码最佳实践，保持代码质量 - 在任务范围内可自主决策实现细节【输出规范】- 仅输出任务结果与必要的改动说明 - 如有代码改动可附 diff（内容较多时节选关键部分并说明）"


# ============================================================================
# 主工具函数
# ============================================================================

async def coder_tool(
    PROMPT: Annotated[str, "发送给 Coder 的任务指令，需要精确、具体"],
    cd: Annotated[Path, "工作目录"],
    sandbox: Annotated[
        Literal["read-only", "workspace-write", "danger-full-access"],
        Field(description="沙箱策略，默认允许写工作区"),
    ] = "workspace-write",
    SESSION_ID: Annotated[str, "会话 ID，用于多轮对话"] = "",
    return_all_messages: Annotated[bool, "是否返回完整消息"] = False,
    return_metrics: Annotated[bool, "是否在返回值中包含指标数据"] = False,
    timeout: Annotated[int, "空闲超时（秒），无输出超过此时间触发超时，默认 300 秒"] = 300,
    max_duration: Annotated[int, "总时长硬上限（秒），默认 1800 秒（30 分钟），0 表示无限制"] = 1800,
    max_retries: Annotated[int, "最大重试次数，默认 0（不重试）"] = 0,
    log_metrics: Annotated[bool, "是否将指标输出到 stderr"] = False,
) -> Dict[str, Any]:
    """执行 Coder 代码任务

    调用可配置的后端模型执行代码生成或修改任务。

    **角色定位**：代码执行者
    - 根据精确的 Prompt 生成或修改代码
    - 执行批量代码任务
    - 成本低，执行力强

    **可配置后端**：需要用户自行配置，推荐使用 GLM-4.7 作为参考案例，
    也可选用其他支持 Claude Code API 的模型（如 Minimax、DeepSeek 等）。

    **注意**：Coder 需要写权限，默认 sandbox 为 workspace-write
    **重试策略**：Coder 默认不重试（有写入副作用），除非显式设置 max_retries
    """
    # 初始化指标收集器
    metrics = MetricsCollector(tool="coder", prompt=PROMPT, sandbox=sandbox)

    # 构建环境变量（直接复制，不注入配置）
    env = os.environ.copy()

    # 构建命令（按逻辑分层排序）
    cmd = [
        "claude-glm",
        "-p",                                    # 1. 运行模式
        "--output-format", "stream-json",        # 2. 输出格式（流式 JSON，支持中间状态）
        "--verbose",                             # 3. stream-json 在 -p 模式下需要 --verbose
    ]

    # 5. 安全策略
    if sandbox != "read-only":
        cmd.append("--dangerously-skip-permissions")

    # 6. 全局设定（Prompt 注入）
    cmd.extend(["--append-system-prompt", CODER_SYSTEM_PROMPT])

    # 7. 动态变量（会话恢复）
    if SESSION_ID:
        cmd.extend(["-r", SESSION_ID])

    # 处理对话 PROMPT 中的换行符（确保跨平台兼容）
    normalized_prompt = PROMPT.replace('\r\n', '\n').replace('\r', '\n')
    # 对话 prompt 通过 stdin 传递，system prompt 通过 --append-system-prompt 命令行参数传递

    # 执行循环（支持重试）
    retries = 0
    last_error: Optional[Dict[str, Any]] = None
    all_last_lines: list[str] = []

    while retries <= max_retries:
        all_messages: list[Dict[str, Any]] = []
        result_content = ""
        success = True
        had_error = False
        err_message = ""
        session_id: Optional[str] = None
        exit_code: Optional[int] = None
        raw_output_lines = 0
        json_decode_errors = 0
        error_kind: Optional[str] = None
        last_lines: list[str] = []
        assistant_text_parts: list[str] = []  # 累积所有 assistant 消息的文本（多轮对话拼接）

        try:
            with safe_coder_command(cmd, env, cd, timeout, max_duration, prompt=normalized_prompt) as gen:
                try:
                    for line in gen:
                        last_lines.append(line)
                        if len(last_lines) > 50:  # 增加到 50 行以便更好的诊断
                            last_lines.pop(0)

                        try:
                            line_dict = json.loads(line.strip())
                            msg_type = line_dict.get("type", "")

                            # 收集完整消息（user 消息需要脱敏 tool_result）
                            if return_all_messages:
                                if msg_type == "user":
                                    # 脱敏 user 消息中的 tool_result 内容
                                    import copy
                                    safe_dict = copy.deepcopy(line_dict)
                                    message = safe_dict.get("message", {})
                                    content = message.get("content")
                                    if isinstance(content, list):
                                        for block in content:
                                            if isinstance(block, dict) and block.get("type") == "tool_result":
                                                block["content"] = "[truncated]"
                                    all_messages.append(safe_dict)
                                else:
                                    all_messages.append(line_dict)

                            # S0.3: 从 system/init 消息提取 session_id
                            if msg_type == "system" and line_dict.get("subtype") == "init":
                                session_id = line_dict.get("session_id")

                            # S0.4: 从 assistant 消息提取文本（多轮对话拼接）
                            elif msg_type == "assistant":
                                message = line_dict.get("message", {})
                                content = message.get("content")
                                # 类型守卫：只处理 list 类型的 content
                                if isinstance(content, list):
                                    for block in content:
                                        if isinstance(block, dict):
                                            if block.get("type") == "text":
                                                text = block.get("text", "")
                                                if text:
                                                    assistant_text_parts.append(text)

                            # 处理 result 类型（stream-json 中可能也有）
                            elif msg_type == "result":
                                # stream-json 的 result 可能包含完整结果或仅包含 stats
                                if "result" in line_dict:
                                    result_content = line_dict.get("result", "")
                                # session_id 也可能在 result 中（兼容）
                                if not session_id and "session_id" in line_dict:
                                    session_id = line_dict.get("session_id")
                                if line_dict.get("is_error"):
                                    had_error = True
                                    err_message = line_dict.get("result", "") or line_dict.get("error", "")
                                    error_kind = ErrorKind.UPSTREAM_ERROR

                            elif msg_type == "error":
                                had_error = True
                                error_data = line_dict.get("error", {})
                                err_message = error_data.get("message", str(line_dict))
                                error_kind = ErrorKind.UPSTREAM_ERROR

                        except json.JSONDecodeError:
                            json_decode_errors += 1
                            continue

                        except Exception as error:
                            err_message += f"\n\n[unexpected error] {error}. Line: {line!r}"
                            had_error = True
                            error_kind = ErrorKind.UNEXPECTED_EXCEPTION
                            break
                except StopIteration as e:
                    # 正确捕获生成器返回值
                    if isinstance(e.value, tuple) and len(e.value) == 2:
                        exit_code, raw_output_lines = e.value

            # 如果没有从 result 获取到内容，拼接所有 assistant 消息的文本
            if not result_content and assistant_text_parts:
                result_content = "\n\n".join(assistant_text_parts)

        except CommandNotFoundError as e:
            metrics.finish(
                success=False,
                error_kind=ErrorKind.COMMAND_NOT_FOUND,
                retries=retries,
            )
            if log_metrics:
                metrics.log_to_stderr()

            result = {
                "success": False,
                "tool": "coder",
                "error": str(e),
                "error_kind": ErrorKind.COMMAND_NOT_FOUND,
                "error_detail": _build_error_detail(str(e)),
            }
            if return_metrics:
                result["metrics"] = metrics.to_dict()
            return result

        except CommandTimeoutError as e:
            # 根据异常属性区分空闲超时和总时长超时
            error_kind = ErrorKind.IDLE_TIMEOUT if e.is_idle else ErrorKind.TIMEOUT
            had_error = True
            err_message = str(e)
            success = False  # 明确设置为失败
            # 超时不重试（已经耗时太久），保存错误信息后跳出
            all_last_lines = last_lines.copy()
            last_error = {
                "error_kind": error_kind,
                "err_message": err_message,
                "exit_code": exit_code,
                "json_decode_errors": json_decode_errors,
                "raw_output_lines": raw_output_lines,
            }
            break

        # 综合判断成功与否
        if had_error:
            success = False

        if session_id is None:
            success = False
            if not error_kind:
                error_kind = ErrorKind.PROTOCOL_MISSING_SESSION
            err_message = "未能获取 SESSION_ID。\n\n" + err_message

        if not result_content and success:
            success = False
            if not error_kind:
                error_kind = ErrorKind.EMPTY_RESULT
            err_message = "未能获取 Coder 响应内容。\n\n" + err_message

        # 检查退出码
        if exit_code is not None and exit_code != 0 and success:
            success = False
            if not error_kind:
                error_kind = ErrorKind.SUBPROCESS_ERROR
            err_message = f"进程退出码非零：{exit_code}\n\n" + err_message

        if success:
            # 成功，跳出重试循环
            break
        else:
            # 失败，保存错误信息
            all_last_lines = last_lines.copy()
            last_error = {
                "error_kind": error_kind,
                "err_message": err_message,
                "exit_code": exit_code,
                "json_decode_errors": json_decode_errors,
                "raw_output_lines": raw_output_lines,
            }
            # 检查是否需要重试
            if retries < max_retries:
                retries += 1
                # 指数退避
                time.sleep(0.5 * (2 ** (retries - 1)))
            else:
                break

    # 完成指标收集
    metrics.finish(
        success=success,
        error_kind=error_kind,
        result=result_content,
        exit_code=exit_code,
        raw_output_lines=raw_output_lines,
        json_decode_errors=json_decode_errors,
        retries=retries,
    )
    if log_metrics:
        metrics.log_to_stderr()

    # 构建返回结果
    if success:
        result = {
            "success": True,
            "tool": "coder",
            "SESSION_ID": session_id,
            "result": result_content,
            "duration": metrics.format_duration(),
        }
    else:
        # 使用最后一次失败的错误信息
        if last_error:
            error_kind = last_error["error_kind"]
            err_message = last_error["err_message"]
            exit_code = last_error["exit_code"]
            json_decode_errors = last_error["json_decode_errors"]

        result = {
            "success": False,
            "tool": "coder",
            "error": err_message,
            "error_kind": error_kind,
            "error_detail": _build_error_detail(
                message=err_message.split('\n')[0] if err_message else "未知错误",
                exit_code=exit_code,
                last_lines=all_last_lines,
                json_decode_errors=json_decode_errors,
                idle_timeout_s=timeout if error_kind == ErrorKind.IDLE_TIMEOUT else None,
                max_duration_s=max_duration if error_kind == ErrorKind.TIMEOUT else None,
                retries=retries,
            ),
            "duration": metrics.format_duration(),
        }

    if return_all_messages:
        result["all_messages"] = all_messages

    if return_metrics:
        result["metrics"] = metrics.to_dict()

    return result
