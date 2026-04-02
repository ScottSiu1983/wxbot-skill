# wxbot-skill 程序流程说明

本文档详细说明 wxbot-skill 的系统架构、基于像素的窗口分析、Retina 缩放处理、多模态消息解析及交互哲学。

---

## 1. 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        wechat.py                                │
│                     (主控制器 ~600 行)                            │
├─────────────────────────────────────────────────────────────────┤
│  WeChatController                                               │
│  ├── chat_list()           → 获取当前聊天列表                   │
│  ├── chat_read()           → 读取聊天内容 (含滚动与去重)        │
│  ├── chat_reply()          → 发送回复 (带 auto_send 控制及 Quartz 事件)│
│  │                                                              │
│  ├── _detect_absolute_layout() → 核心：基于结构化锚点的动态布局分析 │
│  ├── _parse_messages()      → 核心：多模态消息、头像锚点与引用解析  │
│  └── _navigate_to_chat()    → 鲁棒导航 (Section Header + OCR 验证) │
├─────────────────────────────────────────────────────────────────┤
│  local_vision.py          │  computer_use.py                    │
│  (Vision OCR & 视觉工具)   │  (Quartz & 仿真互动)                │
│  ├── find_text()          │  ├── click()                        │
│  ├── get_screen_text()    │  ├── type_text() (Burst Typing 爆发式键入)│
│  └── take_screenshot()    │  ├── press_key() (Quartz底层注入)    │
│                           │  └── smooth_scroll() (CGEvent 像素卷动)│
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. 窗口布局分析 (像素级探测)

目前的系统弃用了固定的比例估算，转而采用基于像素颜色突变的动态探测。

### 2.1 Retina 缩放适配 (L2P/P2L)

WeChat 窗口在 macOS 上会受 Retina 缩放影响。系统在 `_detect_absolute_layout` 中动态计算 `scale`：
- **L (Logic)**: 逻辑像素，通过 AppleScript 获取，用于坐标控制。
- **P (Physical)**: 物理像素，实际截图中的像素大小。
- **转换公式**: `scale = img_width / screenshot_width`。

### 2.2 核心算法：结构化分界探测 (Structural Anchors)

系统通过扫描截图数组中的 RGB 突变来锁定分界线，不再依赖比例硬编码：

#### 2.2.1 纵向泳道分界 (v_line_x)
- **扫描逻辑**: 在窗口中间选取 `1/4`, `1/2`, `3/4` 三个 Y 轴高度作为采样点 (`scan_y_samples`)。
- **算法**: 从窗口中心向右偏移，寻找颜色差异 `np.sum(abs(curr - left)) > 15` 的点。
- **垂直校验**: 要求物理像素上至少 70% 的点在同一垂直线上产生突变，方可认定为 `v_divide_x`。
- **含义**: 该线区分了左侧的“聊天列表/搜索结果”与右侧的“消息内容区”。

#### 2.2.2 横向泳道分界 (h_lines)
- **扫描逻辑**: 在内容泳道（v_line_x 右侧）选取 X 轴采样点。
- **算法**: 向上扫描 Y 轴，寻找背景色从内容区（常为白色）切换到非内容区（标题栏/输入区）的突变点。
- **含义**: 解析出内容区起始（bt）与结束（bb）坐标，避开顶部标题栏和底部输入框。

### 2.3 区域逻辑判定 (Area Logic)

在识别出所有可能的 `h_lines` 后，系统通过以下策略优选消息区域：
1. **高度筛选**: 间隙 (`gap`) 必须大于 150 物理像素。
2. **颜色特征评分**: 对间隙中心块采样 `avg_color`。
    - 消息流区域通常背景较浅（接近 255 白色）。
    - 输入区通常呈浅灰色。
3. **锁定**: `score = gap * (1 if avg_color > 230 else 0.5)`。最高得分区域被定义为 `message_flow`。

### 2.4 布局字典 (Layout Context)

