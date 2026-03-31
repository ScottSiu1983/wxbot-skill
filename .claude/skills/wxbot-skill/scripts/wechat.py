#!/usr/bin/env python3
"""
wechat.py — 统一 WeChat 自动化 CLI

用法:
  python3 wechat.py chat list
  python3 wechat.py chat read <name>
  python3 wechat.py chat reply <name> "<message>"

输出规范（给 Claude 看的极简文本）:
  成功: [OK] ...
  失败: [ERR] ...

所有截图/OCR/导航在本脚本内部完成，不暴露中间状态给 Claude。
"""

__version__ = "0.1-beta"

import argparse
import contextlib
import fcntl
import io
import json
import math
import numpy as np
import os
import random
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ── 导入同目录的基础模块 ─────────────────────────────────────────────────────
from local_vision import find_text, get_screen_text, take_screenshot, SCREEN_W
import computer_use as _cu

import objc
from Foundation import NSURL
from Quartz import (CGImageSourceCreateWithURL, CGImageSourceCreateImageAtIndex,
                     CGEventCreateKeyboardEvent, CGEventKeyboardSetUnicodeString,
                     CGEventPost, kCGHIDEventTap)
objc.loadBundle("Vision", globals(), bundle_path="/System/Library/Frameworks/Vision.framework")

# ── Debug 模块 ───────────────────────────────────────────────────────────────
# 设置 WECHAT_DEBUG=0 关闭调试，默认开启

SKILL_DIR = Path(__file__).resolve().parents[1]
DEBUG_DIR = SKILL_DIR / "debug"
LOCK_FILE = SKILL_DIR / ".wechat_ui.lock"
DEBUG = os.environ.get("WECHAT_DEBUG", "1") != "0"
_debug_log_path = None
_debug_run_dir = None
_debug_step = 0
_debug_start_time = None  # 命令开始时间
_debug_last_time = None   # 上一条日志时间（用于计算步间耗时）


def _init_debug(command: str, args: dict):
    """初始化本次运行的 debug 目录和日志文件。"""
    global _debug_log_path, _debug_run_dir, _debug_step, _debug_start_time, _debug_last_time
    if not DEBUG:
        return
    _debug_step = 0
    _debug_start_time = time.time()
    _debug_last_time = _debug_start_time
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    _debug_run_dir = DEBUG_DIR / f"{ts}_{command}"
    _debug_run_dir.mkdir(parents=True, exist_ok=True)
    _debug_log_path = _debug_run_dir / "log.txt"
    _dbg(f"=== WeChat Skill Debug ===")
    _dbg(f"Time: {ts}")
    _dbg(f"Command: {command}")
    _dbg(f"Args: {json.dumps(args, ensure_ascii=False)}")
    _dbg(f"Debug dir: {_debug_run_dir}")
    # 清理旧的 debug 目录（只保留最近 10 次）
    all_runs = sorted(DEBUG_DIR.iterdir())
    if len(all_runs) > 10:
        for old in all_runs[:-10]:
            if old.is_dir():
                shutil.rmtree(old, ignore_errors=True)


def _dbg(msg: str):
    """写入 debug 日志。每行包含：绝对时间、距上一步耗时(+Δ)、总耗时(T)。"""
    global _debug_last_time
    if not DEBUG or not _debug_log_path:
        return
    now = time.time()
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    if _debug_start_time is not None:
        total = now - _debug_start_time
        delta = now - (_debug_last_time or now)
        prefix = f"[{ts}] T={total:.2f}s +{delta:.2f}s"
    else:
        prefix = f"[{ts}]"
    _debug_last_time = now
    line = f"{prefix} | {msg}\n"
    with open(_debug_log_path, "a") as f:
        f.write(line)


def _dbg_screenshot(label: str) -> str | None:
    """保存带标签的截图到 debug 目录，返回路径。"""
    if not DEBUG or not _debug_run_dir:
        return None
    global _debug_step
    _debug_step += 1
    filename = f"{_debug_step:02d}_{label}.png"
    path = str(_debug_run_dir / filename)
    take_screenshot(path)
    _dbg(f"Screenshot: {filename}")
    return path


def _dbg_ocr(label: str, items: list[dict]):
    """记录 OCR 结果到日志。"""
    if not DEBUG:
        return
    _dbg(f"OCR [{label}]: {len(items)} items")
    for i in sorted(items, key=lambda x: (x["y"], x["x"])):
        _dbg(f"  x={i['x']:4d} y={i['y']:3d} h={i.get('h',0):2d} c={i['confidence']:.2f} | {i['text']}")


def _dbg_action(action: str, **kwargs):
    """记录用户操作到日志。"""
    if not DEBUG:
        return
    params = " ".join(f"{k}={v}" for k, v in kwargs.items())
    _dbg(f"Action: {action} {params}")


# ── 静默包装：抑制 computer_use 的 print 输出 ─────────────────────────────────

@contextlib.contextmanager
def _quiet():
    """把 stdout 重定向到 /dev/null，使 computer_use 的 print 不可见。"""
    with open(os.devnull, "w") as devnull:
        old = sys.stdout
        sys.stdout = devnull
        try:
            yield
        finally:
            sys.stdout = old


def click(x, y, **kw):
    with _quiet():
        _cu.click(x, y, **kw)


def type_text(text):
    with _quiet():
        _cu.type_text(text)


def press_key(key):
    with _quiet():
        _cu.press_key(key)


def scroll(x, y, direction, clicks=3):
    with _quiet():
        _cu.scroll(x, y, direction, clicks)


# ── 常量 ─────────────────────────────────────────────────────────────────────

REPLY_PREFIX_DEFAULT = "[AI分身] "

# WeChat 布局（相对窗口，逻辑像素）
SIDEBAR_W   = 60    # 左侧图标栏宽度（固定）
SETTLE      = 0.35  # 点击后等待 UI 稳定的秒数
MAX_RETRIES = 3

# OCR 过滤：这些模式是 UI 噪音，不是消息内容
_NOISE_PATTERNS = [
    r"^\d{1,2}:\d{2}$",               # 时间戳 HH:MM
    r"^\d{1,2}月\d{1,2}日$",           # 日期如 3月29日
    r"^(昨天|今天|星期[一二三四五六日])$",
    r"^发送$",
    r"^搜索$",                         # 聊天列表顶部的搜索栏标签
    r"^折叠置顶聊天$",                  # 底部 UI 按钮
    r"^\[.*?\]$",                      # 系统通知如 [链接] [图片]
    r"^-+$",
    r"^Search$",
    r"^\s*$",
    r"^\d+$",                          # 纯数字（未读消息角标）
]


# ── WeChat 控制器 ─────────────────────────────────────────────────────────────

