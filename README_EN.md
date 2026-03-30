<p align="center">
  <h1 align="center">wxbot-skill</h1>
  <p align="center">
    A <a href="https://docs.anthropic.com/en/docs/claude-code">Claude Code</a> skill for WeChat desktop automation
    <br />
    Local OCR + keyboard/mouse simulation · Your data never leaves your machine
  </p>
  <p align="center">
    <a href="https://github.com/ScottSiu1983/wxbot-skill/releases"><img src="https://img.shields.io/github/v/release/ScottSiu1983/wxbot-skill?include_prereleases&style=flat-square" alt="Release" /></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue?style=flat-square" alt="License" /></a>
    <a href="https://github.com/ScottSiu1983/wxbot-skill/stargazers"><img src="https://img.shields.io/github/stars/ScottSiu1983/wxbot-skill?style=flat-square" alt="Stars" /></a>
  </p>
  <p align="center">
    English · <a href="README.md">中文</a>
  </p>
</p>

---

## Features

- **Chat List** — List all visible WeChat conversations
- **Chat Read** — Navigate to any chat and extract message history with sender attribution
- **Chat Reply** — Send contextual replies with automatic prefix tagging
- **Group Chat Support** — Detects groups, identifies per-message senders by visual layout
- **Visual Detection** — Classifies images, stickers, and emoji in conversations
- **Haiku-Friendly** — Optimized SKILL.md instructions for cost-efficient operation with Claude Haiku

## Requirements

| Dependency | Version |
|------------|---------|
| macOS | 13+ (Vision Framework, AppleScript) |
| Python | 3.10+ |
| WeChat | Mac desktop app |
| Claude Code | [CLI](https://docs.anthropic.com/en/docs/claude-code) |

### macOS Permissions

Grant these in **System Settings → Privacy & Security**:

- **Accessibility** — Terminal / IDE (for pyautogui keyboard/mouse control)
- **Screen Recording** — Terminal / IDE (for screencapture)

## Quick Start

### 1. Clone and install dependencies

```bash
git clone https://github.com/ScottSiu1983/wxbot-skill.git
cd wxbot-skill
pip install -r requirements.txt
```

### 2. Configure permissions

Create `.claude/settings.local.json` (not tracked by git):

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

### 3. Customize (optional)

Edit `.claude/skills/wxbot-skill/config.json`:

```json
{
  "auto_send": false,
  "reply_prefix": "[AI分身] "
}
```

| Field | Default | Description |
|-------|---------|-------------|
| `auto_send` | `false` | `true`: auto-send replies; `false`: type into input box only |
| `reply_prefix` | `[AI分身] ` | Prefix auto-prepended to all replies |

### 4. Run

```bash
claude  # or: claude --model haiku
```

Then say:

```
列出微信聊天        # list chats
回复 Kent           # read context and compose a reply
给工作群回复 收到    # reply to a group with specific content
```

## How It Works

```
Claude Code  ─→  SKILL.md (trigger + workflow rules)
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

## Limitations

- **macOS only** — depends on Vision Framework and AppleScript
- **Single instance** — one WeChat operation at a time (file lock enforced)
- **Text-only replies** — no images, stickers, or files
- **OCR dependent** — accuracy varies with font size and window layout
- **No WeChat API** — purely visual automation

## License

[Apache-2.0](LICENSE)