```python
layout = {
    'v_divide_x': v_line_x,          # 内容区起点
    'title_bar': (wy, bt),           # 顶部标题栏
    'message_flow': (bt + 1, bb - 2), # 消息流安全区域
    'input_box': (bb, wy + wh)       # 输入区
}
```

---

## 3. 命令流程详解

### 3.1 `chat read` — 读取聊天内容 (增强版)

为了捕捉完整的对话背景，系统执行“主动回溯”策略：

1. **当前快照**: 在初始位置执行 OCR 与视觉元素分析。
2. **向上回溯**: 
    - 执行两次 `_scroll_content_area(dir="up")`。
    - 每次滚动位移为消息流区域高度的 90% (0.9)，以确保重叠度。
    - 每次滚动后等待 1.0s (`SETTLE`) 以消除 UI 抖动。
3. **合并与去重**:
    - 将三次快照的消息按 `(sender, text)` 进行全局去重。
    - 重新按垂直坐标 (`_y`) 进行时间线排序。

### 3.2 `chat reply` — 回复链控制

1. **配置读取**: 获取 `auto_send` (默认 False) 和 `reply_prefix` (如 `[AI分身] `)。
2. **输入框对齐**: 
    - 系统点击 `(ww-25, wh-25)` 激活输入区。
    - 执行 `_cu.type_text()` 进行仿真键入。
3. **发送控制**: 
    - 仅当 `auto_send` 为 `True` 时执行 `press_key("enter")`。
    - 否则保留在输入框中等待人类确认。

---

## 4. 导航流程 (`_navigate_to_chat`)

### 4.1 搜索结果索引策略 (Section Header Navigation)

在 v0.2-beta 中，导航逻辑恢复了基于 UI 分区的精确定位：

1. **一键搜索**: 激活搜索框并粘贴名称。
2. **分区索引 (Sectioning)**:
    - 快速识别搜索结果中的分类标题：`联系人`、`群聊`、`聊天记录`。
    - 构建各分区的 Y 轴范围映射表 `section_ranges`。
3. **优先级匹配**:
    - 优先在 `联系人` 分区查找第一个文本匹配项。
    - 若未命中，则在 `群聊` 分区查找。
    - 支持去除 `[净]` 等群前缀后进行模糊匹配。
4. **安全验证**: 强制执行 `_verify_chat_open()`，确保最终停留在正确的对话界面。

---

## 5. 验证流程 (`_verify_chat_open`)

### 5.1 标题栏比对逻辑

系统通过 OCR 扫描顶部 `title_bar` 区域：
- **判定准则**: 如果识别到的文本包含 `name` 的子集，或长度超过 4 位的开头部分匹配，则判定为成功。
- **坐标修正**: 扫描起点必须为 `wx + SIDEBAR_W` (60px)，以避开侧栏干扰。

---

## 6. 消息解析流程 (`_parse_messages`)

### 6.1 视觉元素检测 (连通域分析)

这是系统最复杂的模块，通过像素级分析识别非文本内容：

1. **背景掩码 (Masking)**:
    - 采集内容区角点颜色作为背景。
    - 计算全图色差，生成 `diff > 15` 的二值掩码图。
    - **OCR 挖孔**: 按照识别出的文字坐标在掩码中“挖孔”，排除文字干扰。
2. **洪水填充 (Flood Fill)**:
    - 对掩码剩余区域进行 4 连通域种子填充。
    - 提取每一个独立物体的边界框 (bx, by, bw, bh)。
3. **对象分类器**:
    - **头像 (Avatars)**: 满足 `30 < w < 55` 且 `abs(w-h) < 10` 的正方形区域。
    - **图片 (Images)**: 连通域色彩方差 `std > 20` 且 `w > 80`。
    - **表情 (Stickers)**: 连通域色彩方差 `std > 20` 且 `w < 80`。

### 6.2 引用消息 (Quotes) 识别

