#!/usr/bin/env python3
"""
wechat.py — 统一 WeChat 自动化 CLI
"""

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

from local_vision import find_text, get_screen_text, take_screenshot, SCREEN_W
import computer_use as _cu

import objc
from Foundation import NSURL
from Quartz import (CGImageSourceCreateWithURL, CGImageSourceCreateImageAtIndex,
                     CGEventCreateKeyboardEvent, CGEventKeyboardSetUnicodeString,
                     CGEventPost, kCGHIDEventTap)
objc.loadBundle("Vision", globals(), bundle_path="/System/Library/Frameworks/Vision.framework")

SKILL_DIR = Path(__file__).resolve().parents[1]
DEBUG_DIR = SKILL_DIR / "debug"
LOCK_FILE = SKILL_DIR / ".wechat_ui.lock"
SESSION_FILE = DEBUG_DIR / ".session"
DEBUG = os.environ.get("WECHAT_DEBUG", "1") != "0"
DEBUG_MAX_ROUNDS = 10

def _get_session_id() -> str:
    now = time.time()
    session_timeout = 3600
    session_lock = DEBUG_DIR / ".session.lock"
    with open(session_lock, "w") as lock_f:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
        try:
            if SESSION_FILE.exists():
                try:
                    with open(SESSION_FILE) as f: data = json.load(f)
                    if now - data.get("last_time", 0) < session_timeout:
                        data["last_time"] = now
                        data["invocation_count"] = data.get("invocation_count", 0) + 1
                        with open(SESSION_FILE, "w") as f: json.dump(data, f)
                        return data["session_id"]
                except: pass
            sid = datetime.now().strftime("%Y%m%d_%H%M%S")
            data = {"session_id": sid, "created_at": now, "last_time": now, "invocation_count": 1}
            with open(SESSION_FILE, "w") as f: json.dump(data, f)
            return sid
        finally: fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)

def _init_debug(command: str, args: dict):
    global _debug_log_path, _debug_run_dir, _debug_step, _debug_start_time, _debug_last_time
    if not DEBUG: return
    sid = _get_session_id()
    _debug_step = 0
    _debug_start_time = time.time()
    _debug_last_time = _debug_start_time
    ts = datetime.now().strftime("%H%M%S")
    _debug_run_dir = DEBUG_DIR / sid / f"{ts}_{command}"
    _debug_run_dir.mkdir(parents=True, exist_ok=True)
    _debug_log_path = _debug_run_dir / "log.txt"
    _dbg(f"=== WeChat Skill Debug ===\nSession: {sid}\nCommand: {command}")

def _dbg(msg: str):
    global _debug_last_time
    if not DEBUG or not _debug_log_path: return
    now = time.time()
    prefix = f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] T={now-_debug_start_time:.2f}s +{now-_debug_last_time:.2f}s"
    _debug_last_time = now
    with open(_debug_log_path, "a") as f: f.write(f"{prefix} | {msg}\n")

def _dbg_screenshot(label: str) -> str | None:
    if not DEBUG or not _debug_run_dir: return None
    global _debug_step
    _debug_step += 1
    path = str(_debug_run_dir / f"{_debug_step:02d}_{label}.png")
    take_screenshot(path)
    return path

def _dbg_ocr(label: str, items: list[dict]):
    if not DEBUG: return
    _dbg(f"OCR [{label}]: {len(items)} items")
    for i in sorted(items, key=lambda x: (x["y"], x["x"])):
        _dbg(f"  x={i['x']:4d} y={i['y']:3d} c={i['confidence']:.2f} | {i['text']}")

# Constants
REPLY_PREFIX_DEFAULT = "[AI分身] "
SIDEBAR_W = 60
SETTLE = 0.35
MAX_RETRIES = 3
_NOISE_PATTERNS = [
    r"^\d{1,2}:\d{2}$", r"^\d{1,2}月\d{1,2}日$", r"^(昨天|今天|星期[一二三四五六日])$",
    r"^\d+条新消息.*", r"^Q?\d{2}:\d{2}$", r"^发送$", r"^搜索$", r"^折叠置顶聊天$",
    r"^\[.*?\]$", r"^-+$", r"^Search$", r"^\s*$", r"^\d+$"
]

