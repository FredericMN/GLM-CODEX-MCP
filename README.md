# GLM-CODEX-MCP

<div align="center">

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.12+-blue.svg)
![MCP](https://img.shields.io/badge/MCP-1.20.0+-green.svg)
![Status](https://img.shields.io/badge/status-beta-orange.svg)

[English Docs](README_EN.md)

**Claude (Opus) + GLM + Codex 三方协作 MCP 服务器**

让 **Claude (Opus)** 作为架构师调度 **GLM** 执行代码任务、**Codex** 审核代码质量，<br>形成**自动化的三方协作闭环**。

[快速开始](#快速开始) • [核心特性](#核心特性) • [架构说明](#架构说明) • [工具详解](#工具详解)

</div>

---

## 🌟 核心特性

GLM-CODEX-MCP 通过连接三大模型，构建了一个高效、低成本且高质量的代码生成与审核流水线：

| 维度 | 价值说明 |
| :--- | :--- |
| **🧠 成本优化** | **Opus** 负责高智商思考与调度（贵但强），**GLM** 负责繁重的代码执行（量大管饱）。 |
| **🧩 能力互补** | **Opus** 补足 **GLM** 的创造力短板，**Codex** 提供独立的第三方审核视角。 |
| **🛡️ 质量保障** | 引入双重审核机制：**Claude 初审** + **Codex 终审**，确保代码健壮性。 |
| **🔄 全自动闭环** | 支持 `拆解` → `执行` → `审核` → `重试` 的全自动流程，最大程度减少人工干预。 |
| **🔧 灵活架构** | **Skills + MCP** 混合架构：MCP 提供工具能力，Skills 提供工作流指导，按需加载节约 Token。 |

## 🤖 角色分工与协作

在这个体系中，每个模型都有明确的职责：

*   **Claude (Opus)**: 👑 **架构师 / 协调者**
    *   负责需求分析、任务拆解、Prompt 优化以及最终决策。
*   **GLM-4.7**: 🔨 **执行者**
    *   负责具体的代码生成、修改、批量任务处理。
*   **Codex (OpenAI)**: ⚖️ **审核官 / 高级代码顾问**
    *   负责独立的代码质量把关，提供客观的 Code Review，也可作为架构设计和复杂方案的咨询顾问。

### 协作流程图

```mermaid
flowchart TB
    subgraph UserLayer ["用户层"]
        User(["👤 用户需求"])
    end

    subgraph ClaudeLayer ["Claude (Opus) - 架构师"]
        Claude["🧠 需求分析 & 任务拆解"]
        Prompt["📝 构造精确 Prompt"]
        Review["🔍 结果审查 & 决策"]
    end

    subgraph MCPLayer ["MCP 服务器"]
        MCP{{"⚙️ GLM-CODEX-MCP"}}
    end

    subgraph ToolLayer ["执行层"]
        GLM["🔨 GLM 工具<br><code>claude CLI → GLM-4.7</code><br>sandbox: workspace-write"]
        Codex["⚖️ Codex 工具<br><code>codex CLI</code><br>sandbox: read-only"]
    end

    User --> Claude
    Claude --> Prompt
    Prompt -->|"glm(PROMPT, cd)"| MCP
    MCP -->|"流式 JSON"| GLM
    GLM -->|"SESSION_ID + result"| Review

    Review -->|"需要审核"| MCP
    MCP -->|"流式 JSON"| Codex
    Codex -->|"SESSION_ID + 审核结论"| Review

    Review -->|"✅ 通过"| Done(["🎉 任务完成"])
    Review -->|"❌ 需修改"| Prompt
    Review -->|"⚠️ 小优化"| Claude
```

**典型工作流**：

```
1. 用户提出需求
       ↓
2. Claude 分析、拆解任务，构造精确 Prompt
       ↓
3. 调用 glm 工具 → GLM-4.7 执行代码生成/修改
       ↓
4. Claude 审查结果，决定是否需要 Codex 审核
       ↓
5. 调用 codex 工具 → Codex 独立 Code Review
       ↓
6. 根据审核结论：通过 / 优化 / 重新执行
```

## 🚀 快速开始

### 1. 前置要求

在开始之前，请确保您已安装以下工具：

*   **uv**: 极速 Python 包管理器 ([安装指南](https://docs.astral.sh/uv/))
    *   Windows: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`
    *   macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
*   **Claude Code**: 版本 **≥ v2.0.56** ([安装指南](https://code.claude.com/docs))
*   **Codex CLI**: 版本 **≥ v0.61.0** ([安装指南](https://developers.openai.com/codex/quickstart))
*   **GLM API Token**: 从 [智谱 AI](https://open.bigmodel.cn) 获取。

### 2. 安装 MCP 服务器

我们只需安装本项目 `glm-codex-mcp` 即可。它内部集成了对系统 `codex` 命令的调用。

```bash
claude mcp add glm-codex -s user --transport stdio -- uvx --refresh --from git+https://github.com/FredericMN/GLM-CODEX-MCP.git glm-codex-mcp
```

### 3. 配置 GLM

推荐使用 **配置文件** 方式进行管理。

**创建配置目录**:
```bash
# Windows
mkdir %USERPROFILE%\.glm-codex-mcp

# macOS/Linux
mkdir -p ~/.glm-codex-mcp
```

**创建配置文件** `~/.glm-codex-mcp/config.toml`:
```toml
[glm]
api_token = "your-glm-api-token"  # 必填
base_url = "https://open.bigmodel.cn/api/anthropic"
model = "glm-4.7"

[glm.env]
CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = "1"
```

### 4. 安装 Skills（推荐）

Skills 层提供工作流指导，确保 Claude 正确使用 MCP 工具。

```bash
# Windows (PowerShell)
if (!(Test-Path "$env:USERPROFILE\.claude\skills")) { mkdir "$env:USERPROFILE\.claude\skills" }
xcopy /E /I "skills\glm-codex-workflow" "$env:USERPROFILE\.claude\skills\glm-codex-workflow"

# macOS/Linux
mkdir -p ~/.claude/skills
cp -r skills/glm-codex-workflow ~/.claude/skills/
```

### 5. 配置全局 Prompt（推荐）

在 `~/.claude/CLAUDE.md` 中添加强制规则，确保 Claude 遵守协作流程：

```markdown
# GLM-CODEX 协作

GLM 是代码执行者，Codex 是代码审核者。**所有决策权归 Claude 所有**。

## 核心流程

1. **GLM 执行**：所有改动任务委托 GLM 处理
2. **Claude 验收**：GLM 完成后快速检查，有误自行修复
3. **Codex 审核**：阶段性开发完成后调用 review，有误委托 GLM 修复，GLM 完成后再次进入 **Claude 验收**，持续迭代直至完全通过。

## 强制规则

- **默认协作**：所有代码/文档改动任务，**必须**委托 GLM 执行，阶段性完成后**必须**调用 Codex 审核
- **跳过需确认**：若判断无需协作，**必须立即暂停**并报告：
  > "这是一个简单的[描述]任务，我判断无需调用 GLM/Codex。是否同意？等待您的确认。"
- **违规即终止**：未经确认跳过 GLM 执行或 Codex 审核 = **流程违规**

## 快速参考

| 工具 | 用途 | sandbox | 重试 |
|------|------|---------|------|
| GLM | 执行改动 | workspace-write | 默认不重试 |
| Codex | 代码审核 | read-only | 默认 1 次 |

**会话复用**：保存 `SESSION_ID` 保持上下文

## 独立决策

GLM/Codex 意见仅供参考。Claude 是最终决策者，需批判性思考。
```

> **说明**：纯 MCP 也能工作，但推荐 Skills + 全局 Prompt 配置以获得最佳体验。

### 6. 验证安装

运行以下命令检查 MCP 服务器状态：

```bash
claude mcp list
```

✅ 看到以下输出即表示安装成功：
```text
glm-codex: ... - ✓ Connected
```

### 7. (可选) 权限配置

为获得流畅体验，可在 `~/.claude/settings.json` 中添加自动授权：

```json
{
  "permissions": {
    "allow": [
      "mcp__glm-codex__glm",
      "mcp__glm-codex__codex"
    ]
  }
}
```

## 🛠️ 工具详解

### `glm` - 代码执行者

调用 GLM-4.7 模型执行具体的代码生成或修改任务。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| :--- | :--- | :---: | :--- | :--- |
| `PROMPT` | string | ✅ | - | 具体的任务指令和代码要求 |
| `cd` | Path | ✅ | - | 目标工作目录 |
| `sandbox` | string | - | `workspace-write` | 沙箱策略，默认允许写入 |
| `SESSION_ID` | string | - | `""` | 会话 ID，用于维持多轮对话上下文 |
| `return_all_messages` | bool | - | `false` | 是否返回完整的对话历史（用于调试） |
| `return_metrics` | bool | - | `false` | 是否在返回值中包含耗时等指标 |
| `timeout` | int | - | `300` | 空闲超时（秒），无输出超过此时间触发超时 |
| `max_duration` | int | - | `1800` | 总时长硬上限（秒），默认 30 分钟，0 表示无限制 |
| `max_retries` | int | - | `0` | 最大重试次数（GLM 默认不重试） |
| `log_metrics` | bool | - | `false` | 是否将指标输出到 stderr |

### `codex` - 代码审核者

调用 Codex 进行独立且严格的代码审查。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| :--- | :--- | :---: | :--- | :--- |
| `PROMPT` | string | ✅ | - | 审核任务描述 |
| `cd` | Path | ✅ | - | 目标工作目录 |
| `sandbox` | string | - | `read-only` | **强制只读**，严禁审核者修改代码 |
| `SESSION_ID` | string | - | `""` | 会话 ID |
| `skip_git_repo_check` | bool | - | `true` | 是否允许在非 Git 仓库运行 |
| `return_all_messages` | bool | - | `false` | 是否返回完整的对话历史（用于调试） |
| `image` | List[Path]| - | `[]` | 附加图片列表（用于 UI 审查等） |
| `model` | string | - | `""` | 指定模型，默认使用 Codex 自己的配置 |
| `return_metrics` | bool | - | `false` | 是否在返回值中包含耗时等指标 |
| `timeout` | int | - | `300` | 空闲超时（秒），无输出超过此时间触发超时 |
| `max_duration` | int | - | `1800` | 总时长硬上限（秒），默认 30 分钟，0 表示无限制 |
| `max_retries` | int | - | `1` | 最大重试次数（Codex 默认允许 1 次重试） |
| `log_metrics` | bool | - | `false` | 是否将指标输出到 stderr |
| `yolo` | bool | - | `false` | 无需审批运行所有命令（跳过沙箱） |
| `profile` | string | - | `""` | 从 ~/.codex/config.toml 加载的配置文件名称 |

### 超时机制

本项目采用**双重超时保护**机制：

| 超时类型 | 参数 | 默认值 | 说明 |
|----------|------|--------|------|
| **空闲超时** | `timeout` | 300s | 无输出超过此时间触发超时，有输出则重置计时器 |
| **总时长硬上限** | `max_duration` | 1800s | 从开始计时，无论是否有输出，超过此时间强制终止 |

**错误类型区分**：
- `idle_timeout`：空闲超时（无输出）
- `timeout`：总时长超时

### 返回值结构

```json
// 成功（默认行为，return_metrics=false）
{
  "success": true,
  "tool": "glm",
  "SESSION_ID": "uuid-string",
  "result": "回复内容"
}

// 成功（启用指标，return_metrics=true）
{
  "success": true,
  "tool": "glm",
  "SESSION_ID": "uuid-string",
  "result": "回复内容",
  "metrics": {
    "ts_start": "2026-01-02T10:00:00.000Z",
    "ts_end": "2026-01-02T10:00:05.123Z",
    "duration_ms": 5123,
    "tool": "glm",
    "sandbox": "workspace-write",
    "success": true,
    "retries": 0,
    "exit_code": 0,
    "prompt_chars": 256,
    "prompt_lines": 10,
    "result_chars": 1024,
    "result_lines": 50,
    "raw_output_lines": 60,
    "json_decode_errors": 0
  }
}

// 失败（结构化错误，默认行为）
{
  "success": false,
  "tool": "glm",
  "error": "错误摘要",
  "error_kind": "idle_timeout | timeout | upstream_error | ...",
  "error_detail": {
    "message": "错误简述",
    "exit_code": 1,
    "last_lines": ["最后20行输出..."],
    "idle_timeout_s": 300,
    "max_duration_s": 1800
    // "retries": 1  // 仅在 retries > 0 时返回
  }
}

// 失败（启用指标，return_metrics=true）
{
  "success": false,
  "tool": "glm",
  "error": "错误摘要",
  "error_kind": "idle_timeout | timeout | upstream_error | ...",
  "error_detail": {
    "message": "错误简述",
    "exit_code": 1,
    "last_lines": ["最后20行输出..."],
    "idle_timeout_s": 300,
    "max_duration_s": 1800
    // "retries": 1  // 仅在 retries > 0 时返回
  },
  "metrics": {
    "ts_start": "2026-01-02T10:00:00.000Z",
    "ts_end": "2026-01-02T10:00:05.123Z",
    "duration_ms": 5123,
    "tool": "glm",
    "sandbox": "workspace-write",
    "success": false,
    "retries": 0,
    "exit_code": 1,
    "prompt_chars": 256,
    "prompt_lines": 10,
    "json_decode_errors": 0
  }
}
```

## 📚 架构说明

### 三层配置架构

本项目采用 **MCP + Skills + 全局 Prompt** 混合架构，各层职责分明：

| 层级 | 职责 | Token 消耗 | 必需性 |
|------|------|-----------|--------|
| **MCP 层** | 工具实现（类型安全、结构化错误、重试、metrics） | 固定（工具 schema） | **必需** |
| **Skills 层** | 工作流指导（触发条件、流程、模板） | 按需加载 | 推荐 |
| **全局 Prompt 层** | 强制规则（确保 Claude 遵守协作流程） | 固定（约 20 行） | 推荐 |

**为什么推荐完整配置？**
- **纯 MCP**：工具可用，但 Claude 可能不理解何时/如何使用
- **+ Skills**：Claude 学会工作流程，知道何时触发协作
- **+ 全局 Prompt**：强制规则确保 Claude 始终遵守协作纪律

**Token 优化**：Skills 按需加载，非代码任务不加载工作流指导，可显著节约 Token

## 🧑‍💻 开发与贡献

欢迎提交 Issue 和 Pull Request！

```bash
# 1. 克隆仓库
git clone https://github.com/FredericMN/GLM-CODEX-MCP.git
cd GLM-CODEX-MCP

# 2. 安装依赖 (使用 uv)
uv sync

# 3. 运行测试
uv run pytest

# 4. 本地调试运行
uv run glm-codex-mcp
```

## 📚 参考资源

- **CodexMCP**: [GitHub](https://github.com/GuDaStudio/codexmcp) - 核心参考实现
- **FastMCP**: [GitHub](https://github.com/jlowin/fastmcp) - 高效的 MCP 框架
- **GLM API**: [智谱 AI](https://open.bigmodel.cn) - 强大的国产大模型
- **Claude Code**: [Documentation](https://docs.anthropic.com/en/docs/claude-code)

## 📄 License

MIT