- **视觉特征**: 引用内容通常包裹在浅灰色背景的气泡中。
- **算法**: 通过 `np.std(color) < 45` 且满足特定宽高比（横向长条）的连通域来锁定。
- **关联**: 若 OCR 文字座落在该引用气泡范围内，则将其标记为 `[引用: ...]` 并与其下的回复内容挂钩。

### 6.3 消息归集与发送人逻辑 (Aggregator)

- **去重归并**: 垂直间距小于 30 像素的消息会自动判定为同一条消息的长文本换行。
- **发送人判定**:
    - **单聊**: 基于 `mid_x` 左右对齐判定。
    - **群聊 (Avatar Pointing)**: 
        - 探测所有物理尺寸符合头像特征 (`40x40`) 的连通域。
        - 消息与其垂直位置最接近的左侧/右侧头像进项关联。
        - 我方消息 (`is_me`) 通过头像位于右侧边缘判定。

---

## 7. OCR 模式详解

### 7.1 模式对比

| 特性 | fast | accurate |
|------|------|----------|
| Vision 框架级别 | VNRequestTextRecognitionLevelFast (1) | VNRequestTextRecognitionLevelAccurate (0) |
| 典型耗时 | 100-300ms | 800-1000ms |
| 中文识别质量 | 一般（可能有乱码） | 高 |
| 适用场景 | 快速查找、初步验证 | 精确匹配、消息解析 |

### 7.2 使用分布

| 函数 | fast | accurate |
|------|------|----------|
| `_click_search_bar` | ✓ | |
| `_navigate_to_chat` (Step 1) | ✓ | |
| `_navigate_to_chat` (Step 2) | | ✓ |
| `_verify_chat_open` | ✓ (可选) | ✓ |
| `_is_group_chat` | ✓ | |
| `_read_content_area` | | ✓ |
| `chat_list` | | ✓ |

**注意**：搜索结果面板的中文在 `fast` 模式下乱码严重，必须用 `accurate`。

### 7.3 滚动机制

```
滚动方式: CGEvent 像素级平滑滚动（模拟真实触摸板）
- 不使用 pyautogui.scroll()（基于滚轮事件，容易被检测）
- 使用 CGEventCreateScrollWheelEvent + kCGScrollEventUnitPixel
- 分解为 5-10 个小事件，添加随机抖动
- 1 页 = 内容区高度 - 60px（屏幕高度相关）
```

---

## 8. 调试系统

### 8.1 Debug 目录结构

同一轮 Claude 对话的多次 skill 调用共享同一个会话目录，避免每次调用都创建新目录。每轮对话结束后自动清理旧会话。

```
.claude/skills/wxbot-skill/debug/
├── .session                      # 当前会话跟踪文件
├── .session_{session_id}         # 各会话的元数据文件
├── 20260331_143052/              # 会话目录（按时间戳命名）
│   ├── 143052_chat_read/         # 一次 chat read 调用
│   │   ├── log.txt               # 时序日志
│   │   ├── 01_nav_attempt1_before.png
│   │   └── ...
│   └── 143120_chat_reply/        # 一次 chat reply 调用（同会话）
│       └── ...
└── 20260331_150000/              # 下一轮 Claude 对话的会话
    └── ...
```

**会话超时**：超过 1 小时无活动视为新会话。

### 8.2 日志格式

```
[14:30:52.123] T=0.00s +0.00s | === WeChat Skill Debug ===
[14:30:52.123] T=0.00s +0.00s | Session: 20260331_143052
[14:30:52.123] T=0.00s +0.00s | Command: chat_read
[14:30:52.123] T=0.00s +0.00s | Args: {"name": "Kent"}
[14:30:52.456] T=0.33s +0.33s | Window rect: (735, 33, 735, 923)
[14:30:52.789] T=0.67s +0.33s | Screenshot: 01_nav_attempt1_before.png
[14:30:53.012] T=0.89s +0.22s | OCR [find_Kent]: 2 items
[14:30:53.012] T=0.89s +0.00s |   x= 180 y=150 h=14 c=0.95 | Kent
```

