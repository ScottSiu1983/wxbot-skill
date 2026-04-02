#!/usr/bin/env python3
"""
scaffold.py — 跨平台技能适配器生成器

用法:
  python3 scaffold.py --platform gemini --target-dir /path/to/project
  python3 scaffold.py --platform all --target-dir /path/to/project

支持平台: gemini | claude | antigravity | openclaw | codex | cursor | all
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
TEMPLATES_DIR = SCRIPT_DIR / "templates"

# 各平台的技能安装路径和入口文件名
PLATFORM_CONFIG = {
    "gemini": {
        "skill_path": ".gemini/skills/wxbot-skill",
        "entry_file": "SKILL.md",
        "description": "Gemini CLI",
    },
    "claude": {
        "skill_path": ".claude/skills/wxbot-skill",
        "entry_file": "SKILL.md",
        "description": "Claude Code",
    },
    "antigravity": {
        "skill_path": ".agents/skills/wxbot-skill",
        "entry_file": "SKILL.md",
        "description": "Antigravity",
    },
    "openclaw": {
        "skill_path": ".openclaw/skills/wxbot-skill",
        "entry_file": "SKILL.md",
        "description": "OpenClaw",
    },
    "codex": {
        "skill_path": ".",
        "entry_file": "AGENTS.md",
        "description": "Codex CLI",
    },
    "cursor": {
        "skill_path": ".cursor/rules",
        "entry_file": "wxbot.mdc",
        "description": "Cursor (规则注入模式)",
    },
}


def read_canonical_skill() -> str:
    """读取平台无关的核心 SKILL.md。"""
    path = SKILL_DIR / "SKILL.md"
    if not path.exists():
        print(f"[ERR] 找不到核心 SKILL.md: {path}")
        sys.exit(1)
    return path.read_text(encoding="utf-8")


def extract_body(content: str) -> str:
    """从带 YAML frontmatter 的 Markdown 中提取 body 部分。"""
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return content.strip()


def extract_description(content: str) -> str:
    """从 YAML frontmatter 中提取 description 字段。"""
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().split("\n"):
                if line.strip().startswith("description:"):
                    desc = line.split(":", 1)[1].strip().strip('"').strip("'")
                    return desc
    return "微信桌面自动化技能"


def resolve_script_path(target_dir: Path, platform: str) -> str:
    """计算脚本在目标项目中的相对路径。"""
    skill_install_path = target_dir / PLATFORM_CONFIG[platform]["skill_path"]
    try:
        rel = os.path.relpath(SKILL_DIR / "scripts", skill_install_path)
        return rel
    except ValueError:
        return str(SKILL_DIR / "scripts")


def generate_gemini(target_dir: Path, body: str, desc: str):
    """生成 Gemini CLI 适配文件。"""
    frontmatter = f"""---
name: wxbot-skill
description: "{desc}"
argument-hint: chat list | chat read <name> | chat reply <name> "<msg>"
allowed-tools: [Bash, Read]
---"""
    return f"{frontmatter}\n\n{body}\n"


def generate_claude(target_dir: Path, body: str, desc: str):
    """生成 Claude Code 适配文件。"""
    frontmatter = f"""---
name: wxbot-skill
description: "{desc}"
user-invocable: true
disable-model-invocation: false
---"""
    # Claude 不需要 allowed-tools，移除 Gemini 专属的 run_in_background 措辞
    adapted_body = body.replace(
        "用 Bash 工具的 `run_in_background: true` 参数运行",
        "在后台运行",
    )
    adapted_body = adapted_body.replace("Gemini 不需要写", "AI 不需要写")
    adapted_body = adapted_body.replace("Gemini", "AI Agent")
    return f"{frontmatter}\n\n{adapted_body}\n"


def generate_antigravity(target_dir: Path, body: str, desc: str):
    """生成 Antigravity 适配文件。"""
    frontmatter = f"""---
