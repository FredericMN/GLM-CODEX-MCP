"""Codex 工具实现

调用 Codex 进行代码审核。
复用 CodexMCP 的核心逻辑。
"""

from __future__ import annotations

import json
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Dict, Generator, Iterator, List, Literal, Optional

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
    AUTH_REQUIRED = "auth_required"  # 需要登录认证
    JSON_DECODE = "json_decode"
    PROTOCOL_MISSING_SESSION = "protocol_missing_session"
    EMPTY_RESULT = "empty_result"
    SUBPROCESS_ERROR = "subprocess_error"
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

def run_reviewer_command(
    cmd: list[str],
    cwd: Path | None = None,
    timeout: int = 300,
    max_duration: int = 1800,
    prompt: str = "",
) -> Generator[str, None, tuple[Optional[int], int]]:
    """执行 Codex 命令并流式返回输出

    Args:
        cmd: 命令和参数列表
        timeout: 空闲超时（秒），无输出超过此时间触发超时，默认 300 秒（5 分钟）
        max_duration: 总时长硬上限（秒），默认 1800 秒（30 分钟），0 表示无限制
        prompt: 通过 stdin 传递的 prompt 内容

    Yields:
        输出行

    Returns:
        (exit_code, raw_output_lines) 元组

    Raises:
        CommandNotFoundError: codex CLI 未安装时抛出
        CommandTimeoutError: 命令执行超时时抛出
    """
    gemini_path = shutil.which('gemini')
    if not gemini_path:
        raise CommandNotFoundError(
            "未找到 gemini CLI。请确保已安装 Gemini CLI 并添加到 PATH。\n"
            "安装指南：https://github.com/google-gemini/gemini-cli"
        )
    popen_cmd = cmd.copy()
    popen_cmd[0] = gemini_path

    process = subprocess.Popen(
        popen_cmd,
        shell=False,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        encoding='utf-8',
        errors='replace',  # 处理非 UTF-8 字符，避免 UnicodeDecodeError
        cwd=cwd,
    )

    # 通过 stdin 传递 prompt，然后关闭 stdin
    if process.stdin:
        try:
            if prompt:
                process.stdin.write(prompt)
        except (BrokenPipeError, OSError):
            # 子进程可能已退出，忽略写入错误
            pass
        finally:
            try:
                process.stdin.close()
            except (BrokenPipeError, OSError):
                pass

    output_queue: queue.Queue[str | None] = queue.Queue()
    raw_output_lines = 0
    GRACEFUL_SHUTDOWN_DELAY = 0.3

    def is_turn_completed(line: str) -> bool:
        """检查是否回合完成"""
        try:
            data = json.loads(line)
            return data.get("type") == "turn.completed"
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
                if is_turn_completed(stripped):
                    # 等待剩余输出被 drain
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
                f"codex 执行超时（总时长超过 {max_duration}s），进程已终止。",
                is_idle=False
            )
            break

        # 检查空闲超时
        if (now - last_activity_time) >= timeout:
            timeout_error = CommandTimeoutError(
                f"codex 空闲超时（{timeout}s 无输出），进程已终止。",
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
            f"codex 进程等待超时，进程已终止。",
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
def safe_reviewer_command(
    cmd: list[str],
    cwd: Path | None = None,
    timeout: int = 300,
    max_duration: int = 1800,
    prompt: str = "",
) -> Iterator[Generator[str, None, tuple[Optional[int], int]]]:
    """安全执行 Codex 命令的上下文管理器

    确保在任何情况下（包括异常）都能正确清理子进程。

    用法:
        with safe_reviewer_command(cmd, timeout, max_duration, prompt) as gen:
            for line in gen:
                process_line(line)
    """
    gemini_path = shutil.which('gemini')
    if not gemini_path:
        raise CommandNotFoundError(
            "未找到 gemini CLI。请确保已安装 Gemini CLI 并添加到 PATH。\n"
            "安装指南：https://github.com/google-gemini/gemini-cli"
        )
    popen_cmd = cmd.copy()
    popen_cmd[0] = gemini_path

    process = subprocess.Popen(
        popen_cmd,
        shell=False,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        encoding='utf-8',
        errors='replace',  # 处理非 UTF-8 字符，避免 UnicodeDecodeError
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
        # 通过 stdin 传递 prompt，然后关闭 stdin
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
        raw_output_lines_holder = [0]
        GRACEFUL_SHUTDOWN_DELAY = 0.3

        def is_turn_completed(line: str) -> bool:
            """检查是否回合完成"""
            try:
                data = json.loads(line)
                return data.get("type") == "turn.completed"
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
                        if is_turn_completed(stripped):
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
                        f"codex 执行超时（总时长超过 {max_duration}s），进程已终止。",
                        is_idle=False
                    )
                    break

                if (now - last_activity_time) >= timeout:
                    timeout_error = CommandTimeoutError(
                        f"codex 空闲超时（{timeout}s 无输出），进程已终止。",
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
                    f"codex 进程等待超时，进程已终止。",
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
        cleanup()


def _filter_last_lines(lines: list[str], max_lines: int = 50) -> list[str]:
    """过滤 last_lines，脱敏 tool_result 中的大内容

    Codex 的 JSONL 格式：tool_result 在 item.type 中。
    这里只脱敏 tool_result 的 content 字段，保留消息结构和所有其他上下文。
    """
    import copy
    filtered = []
    for line in lines:
        try:
            data = json.loads(line)
            item = data.get("item", {})

            # 脱敏 tool_result 内容
            if item.get("type") == "tool_result":
                data = copy.deepcopy(data)
                if "content" in data["item"]:
                    data["item"]["content"] = "[truncated]"
                filtered.append(json.dumps(data, ensure_ascii=False))
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
# 主工具函数
# ============================================================================

async def reviewer_tool(
    PROMPT: Annotated[str, "审核任务描述"],
    cd: Annotated[Path, "工作目录"],
    sandbox: Annotated[
        Literal["read-only", "workspace-write", "danger-full-access"],
        Field(description="沙箱策略，默认只读"),
    ] = "read-only",
    SESSION_ID: Annotated[str, "会话 ID，用于多轮对话"] = "",
    skip_git_repo_check: Annotated[
        bool,
        "允许在非 Git 仓库中运行",
    ] = True,
    return_all_messages: Annotated[bool, "是否返回完整消息"] = False,
    return_metrics: Annotated[bool, "是否在返回值中包含指标数据"] = False,
    image: Annotated[
        Optional[List[Path]],
        Field(description="附加图片文件路径列表"),
    ] = None,
    model: Annotated[
        str,
        Field(description="指定模型，默认使用 Reviewer 自己的配置"),
    ] = "",
    yolo: Annotated[
        bool,
        Field(description="无需审批运行所有命令（跳过沙箱）"),
    ] = False,
    profile: Annotated[
        str,
        "从 ~/.reviewer/config.toml 加载的配置文件名称",
    ] = "",
    timeout: Annotated[
        int,
        Field(description="空闲超时（秒），无输出超过此时间触发超时，默认 300 秒"),
    ] = 300,
    max_duration: Annotated[
        int,
        Field(description="总时长硬上限（秒），默认 1800 秒（30 分钟），0 表示无限制"),
    ] = 1800,
    max_retries: Annotated[int, "最大重试次数，默认 1（Reviewer 只读可安全重试）"] = 1,
    log_metrics: Annotated[bool, "是否将指标输出到 stderr"] = False,
) -> Dict[str, Any]:
    """执行 Reviewer (Gemini) 代码审核

    调用 Gemini 进行代码审核。

    **角色定位**：代码审核者
    - 检查代码质量（可读性、可维护性、潜在 bug）
    - 评估需求完成度
    - 给出明确结论：✅ 通过 / ⚠️ 建议优化 / ❌ 需要修改

    **注意**：Reviewer 仅审核，严禁修改代码，默认 sandbox 为 read-only
    **重试策略**：Reviewer 默认允许 1 次重试（只读操作无副作用）
    """
    # 初始化指标收集器
    metrics = MetricsCollector(tool="reviewer", prompt=PROMPT, sandbox=sandbox)

    # 归一化可选参数
    image_list = image or []

    # 构建命令（gemini CLI 格式）
    cmd = ["gemini", "-o", "stream-json"]

    # 处理沙箱策略
    if sandbox == "read-only":
        # Gemini 默认就是只读，不需要额外参数
        pass
    elif sandbox == "workspace-write":
        # Gemini 需要 --yolo 允许写操作
        cmd.append("--yolo")
    elif sandbox == "danger-full-access":
        cmd.extend(["--yolo", "--approval-mode", "yolo"])

    # 注意：没有 --cd 参数，通过 subprocess.Popen(cwd=cd) 设置工作目录

    # TODO: 处理 image 参数（需要确认 gemini 是否支持）
    # if image_list:
    #     cmd.extend(["--image", ",".join(str(p) for p in image_list)])

    # TODO: 处理 model 参数（需要确认 gemini 的参数名）
    # if model:
    #     cmd.extend(["--model", model])

    # 移除 profile 和 skip_git_repo_check（gemini CLI 不支持）
    # if profile:
    #     cmd.extend(["--profile", profile])

    # if yolo:
    #     cmd.append("--yolo")

    # if skip_git_repo_check:
    #     cmd.append("--skip-git-repo-check")

    if SESSION_ID:
        cmd.extend(["--resume", str(SESSION_ID)])

    # PROMPT 通过 stdin 传递，不再作为命令行参数

    # 执行循环（支持重试）
    retries = 0
    last_error: Optional[Dict[str, Any]] = None
    all_last_lines: list[str] = []

    while retries <= max_retries:
        all_messages: list[Dict[str, Any]] = []
        agent_messages = ""
        had_error = False
        err_message = ""
        thread_id: Optional[str] = None
        exit_code: Optional[int] = None
        raw_output_lines = 0
        json_decode_errors = 0
        error_kind: Optional[str] = None
        last_lines: list[str] = []

        try:
            with safe_reviewer_command(cmd, cwd=cd, timeout=timeout, max_duration=max_duration, prompt=PROMPT) as gen:
                try:
                    for line in gen:
                        last_lines.append(line)
                        if len(last_lines) > 50:
                            last_lines.pop(0)

                        try:
                            line_dict = json.loads(line.strip())
                            msg_type = line_dict.get("type", "")

                            # 收集完整消息
                            if return_all_messages:
                                import copy
                                safe_dict = copy.deepcopy(line_dict)
                                all_messages.append(safe_dict)

                            # 从 init 消息提取 session_id
                            if msg_type == "init":
                                session_id = line_dict.get("session_id")

                            # 从 assistant 消息提取文本（多轮对话拼接）
                            elif msg_type == "message" and line_dict.get("role") == "assistant":
                                content = line_dict.get("content", "")
                                if content:
                                    agent_messages += content

                            # 检查是否完成（从 result 消息）
                            elif msg_type == "result":
                                status = line_dict.get("status")
                                if status == "error":
                                    had_error = True
                                    err_message = line_dict.get("error", "Unknown error")
                                    error_kind = ErrorKind.UPSTREAM_ERROR

                        except json.JSONDecodeError:
                            # JSON 解析失败记录但不影响成功判定
                            json_decode_errors += 1
                            err_message += "\n\n[json decode error] " + line
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

        except CommandNotFoundError as e:
            metrics.finish(
                success=False,
                error_kind=ErrorKind.COMMAND_NOT_FOUND,
                retries=retries,
            )
            if log_metrics:
                metrics.log_to_stderr()

            result: Dict[str, Any] = {
                "success": False,
                "tool": "reviewer",
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
            # 超时可以重试（Codex 只读）
            if retries < max_retries:
                all_last_lines = last_lines.copy()
                last_error = {
                    "error_kind": error_kind,
                    "err_message": err_message,
                    "exit_code": exit_code,
                    "json_decode_errors": json_decode_errors,
                    "raw_output_lines": raw_output_lines,
                }
                retries += 1
                time.sleep(0.5 * (2 ** (retries - 1)))
                continue
            else:
                # 已达最大重试次数
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
        success = True

        if had_error:
            success = False

        if thread_id is None:
            success = False
            if not error_kind:
                error_kind = ErrorKind.PROTOCOL_MISSING_SESSION
            err_message = "未能获取 SESSION_ID。\n\n" + err_message

        if not agent_messages:
            success = False
            if not error_kind:
                error_kind = ErrorKind.EMPTY_RESULT
            err_message = "未能获取 Codex 响应内容。可尝试设置 return_all_messages=True 获取详细信息。\n\n" + err_message

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
            # 简化的重试逻辑：除了命令不存在，其他都重试
            if error_kind != ErrorKind.COMMAND_NOT_FOUND and retries < max_retries:
                all_last_lines = last_lines.copy()
                last_error = {
                    "error_kind": error_kind,
                    "err_message": err_message,
                    "exit_code": exit_code,
                    "json_decode_errors": json_decode_errors,
                    "raw_output_lines": raw_output_lines,
                }
                retries += 1
                # 指数退避
                time.sleep(0.5 * (2 ** (retries - 1)))
            else:
                # 不可重试或已达到最大重试次数
                all_last_lines = last_lines.copy()
                last_error = {
                    "error_kind": error_kind,
                    "err_message": err_message,
                    "exit_code": exit_code,
                    "json_decode_errors": json_decode_errors,
                    "raw_output_lines": raw_output_lines,
                }
                break

    # 完成指标收集
    metrics.finish(
        success=success,
        error_kind=error_kind,
        result=agent_messages,
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
            "tool": "reviewer",
            "SESSION_ID": thread_id,
            "result": agent_messages,
            "duration": metrics.format_duration(),
        }
    else:
        # 使用最后一次失败的错误信息
        if last_error:
            error_kind = last_error["error_kind"]
            err_message = last_error["err_message"]
            exit_code = last_error["exit_code"]
            json_decode_errors = last_error["json_decode_errors"]

        # 如果是认证错误，添加友好提示
        final_error = err_message
        if error_kind == ErrorKind.AUTH_REQUIRED:
            final_error = (
                "请先登录 Codex CLI。运行以下命令完成认证：\n"
                "  codex login\n"
                "\n"
                "或使用 API Key 认证：\n"
                "  printenv OPENAI_API_KEY | codex login --with-api-key\n"
                "\n" + err_message
            )

        result = {
            "success": False,
            "tool": "reviewer",
            "error": final_error,
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