- `Session:` : 所属会话 ID
- `T=` : 从命令开始的总耗时
- `+` : 距上一条日志的增量耗时

### 8.3 环境变量

```bash
WECHAT_DEBUG=1              # 默认开启
WECHAT_DEBUG=0              # 关闭调试
WECHAT_DEBUG_MAX_ROUNDS=5   # 保留最近 N 轮会话（默认10）
```

超过 `WECHAT_DEBUG_MAX_ROUNDS` 的旧会话目录会被自动清理。

---

## 9. 进程锁机制

### 9.1 锁文件

```python
LOCK_FILE = SKILL_DIR / ".wechat_ui.lock"
```

### 9.2 锁定逻辑

```python
# chat read/reply 需要互斥执行
lock_fd = open(LOCK_FILE, "w")
try:
    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    print("[ERR] 另一个 wechat.py 实例正在操作中")
    sys.exit(1)
```

### 9.3 为什么需要锁

- pyautogui 控制鼠标键盘，并发执行会导致混乱
- OCR 截图时窗口状态必须稳定
- 避免多个 Claude 会话同时操作微信

---

## 10. 配置系统

### 10.1 config.json

```json
{
  "auto_send": false,
  "reply_prefix": "[AI分身] "
}
```

### 10.2 配置项说明

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `auto_send` | bool | false | true = 自动发送，false = 只输入不发送 |
| `reply_prefix` | string | "[AI分身] " | 回复消息前缀 |

### 10.3 CLI 覆盖

```bash
# --auto-send 强制不发送（覆盖 auto_send=true）
python3 wechat.py chat reply Kent "测试" --auto-send
```

---

## 11. 错误处理

### 11.1 错误输出格式

所有错误统一格式：`[ERR] 简短描述`

### 11.2 常见错误

| 错误信息 | 原因 | 解决方法 |
|----------|------|----------|
| `[ERR] 无法激活 WeChat` | WeChat 未运行或 AppleScript 失败 | 手动打开 WeChat |
| `[ERR] 找不到聊天 "xxx"` | 导航失败（名字错误或 OCR 未识别） | 检查名称拼写 |
| `[ERR] 无法定位消息输入框` | 输入框点击失败 | 重试 |
| `[ERR] 另一个 wechat.py 实例正在操作中` | 进程锁冲突 | 等待其他实例完成 |
| `[ERR] 消息可能未发送成功` | 发送后验证失败 | 手动检查微信 |

---

## 12. 性能优化要点

| 优化点 | 方法 | 效果 |
|--------|------|------|
| 快速检查已打开 | `_verify_chat_open(fast_only=True)` | 跳过不必要的导航 |
| OCR 模式选择 | fast 用于查找，accurate 用于精确匹配 | 平衡速度和准确率 |
| 窗口 rect 缓存 | `_window_rect_cache` | 避免重复 AppleScript 调用 |
| 聊天列表宽度缓存 | `_chatlist_w_cache` | 避免重复计算 |
| 单次 OCR 验证 | 在内存中匹配关键词 | 减少截图次数 |

---

## 13. 人类仿真

### 13.1 底层注入 (Quartz Layer)

为了避开 WeChat 的键盘劫持检测，系统使用 macOS Quartz 系统的原生 API：

- **CGEventCreateKeyboardEvent**: 创建原生 HID 键盘编码事件。
- **CGEventKeyboardSetUnicodeString**: 安全地将 Unicode 字符注入到事件流中，支持中文输入。
- **kCGHIDEventTap**: 确保持久化且高优先级的事件投递。

### 13.2 爆发式键入 (Burst Typing)

系统模拟真人的打字行为特性（思考→爆发键入→停顿）：

