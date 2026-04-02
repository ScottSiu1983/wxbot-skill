#!/bin/bash
#
# install.sh — wxbot-skill 一键安装脚本
#
# 用法:
#   ./install.sh                           # 交互式选择平台
#   ./install.sh --platform gemini         # 安装到当前目录（Gemini）
#   ./install.sh --platform all            # 安装所有平台适配
#   ./install.sh --platform claude --target-dir /path/to/project
#
# 支持平台: gemini | claude | antigravity | openclaw | codex | cursor | all
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$SCRIPT_DIR/skills/wxbot-skill"
SCAFFOLD="$SKILL_DIR/adapters/scaffold.py"

# 默认值
PLATFORM=""
TARGET_DIR="$(pwd)"

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --platform)
            PLATFORM="$2"
            shift 2
            ;;
        --target-dir)
            TARGET_DIR="$2"
            shift 2
            ;;
        -h|--help)
            echo "用法: ./install.sh [--platform <平台>] [--target-dir <目录>]"
            echo ""
            echo "支持的平台:"
            echo "  gemini       Gemini CLI"
            echo "  claude       Claude Code"
            echo "  antigravity  Antigravity"
            echo "  openclaw     OpenClaw"
            echo "  codex        Codex CLI"
            echo "  cursor       Cursor (降级模式)"
            echo "  all          所有平台"
            echo ""
            echo "示例:"
            echo "  ./install.sh --platform gemini"
            echo "  ./install.sh --platform all --target-dir ~/my-project"
            exit 0
            ;;
        *)
            echo "未知参数: $1"
            exit 1
            ;;
    esac
done

# 交互式选择
if [ -z "$PLATFORM" ]; then
    echo "🔧 wxbot-skill 跨平台安装器"
    echo ""
    echo "请选择目标平台:"
    echo "  1) Gemini CLI"
    echo "  2) Claude Code"
    echo "  3) Antigravity"
    echo "  4) OpenClaw"
    echo "  5) Codex CLI"
    echo "  6) Cursor (降级模式)"
    echo "  7) 全部安装"
    echo ""
    read -rp "输入编号 (1-7): " choice
    case $choice in
        1) PLATFORM="gemini" ;;
        2) PLATFORM="claude" ;;
        3) PLATFORM="antigravity" ;;
        4) PLATFORM="openclaw" ;;
        5) PLATFORM="codex" ;;
        6) PLATFORM="cursor" ;;
        7) PLATFORM="all" ;;
        *)
            echo "无效选择"
            exit 1
            ;;
    esac
fi

# 检查依赖
if ! command -v python3 &>/dev/null; then
    echo "[ERR] 需要 Python 3"
    exit 1
fi

# 检查依赖包
echo "📦 检查 Python 依赖..."
if ! python3 -c "import pyautogui" 2>/dev/null; then
    echo "   安装依赖..."
    pip install -r "$SCRIPT_DIR/requirements.txt"
fi

# 运行适配器生成
echo ""
python3 "$SCAFFOLD" --platform "$PLATFORM" --target-dir "$TARGET_DIR"

echo ""
echo "📋 后续步骤:"
echo "   1. 确保 macOS 权限已授予（辅助功能 + 屏幕录制）"
echo "   2. 打开微信桌面版"
echo "   3. 在你的 AI Agent 中尝试: '列出微信聊天'"
