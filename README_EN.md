<p align="center">
  <h1 align="center">wxbot-skill</h1>
  <p align="center">
    Cross-platform WeChat Desktop Automation Skill (Gemini / Claude / Antigravity / OpenClaw)
    <br />
    Pixel-level Layout Analysis · Human-like Interaction · Privacy-focused Local Data
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

## v0.2-beta New Features

- **Structural Layout Detection** — Dynamically detects WeChat window boundaries, precisely identifying sidebars, message flows, and input fields.
- **Human-like Interaction** — Uses Quartz-level events for character typing and rhythmic "Burst Typing" to simulate natural human input pace.
- **Enhanced Group Support** — Automatic parsing of quotes, avatar-based sender identification, and multi-modal message (image/sticker) classification.
- **Navigation 2.0** — Restored section-header based search (Contacts/Groups) for precise target selection among duplicate names.
- **One-click Adaptation** — Standardized adapter system for one-click installation into Gemini, Claude, Antigravity, OpenClaw, and more.

## Supported Platforms

| Platform | Setup Command | Recommended Model |
|----------|---------------|-------------------|
| **Gemini CLI** | `./install.sh --platform gemini` | Gemini 1.5 Pro/Flash |
| **Claude Code** | `./install.sh --platform claude` | Claude 3.5 Sonnet |
| **Antigravity** | `./install.sh --platform antigravity` | Any SOTA LLM |
| **OpenClaw** | `./install.sh --platform openclaw` | GPT-4o / Claude 3.5 |
| **Codex CLI** | `./install.sh --platform codex` | - |
| **Cursor** | `./install.sh --platform cursor` | - |

## Requirements

- **macOS** 13+ (Vision Framework, AppleScript)
- **Python** 3.10+
- **WeChat** Mac desktop app

### macOS Permissions

Grant these in **System Settings → Privacy & Security**:
- **Accessibility** — Your Terminal / IDE (for key/mouse control)
- **Screen Recording** — Your Terminal / IDE (for OCR screenshots)

## Quick Start

1. **Clone and Install**
   ```bash
   git clone https://github.com/ScottSiu1983/wxbot-skill.git
   cd wxbot-skill
   pip install -r requirements.txt
   ```

2. **One-click Installation**
   ```bash
   ./install.sh  # Interactive mode
   ```

3. **Run**
   Tell your AI Agent:
   - "List my WeChat chats"
   - "Read messages from Project Team and suggest a reply"

## Project Structure

```
wxbot-skill/
├── skills/wxbot-skill/       ← Core skill directory
│   ├── SKILL.md              ← Platform-agnostic skill definition
│   ├── scripts/              ← Implementation scripts (wechat.py, etc.)
│   └── config.json           ← Automation settings
├── adapters/                 ← Cross-platform adapter generator
├── install.sh                ← Integrated installation tool
└── RELEASE_NOTES.md          ← [NEW] Detailed v0.2-beta logs
```

## License

[Apache-2.0](LICENSE)
