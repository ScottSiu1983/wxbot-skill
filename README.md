<p align="center">
  <h1 align="center">wxbot-skill</h1>
  <p align="center">
    跨平台微信桌面自动化技能 (Gemini / Claude / Antigravity / OpenClaw)
    <br />
    像素级布局分析 · 拟人化交互 · 隐私数据本地化
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

## v0.2-beta 特性更新

- **像素级结构化布局** — 动态探测微信窗口分界线，精准识别侧边栏、消息流与输入框。
- **拟人化交互 (Human-like)** — 使用 Quartz 底层事件模拟真实按键，配合“爆发式”律动打字（Burst Typing），完美模拟真人节奏。
- **深度群聊支持** — 自动解析群聊引用（Quote）、头像锚点发送者识别，支持多模态消息（图片/表情）分类。
- **搜索导航 2.0** — 恢复“联系人/群聊”分区标题定位，确保重名情况下精准选中目标。
- **一键跨平台适配** — 新增适配器系统，一键安装到 Gemini, Claude, Antigravity, OpenClaw 等主流 Agent 平台。

## 支持的 AI Agent 平台

| 平台 | 安装方法 | 推荐模型 |
|------|---------|---------|
| **Gemini CLI** | `./install.sh --platform gemini` | Gemini 1.5 Pro/Flash |
| **Claude Code** | `./install.sh --platform claude` | Claude 3.5 Sonnet |
| **Antigravity** | `./install.sh --platform antigravity` | 各主流大模型 |
| **OpenClaw** | `./install.sh --platform openclaw` | GPT-4o / Claude 3.5 |
| **Codex CLI** | `./install.sh --platform codex` | - |
| **Cursor** | `./install.sh --platform cursor` | - |

## 环境要求

- **macOS** 13+ (Vision Framework, AppleScript)
- **Python** 3.10+
- **WeChat** Mac 桌面版

### macOS 权限设置

在 **系统设置 → 隐私与安全性** 中授权：
- **辅助功能** — 终端 / IDE (用于键鼠控制)
- **屏幕录制** — 终端 / IDE (用于 OCR 截屏)

## 快速开始

1. **克隆并安装依赖**
   ```bash
   git clone https://github.com/ScottSiu1983/wxbot-skill.git
   cd wxbot-skill
   pip install -r requirements.txt
   ```

2. **一键安装到你的 Agent**
   ```bash
   ./install.sh  # 交互式选择平台
   ```

3. **运行**
   在你的 Agent 中说：
   - "列出微信聊天"
   - "读取 东方电子规划 的记录，并给出一个合理的回复"

## 项目结构

```
wxbot-skill/
├── skills/wxbot-skill/       ← 技能核心目录
│   ├── SKILL.md              ← 平台无关的技能定义
│   ├── scripts/              ← 核心脚本 (wechat.py/local_vision.py)
│   └── config.json           ← 自动化配置
├── adapters/                 ← 跨平台适配器生成器
├── install.sh                ← 一键安装/迁移工具
└── RELEASE_NOTES.md          ← [NEW] v0.2-beta 详细更新日志
```

## 许可证

[Apache-2.0](LICENSE)