name: wxbot-skill
description: "{desc}"
---"""
    adapted_body = body.replace("Gemini 不需要写", "AI 不需要写")
    adapted_body = adapted_body.replace("Gemini", "AI Agent")
    return f"{frontmatter}\n\n{adapted_body}\n"


def generate_openclaw(target_dir: Path, body: str, desc: str):
    """生成 OpenClaw 适配文件。"""
    # OpenClaw 与 Antigravity 高度一致
    return generate_antigravity(target_dir, body, desc)


def generate_codex(target_dir: Path, body: str, desc: str):
    """生成 Codex CLI 的 AGENTS.md（无 YAML frontmatter）。"""
    adapted_body = body.replace("Gemini 不需要写", "AI 不需要写")
    adapted_body = adapted_body.replace("Gemini", "AI Agent")
    adapted_body = adapted_body.replace(
        "用 Bash 工具的 `run_in_background: true` 参数运行",
        "在后台运行",
    )
    return f"{adapted_body}\n"


def generate_cursor(target_dir: Path, body: str, desc: str):
    """生成 Cursor .mdc 规则文件（降级模式）。"""
    frontmatter = f"""---
description: "{desc}"
globs: ["**/wechat.py", "**/wxbot-skill/**"]
alwaysApply: false
---"""
    # Cursor 只能做规则注入，精简指令
    cursor_body = """# WeChat 自动化辅助

当用户提到微信、回复消息、聊天等关键词时，参考以下脚本路径和命令：

## 可用命令

```bash
python3 scripts/wechat.py chat list
python3 scripts/wechat.py chat read <name>
python3 scripts/wechat.py chat reply <name> "<message>"
```

## 回复原则

- 先 read 再 reply，不要盲目回复
- 回复应极简、口语化、点对点
- 不确定时询问用户

> ⚠️ 注意：此规则为降级模式。Cursor 无法自动触发完整的技能工作流，需用户手动在 Chat 中描述操作意图。
"""
    return f"{frontmatter}\n\n{cursor_body}\n"


GENERATORS = {
    "gemini": generate_gemini,
    "claude": generate_claude,
    "antigravity": generate_antigravity,
    "openclaw": generate_openclaw,
    "codex": generate_codex,
    "cursor": generate_cursor,
}


def install_platform(platform: str, target_dir: Path, body: str, desc: str):
    """为指定平台生成并安装适配文件。"""
    config = PLATFORM_CONFIG[platform]
    generator = GENERATORS[platform]

    content = generator(target_dir, body, desc)

    install_path = target_dir / config["skill_path"]
    install_path.mkdir(parents=True, exist_ok=True)

    output_file = install_path / config["entry_file"]
    output_file.write_text(content, encoding="utf-8")

    # 为 SKILL.md 类型的平台，创建 scripts 的符号链接
    if platform not in ("codex", "cursor"):
        scripts_link = install_path / "scripts"
        scripts_target = SKILL_DIR / "scripts"
        if scripts_link.exists() or scripts_link.is_symlink():
            scripts_link.unlink()
        try:
            scripts_link.symlink_to(scripts_target)
        except OSError:
            # fallback: 如果无法创建符号链接，写个提示
            print(f"  ⚠️ 无法创建 symlink，请手动链接: {scripts_link} → {scripts_target}")

        # 同时链接 config.json
        config_link = install_path / "config.json"
        config_target = SKILL_DIR / "config.json"
        if config_link.exists() or config_link.is_symlink():
            config_link.unlink()
        if config_target.exists():
            try:
                config_link.symlink_to(config_target)
            except OSError:
                pass

    print(f"  ✅ {config['description']}: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="wxbot-skill 跨平台适配器生成器")
    parser.add_argument(
        "--platform",
        required=True,
        choices=list(PLATFORM_CONFIG.keys()) + ["all"],
        help="目标平台",
    )
    parser.add_argument(
        "--target-dir",
        required=True,
        help="目标项目根目录",
    )
    args = parser.parse_args()

    target_dir = Path(args.target_dir).resolve()
    if not target_dir.exists():
        print(f"[ERR] 目标目录不存在: {target_dir}")
        sys.exit(1)

    canonical = read_canonical_skill()
    body = extract_body(canonical)
    desc = extract_description(canonical)

    platforms = list(PLATFORM_CONFIG.keys()) if args.platform == "all" else [args.platform]

    print(f"🔧 wxbot-skill 跨平台适配器")
    print(f"   目标: {target_dir}")
    print(f"   平台: {', '.join(platforms)}")
    print()

    for p in platforms:
        install_platform(p, target_dir, body, desc)

    print()
    print("🎉 完成！")


if __name__ == "__main__":
    main()
