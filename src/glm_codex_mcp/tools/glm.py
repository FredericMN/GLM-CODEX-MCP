"""GLM 工具实现

调用 GLM-4.7 执行代码生成或修改任务。
通过设置环境变量让 claude CLI 使用 GLM 后端。
"""

from __future__ import annotations

import json
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Annotated, Any, Dict, Generator, Literal, Optional

from pydantic import Field

from glm_codex_mcp.config import build_glm_env, get_config


class CommandNotFoundError(Exception):
    """命令不存在错误"""
    pass


def run_glm_command(
    cmd: list[str],
    env: dict[str, str],
    cwd: Path | None = None,
) -> Generator[str, None, None]:
    """执行 GLM 命令并流式返回输出

    Args:
        cmd: 命令和参数列表
        env: 环境变量字典
        cwd: 工作目录

    Yields:
        输出行

    Raises:
        CommandNotFoundError: claude CLI 未安装时抛出
    """
    # 查找 claude CLI 路径
    claude_path = shutil.which('claude')
    if not claude_path:
        raise CommandNotFoundError(
            "未找到 claude CLI。请确保已安装 Claude Code CLI 并添加到 PATH。\n"
            "安装指南：https://docs.anthropic.com/en/docs/claude-code"
        )
    popen_cmd = cmd.copy()
    popen_cmd[0] = claude_path

    process = subprocess.Popen(
        popen_cmd,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        encoding='utf-8',
        env=env,
        cwd=cwd,
    )

    output_queue: queue.Queue[str | None] = queue.Queue()
    GRACEFUL_SHUTDOWN_DELAY = 0.3

    def is_session_completed(line: str) -> bool:
        """检查是否会话完成"""
        try:
            data = json.loads(line)
            # json 格式返回单个 result 对象
            return data.get("type") in ("result", "error")
        except (json.JSONDecodeError, AttributeError, TypeError):
            return False

    def read_output() -> None:
        """在单独线程中读取进程输出"""
        if process.stdout:
            for line in iter(process.stdout.readline, ""):
                stripped = line.strip()
                if stripped:
                    output_queue.put(stripped)
                if is_session_completed(stripped):
                    time.sleep(GRACEFUL_SHUTDOWN_DELAY)
                    break
            process.stdout.close()
        output_queue.put(None)

    thread = threading.Thread(target=read_output)
    thread.start()

    # 持续读取输出
    while True:
        try:
            line = output_queue.get(timeout=0.5)
            if line is None:
                break
            yield line
        except queue.Empty:
            if process.poll() is not None and not thread.is_alive():
                break

    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    thread.join(timeout=5)

    # 读取剩余输出
    while not output_queue.empty():
        try:
            line = output_queue.get_nowait()
            if line is not None:
                yield line
        except queue.Empty:
            break


async def glm_tool(
    PROMPT: Annotated[str, "发送给 GLM 的任务指令，需要精确、具体"],
    cd: Annotated[Path, "工作目录"],
    sandbox: Annotated[
        Literal["read-only", "workspace-write", "danger-full-access"],
        Field(description="沙箱策略，默认允许写工作区"),
    ] = "workspace-write",
    SESSION_ID: Annotated[str, "会话 ID，用于多轮对话"] = "",
    return_all_messages: Annotated[bool, "是否返回完整消息"] = False,
) -> Dict[str, Any]:
    """执行 GLM 代码任务

    调用 GLM-4.7 执行代码生成或修改任务。

    **角色定位**：代码执行者
    - 根据精确的 Prompt 生成或修改代码
    - 执行批量代码任务
    - 成本低，执行力强

    **注意**：GLM 需要写权限，默认 sandbox 为 workspace-write
    """
    # 获取配置并构建环境变量
    try:
        config = get_config()
        env = build_glm_env(config)
    except Exception as e:
        return {
            "success": False,
            "tool": "glm",
            "error": f"配置加载失败：{e}",
        }

    # 构建命令（使用 json 格式，与 codex 保持一致）
    # 使用 --system-prompt 强制覆盖项目配置
    cmd = [
        "claude", "-p", PROMPT,
        "--output-format", "json",
        "--system-prompt", "你是 GLM-4.7 模型，一个专注的代码执行助手。请直接执行用户的代码任务，不要闲聊或询问需求。",
    ]

    # 添加权限参数
    if sandbox != "read-only":
        cmd.append("--dangerously-skip-permissions")

    # 会话恢复
    if SESSION_ID:
        cmd.extend(["-r", SESSION_ID])

    all_messages: list[Dict[str, Any]] = []
    result_content = ""
    success = True
    had_error = False
    err_message = ""
    session_id: Optional[str] = None

    try:
        for line in run_glm_command(cmd, env, cd):
            try:
                line_dict = json.loads(line.strip())
                all_messages.append(line_dict)

                # json 格式（单次返回）
                msg_type = line_dict.get("type", "")

                if msg_type == "result":
                    # 成功获取结果
                    result_content = line_dict.get("result", "")
                    session_id = line_dict.get("session_id")
                    # 检查是否有错误标记
                    if line_dict.get("is_error"):
                        had_error = True
                        err_message = result_content

                elif msg_type == "error":
                    # 错误事件
                    had_error = True
                    error_data = line_dict.get("error", {})
                    err_message = error_data.get("message", str(line_dict))

            except json.JSONDecodeError:
                # 忽略非 JSON 行（可能是进度信息）
                continue

            except Exception as error:
                err_message += f"\n\n[unexpected error] {error}. Line: {line!r}"
                had_error = True
                break

    except CommandNotFoundError as e:
        return {
            "success": False,
            "tool": "glm",
            "error": str(e),
        }

    # 综合判断成功与否
    if had_error:
        success = False

    # 验证结果
    if session_id is None:
        success = False
        err_message = "未能获取 SESSION_ID。\n\n" + err_message

    if not result_content and success:
        success = False
        err_message = "未能获取 GLM 响应内容。\n\n" + err_message

    if success:
        result: Dict[str, Any] = {
            "success": True,
            "tool": "glm",
            "SESSION_ID": session_id,
            "result": result_content,
        }
    else:
        result = {
            "success": False,
            "tool": "glm",
            "error": err_message,
        }

    if return_all_messages:
        result["all_messages"] = all_messages

    return result
