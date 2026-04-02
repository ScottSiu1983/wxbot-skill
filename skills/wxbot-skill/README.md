# WeChat 自动化技能 (v0.2-beta)

通过本地 OCR + Quartz HID 事件控制 WeChat 桌面应用。

## 核心特性

- **结构化探测** — 动态定位窗口布局，支持 Retina 适配。
- **跨平台适配** — 支持 Gemini, Claude, Antigravity, OpenClaw 等。
- **解析增强** — 群聊引用过滤，头像锚点发送者识别。
- **仿真输入** — 基于 Quartz 系统的 Burst Typing 拟人化打字。

## 目录结构

```
skills/wxbot-skill/
├── SKILL.md         # 技能入口定义 (AI Agent 逻辑规则)
├── USAGE.md         # 详细使用指南
├── config.json      # 核心配置 (auto_send, prefix)
├── scripts/         # 核心命令执行脚本
│   ├── wechat.py    # 统一 CLI
│   ├── local_vision.py # OCR 与图像分析
│   └── computer_use.py # Quartz 仿真交互
└── references/      # 布局参考与文档
```

## 快速运行

1. 克隆本项目。
2. 运行 `./install.sh` 进行适配安装。
3. 在你的 AI Agent 中触发动作。

## 调试说明

调试日志与分步截图存放在 `debug/` 目录下，仅保留最近 10 次运行记录。
