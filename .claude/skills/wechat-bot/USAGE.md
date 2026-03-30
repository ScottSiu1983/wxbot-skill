# Usage Guide

## Quick Start

All commands use the same entry point:

```bash
python3 .claude/skills/wechat-bot/scripts/wechat.py <module> <command> [args]
```

## Commands

### `chat list`

List all visible chats in the WeChat sidebar.

```bash
python3 .claude/skills/wechat-bot/scripts/wechat.py chat list
```

**Output:**
```
[OK] 8 chats: Kent | 工作群 | 妈妈 | CDF-AI | 萧Scott | 数据库先进工作者 | ThinkInAI | 情怀新群
```

- Runtime: ~2s
- Can run in foreground

---

### `chat read <name>`

Navigate to a chat and read recent messages.

```bash
python3 .claude/skills/wechat-bot/scripts/wechat.py chat read "Kent" > /tmp/wechat_output.txt 2>&1
```

**Output:**
```
[OK] Kent (5 msgs):
  them: 宵夜在此
  me: 这个不错啊！卜卜蚬好吃的...
  them: 晚上一起去？
  me: [Scott的AI分身] 好的，几点出发？
  them: 8点老地方见
```

- Runtime: ~5–15s (depends on navigation + group scroll)
- **Must run in background** (`run_in_background: true`)
- Redirect stdout to file, then read with `Read` tool

**Group chat behavior:**
1. First OCR at current position (captures latest messages)
2. Scroll up 3 pages, second OCR (captures older context)
3. Merge + deduplicate → chronological order
4. Sender attribution via nickname detection (font size + position near avatar)

**1:1 chat behavior:**
1. Single OCR at current position
2. If < 5 messages, auto-scrolls up for more context

---

### `chat reply <name> "<message>"`

Send a reply to a specific chat.

```bash
python3 .claude/skills/wechat-bot/scripts/wechat.py chat reply "Kent" "好的，几点出发？" > /tmp/wechat_output.txt 2>&1
```

**Output:**
```
[OK] Sent to Kent: [Scott的AI分身] 好的，几点出发？
```

- Runtime: ~5–10s
- **Must run in background** (`run_in_background: true`)
- The prefix `[Scott的AI分身] ` is added automatically — do not include it in the message
- Supports emoji: `"好的 👍"` ✓
- Does not support images, WeChat stickers, or file attachments

---

## Execution Modes

### Foreground (chat list only)

```bash
python3 .claude/skills/wechat-bot/scripts/wechat.py chat list
```

### Background (chat read / chat reply)

These commands control the mouse and keyboard. Running them in the foreground will interfere with the Claude Code terminal.

**Pattern:**
```bash
# Step 1: Run in background, redirect output
python3 .claude/skills/wechat-bot/scripts/wechat.py chat read "Kent" > /tmp/wechat_output.txt 2>&1
# (use run_in_background: true in Bash tool)

# Step 2: After completion, read the result
Read /tmp/wechat_output.txt
```

---

## Multi-Chat Workflow

When processing multiple chats, always complete one before starting the next:

```
✅ Correct: read A → reply A → read B → reply B
❌ Wrong:   read A → read B → reply A → reply B
```

Each `read` / `reply` changes the WeChat window state. Batching reads will cause context to be lost when replying.

---

## Reply Guidelines

| Rule | Description |
|------|-------------|
| Read first | Always `chat read` before `chat reply` — never reply blind |
| Prefix auto-added | Script prepends `[Scott的AI分身] ` — Claude should not include it |
| Conservative | Keep replies short, polite; don't make commitments or disclose private info |
| Emoji OK | Use emoji sparingly for natural tone (e.g., 👍😄🤝); no WeChat stickers |
| When uncertain | Output `[需要确认]: 请问您希望如何回复 <name>？` and let the user decide |

---

## Error Handling

All errors follow the format `[ERR] description`.

| Error | Cause | Fix |
|-------|-------|-----|
| `找不到聊天 "xxx"` | Name mismatch or WeChat not in foreground | Check spelling; ensure WeChat is open |
| `无法激活 WeChat` | WeChat not running | Open WeChat manually |
| `获取窗口位置失败` | Window minimized or off-screen | Restore the WeChat window |
| `消息可能未发送成功` | Verification failed after sending | Check WeChat manually |
| `PyAutoGUI fail-safe` | Mouse hit screen corner | Normal safety trigger; retry the command |

---

## Debugging

Each run creates a timestamped directory under `debug/`:

```
debug/20260329_223534_chat_read/
├── log.txt                          # Full execution timeline
├── 01_nav_attempt1_before.png       # Before navigation
├── 02_nav_attempt1_search_results.png
├── 03_nav_attempt1_after_search_click.png
├── 04_group_bottom_before_ocr.png   # Bottom OCR (recent msgs)
├── 05_read_content_area.png         # Content area screenshot
├── 06_after_group_scroll_up.png     # After scrolling up
└── 07_read_content_area.png         # Top OCR (older context)
```

**Log format:**
```
[HH:MM:SS.ms] T=total_s +delta_s | message
```

Only the 10 most recent runs are kept; older directories are auto-cleaned.

---

## Supported Chat Name Formats

| Format | Example | Notes |
|--------|---------|-------|
| Chinese name | `"萧Scott"` | Mixed scripts OK |
| English name | `"Kent"` | Case-insensitive matching |
| Group name | `"CDF-AI"` | Partial match supported |
| Long group name | `"博客园终身会员总群"` | Prefix matching handles window truncation |
| Name with brackets | `"[净]数据库先进工作者"` | Brackets auto-stripped during matching |

---

## Placeholder Commands (Not Yet Implemented)

```bash
python3 wechat.py moments comment <content>    # Moments comment
python3 wechat.py contacts tag <name> <tag>    # Add contact tag
python3 wechat.py contacts approve             # Accept friend request
python3 wechat.py contacts add <phone_or_id>   # Add contact
```

These commands are defined but return `[ERR] ... 尚未实现`.
