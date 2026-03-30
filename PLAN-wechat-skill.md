# WeChat Skill — 通用微信自动化技能

## Context

前一阶段完成了 Computer Use MVP：用 `local_vision.py`（macOS Vision OCR, ~280ms）+ `computer_use.py`（pyautogui 动作）+ Claude Code 编排，成功在 WeChat 中回复了 Kent。

**但存在两个问题：**
1. **Token 浪费严重**：一次简单回复需 10+ 个 tool call，每次 Claude 都要处理大量 OCR JSON（~5000 chars），决定下一步操作
2. **不可复用**：每次都需手动编排步骤

**解决方案：** 创建一个 Claude Code Skill，将所有 WeChat 操作封装到 `wechat.py` 脚本中自主执行，Claude 只需看极简文字摘要。

**Token 优化效果对比：**

| 操作 | 改造前 | 改造后 |
|------|--------|--------|
| 读取 Kent 的聊天 | ~10 tool calls, ~5000 chars OCR JSON | **1 tool call, ~200 chars 摘要** |
| 回复一条消息 | ~10 tool calls, 多次截图分析 | **1 tool call, ~50 chars 确认** |
| 完整"读+回复"流程 | ~20 tool calls | **2-3 tool calls** |

---

## 文件结构

```
ComputerUse/
├── local_vision.py                     # 已有 — OCR 模块（不修改）
├── computer_use.py                     # 已有 — 动作执行器（不修改）
├── CLAUDE.md                           # 已有 — 保留通用指南
└── .claude/skills/wechat/
    ├── SKILL.md                        # 新建 — 技能定义
    ├── scripts/
    │   └── wechat.py                   # 新建 — 核心：统一 WeChat CLI (~350行)
    └── references/
        └── wechat-layout.md            # 新建 — WeChat UI 布局参考
```

---

## 1. `SKILL.md` — 技能定义

```yaml
---
name: wechat
description: "当用户提到回复微信、查看微信消息、给某人发微信、或任何微信自动化任务时使用。"
argument-hint: chat read <name> | chat reply <name> "<msg>" | chat list
allowed-tools: [Bash, Read]
---
```

正文包含：
- 3 个 MVP 命令的精确调用语法
- 标准工作流（读→分析→回复 = 2 步）
- 回复规则：自动前缀 `[Scott的AI分身]`，纯文字，保守回复
- 错误格式：`[ERR] 一行描述`
- 未来命令占位（moments、contacts）

---

## 2. `wechat.py` — 核心脚本

### CLI 接口（面向 Claude 的最终输出）

```bash
# 列出可见聊天
python3 .claude/skills/wechat/scripts/wechat.py chat list
# → [OK] 8 chats: Kent | 工作群 | 妈妈 | ...       (~100 chars)

# 读取对话上下文
python3 .claude/skills/wechat/scripts/wechat.py chat read Kent
# → [OK] Kent (5 msgs):                             (~200 chars)
#   them: 宵夜在此 [图片]
#   me: 这个不错啊！卜卜蚬好吃的...
#   them: 晚上一起去？
#   [last: 14:50]

# 回复（自动前缀 [Scott的AI分身]）
python3 .claude/skills/wechat/scripts/wechat.py chat reply Kent "好的，几点出发？"
# → [OK] Sent to Kent: [Scott的AI分身] 好的，几点出发？  (~60 chars)
```

### 类结构

```python
class WeChatController:
    REPLY_PREFIX = "[Scott的AI分身] "

    # ── 私有方法（自主导航，不输出到 Claude） ──────────
    _activate_wechat() -> bool          # AppleScript 激活
    _get_window_rect() -> (x,y,w,h)    # 获取窗口位置
    _navigate_to_chat(name) -> bool     # 核心导航逻辑（3步重试）
    _read_content_area() -> list[dict]  # OCR 内容区域
    _parse_messages(ocr) -> list[dict]  # 解析消息（左=对方/右=我）
    _summarize(msgs) -> str             # 压缩为极简文本
    _click_input_box() -> bool          # 定位输入框
    _type_and_send(text) -> bool        # 输入+发送

    # ── 公开方法（输出精简文本给 Claude） ─────────────
    chat_list() -> str                  # "[OK] 8 chats: ..."
    chat_read(name) -> str              # "[OK] Kent (5 msgs): ..."
    chat_reply(name, msg) -> str        # "[OK] Sent to Kent: ..."
```

### 导航策略 `_navigate_to_chat(name)`

```
Step 1: _activate_wechat()
Step 2: _get_window_rect() → 动态获取窗口坐标
Step 3: find_text(name, region=chat_list_area) → 在聊天列表直接查找
  ├── 找到 → click(x, y) → 等待 0.5s → 验证标题
  └── 没找到 → Step 4
Step 4: Cmd+F 搜索 → type(name) → 等 0.5s → find_text(name) → click
Step 5: 验证：OCR 内容区标题是否包含 name
         最多重试 3 次
```

