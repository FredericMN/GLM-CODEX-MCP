# GLM-CODEX-MCP

<div align="center">

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.12+-blue.svg)
![MCP](https://img.shields.io/badge/MCP-1.20.0+-green.svg)
![Status](https://img.shields.io/badge/status-beta-orange.svg)

**Claude (Opus) + GLM + Codex 三方协作 MCP 服务器**

让 **Claude (Opus)** 作为架构师调度 **GLM** 执行代码任务、**Codex** 审核代码质量，<br>形成**自动化的三方协作闭环**。

[快速开始](#快速开始) • [核心特性](#核心特性) • [配置指南](#配置指南) • [工具详解](#工具详解)

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

## 🤖 角色分工与协作

在这个体系中，每个模型都有明确的职责：

*   **Claude (Opus)**: 👑 **架构师 / 协调者**
    *   负责需求分析、任务拆解、Prompt 优化以及最终决策。
*   **GLM-4.7**: 🔨 **执行者**
    *   负责具体的代码生成、修改、批量任务处理。
*   **Codex (OpenAI)**: ⚖️ **审核官**
    *   负责独立的代码质量把关，提供客观的 Code Review。

### 协作流程图

### 协作流程图

```text
用户需求
  │
  ▼
Claude (Opus) ────[1. 拆解 & Prompt]───▶ GLM (执行者)
  │                                         │
  │◀───────────[2. 返回结果]────────────────┘
  │
  ▼
Claude (初审)
  │
  ├─❌ 有问题 ──▶ Claude (直接修复) ──┐
  │                                  │
  ▼ (✅ 通过)                         │
  │                                  │
Codex (审核官) ◀─────────────────────┘
  │
  ▼
[深度 Review]
  │
  ├── ✅ 通过 ──────────────▶ 🎉 任务完成
  │
  ├── ⚠️ 建议优化 ──▶ Claude (优化) ────┐
  │                                    │
  └── ❌ 需要修改 ──▶ [问题根因?]        │
                         │             │
           ┌── [简单] ───┴── [复杂]     │
           │                         │
           ▼                         │
      Claude (修复) ───────────────────┴──▶ 重新提交 Codex
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

> [!NOTE]
> Windows 用户强烈推荐在 **WSL** 环境中运行本项目以获得最佳体验。

### 2. 安装 MCP 服务器

我们只需安装本项目 `glm-codex-mcp` 即可。它内部集成了对系统 `codex` 命令的调用。

```bash
claude mcp add glm-codex -s user --transport stdio -- uvx --from git+https://github.com/FredericMN/GLM-CODEX-MCP.git glm-codex-mcp
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

### 4. 验证安装

运行以下命令检查 MCP 服务器状态：

```bash
claude mcp list
```

✅ 看到以下输出即表示安装成功：
```text
glm-codex: ... - ✓ Connected
```

### 5. (可选) 权限配置

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

### `codex` - 代码审核者

调用 Codex 进行独立且严格的代码审查。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| :--- | :--- | :---: | :--- | :--- |
| `PROMPT` | string | ✅ | - | 审核任务描述 |
| `cd` | Path | ✅ | - | 目标工作目录 |
| `sandbox` | string | - | `read-only` | **强制只读**，严禁审核者修改代码 |
| `SESSION_ID` | string | - | `""` | 会话 ID |
| `skip_git_repo_check` | bool | - | `true` | 是否允许在非 Git 仓库运行 |
| `image` | List[Path]| - | `[]` | 附加图片列表（用于 UI 审查等） |

## 全局推荐提示词

<details>
<summary>点击展开全局提示词配置（推荐添加到 ~/.claude/CLAUDE.md）</summary>

````markdown
# GLM-CODEX-MCP 协作指南

## 核心规则

GLM 是你的代码执行者，Codex 是你的代码审核者。**所有代码决策权归你（Claude）所有**。

**角色分工**：
- 你（Claude/Opus）：架构师 + 协调者 + 最终决策者
- GLM-4.7：代码执行者（量大管饱，执行力强）
- Codex：独立审核者（第三方视角，质量把关）

## 协作流程

**1. 编码前（可选）**

复杂任务可先调用 Codex 讨论思路，获取建议。但最终方案由你决定。

**2. 编码中**

- **简单任务**：优先调用 GLM 执行
- **批量/重复任务**：调用 GLM 执行，你负责给出清晰、精确的 Prompt
- **需求不明确**：先理解、拆解，再委托执行

**3. 编码后（推荐）**

完成代码改动后，**调用 Codex 进行 review**：
- 检查代码质量（可读性、可维护性、潜在 bug）
- 评估需求完成度
- 给出明确结论：✅ 通过 / ⚠️ 建议优化 / ❌ 需要修改

**4. 独立判断**

Codex 和 GLM 的意见**仅供参考**。你必须有自己的判断，批判性采纳建议，不盲从。

## 工具调用规范

### GLM 工具（代码执行）

**调用时机**：批量代码生成、重复性修改、明确定义的功能实现

**参数**：
- PROMPT (string, 必填): 任务指令
- cd (Path, 必填): 工作目录
- sandbox (string): 沙箱策略，默认 `workspace-write`
- SESSION_ID (string): 会话 ID，用于多轮对话，默认空字符串（开启新会话）
- return_all_messages (boolean): 返回完整消息，默认 False

**返回值**：
```json
// 成功时
{
  "success": true,
  "tool": "glm",
  "SESSION_ID": "uuid-string",  // ← 保存此值用于后续对话
  "result": "GLM回复的文本内容"
}

// 失败时
{
  "success": false,
  "tool": "glm",
  "error": "错误信息"
}
```

**Prompt 模板**：
```
请执行以下代码任务：

**任务类型**：[新增功能 / 修复 Bug / 重构 / 其他]
**目标文件**：[文件路径]

**具体要求**：
1. [要求1]
2. [要求2]

**约束条件**：
- [约束1，如：仅修改 X 函数，不要动其他部分]
- [约束2，如：保持 API 签名不变]

**验收标准**：
- [标准1，如：性能不劣化]

请严格按照上述范围修改代码，完成后说明改动内容。
```

**使用规范**：
- **必须保存** `SESSION_ID` 以便多轮对话
- 检查 `success` 字段判断执行是否成功
- 从 `result` 字段获取 GLM 的回复内容
- 调试时设置 `return_all_messages=True` 获取 `all_messages` 详细过程

### Codex 工具（代码审核）

**调用时机**：代码改动完成后，需要独立审核时

**参数**：
- PROMPT (string, 必填): 审核任务描述
- cd (Path, 必填): 工作目录
- sandbox (string): 沙箱策略，**必须** `read-only`（严禁修改代码）
- SESSION_ID (string): 会话 ID，用于多轮对话，默认空字符串（开启新会话）
- return_all_messages (boolean): 返回完整消息，默认 False
- skip_git_repo_check (boolean): 允许非 Git 仓库，默认 True
- image (List[Path]): 附加图片文件路径列表，默认空列表
- model (string): 指定模型，默认使用 Codex 自己的配置
- yolo (boolean): 无需审批运行所有命令，默认 False
- profile (string): 配置文件名称，默认使用默认配置

**返回值**：
```json
// 成功时
{
  "success": true,
  "tool": "codex",
  "SESSION_ID": "uuid-string",  // ← 保存此值用于后续对话
  "result": "Codex回复的文本内容"
}

// 失败时
{
  "success": false,
  "tool": "codex",
  "error": "错误信息"
}
```

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

**使用规范**：
- **严格边界**：必须使用 `sandbox="read-only"`，Codex 严禁修改代码
- **必须保存** `SESSION_ID` 以便多轮对话
- 检查 `success` 字段判断审核是否成功
- 从 `result` 字段获取 Codex 的审核结论
- 调试时设置 `return_all_messages=True` 获取 `all_messages` 详细过程

## 推荐用法

**Codex 工具**（审核）：
- 如需详细追踪推理过程，设置 `return_all_messages=True`
- 用于精准定位问题、debug、代码审核

**GLM 工具**（执行）：
- 如需详细追踪执行过程，设置 `return_all_messages=True`
- 用于批量代码生成、重复性修改、代码原型快速编写

## 注意事项

- **严格边界**：Codex 默认 `sandbox=read-only`，严禁修改代码，仅提供 diff 建议
- **GLM 可写**：GLM 默认 `sandbox=workspace-write`，允许修改代码
- **会话管理**：每次调用后保存 `SESSION_ID` 以便多轮对话
- **工作目录**：确保 `cd` 参数指向正确的项目目录
- **独立思考**：对工具的建议要有自己的判断，不盲从
- **工具识别**：通过 `tool` 字段区分是 `glm` 还是 `codex` 的返回
````

</details>

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