def _load_config():
    config_path = SKILL_DIR / "config.json"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}

class WeChatController:
    def __init__(self):
        self._layout_anchors = None
        self._window_rect_cache = None
        self._wechat_activated = False
        self._last_click_pos = (0, 0)
        self._last_screenshot = None

    def chat_list(self) -> str:
        _init_debug("chat_list", {})
        rect = self._get_window_rect()
        xmin, xmax = self._chatlist_x_range(rect)
        wy = rect[1]
        wh = rect[3]
        all_res = self._focused_screen_text("accurate")
        list_items = [i for i in all_res if xmin < i["x"] < xmax and wy + 60 < i["y"] < wy + wh - 80]
        names = []
        for i in list_items:
            t = i["text"].strip()
            if not self._is_noise(t):
                if t not in names: names.append(t)
        return f"[OK] {len(names)} chats: " + " | ".join(names)

    def _activate_wechat(self, force: bool = False) -> bool:
        """通过 AppleScript 强制激活 WeChat 到最前台。"""
        if self._wechat_activated and not force: return True
        script = '''
tell application "WeChat" to activate
delay 0.1
tell application "System Events"
    tell process "WeChat"
        set frontmost to true
    end tell
end tell
'''
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=3)
        if result.returncode == 0:
            self._wechat_activated = True
            return True
        return False

    def _activate_and_get_rect(self) -> tuple:
        """激活 WeChat 并获取窗口位置。"""
        self._activate_wechat()
        script = '''
tell application "System Events"
    tell process "WeChat"
        set frontmost to true
        set w to window 1 where title is "微信"
        set p to position of w
        set s to size of w
        return ((item 1 of p) as string) & "," & ((item 2 of p) as string) & "," & ((item 1 of s) as string) & "," & ((item 2 of s) as string)
    end tell
end tell'''
        try:
            result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=3)
            raw = result.stdout.strip()
            if raw:
                parts = [int(v) for v in raw.split(",")]
                if len(parts) == 4:
                    self._window_rect_cache = tuple(parts)
                    return self._window_rect_cache
        except Exception as e:
            pass
        
        import pyautogui
        sw, sh = pyautogui.size()
        return (sw // 4, 33, sw // 2, sh - 33)

    def _get_window_rect(self) -> tuple:
        if self._window_rect_cache: return self._window_rect_cache
        return self._activate_and_get_rect()

    def _focused_click(self, x, y):
        self._activate_wechat(); _cu.click(x, y); self._last_click_pos = (x, y)

    def _focused_press(self, key):
        self._activate_wechat(); _cu.press_key(key)

    def _focused_find_text(self, target: str, mode: str = "accurate") -> list[dict]:
        self._activate_wechat(); return find_text(target, mode=mode)

    def _focused_screen_text(self, mode="accurate"):
        self._activate_wechat(); return get_screen_text(mode=mode)

    def _detect_absolute_layout(self, rect: tuple) -> dict:
        """核心布局解剖：识别侧边栏、消息泳道以及各功能块坐标。"""
        if self._layout_anchors and self._window_rect_cache == rect: return self._layout_anchors
        wx, wy, ww, wh = rect
        from PIL import Image
        path = take_screenshot()
        self._last_screenshot = path
        img = Image.open(path)
        img_np = np.array(img)
        
        # 探测 Retina 缩放倍率
        scale = img_np.shape[1] / SCREEN_W
        def L2P(v): return int(v * scale)
        def P2L(v): return int(v / scale)

        # 1. 探测纵向泳道分界 (X 轴)
        # 参考 xray: 在窗口中间选取样本点进行验证
        scan_y_samples = [L2P(wy + wh // 4), L2P(wy + wh // 2), L2P(wy + wh * 3 // 4)]
        v_line_x = None
        for px in range(L2P(wx + ww // 2), L2P(wx + ww - 50)):
            is_cand = False
            for sy in scan_y_samples:
                c_curr, c_left = img_np[sy, px].astype(np.int16), img_np[sy, px-1].astype(np.int16)
                if np.sum(np.abs(c_curr - c_left)) > 15:
                    is_cand = True; break
            if is_cand:
                # 垂直贯穿校验
                matches, total = 0, 0
                for sy_check in range(L2P(wy + 80), L2P(wy + wh - 80), 10):
                    total += 1
                    if np.sum(np.abs(img_np[sy_check, px].astype(np.int16) - img_np[sy_check, px-1].astype(np.int16))) > 10: matches += 1
                if matches / total > 0.7: v_line_x = P2L(px); break
        if not v_line_x: v_line_x = wx + int(ww * 0.33)
        
        # 2. 在消息流泳道内探测横向分界 (Y 轴)
        p_lx, p_rx = L2P(v_line_x), L2P(wx + ww)
        scan_x_samples = [int(p_lx + (p_rx - p_lx) * 0.25), int(p_lx + (p_rx - p_lx) * 0.5), int(p_lx + (p_rx - p_lx) * 0.75)]
        h_lines = []
        for py in range(L2P(wy + 20), L2P(wy + wh - 20)):
            is_cand = False
            for sx in scan_x_samples:
                c_curr, c_up = img_np[py, sx].astype(np.int16), img_np[py-1, sx].astype(np.int16)
                if np.sum(np.abs(c_curr - c_up)) > 15:
                    is_cand = True; break
            if is_cand:
                # 水平贯穿校验
                matches, total = 0, 0
                for sx_check in range(p_lx + 5, p_rx - 5, 10):
                    total += 1
                    if np.sum(np.abs(img_np[py, sx_check].astype(np.int16) - img_np[py-1, sx_check].astype(np.int16))) > 10: matches += 1
                if matches / total > 0.85:
                    ly = P2L(py)
                    if not h_lines or ly - h_lines[-1] > 5: h_lines.append(ly)
        
        # 3. 筛选消息流逻辑：寻找最大的横向间隙作为消息列表
        # 同时利用颜色特征辅助：消息流通常背景较浅（接近白色），输入区通常有浅灰色背景
        bounds = [wy] + h_lines + [wy + wh]
        candidates = []
        for i in range(len(bounds) - 1):
            ty, by = bounds[i], bounds[i+1]
            gap = by - ty
            if gap > 150: # 消息区域至少有一定高度
                # 采样块中心颜色以确认是否为消息流（通常比输入区更白）
                p_my = L2P(ty + gap // 2)
                p_mx = L2P(wx + ww // 2)
                if p_my < img_np.shape[0] and p_mx < img_np.shape[1]:
                    avg_color = np.mean(img_np[p_my-5:p_my+5, p_mx-5:p_mx+5], axis=(0,1))
                    score = gap * (1 if np.mean(avg_color) > 230 else 0.5) # 偏向白色区域
                    candidates.append((score, ty, by))
        
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            _, bt, bb = candidates[0]
        else:
            bt, bb = wy + 60, wy + wh - 130
        
        # 严格锁定 ymax (bb) 到探测到的最后一条划线
        layout = {
            'v_divide_x': v_line_x,
            'title_bar': (wy, bt),
            'message_flow': (bt + 1, bb - 2), # 留出 1-2 像素避免踩线
            'input_box': (bb, wy + wh)
        }
        self._layout_anchors, self._window_rect_cache = layout, rect
        _dbg(f"Layout ANALYZED: X={v_line_x}, Y={layout['message_flow']}")
        return layout

    def _content_x_min(self, rect): return self._detect_absolute_layout(rect)['v_divide_x']
    def _detect_content_y_min(self, rect): return self._detect_absolute_layout(rect)['message_flow'][0]
    def _detect_content_y_max(self, rect): return self._detect_absolute_layout(rect)['message_flow'][1]
    def _chatlist_x_range(self, rect): return (rect[0]+SIDEBAR_W, self._content_x_min(rect))

    def _click_search_bar(self, rect):
        wx, wy, ww, wh = rect
        xmin, xmax = self._chatlist_x_range(rect)
        items = [i for i in self._focused_screen_text("accurate") if xmin < i["x"] < xmax and wy < i["y"] < wy + 80]
        cands = [i for i in items if "搜索" in i["text"]]
        if cands:
            best = sorted(cands, key=lambda x: x["confidence"], reverse=True)[0]
            self._focused_click(best["x"], best["y"])
            return best["y"]
        self._focused_click(xmin + 40, wy + 35); return wy + 35

    def _navigate_to_chat(self, name: str) -> bool:
        rect = self._activate_and_get_rect()
        if not rect: return False
        if self._verify_chat_open(name, rect): return True
        xmin, xmax = self._chatlist_x_range(rect)
        for attempt in range(MAX_RETRIES):
            _dbg(f"Nav attempt {attempt+1}")
            all_res = self._focused_find_text(name, mode="fast")
            matches = [r for r in all_res if xmin < r["x"] < xmax and r["confidence"] >= 0.4]
            if matches:
                best = sorted(matches, key=lambda r: r["confidence"], reverse=True)[0]
                self._focused_click(best["x"], best["y"])
                time.sleep(SETTLE)
                if self._verify_chat_open(name, rect): return True
            self._focused_press("escape")
            self._click_search_bar(rect)
            time.sleep(0.3)
            subprocess.run(["pbcopy"], input=name.encode("utf-8"), check=True)
            self._focused_press("command+v")
            time.sleep(3.0)
            all_txt = [i for i in self._focused_screen_text("accurate") if rect[0] < i["x"] < rect[0]+rect[2]]
            all_txt.sort(key=lambda i: i["y"])
            target = None
            for i in all_txt:
                # 排除搜索框本身（位于窗口顶部约 90 像素以内）
                if i["y"] < rect[1] + 90:
                    continue
                if name.lower() in i["text"].lower().replace(" ", ""): target = i; break
            if target:
                self._focused_click(target["x"], target["y"])
                time.sleep(1.0)
                if self._verify_chat_open(name, rect): return True
            self._focused_press("escape")
        return False

    def _is_group_chat(self, rect):
        xmin, xmax = self._content_x_min(rect), rect[0]+rect[2]
        ymin, ymax = rect[1], self._detect_content_y_min(rect)
        title_items = [i for i in self._focused_screen_text("fast") if xmin < i["x"] < xmax and ymin < i["y"] < ymax]
        return any(re.search(r'\(\d+\)', i["text"]) for i in title_items)

    def _verify_chat_open(self, name, rect):
        # 核心修复：xmin 必须从内容区开始，不能包含左侧聊天列表，否则会误匹配列表里的名字
        xmin, xmax = self._content_x_min(rect), rect[0]+rect[2]
        ymin, ymax = rect[1], self._detect_content_y_min(rect)
        items = self._focused_screen_text("accurate")
        title_items = [i for i in items if xmin < i["x"] < xmax and ymin < i["y"] < ymax]
        
        target = name.lower().replace(" ", "")
        found_texts = [i["text"].lower().replace(" ", "") for i in title_items]
        _dbg(f"Verify chat '{name}' in titles: {found_texts}")
        
        for t in found_texts:
            if target in t or t in target: return True
            # 如果匹配度足够高（前 4 位一致）
            if len(target) >= 4 and target[:4] in t: return True
        return False

    def _is_noise(self, text):
        t = text.strip()
        if not t or (len(t) <= 1 and not re.match(r'[\u4e00-\u9fff]', t)): return True
        return any(re.match(p, t) for p in _NOISE_PATTERNS)

    def _detect_visual_elements(self, screenshot_path, ocr_items, rect):
        from PIL import Image
        img = Image.open(screenshot_path); scale = img.size[0] / SCREEN_W
        xmin, xmax = self._content_x_min(rect), rect[0]+rect[2]
        ymin, ymax = self._detect_content_y_min(rect), self._detect_content_y_max(rect)
        arr = np.array(img.crop((int(xmin*scale), int(ymin*scale), int(xmax*scale), int(ymax*scale))))
        if arr.ndim == 2: return [], [], []
        if arr.shape[2] == 4: arr = arr[:, :, :3]
        h_px, w_px = arr.shape[:2]
        bg_color = np.median(arr[:10, :10].reshape(-1,3), axis=0)
        mask = (np.sqrt(np.sum((arr.astype(float)-bg_color)**2, axis=2)) > 15).astype(np.uint8)
        for i in ocr_items:
            ix, iy = int((i["x"]-xmin)*scale), int((i["y"]-ymin)*scale)
            pad = int(8*scale)
            mask[max(0,iy-pad):min(h_px,iy+pad), max(0,ix-pad):min(w_px,ix+pad)] = 0
        visuals, avatars, quotes = [], [], []
        visited = np.zeros_like(mask, dtype=bool)
        def _flood(sy, sx):
            from collections import deque
            q, mn_y, mx_y, mn_x, mx_x = deque([(sy, sx)]), sy, sy, sx, sx
            visited[sy,sx] = True
            while q:
                cy, cx = q.popleft()
                for dy, dx in [(-2,0),(2,0),(0,-2),(0,2)]:
                    ny, nx = cy+dy, cx+dx
                    if 0<=ny<h_px and 0<=nx<w_px and not visited[ny,nx] and mask[ny,nx]:
                        visited[ny,nx]=True; mn_y=min(mn_y,ny); mx_y=max(mx_y,ny); mn_x=min(mn_x,nx); mx_x=max(mx_x,nx); q.append((ny,nx))
            return mn_x, mn_y, mx_x-mn_x, mx_y-mn_y
        for y in range(0, h_px, 4):
            for x in range(0, w_px, 4):
                if mask[y,x] and not visited[y,x]:
                    bx, by, bw, bh = _flood(y, x)
                    lx, ly, lw, lh = bx/scale+xmin, by/scale+ymin, bw/scale, bh/scale
                    cx = lx + lw/2
                    # 放宽头像判定范围 (WeChat 桌面版通常在 35-45 逻辑像素之间)
                    if 30<lw<55 and 30<lh<55 and abs(lw-lh)<10:
                        avatars.append({"x":int(lx),"y":int(ly),"w":int(lw),"h":int(lh),"is_me":cx>(xmin+(xmax-xmin)*0.8)})
                        continue
                    std = np.std(arr[by:by+bh, bx:bx+bw].reshape(-1,3), axis=0).mean()
                    if 20<=std<45 and 50<lw<600 and 15<lh<150: quotes.append({"x":int(lx),"y":int(ly),"w":int(lw),"h":int(lh)}); continue
                    if std < 20: continue
                    visuals.append({"type":"image" if lw>80 else "sticker", "x":int(cx), "y":int(ly+lh/2), "sender":"me" if cx>(xmin+(xmax-xmin)//2) else "them"})
        return visuals, avatars, quotes

    def _read_content_area(self, rect: tuple) -> tuple[list[dict], str | None]:
        xmin, xmax = self._content_x_min(rect), rect[0]+rect[2]
        ymin, ymax = self._detect_content_y_min(rect), self._detect_content_y_max(rect)
        path = take_screenshot()
        self._last_screenshot = path
        all_items = self._focused_screen_text(mode="accurate")
        filtered = [i for i in all_items if xmin < i["x"] < xmax and ymin < i["y"] < ymax]
        return filtered, path

    def _parse_messages(self, ocr_items, rect, screenshot_path=None, is_group=False):
        xmin, xmax = self._content_x_min(rect), rect[0]+rect[2]
        ymin, ymax = self._detect_content_y_min(rect), self._detect_content_y_max(rect)
        mid_x = xmin + (xmax-xmin)//2
        items = [i for i in ocr_items if not self._is_noise(i["text"])]
        vis, avs, qbs = [], [], []
        if screenshot_path: vis, avs, qbs = self._detect_visual_elements(screenshot_path, ocr_items, rect)
        all_msgs = []
        if is_group:
            all_avs = sorted(avs, key=lambda a: a["y"])
            if items and (not all_avs or items[0]["y"] < all_avs[0]["y"] - 15):
                is_me_v = items[0]["x"] > (mid_x + 50)
                all_avs.insert(0, {"x": (xmax-50) if is_me_v else (xmin+5), "y": ymin, "w":40, "h":40, "is_me":is_me_v, "virtual":True})
            for i, av in enumerate(all_avs):
                atop, al, is_me, is_v = av["y"], av["x"], av.get("is_me", False), av.get("virtual", False)
                abottom = all_avs[i+1]["y"] if i+1 < len(all_avs) else ymax
                m_txts = []
                for it in items:
                    if (is_me and xmin-20 < it["x"] < al+15) or (not is_me and al+av["w"]-15 < it["x"] < xmax+20):
                        if atop-15 < it["y"] < abottom: m_txts.append(it)
                if not m_txts and not any(atop-15 < v["y"] < abottom for v in vis): continue
                m_txts.sort(key=lambda x: x["y"])
                qs = [qb for qb in qbs if atop-15 < qb["y"] < abottom]
                q_sum, final_txts = "", m_txts
                if qs and m_txts:
                    qp, rem = [], []
                    for it in m_txts:
                        if any(q["x"]-10 < it["x"] < q["x"]+q["w"]+10 and q["y"]-10 < it["y"] < q["y"]+q["h"]+10 for q in qs): qp.append(it["text"])
                        else: rem.append(it)
                    if qp: q_sum, final_txts = f"[引用: {' '.join(qp)}]", rem
                if is_me: sender, start = "me", 0
                else: sender = "them" if is_v else (final_txts[0]["text"] if final_txts else "them"); start = 0 if is_v else 1
                body = [q_sum] if q_sum else []
                for it in final_txts[start:]: body.append(it["text"])
                m_vis = [("[图片]" if v["type"]=="image" else "[表情]") for v in vis if atop-15 < v["y"] < abottom]
                txt = " ".join(body + m_vis)
                if txt: all_msgs.append({"sender": sender, "text": txt, "_y": atop})
        else:
            for it in items: all_msgs.append({"sender": "me" if it["x"] >= mid_x else "them", "text": it["text"], "_y": it["y"]})
            for v in vis: all_msgs.append({"sender": v["sender"], "text": "[图片]" if v["type"]=="image" else "[表情]", "_y": v["y"]})
        all_msgs.sort(key=lambda x: x["_y"])
        res = []
        for m in all_msgs:
            if res and res[-1]["sender"] == m["sender"] and abs(m["_y"]-res[-1].get("_y",0)) < 30: res[-1]["text"] += " " + m["text"]; res[-1]["_y"] = m["_y"]
            else: res.append(m)
        for m in res: m.pop("_y", None)
        return res

    def _summarize(self, name, messages, is_group=False):
        if not is_group:
            for m in messages:
                if m["sender"] == "them": m["sender"] = name
        res = [f"[OK] {name} ({len(messages)} msgs):"]
        for m in messages[-15:]:
            txt = m["text"].replace("\n", " ").strip()
            res.append(f"  {m['sender']}: {txt[:120]}")
        return "\n".join(res)

    def _activate_and_get_rect(self):
        self._activate_wechat()
        script = 'tell application "System Events" to tell process "WeChat" to tell window "微信"\nset p to position\nset s to size\nreturn (item 1 of p as string) & "," & (item 2 of p as string) & "," & (item 1 of s as string) & "," & (item 2 of s as string)\nend tell'
        try:
            res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True).stdout.strip()
            p = [int(v) for v in res.split(",")]
            self._window_rect_cache = tuple(p)
            return self._window_rect_cache
        except: return (0, 33, 800, 600)

    def _scroll_content_area(self, rect, dir="up", pages=1):
        xmin, xmax = self._content_x_min(rect), rect[0]+rect[2]
        ymin, ymax = self._detect_content_y_min(rect), self._detect_content_y_max(rect)
        for _ in range(pages):
            # 将滚动幅度调整为消息流区域高度的 90% (0.9)，配合 slower scroll 减震
            _cu.smooth_scroll(xmin+(xmax-xmin)//2, ymin+(ymax-ymin)//2, dir, distance=int((ymax-ymin)*0.90))
            time.sleep(1.0)

    def chat_read(self, name: str) -> str:
        _init_debug("chat_read", {"name": name})
        if not self._navigate_to_chat(name): return f'[ERR] 找不到聊天 "{name}"'
        rect = self._get_window_rect()
        is_group = self._is_group_chat(rect)
        all_messages = []
        items, path = self._read_content_area(rect)
        all_messages.append(self._parse_messages(items, rect, path, is_group))
        for _ in range(2):
            self._scroll_content_area(rect, "up", 1)
            items, path = self._read_content_area(rect)
            all_messages.append(self._parse_messages(items, rect, path, is_group))
        self._scroll_content_area(rect, "down", 2)
        seen, final = set(), []
        for msgs in reversed(all_messages):
            for m in msgs:
                key = (m["sender"], m["text"].strip())
                if key not in seen: seen.add(key); final.append(m)
        return self._summarize(name, final, is_group)

    def chat_reply(self, name, message, auto_send=None):
        _init_debug("chat_reply", {"name":name})
        if not self._navigate_to_chat(name): return f'[ERR] 找不到聊天 "{name}"'
        rect = self._get_window_rect()
        ymin, ymax = self._detect_content_y_min(rect), self._detect_content_y_max(rect)
        self._focused_click(rect[0]+rect[2]-25, rect[1]+rect[3]-25)
        
        cfg = _load_config()
        # 统一 auto_send 控制体系：命令行若未配置，则继承 config.json (默认 False 不抛出)
        final_auto_send = auto_send if auto_send is not None else cfg.get("auto_send", False)
            
        prefix = cfg.get("reply_prefix", REPLY_PREFIX_DEFAULT)
        full = prefix + message
        self._activate_wechat()
        _cu.type_text(full)
        if final_auto_send: 
            _cu.press_key("enter")
            return f"[OK] Sent to {name}: {full}"
        else:
            return f"[OK] Typed to {name} (未发送，请在微信中确认后手动按回车): {full}"

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="group")
    chat = sub.add_parser("chat")
    chat_sub = chat.add_subparsers(dest="action")
    chat_sub.add_parser("list")
    p_read = chat_sub.add_parser("read"); p_read.add_argument("name")
    p_reply = chat_sub.add_parser("reply"); p_reply.add_argument("name"); p_reply.add_argument("message"); p_reply.add_argument("--auto-send", action=argparse.BooleanOptionalAction, default=None, dest="auto_send")
    args = parser.parse_args()
    ctrl = WeChatController()
    if args.group == "chat":
        if args.action == "list": print(ctrl.chat_list())
        elif args.action == "read": print(ctrl.chat_read(args.name))
        elif args.action == "reply": print(ctrl.chat_reply(args.name, args.message, auto_send=args.auto_send))

if __name__ == "__main__":
    main()