class WeChatController:

    # ── 私有：系统操作 ────────────────────────────────────────────────────────

    def _activate_wechat(self, force: bool = False) -> bool:
        """通过 AppleScript 强制激活 WeChat 到最前台。同一实例内只执行一次，除非 force=True。"""
        if self._wechat_activated and not force:
            return True
        script = '''
tell application "WeChat" to activate
delay 0.1
tell application "System Events"
    tell process "WeChat"
        set frontmost to true
    end tell
end tell
'''
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=3
        )
        time.sleep(0.05)
        if result.returncode == 0:
            self._wechat_activated = True
        return result.returncode == 0

    # ── 人类仿真延迟 + 焦点安全包装 ─────────────────────────────────────────────

    def _human_delay(self, x, y):
        """根据与上次点击的距离，模拟人类鼠标移动延迟。"""
        dx = x - self._last_click_pos[0]
        dy = y - self._last_click_pos[1]
        distance = math.sqrt(dx * dx + dy * dy)
        delay = 0.05 + (distance / 3000.0) + random.uniform(-0.02, 0.02)
        delay = max(0.05, min(0.5, delay))
        time.sleep(delay)

    def _focused_click(self, x, y, **kw):
        """激活 WeChat + 人类延迟后单击，确保点击落在 WeChat 窗口。"""
        _dbg_action("click", x=x, y=y, **kw)
        self._human_delay(x, y)
        self._activate_wechat()
        click(x, y, **kw)
        self._last_click_pos = (x, y)

    def _focused_type(self, text, activate=True):
        """激活 WeChat 后立即输入文字。"""
        _dbg_action("type", text=repr(text))
        if activate:
            self._activate_wechat()
        type_text(text)

    def _focused_press(self, key, activate=True):
        """激活 WeChat 后立即按键。"""
        _dbg_action("press", key=key)
        if activate:
            self._activate_wechat()
        press_key(key)

    def _focused_find_text(self, target: str, mode: str = "accurate") -> list[dict]:
        """激活 WeChat 到最前端后截图 OCR 查找文字。确保截到的是 WeChat 而非其他窗口。"""
        self._activate_wechat()
        return find_text(target, mode=mode)

    def _focused_screen_text(self, mode: str = "accurate") -> list[dict]:
        """激活 WeChat 到最前端后截图 OCR 获取全部文字。"""
        self._activate_wechat()
        return get_screen_text(mode=mode)

    def _activate_and_get_rect(self) -> tuple:
        """激活 WeChat 并获取窗口位置，合并为单次 AppleScript 调用。"""
        if self._wechat_activated and self._window_rect_cache:
            return self._window_rect_cache

        import pyautogui
        sw, sh = pyautogui.size()

        script = '''
tell application "WeChat" to activate
delay 0.1
tell application "System Events"
    tell process "WeChat"
        set frontmost to true
        set w to window "微信"
        set p to position of w
        set s to size of w
        return ((item 1 of p) as string) & "," & ((item 2 of p) as string) & "," & ((item 1 of s) as string) & "," & ((item 2 of s) as string)
    end tell
end tell'''
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=3
        )
        time.sleep(0.05)
        self._wechat_activated = True

        raw = result.stdout.strip()
        if raw:
            try:
                parts = [int(v) for v in raw.split(",")]
                if len(parts) == 4 and parts[2] > 200:
                    self._window_rect_cache = tuple(parts)
                    return self._window_rect_cache
            except Exception:
                pass

        # 兜底
        self._window_rect_cache = (sw // 2, 33, sw // 2, sh - 33)
        return self._window_rect_cache

    def _get_window_rect(self) -> tuple:
        """获取 WeChat 主窗口逻辑坐标 (x, y, w, h)。使用缓存。"""
        if self._window_rect_cache:
            return self._window_rect_cache
        return self._activate_and_get_rect()

    def __init__(self):
        self._chatlist_w_cache = None
        self._chatlist_rect_cache = None  # 窗口 rect 变化时缓存失效
        self._last_click_pos = (0, 0)
        self._window_rect_cache = None
        self._wechat_activated = False

    def _detect_chatlist_width(self, rect: tuple) -> int:
        """
        动态检测聊天列表面板宽度。
        直接用窗口宽度比例估算（33%），避免 OCR 调用。
        """
        if self._chatlist_w_cache and self._chatlist_rect_cache == rect:
            return self._chatlist_w_cache

        wx, wy, ww, wh = rect
        chatlist_w = int((ww - SIDEBAR_W) * 0.33)
        chatlist_w = max(180, min(chatlist_w, ww // 2))
        _dbg(f"Chatlist width: {chatlist_w} (33% of content area)")

        self._chatlist_w_cache = chatlist_w
        self._chatlist_rect_cache = rect
        return chatlist_w

    def _chatlist_x_range(self, rect: tuple) -> tuple:
        """返回聊天列表的 (x_min, x_max)。"""
        wx = rect[0]
        chatlist_w = self._detect_chatlist_width(rect)
        return (wx + SIDEBAR_W, wx + SIDEBAR_W + chatlist_w)

    def _content_x_min(self, rect: tuple) -> int:
        """返回内容区域左边界 x。"""
        return self._chatlist_x_range(rect)[1]

    # ── 私有：导航 ────────────────────────────────────────────────────────────

    def _click_search_bar(self, rect: tuple) -> int:
        """
        点击聊天列表顶部的"搜索"栏。
        优先用 OCR 查找"搜索"文字，失败则 fallback 到硬编码位置。
        返回搜索栏的 y 坐标。
        """
        wx, wy, ww, wh = rect
        list_x_min, list_x_max = self._chatlist_x_range(rect)

        # 尝试 OCR 查找"搜索"文字（fast 模式约 300ms）
        search_items = self._focused_find_text("搜索", mode="fast")
        # 筛选在聊天列表顶部区域内的结果（y 在窗口顶部 60px 内）
        candidates = [i for i in search_items
                      if list_x_min < i["x"] < list_x_max
                      and wy < i["y"] < wy + 60]

        if candidates:
            best = candidates[0]
            search_x, search_y = best["x"], best["y"]
            _dbg(f"click_search_bar: OCR found '搜索' at ({search_x}, {search_y})")
        else:
            # Fallback: 硬编码位置
            search_x = (list_x_min + list_x_max) // 2
            search_y = wy + 30
            _dbg(f"click_search_bar: OCR not found, fallback to ({search_x}, {search_y})")

        self._focused_click(search_x, search_y)
        time.sleep(0.15)
        return search_y

    def _navigate_to_chat(self, name: str) -> bool:
        """
        导航到指定聊天。返回 True 表示成功。
        策略：
          1. 全屏 OCR 查找名字，筛选在聊天列表 x 范围内的结果
          2. 点击"搜索"栏，输入名称，从结果中找联系人并点击
        注意：Cmd+F 是"搜索当前对话内容"，不是联系人搜索，绝对不能用！
        注意：不对 find_text/get_screen_text 使用 --region，因为 region 模式坐标计算有精度问题。
        注意：所有键盘/鼠标操作必须用 _focused_xxx 方法，确保 WeChat 保持焦点。
        """
        rect = self._activate_and_get_rect()
        _dbg(f"Window rect: {rect}")
        if not rect:
            _dbg("FAIL: cannot activate WeChat or get window rect")
            return False

        # 快速检查：目标对话是否已经打开（避免不必要的导航）
        # 先 fast 模式（~0.5s），失败则 accurate 模式（~1.3s），均比搜索路径（~7-9s）快
        if self._verify_chat_open(name, rect, fast_only=True):
            _dbg(f"Chat '{name}' is already open, skipping navigation")
            return True
        if self._verify_chat_open(name, rect, accurate_only=True):
            _dbg(f"Chat '{name}' is already open (accurate), skipping navigation")
            return True

        wx, wy, ww, wh = rect
        list_x_min, list_x_max = self._chatlist_x_range(rect)
        _dbg(f"Chat list x range: {list_x_min}-{list_x_max}")

        for attempt in range(MAX_RETRIES):
            _dbg(f"--- Attempt {attempt + 1}/{MAX_RETRIES} ---")
            _dbg_screenshot(f"nav_attempt{attempt+1}_before")

            # Step 1: 全屏 OCR 查找名字，筛选在聊天列表 x 范围内（fast 足够）
            _dbg(f"Step 1: find_text('{name}', fast)")
            all_results = self._focused_find_text(name, mode="fast")
            _dbg_ocr(f"find_{name}", all_results)
            outside = [r for r in all_results if r["x"] < wx or r["x"] > wx+ww or r["y"] < wy or r["y"] > wy+wh]
            if outside:
                _dbg(f"WARNING: {len(outside)} OCR results outside WeChat window (terminal contamination?)")
            list_matches = [r for r in all_results
                            if list_x_min < r["x"] < list_x_max
                            and wy < r["y"] < wy + wh
                            and r["confidence"] >= 0.7]
            _dbg(f"Chat list matches: {len(list_matches)}")

            if list_matches:
                best = sorted(list_matches, key=lambda r: r["confidence"], reverse=True)[0]
                _dbg(f"Clicking best match: x={best['x']} y={best['y']} '{best['text']}'")
                self._focused_click(best["x"], best["y"])
                time.sleep(SETTLE)
                _dbg_screenshot(f"nav_attempt{attempt+1}_after_click")
                verified = self._verify_chat_open(name, rect, accurate_only=True)
                _dbg(f"Verify (1st): {verified}")
                if verified:
                    return True
                time.sleep(0.5)
                verified = self._verify_chat_open(name, rect, accurate_only=True)
                _dbg(f"Verify (2nd, after 0.5s wait): {verified}")
                if verified:
                    return True
                _dbg("Click didn't open chat, will retry OCR (no re-click)")
                continue

            # Step 2: 聊天列表中没直接找到 → 通过搜索栏查找
            # 策略：输入名字后，用全屏 OCR 找到"联系人"分类标题，
            # 然后点击"联系人"标题下方的第一个匹配条目。
            _dbg("Step 2: search bar path")
            self._focused_press("escape")
            time.sleep(0.15)
            search_bar_y = self._click_search_bar(rect)
            time.sleep(0.15)

            self._focused_press("command+a", activate=False)
            time.sleep(0.05)
            # 搜索框必须用剪贴板粘贴，避免输入法拦截（如拼音上屏）
            subprocess.run(["pbcopy"], input=name.encode("utf-8"), check=True)
            self._focused_press("command+v", activate=False)
            _dbg_action("paste_search", text=name)
            time.sleep(2.5)  # 等待搜索结果完整加载（群聊/联系人分区需要时间渲染）

            _dbg_screenshot(f"nav_attempt{attempt+1}_search_results")
            # 全屏 OCR 获取搜索面板的完整布局（必须 accurate，fast 中文乱码严重）
            all_text = self._focused_screen_text(mode="accurate")
            # 筛选 WeChat 窗口内的文字
            wechat_text = [i for i in all_text if wx < i["x"] < wx + ww and wy < i["y"] < wy + wh]
            wechat_text.sort(key=lambda i: i["y"])
            _dbg(f"Search panel OCR: {len(wechat_text)} items in WeChat window")
            for i in wechat_text:
                _dbg(f"  x={i['x']:4d} y={i['y']:3d} h={i.get('h',0):2d} c={i['confidence']:.2f} | {i['text']}")

            # 收集分类标题及其 y 范围
            section_headers = []
            for i in wechat_text:
                if i["text"].strip() in ("联系人", "群聊", "聊天记录", "搜索网络结果"):
                    section_headers.append(i)
            section_headers.sort(key=lambda i: i["y"])
            _dbg(f"Section headers: {[(h['text'], h['y']) for h in section_headers]}")

            # 构建各分类的 y 范围
            section_ranges = {}
            for idx, hdr in enumerate(section_headers):
                y_end = section_headers[idx + 1]["y"] if idx + 1 < len(section_headers) else wy + wh
                section_ranges[hdr["text"].strip()] = (hdr["y"], y_end)

            # 在"联系人"和"群聊"分区中收集候选项，每个分区取标题下方的第一个匹配
            candidates = []
            best = None
            name_lower = name.lower().replace(" ", "")
            for section_name in ("联系人", "群聊"):
                if section_name not in section_ranges:
                    continue
                y_start, y_end = section_ranges[section_name]
                # 严格在分区标题之下、下一分区标题之上
                section_items = [i for i in wechat_text
                                 if y_start < i["y"] < y_end]
                # 按 y 排序，确保取分区标题下方最近的匹配项
                section_items.sort(key=lambda i: i["y"])
                for i in section_items:
                    text_clean = i["text"].strip().replace(" ", "").lower()
                    # 去除 WeChat 群前缀如 [净]
                    text_bare = re.sub(r'[\[［].*?[\]］]', '', text_clean).strip()
                    if name_lower in text_clean or text_clean in name_lower \
                            or name_lower in text_bare:
                        is_exact = (name_lower == text_clean or name_lower == text_bare)
                        candidates.append({
                            "item": i,
                            "section": section_name,
                            "exact": is_exact,
                        })
                        _dbg(f"Candidate in '{section_name}': x={i['x']} y={i['y']} "
                             f"'{i['text']}' exact={is_exact}")
                        break  # 每个分区只取第一个匹配

            if candidates:
                # 精确匹配优先，同等条件下优先联系人
                candidates.sort(key=lambda c: (
                    not c["exact"],
                    c["section"] != "联系人",
                ))
                best = candidates[0]["item"]
                _dbg(f"Selected from '{candidates[0]['section']}': '{best['text']}'")

            if not best and not section_ranges:
                _dbg("No section headers found, falling back to name match")
                for i in wechat_text:
                    if i["y"] <= search_bar_y + 15:
                        continue
                    text_clean = i["text"].strip().replace(" ", "").lower()
                    if name_lower in text_clean or text_clean in name_lower:
                        best = i
                        _dbg(f"Fallback match: x={i['x']} y={i['y']} '{i['text']}'")
                        break

            if best:
                _dbg(f"Clicking search result: x={best['x']} y={best['y']} '{best['text']}'")
                self._focused_click(best["x"], best["y"])
                time.sleep(SETTLE)
                _dbg_screenshot(f"nav_attempt{attempt+1}_after_search_click")
                verified = self._verify_chat_open(name, rect, accurate_only=True)
                _dbg(f"Verify after search click: {verified}")
                if verified:
                    # 搜索面板可能还在，按 Escape 关闭后再返回
                    self._focused_press("escape")
                    time.sleep(0.15)
                    _dbg("Search panel closed, navigation complete")
                    return True

            self._focused_press("escape")
            time.sleep(0.15)

        _dbg("FAIL: all attempts exhausted")
        return False

    def _is_group_chat(self, rect: tuple) -> bool:
        """检测当前打开的是否为群聊。群聊标题栏显示 (N) 格式的成员数。"""
        wx, wy, ww, wh = rect
        cx_min = self._content_x_min(rect)
        title_items = [i for i in self._focused_screen_text(mode="fast")
                       if cx_min < i["x"] < wx + ww and wy < i["y"] < wy + 40]
        for item in title_items:
            if re.search(r'\(\d+\)', item["text"]):
                _dbg(f"Group chat detected: '{item['text']}'")
                return True
        _dbg("Not a group chat (no member count in title)")
        return False

    def _verify_chat_open(self, name: str, rect: tuple, fast_only: bool = False, accurate_only: bool = False) -> bool:
        """
        检查对话是否成功打开。
        用单次 OCR 获取标题栏所有文字，再在内存中做子串匹配。
        验证条件：标题栏文字包含 name 或其前缀子串。
        """
        wx, wy, ww, wh = rect
        cx_min = self._content_x_min(rect)
        cx_max = wx + ww
        cy_min = wy
        cy_max = wy + 40

        # 构建匹配关键词：完整名字 → 逐步缩短前缀 → 单个词组
        keywords = [name]
        for i in range(len(name) - 1, 2, -1):
            prefix = name[:i]
            if prefix not in keywords:
                keywords.append(prefix)
        for p in re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z0-9]+', name):
            if p not in keywords and len(p) >= 2:
                keywords.append(p)

        # 决定 OCR 模式
        if accurate_only:
            modes = ("accurate",)
        elif fast_only:
            modes = ("fast",)
        else:
            modes = ("fast", "accurate")

        for mode in modes:
            # 单次全屏 OCR，过滤出标题栏区域的文字
            all_items = self._focused_screen_text(mode=mode)
            title_items = [i for i in all_items
                           if cx_min < i["x"] < cx_max
                           and cy_min < i["y"] < cy_max]
            title_text = " ".join(i["text"] for i in title_items)
            _dbg(f"Verify [{mode}]: title bar text='{title_text}' (x:{cx_min}-{cx_max}, y:{cy_min}-{cy_max})")

            # 在标题栏文字中匹配关键词
            for kw in keywords:
                if len(kw) < 2:
                    continue
                if kw in title_text:
                    matched_items = [i for i in title_items if kw in i["text"]]
                    for m in matched_items:
                        _dbg(f"  matched '{kw}' in: x={m['x']} y={m['y']} c={m['confidence']:.2f} '{m['text']}'")
                    return True
            _dbg(f"Verify [{mode}]: no keyword matched")
        return False

    # ── 私有：读取消息 ────────────────────────────────────────────────────────

    def _read_content_area(self, rect: tuple) -> tuple[list[dict], str | None]:
        """
        OCR 内容区域，返回 (原始条目列表, 截图路径)。
        使用全屏 OCR 再按坐标过滤，避免 region 模式的坐标计算误差。
        截图路径供后续视觉元素检测使用。
        """
        wx, wy, ww, wh = rect
        cx_min = self._content_x_min(rect)
        content_x_max = wx + ww
        content_y_min = wy + 40
        content_y_max = wy + wh - 80

        screenshot_path = _dbg_screenshot("read_content_area")
        all_items = self._focused_screen_text(mode="accurate")
        filtered = [i for i in all_items
                    if cx_min < i["x"] < content_x_max
                    and content_y_min < i["y"] < content_y_max]
        _dbg_ocr("content_area", filtered)
        # 保存最新截图路径（非 debug 模式也需要截图用于视觉检测）
        if not screenshot_path:
            screenshot_path = take_screenshot()
            self._last_screenshot = screenshot_path
        else:
            self._last_screenshot = screenshot_path
        return filtered, screenshot_path

    def _is_noise(self, text: str) -> bool:
        """判断是否是 UI 噪音（时间戳、系统词等）。"""
        text = text.strip()
        for pat in _NOISE_PATTERNS:
            if re.match(pat, text):
                return True
        return False

    # 分类标签中英映射（VNClassifyImageRequest 返回英文标签）
    _CLASSIFY_LABEL_MAP = {
        "bedroom": "卧室", "bathroom": "浴室", "kitchen": "厨房",
        "living_room": "客厅", "dining_room": "餐厅", "office": "办公室",
        "building": "建筑", "structure": "建筑", "house": "房屋",
        "food": "食物", "drink": "饮料", "fruit": "水果",
        "people": "人物", "adult": "成人", "baby": "婴儿", "child": "儿童",
        "face": "人脸", "portrait": "人像",
        "animal": "动物", "cat": "猫", "dog": "狗", "bird": "鸟",
        "car": "汽车", "vehicle": "车辆", "bicycle": "自行车",
        "flower": "花", "plant": "植物", "tree": "树",
        "sky": "天空", "ocean": "海洋", "mountain": "山", "beach": "海滩",
        "sunset": "日落", "landscape": "风景", "nature": "自然",
        "text": "文字", "document": "文档", "screenshot": "截图",
        "pillow": "枕头", "bedding": "床上用品", "housewares": "家居用品",
        "clothing": "服装", "shoe": "鞋子", "bag": "包",
        "toy": "玩具", "book": "书", "phone": "手机",
        "sport": "运动", "game": "游戏",
    }

    def _classify_image_region(self, arr: 'np.ndarray', bx: int, by: int, bw: int, bh: int) -> str:
        """
        用 macOS Vision VNClassifyImageRequest 对裁剪区域做本地图像分类。
        返回中文描述（如"卧室/床上用品"），失败返回空字符串。
        """
        from PIL import Image
        import tempfile

        try:
            h_px, w_px = arr.shape[:2]
            region = arr[max(0, by):min(h_px, by + bh), max(0, bx):min(w_px, bx + bw)]
            if region.size == 0:
                return ""

            # 保存裁剪区域为临时文件
            crop_img = Image.fromarray(region)
            tmp_path = tempfile.mktemp(suffix=".png")
            crop_img.save(tmp_path)

            # VNClassifyImageRequest
            url = NSURL.fileURLWithPath_(tmp_path)
            source = CGImageSourceCreateWithURL(url, None)
            cg_image = CGImageSourceCreateImageAtIndex(source, 0, None)
            if not cg_image:
                return ""

            req = VNClassifyImageRequest.alloc().init()
            handler = VNImageRequestHandler.alloc().initWithCGImage_options_(cg_image, {})
            handler.performRequests_error_([req], None)
            results = req.results()

            Path(tmp_path).unlink(missing_ok=True)

            if not results:
                return ""

            # 取置信度 > 0.15 的标签，排除 document/screenshot（截图本身的噪音）
            skip = {"document", "screenshot", "machine", "consumer_electronics", "computer", "computer_monitor"}
            labels = []
            for r in sorted(results, key=lambda r: r.confidence(), reverse=True):
                ident = str(r.identifier())
                conf = float(r.confidence())
                if conf < 0.15:
                    break
                if ident in skip:
                    continue
                zh = self._CLASSIFY_LABEL_MAP.get(ident, ident)
                labels.append(zh)
                if len(labels) >= 3:
                    break

            desc = "/".join(labels) if labels else ""
            _dbg(f"classify_image: {desc}")
            return desc

        except Exception as e:
            _dbg(f"classify_image error: {e}")
            return ""

    def _detect_visual_elements(self, screenshot_path: str, ocr_items: list[dict], rect: tuple) -> list[dict]:
        """
        检测内容区域中的非文字视觉元素（图片、表情包、emoji）。

        原理：WeChat 聊天背景为浅灰色。在 OCR 文字区域之外，若存在大面积
        非背景色像素簇，即为图片/表情/emoji。按区域大小分类：
          - 宽 > 80px 且高 > 60px → [图片] (附带 VNClassifyImageRequest 内容描述)
          - 宽 15~80px 且高 15~60px → [表情]
          - 更小 → 忽略（可能是 UI 碎片）

        返回: [{"type": "image"|"sticker", "x": int, "y": int, "w": int, "h": int, "sender": str, "desc": str}]
        坐标为逻辑坐标（与 OCR 一致）。
        """
        from PIL import Image

        if not screenshot_path or not Path(screenshot_path).exists():
            _dbg("detect_visual: no screenshot available")
            return []

        wx, wy, ww, wh = rect
        cx_min = self._content_x_min(rect)
        content_x_max = wx + ww
        content_y_min = wy + 40
        content_y_max = wy + wh - 80
        midline_x = cx_min + (content_x_max - cx_min) // 2

        img = Image.open(screenshot_path)
        scale = img.size[0] / SCREEN_W  # Retina 2x

        # 裁剪内容区域（物理像素）
        crop_box = (
            int(cx_min * scale), int(content_y_min * scale),
            int(content_x_max * scale), int(content_y_max * scale),
        )
        content_img = img.crop(crop_box)
        arr = np.array(content_img)

        # WeChat 聊天背景色检测：取四个角落 10x10 区域的中位色
        h_px, w_px = arr.shape[:2]
        # 确保图片至少有 RGB 3 通道；RGBA 则只取前 3 通道
        if arr.ndim == 2:
            _dbg("detect_visual: grayscale image, skipping")
            return []
        if arr.shape[2] == 4:
            arr = arr[:, :, :3]
        cs = min(10, h_px, w_px)  # 角落取样大小
        corners = [
            arr[:cs, :cs],
            arr[:cs, -cs:],
            arr[-cs:, :cs],
            arr[-cs:, -cs:],
        ]
        bg_color = np.median(np.concatenate([c.reshape(-1, 3) for c in corners], axis=0), axis=0)
        _dbg(f"detect_visual: bg_color={bg_color.astype(int).tolist()}")

        # 计算每个像素与背景色的色差（欧氏距离）
        diff = np.sqrt(np.sum((arr.astype(float) - bg_color) ** 2, axis=2))

        # 色差阈值：> 40 认为是非背景内容
        mask = (diff > 40).astype(np.uint8)

        # 排除 OCR 已识别的文字区域（在 mask 上置零）
        for item in ocr_items:
            # 转换为相对于裁剪区域的物理像素坐标
            ix = int((item["x"] - cx_min) * scale)
            iy = int((item["y"] - content_y_min) * scale)
            iw = int(item.get("w", 30) * scale)
            ih = int(item.get("h", 15) * scale)
            # 扩大文字区域边距，避免文字边缘被误检
            pad = int(8 * scale)
            x1 = max(0, ix - iw // 2 - pad)
            y1 = max(0, iy - ih // 2 - pad)
            x2 = min(w_px, ix + iw // 2 + pad)
            y2 = min(h_px, iy + ih // 2 + pad)
            mask[y1:y2, x1:x2] = 0

        # 连通域分析：找非背景像素簇
        # 简化实现：按行扫描，用 run-length 找连续非零区域，再垂直合并
        visual_elements = []
        visited = np.zeros_like(mask, dtype=bool)

        def _flood_bbox(sy, sx):
            """简单 BFS 找连通域的外接矩形。"""
            from collections import deque
            q = deque([(sy, sx)])
            visited[sy, sx] = True
            min_y, max_y = sy, sy
            min_x, max_x = sx, sx
            count = 0
            # 用步长加速扫描（每 2 像素采样）
            step = 2
            while q:
                cy, cx = q.popleft()
                count += 1
                if count > 50000:  # 防止超大区域卡死
                    break
                for dy, dx in [(-step, 0), (step, 0), (0, -step), (0, step)]:
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < h_px and 0 <= nx < w_px and not visited[ny, nx] and mask[ny, nx]:
                        visited[ny, nx] = True
                        min_y = min(min_y, ny)
                        max_y = max(max_y, ny)
                        min_x = min(min_x, nx)
                        max_x = max(max_x, nx)
                        q.append((ny, nx))
            return min_x, min_y, max_x - min_x, max_y - min_y, count

        # 降采样扫描（每 4 像素检查一次，提高速度）
        scan_step = 4
        for y in range(0, h_px, scan_step):
            for x in range(0, w_px, scan_step):
                if mask[y, x] and not visited[y, x]:
                    bx, by, bw, bh, pixel_count = _flood_bbox(y, x)
                    # 转换回逻辑坐标
                    lx = bx / scale + cx_min
                    ly = by / scale + content_y_min
                    lw = bw / scale
                    lh = bh / scale
                    center_x = lx + lw / 2

                    # 排除头像：约 30~45px 正方形，紧贴内容区左/右边缘
                    is_avatar = (25 < lw < 50 and 25 < lh < 50
                                 and abs(lw - lh) < 10  # 近似正方形
                                 and (lx < cx_min + 55 or lx + lw > content_x_max - 55))
                    if is_avatar:
                        _dbg(f"detect_visual: skipped avatar at ({int(center_x)},{int(ly+lh/2)}) {int(lw)}x{int(lh)}")
                        continue

                    # 排除消息气泡背景（白色/绿色矩形，覆盖面积大但颜色单一）
                    # 取区域内像素的色彩标准差，低则为纯色块（气泡），高则为图片
                    region_slice = arr[max(0,by):min(h_px,by+bh), max(0,bx):min(w_px,bx+bw)]
                    if region_slice.size > 0:
                        color_std = np.std(region_slice.reshape(-1, 3).astype(float), axis=0).mean()
                        _dbg(f"detect_visual: region ({int(lw)}x{int(lh)}) color_std={color_std:.1f}")
                        if color_std < 20:
                            _dbg(f"detect_visual: skipped low-variance region (bubble/bg)")
                            continue

                    # 分类
                    if lw > 80 and lh > 60:
                        elem_type = "image"
                    elif lw > 15 and lh > 15:
                        elem_type = "sticker"
                    else:
                        continue  # 太小，忽略

                    sender = "me" if center_x >= midline_x else "them"
                    desc = ""

                    # 图片内容识别：裁剪区域用 VNClassifyImageRequest 本地分类
                    if elem_type == "image":
                        desc = self._classify_image_region(arr, bx, by, bw, bh)

                    visual_elements.append({
                        "type": elem_type,
                        "x": int(center_x),
                        "y": int(ly + lh / 2),
                        "w": int(lw),
                        "h": int(lh),
                        "sender": sender,
                        "desc": desc,
                    })
                    _dbg(f"detect_visual: {elem_type} at ({int(center_x)},{int(ly+lh/2)}) {int(lw)}x{int(lh)} sender={sender} desc='{desc}'")

        _dbg(f"detect_visual: found {len(visual_elements)} visual elements")
        return visual_elements

    def _parse_messages(self, ocr_items: list[dict], rect: tuple, screenshot_path: str = None, is_group: bool = False) -> list[dict]:
        """
        将 OCR 条目 + 视觉元素解析为结构化消息列表。
        is_group=True 时，识别群聊中每条消息的实际发言人昵称。
        返回: [{"sender": "me"|"昵称"|"them", "text": str}, ...]
        """
        wx, wy, ww, wh = rect
        content_x = self._content_x_min(rect)
        content_w = wx + ww - content_x
        midline_x = content_x + content_w // 2

        # 过滤噪音
        items = [i for i in ocr_items if not self._is_noise(i["text"])]

        # 检测视觉元素（图片、表情）
        visual_items = []
        if screenshot_path:
            visual_items = self._detect_visual_elements(screenshot_path, ocr_items, rect)

        # 合并：文字条目 + 视觉元素，统一按 Y 排序
        all_items = []

        if is_group:
            # 群聊模式：基于视觉特征（x 位置 + 字体高度）区分昵称和消息
            # WeChat 布局：[头像] 昵称(小号灰色) → 气泡[消息(大号深色)]
            # 昵称紧贴头像右侧，x 偏左；消息在气泡内，x 偏右
            left_items = sorted([i for i in items if i["x"] < midline_x], key=lambda i: i["y"])
            right_items = [i for i in items if i["x"] >= midline_x]

            # 昵称区域 x 阈值：头像(~35px宽)在 content_x+10 处，昵称紧随其后
            nickname_x_max = content_x + 140

            # 收集左侧 h 值，用中位数区分昵称字体（小）和消息字体（大）
            left_h_values = [i.get("h", 0) for i in left_items]
            h_available = any(v > 0 for v in left_h_values)
            if h_available and left_h_values:
                median_h = sorted(left_h_values)[len(left_h_values) // 2]
                nickname_h_max = median_h * 0.9
            else:
                median_h = 0
                nickname_h_max = 0

            # 第一遍：标记昵称行
            nickname_ys = set()
            for item in left_items:
                text = item["text"].strip()
                h = item.get("h", 0)
                x = item["x"]

                if h_available:
                    # 主方案：x 位置（靠近头像）+ h 字体高度（小号字体）
                    is_nickname = (
                        x < nickname_x_max
                        and h < nickname_h_max
                        and len(text) <= 20
                    )
                else:
                    # h 不可用时回退：x 位置 + 排除含中文句内标点的文本
                    is_nickname = (
                        x < nickname_x_max
                        and len(text) <= 15
                        and not re.search(r'[，！？；：、]', text)
                    )

                if is_nickname:
                    nickname_ys.add(item["y"])
                    _dbg(f"Nickname detected: '{text}' at y={item['y']} x={x} h={h}")

            # 第二遍：构建左侧消息，关联最近的上方昵称
            current_nickname = None
            for item in left_items:
                if item["y"] in nickname_ys:
                    current_nickname = item["text"].strip()
                    continue
                sender = current_nickname or "them"
                all_items.append({"sender": sender, "text": item["text"].strip(), "_y": item["y"], "_type": "text"})

            # 右侧消息 = "me"
            for item in right_items:
                all_items.append({"sender": "me", "text": item["text"].strip(), "_y": item["y"], "_type": "text"})
        else:
            # 1:1 模式：原有逻辑
            for item in items:
                sender = "me" if item["x"] >= midline_x else "them"
                all_items.append({"sender": sender, "text": item["text"].strip(), "_y": item["y"], "_type": "text"})

        for ve in visual_items:
            if ve["type"] == "image":
                desc = ve.get("desc", "")
                label = f"[图片:{desc}]" if desc else "[图片]"
            else:
                label = "[表情]"
            all_items.append({"sender": ve["sender"], "text": label, "_y": ve["y"], "_type": ve["type"]})

        all_items.sort(key=lambda i: i["_y"])

        # 合并相邻同 sender 的条目（文字合并，但视觉标签独立保留）
        messages = []
        for item in all_items:
            text = item["text"]
            if not text:
                continue
            if item["_type"] != "text":
                messages.append({"sender": item["sender"], "text": text, "_y": item["_y"]})
                continue
            if messages and messages[-1]["sender"] == item["sender"] \
                    and messages[-1].get("_merge", True) \
                    and abs(item["_y"] - messages[-1]["_y"]) < 25:
                messages[-1]["text"] += " " + text
                messages[-1]["_y"] = item["_y"]
            else:
                messages.append({"sender": item["sender"], "text": text, "_y": item["_y"], "_merge": True})

        for m in messages:
            m.pop("_y", None)
            m.pop("_merge", None)

        return messages

    def _summarize(self, name: str, messages: list[dict], is_group: bool = False) -> str:
        """
        将消息列表压缩为极简文本摘要。
        群聊显示实际发言人昵称，1:1 聊天将 them 替换为对方名字。
        """
        if not is_group:
            for m in messages:
                if m["sender"] == "them":
                    m["sender"] = name
        recent = messages[-15:]  # 群聊需要更多上下文
        lines = [f"[OK] {name} ({len(recent)} msgs):"]
        for m in recent:
            txt = m["text"]
            if len(txt) > 80:
                txt = txt[:77] + "..."
            lines.append(f"  {m['sender']}: {txt}")
        return "\n".join(lines)

    # ── 私有：输入框和发送 ────────────────────────────────────────────────────

    def _click_input_box(self, rect: tuple) -> bool:
        """
        定位并点击输入框（使用焦点安全方法）。
        策略: 在底部区域找"发送"按钮，点击其左侧；或按坐标估算。
        """
        wx, wy, ww, wh = rect
        cx_min = self._content_x_min(rect)
        content_w = wx + ww - cx_min
        # 输入框在内容区底部，直接用计算位置（"发送"按钮 OCR 命中率低）
        input_x = cx_min + content_w // 2
        input_y = wy + wh - 45
        _dbg(f"click_input_box: clicking ({input_x}, {input_y})")
        self._focused_click(input_x, input_y)
        time.sleep(0.1)
        _dbg_screenshot("after_click_input_box")
        return True

    def _cgevent_type_chars(self, text: str):
        """通过 CGEvent 逐字符注入 Unicode 键盘事件，绕过剪贴板。"""
        for char in text:
            # Emoji 等 supplementary plane 字符在 UTF-16 中需要 surrogate pair
            utf16_len = len(char.encode('utf-16-le')) // 2
            event_down = CGEventCreateKeyboardEvent(None, 0, True)
            CGEventKeyboardSetUnicodeString(event_down, utf16_len, char)
            CGEventPost(kCGHIDEventTap, event_down)
            event_up = CGEventCreateKeyboardEvent(None, 0, False)
            CGEventKeyboardSetUnicodeString(event_up, utf16_len, char)
            CGEventPost(kCGHIDEventTap, event_up)
            time.sleep(random.uniform(0.03, 0.12))

    def _type_and_send(self, message: str, send: bool = True) -> bool:
        """
        通过 CGEvent Unicode 键盘事件逐字输入消息。
        将消息随机分块，配合人类节奏延迟，模拟真人打字行为。
        send=False 时只输入不按回车。
        """
        _dbg(f"type_and_send: '{message}' (send={send})")
        _dbg_screenshot("before_type_and_send")

        self._activate_wechat()

        # 将消息随机分成 1-4 字符的小块，模拟人类输入节奏
        i = 0
        while i < len(message):
            chunk_size = random.randint(1, 4)
            chunk = message[i:i + chunk_size]
            self._cgevent_type_chars(chunk)
            # 块间停顿：模拟思考/看屏幕
            time.sleep(random.uniform(0.05, 0.25))
            i += chunk_size

        if send:
            _dbg("Typed, pressing Enter")
            time.sleep(random.uniform(0.1, 0.25))
            press_key("enter")
            time.sleep(0.15)
        else:
            _dbg("Typed, NOT sending (--no-send)")
        _dbg_screenshot("after_type_and_send")
        return True

    def _verify_sent(self, message: str, rect: tuple, prefix: str = "") -> bool:
        """
        验证消息是否发送成功。
        用 accurate 模式搜索回复前缀中的关键词，检查内容区和聊天列表预览。
        """
        # 从前缀中提取 2+ 字符的中文/英文词作为搜索关键词
        prefix_keywords = re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{2,}', prefix)
        search_kw = prefix_keywords[0] if prefix_keywords else message[:4]
        _dbg(f"verify_sent: searching for '{search_kw}' (from prefix='{prefix}')")
        _dbg_screenshot("verify_sent")
        wx, wy, ww, wh = rect
        lx_min = self._chatlist_x_range(rect)[0]
        wx_max = wx + ww
        all_results = self._focused_find_text(search_kw, mode="accurate")
        # 必须在 WeChat 窗口范围内
        wechat_matches = [r for r in all_results
                          if lx_min < r["x"] < wx_max and wy < r["y"] < wy + wh]
        _dbg(f"verify_sent: '分身' matches in WeChat window: {len(wechat_matches)}")
        for m in wechat_matches:
            _dbg(f"  x={m['x']} y={m['y']} '{m['text']}'")
        if wechat_matches:
            return True
        keyword = message[:4] if len(message) >= 4 else message
        _dbg(f"verify_sent: fallback search '{keyword}'")
        all_results2 = self._focused_find_text(keyword, mode="accurate")
        wechat_matches2 = [r for r in all_results2
                           if lx_min < r["x"] < wx_max and wy < r["y"] < wy + wh]
        _dbg(f"verify_sent: fallback matches: {len(wechat_matches2)}")
        return len(wechat_matches2) > 0

    # ── 公开方法 ──────────────────────────────────────────────────────────────

    def chat_list(self) -> str:
        """
        列出聊天列表中可见的聊天名称。
        输出: [OK] N chats: 名1 | 名2 | ...
        """
        _init_debug("chat_list", {})
        if not self._activate_wechat():
            return "[ERR] 无法激活 WeChat"

        rect = self._get_window_rect()
        if not rect:
            return "[ERR] 找不到 WeChat 主窗口，请确认 WeChat 已打开"

        # 激活 WeChat + 全屏 OCR，筛选聊天列表区域内的文字
        wx, wy, ww, wh = rect
        list_x_min, list_x_max = self._chatlist_x_range(rect)
        all_items = self._focused_screen_text(mode="accurate")
        # 聊天列表项从 wy+60 开始（搜索栏在 wy~wy+60），底部留 80px 给 UI 按钮
        items = [i for i in all_items
                 if list_x_min < i["x"] < list_x_max
                 and wy + 60 < i["y"] < wy + wh - 80]

        # 过滤：只取高置信度、非噪音的短文本（聊天名称通常 2-20 字）
        names = []
        seen = set()
        for item in sorted(items, key=lambda i: i["y"]):
            txt = item["text"].strip()
            if self._is_noise(txt):
                continue
            if len(txt) < 2 or len(txt) > 30:
                continue
            if item["confidence"] < 0.5:
                continue
            if txt in seen:
                continue
            # 排除明显是消息预览的长文本
            if any(c in txt for c in ["：", ":", "...", "【"]):
                continue
            seen.add(txt)
            names.append(txt)

        if not names:
            return "[ERR] 未能识别到聊天列表，WeChat 可能未正常显示"

        preview = " | ".join(names[:12])
        return f"[OK] {len(names)} chats: {preview}"

    def _scroll_content_area(self, rect: tuple, direction: str = "up", pages: int = 1):
        """在内容区域滚动指定页数，用于加载更多历史消息。"""
        wx, wy, ww, wh = rect
        cx_min = self._content_x_min(rect)
        scroll_x = cx_min + (wx + ww - cx_min) // 2
        scroll_y = wy + wh // 2
        for _ in range(pages):
            scroll(scroll_x, scroll_y, direction, clicks=5)
            time.sleep(0.3)
        _dbg(f"Scrolled {direction} {pages} page(s) at ({scroll_x}, {scroll_y})")

    def chat_read(self, name: str) -> str:
        """
        导航到指定聊天，读取并返回对话摘要。
        支持群聊：自动检测群聊并识别每条消息的发言人。
        群聊先读底部（最新消息），再滚动上读历史，两次合并。
        """
        _init_debug("chat_read", {"name": name})
        if not self._navigate_to_chat(name):
            return f'[ERR] 找不到聊天 "{name}"，请检查名称是否正确'

        rect = self._get_window_rect()
        if not rect:
            return "[ERR] 获取窗口位置失败"

        is_group = self._is_group_chat(rect)
        _dbg(f"Chat type: {'group' if is_group else '1:1'}")

        if is_group:
            # 群聊第一步：先在底部（当前位置）OCR，捕获最新消息
            _dbg("Group chat: reading bottom (recent messages) first")
            _dbg_screenshot("group_bottom_before_ocr")
            bottom_ocr, bottom_path = self._read_content_area(rect)
            bottom_msgs = self._parse_messages(bottom_ocr, rect, bottom_path, is_group=True) if bottom_ocr else []
            _dbg(f"Group bottom read: {len(bottom_msgs)} messages")

            # 群聊第二步：向上滚动获取历史上下文
            scroll_pages = 3
            _dbg(f"Group chat: scrolling up {scroll_pages} pages for context")
            self._scroll_content_area(rect, "up", scroll_pages)
            _dbg_screenshot("after_group_scroll_up")

            top_ocr, top_path = self._read_content_area(rect)
            top_msgs = self._parse_messages(top_ocr, rect, top_path, is_group=True) if top_ocr else []
            _dbg(f"Group top read: {len(top_msgs)} messages")

            # 滚回底部
            self._scroll_content_area(rect, "down", scroll_pages)
            time.sleep(0.2)

            # 合并：历史消息在前 + 最新消息在后，按文本去重
            seen_texts = set()
            messages = []
            for msg in top_msgs + bottom_msgs:
                key = msg.get("text", "").strip()
                if key and key in seen_texts:
                    continue
                if key:
                    seen_texts.add(key)
                messages.append(msg)
            _dbg(f"Group merged: {len(messages)} messages (top:{len(top_msgs)} + bottom:{len(bottom_msgs)} - dedup)")
        else:
            # 1:1 聊天：原有逻辑
            ocr_items, screenshot_path = self._read_content_area(rect)
            messages = self._parse_messages(ocr_items, rect, screenshot_path) if ocr_items else []
            _dbg(f"Initial read: {len(messages)} messages")

            if len(messages) < 5:
                scroll_pages = 2 if len(messages) < 2 else 1
                _dbg(f"Messages insufficient ({len(messages)}), scrolling up {scroll_pages} page(s)")
                self._scroll_content_area(rect, "up", scroll_pages)
                _dbg_screenshot("after_scroll_up")

                ocr_items_more, screenshot_path_more = self._read_content_area(rect)
                if ocr_items_more:
                    messages_more = self._parse_messages(ocr_items_more, rect, screenshot_path_more)
                    if len(messages_more) > len(messages):
                        messages = messages_more
                        _dbg(f"After scroll: {len(messages)} messages")

                self._scroll_content_area(rect, "down", scroll_pages)
                time.sleep(0.2)

        if not messages:
            return f"[OK] {name} (0 msgs): 无可读取的文字内容（可能全是图片/表情）"

        return self._summarize(name, messages, is_group=is_group)

    def _load_config(self) -> dict:
        """读取 skill config.json，返回配置字典。"""
        config_path = SKILL_DIR / "config.json"
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def chat_reply(self, name: str, message: str, no_send: bool = False) -> str:
        """
        向指定聊天发送回复（自动添加 REPLY_PREFIX）。
        发送行为由 config.json 的 auto_send 决定：
          - auto_send: true  → 自动发送
          - auto_send: false → 只输入到输入框，不按回车（默认）
        CLI --no-send 参数可强制覆盖为不发送。
        输出: [OK] Sent/Typed to <name>: <full_message>
        """
        config = self._load_config()
        auto_send = config.get("auto_send", False)
        reply_prefix = config.get("reply_prefix", REPLY_PREFIX_DEFAULT)
        # --no-send CLI 参数优先级最高
        should_send = False if no_send else auto_send

        _init_debug("chat_reply", {"name": name, "message": message, "no_send": no_send, "auto_send": auto_send, "should_send": should_send})
        full_message = reply_prefix + message

        if not self._navigate_to_chat(name):
            return f'[ERR] 找不到聊天 "{name}"'

        rect = self._get_window_rect()
        if not rect:
            return "[ERR] 获取窗口位置失败"

        # 必须先点击输入框确保光标在正确位置，再粘贴发送
        if not self._click_input_box(rect):
            return "[ERR] 无法定位消息输入框"

        if not self._type_and_send(full_message, send=should_send):
            return "[ERR] 输入失败"

        if not should_send:
            return f"[OK] Typed to {name} (未发送，请在微信中确认后手动按回车): {full_message}"

        # 验证：检查消息是否出现在对话内容区 或 聊天列表预览中
        time.sleep(0.3)
        if self._verify_sent(message, rect, prefix=reply_prefix):
            return f"[OK] Sent to {name}: {full_message}"
        else:
            return f"[ERR] 消息可能未发送成功（未在对话中检测到），请手动检查"


# ── 未来扩展占位 ──────────────────────────────────────────────────────────────

class MomentsController:
    """朋友圈操作（未实现）"""
    def comment(self, content: str) -> str:
        return "[ERR] moments comment 尚未实现"


class ContactsController:
    """联系人操作（未实现）"""
    def tag(self, name: str, tag: str) -> str:
        return "[ERR] contacts tag 尚未实现"

    def approve(self) -> str:
        return "[ERR] contacts approve 尚未实现"

    def add(self, id_or_phone: str) -> str:
        return "[ERR] contacts add 尚未实现"


# ── CLI 入口 ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="WeChat 自动化 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 wechat.py chat list
  python3 wechat.py chat read Kent
  python3 wechat.py chat reply Kent "好的，明天见！"
        """
    )
    sub = parser.add_subparsers(dest="group", metavar="<group>")
    sub.required = True

    # ── chat ──────────────────────────────────────────────────────────────────
    chat_p = sub.add_parser("chat", help="聊天操作")
    chat_sub = chat_p.add_subparsers(dest="action", metavar="<action>")
    chat_sub.required = True

    chat_sub.add_parser("list", help="列出可见聊天")

    p_read = chat_sub.add_parser("read", help="读取聊天内容")
    p_read.add_argument("name", help="联系人或群组名称")

    p_reply = chat_sub.add_parser("reply", help="回复聊天")
    p_reply.add_argument("name", help="联系人或群组名称")
    p_reply.add_argument("message", help="回复内容（不含前缀，前缀自动添加）")
    p_reply.add_argument("--no-send", action="store_true", help="只输入到输入框，不按回车发送")

    # ── moments（占位） ───────────────────────────────────────────────────────
    moments_p = sub.add_parser("moments", help="朋友圈操作（未实现）")
    moments_sub = moments_p.add_subparsers(dest="action", metavar="<action>")
    moments_sub.required = True
    p_comment = moments_sub.add_parser("comment", help="评论朋友圈")
    p_comment.add_argument("content")

    # ── contacts（占位） ──────────────────────────────────────────────────────
    contacts_p = sub.add_parser("contacts", help="联系人操作（未实现）")
    contacts_sub = contacts_p.add_subparsers(dest="action", metavar="<action>")
    contacts_sub.required = True
    p_tag = contacts_sub.add_parser("tag", help="添加标签")
    p_tag.add_argument("name")
    p_tag.add_argument("tag")
    contacts_sub.add_parser("approve", help="通过好友申请")
    p_add = contacts_sub.add_parser("add", help="添加好友")
    p_add.add_argument("id_or_phone")

    args = parser.parse_args()

    # read/reply 需要控制鼠标键盘，必须互斥执行
    needs_lock = args.group == "chat" and args.action in ("read", "reply")
    lock_fd = None

    if needs_lock:
        lock_fd = open(LOCK_FILE, "w")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("[ERR] 另一个 wechat.py 实例正在操作中，请等待完成后重试")
            lock_fd.close()
            sys.exit(1)

    try:
        if args.group == "chat":
            ctrl = WeChatController()
            if args.action == "list":
                print(ctrl.chat_list())
            elif args.action == "read":
                print(ctrl.chat_read(args.name))
            elif args.action == "reply":
                print(ctrl.chat_reply(args.name, args.message, no_send=args.no_send))

        elif args.group == "moments":
            ctrl = MomentsController()
            if args.action == "comment":
                print(ctrl.comment(args.content))

        elif args.group == "contacts":
            ctrl = ContactsController()
            if args.action == "tag":
                print(ctrl.tag(args.name, args.tag))
            elif args.action == "approve":
                print(ctrl.approve())
            elif args.action == "add":
                print(ctrl.add(args.id_or_phone))

    except KeyboardInterrupt:
        print("\n[ERR] 被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"[ERR] 未预期错误: {e}")
        sys.exit(1)
    finally:
        if lock_fd:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()


if __name__ == "__main__":
    main()
