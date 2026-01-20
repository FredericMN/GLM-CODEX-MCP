"""配置管理（简化版）

Coder-Reviewer-MCP 不再需要配置文件注入环境变量。
CLI 工具（claude-glm、gemini）已内置配置。
此模块保留是为了向后兼容和未来扩展。
"""

from pathlib import Path
from typing import Dict, Any

# 默认配置文件路径（保留接口）
DEFAULT_CONFIG_PATH = Path.home() / ".ccg-mcp" / "config.toml"


def get_config() -> Dict[str, Any]:
    """加载配置文件

    当前版本不使用配置文件，CLI 工具已内置配置。
    此函数保留是为了向后兼容和未来扩展。

    Returns:
        空配置字典
    """
    return {}


def get_config_path() -> Path:
    """获取配置文件路径

    Returns:
        配置文件路径
    """
    return DEFAULT_CONFIG_PATH
