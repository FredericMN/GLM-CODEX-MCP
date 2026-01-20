"""Coder-Reviewer-MCP 服务器主体

提供 coder 和 reviewer 两个 MCP 工具，实现多模型协作。
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Dict, List, Literal, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ccg_mcp.tools.coder import coder_tool
from ccg_mcp.tools.reviewer import reviewer_tool

# 创建 MCP 服务器实例
mcp = FastMCP("CCG-MCP Server")


@mcp.tool(
    name="coder",
    description="""
    调用 claude-glm (GLM-4.7) 执行代码生成或修改任务。

    **角色定位**：代码执行者
    - 根据精确的 Prompt 生成或修改代码
    - 执行批量代码任务
    - 成本低，执行力强

    **后端模型**：claude-glm CLI 封装的 GLM-4.7 模型。

    **使用场景**：
    - 新增功能：根据需求生成代码
    - 修复 Bug：根据问题描述修改代码
    - 重构：根据目标进行代码重构
    - 批量任务：执行大量相似的代码修改

    **注意**：Coder 需要写权限，默认 sandbox 为 workspace-write

    **Prompt 模板**：
    ```
    请执行以下代码任务：
    **任务类型**：[新增功能 / 修复 Bug / 重构 / 其他]
    **目标文件**：[文件路径]
    **具体要求**：
    1. [要求1]
    2. [要求2]
    **约束条件**：
    - [约束1]
    **验收标准**：
    - [标准1]
    ```
    """,
)
async def coder(
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
    max_retries: Annotated[int, "最大重试次数，默认 0（Coder 有写入副作用，默认不重试）"] = 0,
    log_metrics: Annotated[bool, "是否将指标输出到 stderr"] = False,
) -> Dict[str, Any]:
    """执行 Coder 代码任务"""
    return await coder_tool(
        PROMPT=PROMPT,
        cd=cd,
        sandbox=sandbox,
        SESSION_ID=SESSION_ID,
        return_all_messages=return_all_messages,
        return_metrics=return_metrics,
        timeout=timeout,
        max_duration=max_duration,
        max_retries=max_retries,
        log_metrics=log_metrics,
    )


@mcp.tool(
    name="reviewer",
    description="""
    调用 Gemini 进行代码审核。

    **角色定位**：代码审核者
    - 检查代码质量（可读性、可维护性、潜在 bug）
    - 评估需求完成度
    - 给出明确结论：✅ 通过 / ⚠️ 建议优化 / ❌ 需要修改

    **使用场景**：
    - Coder 完成代码后，调用 Reviewer 进行质量审核
    - 需要独立第三方视角时
    - 代码合入前的最终检查

    **注意**：Reviewer 仅审核，严禁修改代码，默认 sandbox 为 read-only

    **Prompt 模板**：
    ```
    请 review 以下代码改动：
    **改动文件**：[文件列表]
    **改动目的**：[简要描述]
    **请检查**：
    1. 代码质量（可读性、可维护性）
    2. 潜在 Bug 或边界情况
    3. 需求完成度
    **请给出明确结论**：
    - ✅ 通过：代码质量良好，可以合入
    - ⚠️ 建议优化：[具体建议]
    - ❌ 需要修改：[具体问题]
    ```
    """,
)
async def reviewer(
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
    timeout: Annotated[int, "空闲超时（秒），无输出超过此时间触发超时，默认 300 秒"] = 300,
    max_duration: Annotated[int, "总时长硬上限（秒），默认 1800 秒（30 分钟），0 表示无限制"] = 1800,
    max_retries: Annotated[int, "最大重试次数，默认 1（Reviewer 只读可安全重试）"] = 1,
    log_metrics: Annotated[bool, "是否将指标输出到 stderr"] = False,
) -> Dict[str, Any]:
    """执行 Reviewer (Gemini) 代码审核"""
    return await reviewer_tool(
        PROMPT=PROMPT,
        cd=cd,
        sandbox=sandbox,
        SESSION_ID=SESSION_ID,
        skip_git_repo_check=skip_git_repo_check,
        return_all_messages=return_all_messages,
        return_metrics=return_metrics,
        image=image,
        model=model,
        yolo=yolo,
        profile=profile,
        timeout=timeout,
        max_duration=max_duration,
        max_retries=max_retries,
        log_metrics=log_metrics,
    )


def run() -> None:
    """启动 MCP 服务器"""
    mcp.run(transport="stdio")
