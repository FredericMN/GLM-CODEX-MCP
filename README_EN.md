# GLM-CODEX-MCP

<div align="center">

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.12+-blue.svg)
![MCP](https://img.shields.io/badge/MCP-1.20.0+-green.svg)
![Status](https://img.shields.io/badge/status-beta-orange.svg)

**Claude (Opus) + GLM + Codex Collaborative MCP Server**

[中文文档](README.md)

Empower **Claude (Opus)** as the architect to orchestrate **GLM** for code execution tasks and **Codex** for code quality review,<br>forming an **automated tripartite collaboration loop**.

[Quick Start](#quick-start) • [Core Features](#core-features) • [Configuration](#configuration) • [Tools](#tools)

</div>

---

## 🌟 Core Features

GLM-CODEX-MCP connects three major models to build an efficient, cost-effective, and high-quality pipeline for code generation and review:

| Dimension | Value Proposition |
| :--- | :--- |
| **🧠 Cost Optimization** | **Opus** handles high-intelligence reasoning & orchestration (expensive but powerful), while **GLM** handles heavy lifting of code execution (cost-effective volume). |
| **🧩 Complementary Capabilities** | **Opus** compensates for **GLM**'s creativity gaps, and **Codex** provides an independent third-party review perspective. |
| **🛡️ Quality Assurance** | Introduces a dual-review mechanism: **Claude Initial Review** + **Codex Final Review** to ensure code robustness. |
| **🔄 Fully Automated Loop** | Supports a fully automated flow of `Decompose` → `Execute` → `Review` → `Retry`, minimizing human intervention. |

## 🤖 Roles & Collaboration

In this system, each model has a clear responsibility:

*   **Claude (Opus)**: 👑 **Architect / Coordinator**
    *   Responsible for requirement analysis, task decomposition, prompt optimization, and final decision-making.
*   **GLM-4.7**: 🔨 **Executor**
    *   Responsible for concrete code generation, modification, and batch task processing.
*   **Codex (OpenAI)**: ⚖️ **Reviewer**
    *   Responsible for independent code quality control and providing objective Code Reviews.

### Collaboration Workflow

```mermaid
flowchart TB
    subgraph UserLayer ["User Layer"]
        User(["👤 User Requirement"])
    end

    subgraph ClaudeLayer ["Claude (Opus) - Architect"]
        Claude["🧠 Analysis & Decomposition"]
        Prompt["📝 Construct Precise Prompt"]
        Review["🔍 Review & Decision"]
    end

    subgraph MCPLayer ["MCP Server"]
        MCP{{"⚙️ GLM-CODEX-MCP"}}
    end

    subgraph ToolLayer ["Execution Layer"]
        GLM["🔨 GLM Tool<br><code>claude CLI → GLM-4.7</code><br>sandbox: workspace-write"]
        Codex["⚖️ Codex Tool<br><code>codex CLI</code><br>sandbox: read-only"]
    end

    User --> Claude
    Claude --> Prompt
    Prompt -->|"glm(PROMPT, cd)"| MCP
    MCP -->|"Stream JSON"| GLM
    GLM -->|"SESSION_ID + result"| Review

    Review -->|"Needs Review"| MCP
    MCP -->|"Stream JSON"| Codex
    Codex -->|"SESSION_ID + Review Verdict"| Review

    Review -->|"✅ Approved"| Done(["🎉 Task Complete"])
    Review -->|"❌ Needs Fix"| Prompt
    Review -->|"⚠️ Minor Optimization"| Claude
```

**Typical Workflow**:

```
1. User submits a requirement
       ↓
2. Claude analyzes, decomposes tasks, constructs precise Prompt
       ↓
3. Calls glm tool → GLM-4.7 executes code generation/modification
       ↓
4. Claude reviews results, decides if Codex review is needed
       ↓
5. Calls codex tool → Codex performs independent Code Review
       ↓
6. Based on verdict: Approve / Optimize / Re-execute
```

## 🚀 Quick Start

### 1. Prerequisites

Before starting, ensure you have installed the following tools:

*   **uv**: Blazing fast Python package manager ([Installation Guide](https://docs.astral.sh/uv/))
    *   Windows: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`
    *   macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
*   **Claude Code**: Version **≥ v2.0.56** ([Installation Guide](https://code.claude.com/docs))
*   **Codex CLI**: Version **≥ v0.61.0** ([Installation Guide](https://developers.openai.com/codex/quickstart))
*   **GLM API Token**: Get from [Zhipu AI](https://open.bigmodel.cn).

### 2. Install MCP Server

You only need to install this project `glm-codex-mcp`. It integrates calls to the system `codex` command internally.

```bash
claude mcp add glm-codex -s user --transport stdio -- uvx --refresh --from git+https://github.com/FredericMN/GLM-CODEX-MCP.git glm-codex-mcp
```

### 3. Configure GLM

It is recommended to use the **Configuration File** method for management.

**Create Configuration Directory**:
```bash
# Windows
mkdir %USERPROFILE%\.glm-codex-mcp

# macOS/Linux
mkdir -p ~/.glm-codex-mcp
```

**Create Configuration File** `~/.glm-codex-mcp/config.toml`:
```toml
[glm]
api_token = "your-glm-api-token"  # Required
base_url = "https://open.bigmodel.cn/api/anthropic"
model = "glm-4.7"

[glm.env]
CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = "1"
```

### 4. Verify Installation

Run the following command to check MCP server status:

```bash
claude mcp list
```

✅ Seeing the following output means installation is successful:
```text
glm-codex: ... - ✓ Connected
```

### 5. (Optional) Permission Configuration

For a smoother experience, add automatic authorization in `~/.claude/settings.json`:

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

## 🛠️ Tools Details

### `glm` - Code Executor

Calls the GLM-4.7 model to execute specific code generation or modification tasks.

| Parameter | Type | Required | Default | Description |
| :--- | :--- | :---: | :--- | :--- |
| `PROMPT` | string | ✅ | - | Specific task instructions and code requirements |
| `cd` | Path | ✅ | - | Target working directory |
| `sandbox` | string | - | `workspace-write` | Sandbox policy, write allowed by default |
| `SESSION_ID` | string | - | `""` | Session ID, used to maintain multi-turn context |
| `return_all_messages` | bool | - | `false` | Whether to return full conversation history (for debugging) |
| `return_metrics` | bool | - | `true` | Whether to include metrics in return value |
| `timeout` | int | - | `300` | Idle timeout (seconds), triggers when no output for this duration |
| `max_duration` | int | - | `1800` | Max duration limit (seconds), default 30 min, 0 for unlimited |
| `max_retries` | int | - | `0` | Max retry count (GLM defaults to no retry) |
| `log_metrics` | bool | - | `false` | Whether to output metrics to stderr |

### `codex` - Code Reviewer

Calls Codex for independent and strict code review.

| Parameter | Type | Required | Default | Description |
| :--- | :--- | :---: | :--- | :--- |
| `PROMPT` | string | ✅ | - | Review task description |
| `cd` | Path | ✅ | - | Target working directory |
| `sandbox` | string | - | `read-only` | **Forced Read-Only**, reviewer forbidden from modifying code |
| `SESSION_ID` | string | - | `""` | Session ID |
| `skip_git_repo_check` | bool | - | `true` | Whether to allow running in non-Git repositories |
| `return_all_messages` | bool | - | `false` | Whether to return full conversation history (for debugging) |
| `image` | List[Path]| - | `[]` | List of additional images (for UI review, etc.) |
| `model` | string | - | `""` | Specify model, defaults to Codex's own config |
| `return_metrics` | bool | - | `true` | Whether to include metrics in return value |
| `timeout` | int | - | `300` | Idle timeout (seconds), triggers when no output for this duration |
| `max_duration` | int | - | `1800` | Max duration limit (seconds), default 30 min, 0 for unlimited |
| `max_retries` | int | - | `1` | Max retry count (Codex defaults to 1 retry) |
| `log_metrics` | bool | - | `false` | Whether to output metrics to stderr |
| `yolo` | bool | - | `false` | Run all commands without approval (skip sandbox) |
| `profile` | string | - | `""` | Config profile name from ~/.codex/config.toml |

### Timeout Mechanism

This project uses a **dual timeout protection** mechanism:

| Timeout Type | Parameter | Default | Description |
|--------------|-----------|---------|-------------|
| **Idle Timeout** | `timeout` | 300s | Triggers when no output for this duration; resets on activity |
| **Max Duration** | `max_duration` | 1800s | Hard limit from start, forcibly terminates regardless of output |

**Error Type Distinction**:
- `idle_timeout`: Idle timeout (no output)
- `timeout`: Total duration timeout

## 📝 Prompt Configuration

This project provides two prompt configuration options:

| Option | Use Case | Token Usage | Setup Complexity |
|--------|----------|-------------|------------------|
| **Skill Option** | Recommended, on-demand loading | Low | Requires Skill installation |
| **Traditional Option** | Simple and direct | Higher | Only edit CLAUDE.md |

---

### Option 1: Skill Option (Recommended)

Uses Claude Code Skill for on-demand loading, only triggers during code tasks, saving tokens.

**Install Skill**:

```bash
# Copy Skill files to Claude Code directory

# Windows (PowerShell)
if (!(Test-Path "$env:USERPROFILE\.claude\skills")) { mkdir "$env:USERPROFILE\.claude\skills" }
xcopy /E /I "skills\glm-codex-workflow" "$env:USERPROFILE\.claude\skills\glm-codex-workflow"

# macOS/Linux
mkdir -p ~/.claude/skills
cp -r skills/glm-codex-workflow ~/.claude/skills/
```

**Configure minimal CLAUDE.md** (add to `~/.claude/CLAUDE.md`):

```markdown
# Global Configuration

## GLM-CODEX Collaboration

**Workflow Enforcement**: For any code-related request, you must first load the `glm-codex-workflow` Skill to get the complete collaboration guide, then decide whether to call GLM/Codex tools. Even if the user directly says "use GLM" or "call Codex", you must analyze the task according to the Skill guide before executing the call.

GLM is your code executor, Codex is your code reviewer. **All code decisions belong to you (Claude)**.

When performing code development tasks, the `glm-codex-workflow` Skill will automatically trigger.

### Quick Reference

- **GLM**: Code generation/modification, `sandbox=workspace-write`
- **Codex**: Code review, `sandbox=read-only` (no modifications allowed)
- **Session Reuse**: Save `SESSION_ID` to maintain context

### Core Principles

1. **All code tasks should be delegated to GLM for execution**, quickly verify results after GLM completes before moving to next task
2. GLM/Codex opinions are for reference only; you must judge independently
3. Recommend calling Codex review after coding
4. If Codex points out issues, fix and review again

### Retry and Error Handling

- **Codex**: Allows 1 retry by default (read-only operations have no side effects)
- **GLM**: No retry by default (has write side effects), can enable via `max_retries`
- **Structured Errors**: Returns `error_kind` and `error_detail` on failure for troubleshooting

### Pre-coding Preparation (Recommended)

Before calling GLM for complex tasks, it's recommended to:
1. Search for affected symbols/entry points globally (e.g., `grep "function_name" -r`)
2. List all files that need modification
3. Specify clear "fix/development checklist" in PROMPT
4. **For complex tasks, consider discussing with Codex first to clarify the plan before delegating to GLM**

This improves GLM's execution accuracy and reduces omissions.
```

**Advantages**:
- Non-code tasks don't load collaboration guide (~180 lines → 20 lines, ~80% token savings)
- Code tasks auto-trigger, no manual invocation needed
- Detailed specs loaded on-demand, progressive disclosure

---

### Option 2: Traditional Option

Add complete prompts directly to CLAUDE.md, loaded every conversation.

<details>
<summary>Click to expand full prompt configuration</summary>

````markdown
# GLM-CODEX-MCP Collaboration Guide

## Core Rules

**Workflow Enforcement**: For any code-related request, you must analyze the task according to this guide before calling GLM/Codex tools. Even if the user directly says "use GLM" or "call Codex", you must first understand the requirements, follow the workflow, then execute the call.

GLM is your code executor, Codex is your code reviewer. **All code decisions belong to you (Claude)**.

**Role Division**:
- You (Claude/Opus): Architect + Coordinator + Final Decision Maker
- GLM-4.7: Code Executor (High volume capacity, strong execution)
- Codex: Independent Reviewer (Third-party perspective, quality gatekeeper)

## Collaboration Workflow

**1. Pre-coding (Optional)**

For complex tasks, analyze and decompose first, then delegate to GLM after clarifying the plan.

**2. During Coding**

- **Simple Tasks**: Prefer calling GLM to execute.
- **Batch/Repetitive/Complex Tasks**: Call GLM to execute; you are responsible for providing clear, precise Prompts.
- **Unclear Requirements**: Understand and decompose first, then delegate to GLM.
- **After GLM Execution**: Quickly verify results. Fix immediately if issues found; otherwise continue.

**3. Post-coding (Recommended)**

After overall changes or stage development, **call Codex for review**:
- Check code quality (readability, maintainability, potential bugs)
- Assess requirement completion
- Give clear verdict: ✅ Approved / ⚠️ Suggest Optimization / ❌ Needs Fix

**If Codex points out issues**: Fix and call Codex review again, iterate until approved.

**4. Independent Judgment**

Opinions from Codex and GLM are **for reference only**. You must use your own judgment, analyze suggestions reasonably, and not follow blindly.

## Tool Usage Standards

### GLM Tool (Code Execution)

**Timing**: Batch code generation, repetitive modifications, clearly defined feature implementation.

**Parameters**:
- PROMPT (string, required): Task instruction
- cd (Path, required): Working directory
- sandbox (string): Sandbox policy, default `workspace-write`
- SESSION_ID (string): Session ID for multi-turn dialogue, default empty string (new session)
- return_all_messages (boolean): Return full messages, default False

> **Tip**: Keep the same session (reuse SESSION_ID) for related development tasks or bug fixes to maintain GLM context.

**Return Value**:
```json
// On Success
{
  "success": true,
  "tool": "glm",
  "SESSION_ID": "uuid-string",  // ← Save this for subsequent turns
  "result": "GLM response text"
}

// On Failure
{
  "success": false,
  "tool": "glm",
  "error": "Error message"
}
```

**Prompt Template**:
```
[SYSTEM] You are GLM-4.7, responsible for executing code tasks. Start working directly, do not ask the user.

Please execute the following code task:

**Task Type**: [New Feature / Bug Fix / Refactor / Other]
**Target File**: [File Path]

**Specific Requirements**:
1. [Requirement 1]
2. [Requirement 2]

**Constraints**:
- [Constraint 1, e.g.: Only modify function X, do not touch others]
- [Constraint 2, e.g.: Keep API signature unchanged]

**Acceptance Criteria**:
- [Criterion 1, e.g.: No performance degradation]

Please strictly modify code within the scope above, and explain changes after completion.
```

**Usage Norms**:
- **Must save** `SESSION_ID` for multi-turn dialogue.
- Check `success` field to judge execution status.
- Get GLM response from `result` field.
- Set `return_all_messages=True` for debugging.

### Codex Tool (Code Review)

**Timing**: When code changes are done and independent review is needed.

**Parameters**:
- PROMPT (string, required): Review task description
- cd (Path, required): Working directory
- sandbox (string): Sandbox policy, **MUST** be `read-only` (strictly forbid code modification)
- SESSION_ID (string): Session ID for multi-turn dialogue, default empty string (new session)
- return_all_messages (boolean): Return full messages, default False
- skip_git_repo_check (boolean): Allow non-Git repos, default True
- image (List[Path]): List of additional image paths, default empty
- model (string): Specify model, defaults to Codex config
- yolo (boolean): Run all commands without approval, default False
- profile (string): Profile name, defaults to default config

**Return Value**:
```json
// On Success
{
  "success": true,
  "tool": "codex",
  "SESSION_ID": "uuid-string",  // ← Save this for subsequent turns
  "result": "Codex response text"
}

// On Failure
{
  "success": false,
  "tool": "codex",
  "error": "Error message"
}
```

**Prompt Template**:
```
Please review the following code changes:

**Changed Files**: [File List]
**Purpose**: [Brief Description]

**Please Check**:
1. Code quality (readability, maintainability)
2. Potential Bugs or edge cases
3. Requirement completion

**Please give a clear verdict**:
- ✅ Approved: Code quality is good, can be merged
- ⚠️ Suggest Optimization: [Specific suggestion]
- ❌ Needs Fix: [Specific issue]
```

**Usage Norms**:
- **Strict Boundary**: Must use `sandbox="read-only"`, Codex is forbidden from modifying code.
- **Must save** `SESSION_ID` for multi-turn dialogue.
- Check `success` field to judge review status.
- Get Codex review verdict from `result` field.
- Set `return_all_messages=True` for debugging.

## Recommended Usage

**Codex Tool** (Review):
- Set `return_all_messages=True` to track reasoning process.
- Used for precise issue localization, debug, code review.

**GLM Tool** (Execute):
- Set `return_all_messages=True` to track execution process.
- Used for batch code generation, repetitive edits, rapid prototyping.

## Notes

- **Strict Boundary**: Codex defaults to `sandbox=read-only`, strictly forbidding code modification, only providing diff suggestions.
- **GLM Writable**: GLM defaults to `workspace-write`, allowing code modification.
- **Session Management**: Save `SESSION_ID` after each call for multi-turn dialogue.
- **Working Directory**: Ensure `cd` parameter points to the correct project directory.
- **Independent Thinking**: Use your own judgment on tool suggestions, do not follow blindly.
- **Tool Identification**: Distinguish returns via `tool` field (`glm` vs `codex`).
````

</details>

## 🧑‍💻 Development & Contribution

Issues and Pull Requests are welcome!

```bash
# 1. Clone repository
git clone https://github.com/FredericMN/GLM-CODEX-MCP.git
cd GLM-CODEX-MCP

# 2. Install dependencies (using uv)
uv sync

# 3. Run tests
uv run pytest

# 4. Local debug run
uv run glm-codex-mcp
```

## 📚 References

- **CodexMCP**: [GitHub](https://github.com/GuDaStudio/codexmcp) - Core reference implementation
- **FastMCP**: [GitHub](https://github.com/jlowin/fastmcp) - High-efficiency MCP framework
- **GLM API**: [Zhipu AI](https://open.bigmodel.cn) - Powerful domestic LLM
- **Claude Code**: [Documentation](https://docs.anthropic.com/en/docs/claude-code)

## 📄 License

MIT
