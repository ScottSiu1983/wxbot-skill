---
name: wechat-bot
description: "当用户提到微信、WeChat、回复消息、查看聊天、发消息给某人、群聊、回复群、给某个群回复、操作联系人、或任何涉及聊天消息自动化的任务时使用此技能。触发关键词包括但不限于：微信、群、群聊、聊天、回复、发送、消息、WeChat。即使用户没有明确说'微信'二字，只要涉及给人或群发消息、回复消息，都应触发此技能。"
argument-hint: chat list | chat read <name> | chat reply <name> "<msg>"
allowed-tools: [Bash, Read]
---

> **配置文件**: `.claude/skills/wechat-bot/config.json`
> - `auto_send`: 是否自动发送回复（默认 `false`，需用户确认后才发送）

# WeChat 自动化技能

通过本地 OCR + pyautogui 控制 WeChat 桌面应用。所有截图识别在本机完成，不调用任何远端 API。

## 脚本路径

```
.claude/skills/wechat-bot/scripts/wechat.py
```

## MVP 命令

### 列出可见聊天
```bash
python3 .claude/skills/wechat-bot/scripts/wechat.py chat list
```
输出: `[OK] 8 chats: Kent | 工作群 | 妈妈 | ...`

### 读取聊天上下文
```bash
python3 .claude/skills/wechat-bot/scripts/wechat.py chat read <name>
```
输出示例:
```
[OK] Kent (5 msgs):
  them: 宵夜在此
  me: 这个不错啊！卜卜蚬好吃的...
  them: 晚上一起去？
```

### 回复聊天
```bash
# 输入并发送
python3 .claude/skills/wechat-bot/scripts/wechat.py chat reply <name> "<message>"
# 只输入到输入框，不发送（用户自行在微信按回车）
python3 .claude/skills/wechat-bot/scripts/wechat.py chat reply <name> "<message>" --no-send
```
输出: `[OK] Sent to Kent: [Scott的AI分身] 好的，几点出发？`
或: `[OK] Typed to Kent (未发送，请在微信中确认后手动按回车): [Scott的AI分身] 好的，几点出发？`

## 执行模式（重要）

**`chat read` 和 `chat reply` 必须用 Bash 工具的 `run_in_background: true` 参数运行**，因为脚本通过 pyautogui 控制键盘鼠标，前台运行时会干扰终端。

**严禁使用 shell `&` 后台**（如 `cmd &`）——这会导致无法跟踪进程状态，容易因为误判"没输出"而重复执行，造成文字被输入两次。**每条命令只执行一次，绝不重试。**

```bash
# chat list 较快（~2s），可以前台运行
python3 .claude/skills/wechat-bot/scripts/wechat.py chat list

# chat read 和 chat reply：用 run_in_background: true，输出重定向到文件
python3 .claude/skills/wechat-bot/scripts/wechat.py chat read Kent > /tmp/wechat_output.txt 2>&1
python3 .claude/skills/wechat-bot/scripts/wechat.py chat reply Kent "内容" > /tmp/wechat_output.txt 2>&1
# 等 run_in_background 通知完成后，再用 Read 读取 /tmp/wechat_output.txt
```

## 标准工作流（回复某人）

当用户说「回复 Kent」「给情怀新群回复」「按上下文回复」等，**不要反问用户要回复什么**，而是：

### Step 1: 读取上下文（后台运行）
```bash
python3 .claude/skills/wechat-bot/scripts/wechat.py chat read Kent > /tmp/wechat_output.txt 2>&1
```
完成后 `Read /tmp/wechat_output.txt`

### Step 2: 根据聊天上下文，自行分析并拟写回复内容

### Step 3: 检查 config.json 中的 `auto_send` 配置

用 Read 工具读取 `.claude/skills/wechat-bot/config.json`（不要用 cat，避免触发 Bash 权限确认）。

- **`auto_send: true`** → 直接发送：
  ```bash
  python3 .claude/skills/wechat-bot/scripts/wechat.py chat reply Kent "拟写的回复内容" > /tmp/wechat_output.txt 2>&1
  ```
- **`auto_send: false`**（默认）→ 只输入到微信输入框，不发送，用户在微信中确认后自行按回车：
  ```bash
  python3 .claude/skills/wechat-bot/scripts/wechat.py chat reply Kent "拟写的回复内容" --no-send > /tmp/wechat_output.txt 2>&1
  ```

完成后 `Read /tmp/wechat_output.txt`

## 多聊天处理顺序（重要）

当需要处理多个聊天时，必须逐个完成——先读取并回复一个聊天，再处理下一个。

正确: read A → reply A → read B → reply B
错误: read A → read B → reply A → reply B

原因：每次 read/reply 都会切换 WeChat 窗口状态，批量读取后窗口已切换，上下文会丢失。

## 回复规则

1. **必须先 read 再 reply** — 未读上下文不得盲目回复
2. **默认按上下文自行拟写回复** — 用户说「回复某人」时，不要反问「要回复什么」，应读完上下文后自行拟写
3. **前缀自动添加** — 所有回复由脚本自动加上 `[Scott的AI分身] `，Claude 不需要写
4. **保守原则** — 回复简短、礼貌、不承诺、不透露隐私
5. **纯文字回复** — 不使用 emoji、不发图片/微信表情包/文件
6. **不确定时** — 输出 `[需要确认]: 请问您希望如何回复 Kent？`

## 错误处理

所有错误输出 `[ERR] 一行描述`。常见情况：
- `[ERR] 找不到聊天 "xxx"` → 检查名称拼写，或 WeChat 未在前台
- `[ERR] 无法激活 WeChat` → 手动打开 WeChat 后重试

## 未来命令（已预留，尚未实现）

```bash
python3 wechat.py moments comment <content>      # 朋友圈评论
python3 wechat.py contacts tag <name> <tag>      # 添加标签
python3 wechat.py contacts approve               # 通过好友申请
python3 wechat.py contacts add <phone_or_id>     # 添加好友
```
