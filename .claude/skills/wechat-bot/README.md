# WeChat Desktop Automation Skill

A Claude Code skill that automates WeChat desktop (macOS) through local OCR and keyboard/mouse simulation. All text recognition runs on-device via Apple Vision Framework — no data leaves your machine.

## Features

- **Chat List** — List all visible conversations in the sidebar
- **Chat Read** — Navigate to any chat and extract message history with sender attribution
- **Chat Reply** — Send contextual replies with automatic prefix tagging
- **Group Chat Support** — Detects group chats, identifies per-message senders by visual layout
- **Visual Detection** — Classifies images, stickers, and emoji in conversations
- **Debug Logging** — Timestamped logs + screenshots for every operation

## Requirements

| Dependency | Purpose |
|-----------|---------|
| macOS 13+ | Vision Framework OCR, AppleScript |
| Python 3.10+ | Runtime |
| WeChat for Mac | Target application |
| pyautogui | Mouse / keyboard control |
| pyobjc | macOS framework bindings (Vision, Quartz) |
| numpy | Image array operations |
| Pillow | Image cropping for region OCR |

### macOS Permissions

Grant these in **System Settings > Privacy & Security**:

- **Accessibility** — Terminal / IDE (for pyautogui)
- **Screen Recording** — Terminal / IDE (for screencapture)

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Claude Code                        │
│              (interprets user intent)                │
├─────────────────────────────────────────────────────┤
│                  SKILL.md                            │
│         (trigger rules, reply guidelines)            │
├─────────────────────────────────────────────────────┤
│               wechat.py CLI                          │
│        chat list | chat read | chat reply            │
├──────────┬──────────────┬───────────────────────────┤
│ local_vision.py         │  computer_use.py           │
│ (Vision OCR)            │  (pyautogui wrapper)       │
├──────────┴──────────────┴───────────────────────────┤
│  macOS: Vision · Quartz · AppleScript · screencapture│
└─────────────────────────────────────────────────────┘
```

### Processing Pipelines

**Read Pipeline:**
1. Activate WeChat via AppleScript
2. Verify target chat is open (title bar OCR) or navigate via search
3. Screenshot content area → Vision OCR → structured messages
4. For groups: dual-pass OCR (bottom + scroll-up) with dedup
5. Detect visual elements (images/emoji) via pixel classification
6. Return formatted summary with sender labels

**Reply Pipeline:**
1. Navigate to target chat (reuses read pipeline's navigation)
2. Locate input box via "Send" button position
3. Type message character-by-character via CGEvent Unicode injection
4. Press Enter → verify message appears in conversation

## Project Structure

```
.claude/skills/wechat-bot/
├── README.md              # This file
├── USAGE.md               # Detailed usage guide
├── SKILL.md               # Claude Code skill definition
├── scripts/
│   └── wechat.py          # Main CLI (1377 lines)
├── references/
│   └── wechat-layout.md   # WeChat UI layout reference
└── debug/                 # Auto-generated (last 10 runs)
    └── {timestamp}_{cmd}/
        ├── log.txt        # Execution timeline
        └── *.png          # Step screenshots
```

**Sibling dependencies** (in project root):

```
ComputerUse/
├── local_vision.py        # Vision Framework OCR wrapper
├── computer_use.py        # pyautogui wrapper
└── CLAUDE.md              # Project-level instructions
```

## Configuration

Key constants in `wechat.py`:

```python
REPLY_PREFIX = "[Scott的AI分身] "  # Auto-prepended to all replies
SIDEBAR_W   = 60                   # WeChat left icon bar width (px)
SETTLE      = 0.35                 # UI stabilization delay (s)
MAX_RETRIES = 3                    # Navigation retry attempts
```

## Limitations

- **macOS only** — depends on Vision Framework and AppleScript
- **Single instance** — one WeChat operation at a time (sequential processing)
- **OCR accuracy** — fast mode (~0.3s) trades accuracy for speed; accurate mode (~1s) is slower but reliable for Chinese text
- **Window size dependent** — long group names may be truncated in narrow windows
- **No API access** — purely visual automation; no WeChat internal API

## License

Private skill — not for redistribution.
