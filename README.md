# wechat-bot-skill

A [Claude Code](https://docs.anthropic.com/en/docs/claude-code) skill that automates WeChat desktop on macOS through local OCR and keyboard/mouse simulation. All text recognition runs on-device via Apple Vision Framework — no data leaves your machine.

## Features

- **Chat List** — List all visible conversations
- **Chat Read** — Navigate to any chat and extract message history with sender attribution
- **Chat Reply** — Send contextual replies with automatic prefix tagging
- **Group Chat Support** — Detects groups, identifies per-message senders by visual layout
- **Visual Detection** — Classifies images, stickers, and emoji in conversations
- **Haiku-Friendly** — Optimized SKILL.md instructions for cost-efficient operation with Claude Haiku

## Requirements

- macOS 13+ (Vision Framework, AppleScript)
- Python 3.10+
- WeChat for Mac
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI

### macOS Permissions

Grant these in **System Settings > Privacy & Security**:

- **Accessibility** — Terminal / IDE (for pyautogui mouse/keyboard control)
- **Screen Recording** — Terminal / IDE (for screencapture)

## Quick Start

### 1. Clone and install dependencies

```bash
git clone https://github.com/nicksiu/wechat-bot-skill.git
cd wechat-bot-skill
pip install -r requirements.txt
```

### 2. Configure permissions

Create `.claude/settings.local.json` (not tracked by git):

```json
{
  "permissions": {
    "allow": [
      "Bash(python3:*)",
      "Skill(wechat-bot)"
    ]
  }
}
```

### 3. Customize (optional)

Edit `.claude/skills/wechat-bot/config.json`:

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

- `列出微信聊天` — list chats
- `回复 Kent` — read context and compose a reply
- `给工作群回复 收到` — reply with specific content

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

MIT
