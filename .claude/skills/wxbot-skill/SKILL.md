---
name: wxbot-skill
description: "当用户提到微信、WeChat、回复消息、查看聊天、发消息给某人、群聊、回复群、给某个群回复、操作联系人、或任何涉及聊天消息自动化的任务时使用此技能。触发关键词包括但不限于：微信、群、群聊、聊天、回复、发送、消息、WeChat。即使用户没有明确说'微信'二字，只要涉及给人或群发消息、回复消息，都应触发此技能。"
argument-hint: chat list | chat read <name> | chat reply <name> "<msg>"
allowed-tools: [Bash, Read]
---

# WeChat 自动化技能

通过本地 OCR + pyautogui 控制 WeChat 桌面应用。所有截图识别在本机完成，不调用任何远端 API。

## 脚本路径

```
.claude/skills/wxbot-skill/scripts/wechat.py
```

## MVP 命令

### 列出可见聊天
```bash
python3 .claude/skills/wxbot-skill/scripts/wechat.py chat list
```
输出: `[OK] 8 chats: Kent | 工作群 | 妈妈 | ...`

### 读取聊天上下文
```bash
python3 .claude/skills/wxbot-skill/scripts/wechat.py chat read <name>
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
python3 .claude/skills/wxbot-skill/scripts/wechat.py chat reply <name> "<message>"
```
脚本根据 `config.json` 中的 `auto_send` 设置自动决定是否发送（默认不发送，只输入到输入框）。
输出: `[OK] Sent to Kent: [AI分身] 好的，几点出发？`
或: `[OK] Typed to Kent (未发送，请在微信中确认后手动按回车): [AI分身] 好的，几点出发？`

## 执行模式（重要）

**`chat read` 和 `chat reply` 必须用 Bash 工具的 `run_in_background: true` 参数运行**，因为脚本通过 pyautogui 控制键盘鼠标，前台运行时会干扰终端。

**严禁使用 shell `&` 后台**（如 `cmd &`）——这会导致无法跟踪进程状态，容易因为误判"没输出"而重复执行，造成文字被输入两次。**每条命令只执行一次，绝不重试。**

```bash
# chat list 较快（~2s），可以前台运行
python3 .claude/skills/wxbot-skill/scripts/wechat.py chat list

# chat read 和 chat reply：用 run_in_background: true，不需要重定向
# run_in_background 会自动捕获输出，完成后直接显示结果
python3 .claude/skills/wxbot-skill/scripts/wechat.py chat read Kent
python3 .claude/skills/wxbot-skill/scripts/wechat.py chat reply Kent "内容"
```

## 标准工作流（回复某人）

当用户说「回复 Kent」「给情怀新群回复」「按上下文回复」等，**不要反问用户要回复什么**，而是：

### Step 1: 读取上下文（后台运行，run_in_background: true）
```bash
python3 .claude/skills/wxbot-skill/scripts/wechat.py chat read Kent
```
等待后台任务完成，输出会自动返回。

### Step 2: 根据聊天上下文，自行分析并拟写回复内容

### Step 3: 发送回复（后台运行，run_in_background: true）
```bash
python3 .claude/skills/wxbot-skill/scripts/wechat.py chat reply Kent "拟写的回复内容"
```
等待后台任务完成，输出会自动返回。脚本会根据 `config.json` 自动决定是直接发送还是只输入到输入框。

## 多聊天处理顺序（重要）

当需要处理多个聊天时，必须逐个完成——先读取并回复一个聊天，再处理下一个。

正确: read A → reply A → read B → reply B
错误: read A → read B → reply A → reply B

原因：每次 read/reply 都会切换 WeChat 窗口状态，批量读取后窗口已切换，上下文会丢失。

## 回复规则

1. **必须先 read 再 reply** — 未读上下文不得盲目回复
2. **默认按上下文自行拟写回复** — 用户说「回复某人」时，不要反问「要回复什么」，应读完上下文后自行拟写
3. **前缀自动添加** — 所有回复由脚本根据 config.json 中的 `reply_prefix` 自动加前缀，Claude 不需要写
4. **保守原则** — 回复简短、礼貌、不承诺、不透露隐私
5. **纯文字回复** — 不使用 emoji、不发图片/微信表情包/文件
6. **不确定时必须确认** — 输出 `[需要确认]: 请问您希望如何回复 <name>？` 并等待用户指示

## 回复前必须检查（重要）

**在拟写回复之前，必须逐条检查以下条件。任何一条不满足，就不要回复，改为输出 `[需要确认]`。**

1. **对话是否活跃？** — 如果最后几条消息是表情、`[表情]`、`6`、`666`、`%~` 等结束性内容，说明话题已结束，不要强行接话
2. **是否有明确的回复点？** — 对方是否在提问、@你、或等待回应？如果没有，不要主动插话
3. **回复内容是否与最新话题直接相关？** — 不要回复已经过去的旧话题，只回复当前正在讨论的内容
4. **群聊中是否适合以 AI 分身身份发言？** — 在技术讨论群中用 `[AI分身]` 前缀发言需要谨慎，除非用户明确指定了回复内容
5. **是否在编造信息？** — 不要生成你不确定的技术建议、工具推荐、事实性陈述

**宁可多问一次用户，也不要发出一条不恰当的消息。发出去的消息无法撤回。**

## 错误处理

所有错误输出 `[ERR] 一行描述`。常见情况：
- `[ERR] 找不到聊天 "xxx"` → 检查名称拼写，或 WeChat 未在前台
- `[ERR] 无法激活 WeChat` → 手动打开 WeChat 后重试

