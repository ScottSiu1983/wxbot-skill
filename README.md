<p align="center">
  <h1 align="center">wxbot-skill</h1>
  <p align="center">
    跨平台微信桌面自动化技能
    <br />
    本地 OCR + 键鼠模拟 · 数据不离开你的电脑
  </p>
  <p align="center">
    <a href="https://github.com/ScottSiu1983/wxbot-skill/releases"><img src="https://img.shields.io/github/v/release/ScottSiu1983/wxbot-skill?include_prereleases&style=flat-square" alt="Release" /></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue?style=flat-square" alt="License" /></a>
    <a href="https://github.com/ScottSiu1983/wxbot-skill/stargazers"><img src="https://img.shields.io/github/stars/ScottSiu1983/wxbot-skill?style=flat-square" alt="Stars" /></a>
  </p>
  <p align="center">
    <a href="README_EN.md">English</a> · 中文
  </p>
</p>

---

## 功能特性

- **聊天列表** — 列出所有可见的微信对话
- **聊天阅读** — 打开任意聊天并提取消息记录（含发送者归属）
- **聊天回复** — 发送带前缀标识的智能回复
- **群聊支持** — 自动识别群聊，支持提取回复引用（Quote Detection），并区分每条消息的发送者
- **视觉识别** — 识别对话中的图片、表情包和 emoji
- **跨平台兼容** — 支持 Gemini CLI、Claude Code、Antigravity、OpenClaw、Codex CLI、Cursor

## 支持的 AI Agent 平台

| 平台 | 支持模式 | 安装路径 |
|------|---------|---------|
| **Gemini CLI** | ✅ 完整技能 | `.gemini/skills/wxbot-skill/` |
| **Claude Code** | ✅ 完整技能 | `.claude/skills/wxbot-skill/` |
| **Antigravity** | ✅ 完整技能 | `.agents/skills/wxbot-skill/` |
| **OpenClaw** | ✅ 完整技能 | `.openclaw/skills/wxbot-skill/` |
| **Codex CLI** | ✅ 指令注入 | `AGENTS.md` |
| **Cursor** | ⚠️ 规则注入 | `.cursor/rules/wxbot.mdc` |

## 环境要求

| 依赖 | 版本 |
|------|------|
| macOS | 13+（Vision Framework、AppleScript） |
| Python | 3.10+ |
| WeChat | Mac 桌面版 |

### macOS 权限

在 **系统设置 → 隐私与安全性** 中授权：

- **辅助功能** — 终端 / IDE（pyautogui 键鼠控制）
- **屏幕录制** — 终端 / IDE（screencapture 截屏）

## 快速开始

### 1. 克隆并安装依赖

```bash
git clone https://github.com/ScottSiu1983/wxbot-skill.git
cd wxbot-skill
pip install -r requirements.txt
```

### 2. 一键安装到你的 AI Agent

```bash
# 交互式选择平台
./install.sh

# 或直接指定平台
./install.sh --platform gemini --target-dir /path/to/your/project

# 安装所有平台
./install.sh --platform all --target-dir /path/to/your/project
```

### 3. 自定义配置（可选）

编辑 `skills/wxbot-skill/config.json`：

```json
{
  "auto_send": false,
  "reply_prefix": "[AI分身] "
}
```

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `auto_send` | `false` | `true`：自动发送回复；`false`：仅输入到输入框 |
| `reply_prefix` | `[AI分身] ` | 自动添加到所有回复前的前缀标识 |

### 4. 运行

在你的 AI Agent 中说：

```
列出微信聊天
回复 Kent
给工作群回复 收到
```

## 工作原理

```
AI Agent  ─→  SKILL.md（触发规则 + 工作流）
                    │
                    ▼
               wechat.py CLI
          chat list | read | reply
                    │
          ┌─────────┴──────────┐
          ▼                    ▼
   local_vision.py      computer_use.py
   (Vision OCR)         (pyautogui)
          │                    │
          └─────────┬──────────┘
                    ▼
    macOS: Vision · Quartz · AppleScript
```

## 跨平台架构

```
wxbot-skill/
├── SKILL.md                  ← 平台无关的核心技能定义
├── scripts/                  ← 所有可执行脚本（共享）
│   ├── wechat.py
│   ├── computer_use.py
│   └── local_vision.py
├── adapters/                 ← 跨平台适配层
│   └── scaffold.py           ← 适配器生成器
└── install.sh                ← 一键安装脚本
```

适配器通过生成各平台专属的入口文件（SKILL.md / AGENTS.md / .mdc），将同一套核心脚本注入到不同的 AI Agent 工具中。脚本目录通过符号链接共享，无需拷贝。

## 已知限制

- **仅支持 macOS** — 依赖 Vision Framework 和 AppleScript
- **单实例运行** — 同一时间只能执行一个微信操作（文件锁控制）
- **仅支持文字回复** — 暂不支持图片、表情包或文件
- **OCR 精度受限** — 准确率受字体大小和窗口布局影响
- **无微信 API** — 纯视觉自动化方案

## 许可证

[Apache-2.0](LICENSE)