### 对话解析 `_parse_messages(ocr_items)`

```
1. 按 Y 坐标排序（从上到下 = 时间顺序）
2. 过滤掉 UI 噪音：时间戳（HH:MM）、"发送"、系统通知
3. 按 X 位置分类：
   - x < 内容区中线 → sender="them"（对方发的，左对齐）
   - x >= 内容区中线 → sender="me"（我发的，右对齐）
4. 截取最近 10 条消息
5. 每条消息截断到 80 字符
```

### Token 优化机制

| 层面 | 策略 |
|------|------|
| **OCR 结果** | 在 wechat.py 内部消化，只返回文本摘要 |
| **导航过程** | 完全在脚本内部完成，不暴露中间状态 |
| **错误处理** | 统一 `[ERR] 一行` / `[OK] 简要结果` |
| **消息格式** | `them: 文字` / `me: 文字`，一行一条 |
| **截断** | 单条 ≤80 字符，最多 10 条，总输出 ≤300 chars |
| **二进制内容** | 图片/表情标记为 `[图片]` / `[表情]`，不传任何图片数据 |

---

## 3. `wechat-layout.md` — UI 布局参考

- 屏幕：1470×956 逻辑，2940×1912 物理（2x Retina）
- WeChat 窗口位置：通过 AppleScript 动态获取（不硬编码）
- WeChat 布局（相对窗口左上角的偏移）：
  - 图标侧栏：0~60px
  - 聊天列表：60~280px
  - 内容区域：280px~末尾
- 输入框定位：OCR 查找"发送"按钮 → 其左侧为输入框
- 已知过滤词：时间戳模式、"发送"、"[链接]"、系统通知文字

---

## 4. 可扩展性设计

MVP 只实现 `chat` 子命令组。未来在 `wechat.py` 中增加子命令组即可：

```bash
# MVP（本次实现）
wechat.py chat list / read / reply

# 未来扩展（仅预留代码结构）
wechat.py moments comment <content>      # 朋友圈评论
wechat.py contacts tag <name> <tag>      # 添加标签
wechat.py contacts approve               # 通过好友申请
wechat.py contacts add <phone_or_id>     # 添加好友
```

CLI 架构用 argparse 二级子命令，新增功能只需添加 subparser + 方法。

---

## 5. 回复安全规则（硬编码）

1. **前缀**：所有回复自动加 `[Scott的AI分身] `，写死在 `REPLY_PREFIX` 常量中
2. **上下文检查**：`chat_reply()` 内部先调用 `chat_read()` 读取对话（但不暴露给 Claude，仅做内部验证用）
3. **纯文字**：只支持 `type_text()` 发送文字，不支持图片/表情/文件
4. **Claude 决策权**：Claude 根据 `chat read` 的返回摘要决定回复内容，wechat.py 不自主生成内容

---

## 6. 验证计划

```bash
# 1. 单独测试 chat list
python3 .claude/skills/wechat/scripts/wechat.py chat list
# 期望：[OK] N chats: 名称1 | 名称2 | ...

# 2. 测试 chat read
python3 .claude/skills/wechat/scripts/wechat.py chat read Kent
# 期望：[OK] Kent (N msgs): them: xxx / me: xxx ...

# 3. 测试 chat reply（用安全消息）
python3 .claude/skills/wechat/scripts/wechat.py chat reply Kent "测试消息，请忽略"
# 期望：[OK] Sent to Kent: [Scott的AI分身] 测试消息，请忽略

# 4. 端到端：在 Claude Code 中输入 "/wechat chat read Kent"
# 期望：Claude 用一个 Bash tool call 完成，返回精简摘要

# 5. Token 对比验证：对比改造前后同一任务的 token 消耗
```

---

## 实现顺序

| 步骤 | 文件 | 内容 |
|------|------|------|
| 1 | `.claude/skills/wechat/scripts/wechat.py` | WeChatController 类骨架 + CLI |
| 2 | 同上 | `_activate_wechat` + `_get_window_rect` |
| 3 | 同上 | `_navigate_to_chat` 核心导航 |
| 4 | 同上 | `_parse_messages` + `_summarize` + `chat_read` |
| 5 | 同上 | `chat_list` |
| 6 | 同上 | `_click_input_box` + `_type_and_send` + `chat_reply` |
| 7 | `.claude/skills/wechat/SKILL.md` | 技能定义 |
| 8 | `.claude/skills/wechat/references/wechat-layout.md` | 布局参考 |
| 9 | 验证 | 逐个命令测试 + 端到端 |
