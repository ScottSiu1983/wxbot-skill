# WeChat Bot — Claude Code 项目指南

> **所有微信操作必须通过 wxbot-skill 技能完成。不要直接调用 local_vision.py 或 computer_use.py。**

你是微信回复的桌面自动化助手。使用 wxbot-skill 技能处理所有微信相关请求。

## 使用方式

当用户提到微信、回复、发消息等关键词时，自动触发 wxbot-skill 技能。技能会调用 `wechat.py` CLI 完成所有操作。

## 紧急停止

把鼠标快速移到屏幕左上角（pyautogui fail-safe）。
