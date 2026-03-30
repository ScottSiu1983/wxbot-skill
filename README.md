<p align="center">
  <h1 align="center">wxbot-skill</h1>
  <p align="center">
    基于 <a href="https://docs.anthropic.com/en/docs/claude-code">Claude Code</a> 的微信桌面自动化技能
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
- **群聊支持** — 自动识别群聊，通过视觉布局区分每条消息的发送者
- **视觉识别** — 识别对话中的图片、表情包和 emoji
- **Haiku 适配** — 优化 SKILL.md 指令，支持 Claude Haiku 低成本运行

## 环境要求

| 依赖 | 版本 |
|------|------|
| macOS | 13+（Vision Framework、AppleScript） |
| Python | 3.10+ |
| WeChat | Mac 桌面版 |
| Claude Code | [CLI](https://docs.anthropic.com/en/docs/claude-code) |

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

### 2. 配置权限

创建 `.claude/settings.local.json`（不会被 git 追踪）：

```json
{
  "permissions": {
    "allow": [
      "Bash(python3:*)",
      "Skill(wxbot-skill)"
    ]
  }
}
```

### 3. 自定义配置（可选）

编辑 `.claude/skills/wxbot-skill/config.json`：

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

```bash
claude  # 或: claude --model haiku
```

然后对 Claude 说：

```
列出微信聊天
回复 Kent
给工作群回复 收到
```

## 工作原理

```
Claude Code  ─→  SKILL.md（触发规则 + 工作流）
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

## 已知限制

- **仅支持 macOS** — 依赖 Vision Framework 和 AppleScript
- **单实例运行** — 同一时间只能执行一个微信操作（文件锁控制）
- **仅支持文字回复** — 暂不支持图片、表情包或文件
- **OCR 精度受限** — 准确率受字体大小和窗口布局影响
- **无微信 API** — 纯视觉自动化方案

## 许可证

[Apache-2.0](LICENSE)