- **词组分块**: 将长句随机切割成 1-4 个字符的长短不等的分块。
- **节奏律动**: 
    - 块内停顿较短 (30-100ms)，模拟手指跳动。
    - 块间停顿较长 (120-300ms)，模拟思考和选词过程。
    - 在标点符号后强制增加额外的呼吸停顿。

---

## 14. 紧急停止

pyautogui fail-safe：将鼠标快速移到屏幕左上角（x=0, y=0）会触发异常，终止脚本执行。

```python
pyautogui.FAILSAFE = True  # 默认开启
```

---

## 15. 关键修复历史

### 15.1 搜索结果点击穿透问题

**问题**：点击搜索面板上的联系人坐标会"穿透"到底层的聊天列表，打开错误的聊天。

**修复**：改用键盘 `Enter` 打开搜索结果，而非鼠标点击。

```python
# 改前
self._focused_click(best["x"], best["y"])

# 改后
self._focused_press("enter", activate=False)
```

### 15.2 标题栏验证区域错误

**问题**：`_verify_chat_open` 使用 `_content_x_min(rect)` 作为标题栏 x 起点，这实际上是聊天列表右边界，导致标题栏文字（在侧栏右侧）无法被正确匹配。

**修复**：改用 `wx + SIDEBAR_W` 作为标题栏 x 起点。

```python
# 改前
cx_min = self._content_x_min(rect)  # 聊天列表右边界

# 改后
cx_min = wx + SIDEBAR_W  # 侧栏右边界
```

---

## 16. chatlist 宽度检测策略

### 16.1 问题背景

用户可手动调整 WeChat 窗口中 chatlist 和 content 区域的宽度比例，范围约 33%~75%。如果使用固定比例估算，可能导致：
- chatlist 区域 OCR 结果被误认为 content 区域
- content 区域左侧消息被误过滤

### 16.2 检测方案：像素颜色扫描

```
原理: WeChat 的 chatlist 和 content 区域背景色不同
     扫描 y 中线，找到背景色变化的 x 坐标

步骤:
  1. 截图（~50ms）
  2. 取 chatlist 典型背景色（采样点）
  3. 从最小宽度位置开始向右扫描
  4. 找到颜色差异 > 30 的点即为边界
  5. 计算 chatlist_w = 边界x - wx - SIDEBAR_W

延迟: ~50-100ms
fallback: 如果扫描失败，使用 33% 估算
```

### 16.3 为什么不用 OCR

- OCR 检测需要 300-500ms
- chatlist 宽度用于多处的 x 范围过滤
- 像素扫描延迟低、准确度高

---

## 17. AI 交互与回复哲学

为了确保「AI 分身」的回复具有真实的人感（人味）并符合即时通讯（IM）的特征，系统遵循以下交互原则：

### 17.1 极简主义 (Minimalism)

- **字数控制**：严禁生成长篇大论、总结式或汇报式的长难句。
- **单点突破**：一条消息只说一件事，或者只针对当前上下文中最具体、最新的一个观点进行回复。

### 17.2 拟人化节奏 (Human-like Rhythm)

- **你来我往**：模拟“你一句我一句”的自然对话流，而不是一次性给出完整答案。
- **口语化**：使用自然口语（如“真绝了”、“带感”、“顺应潮流”），避免过于机械和礼貌的 AI 腔调。

### 17.3 身份锚定 (Identity Alignment)

- **分身自觉**：回复内容应与其 `[AI分身]` 的身份前缀相符。例如，在讨论 AI、自动化或 Avatar 相关话题时，利用身份关联性增加互动质量。
- **情境感**：根据群聊或私聊的氛围调整语气，但在任何情况下都优先保持简洁。

### 17.4 输入仿真

- **词组分块**：如 `computer_use.py` 中实现的，模拟人脑思考词组的过程，分块进行 Unicode 键入。
- **呼吸停顿**：在标点符号后增加较长停顿，模拟真实打字中的顿挫感。
