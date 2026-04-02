#!/usr/bin/env python3
"""
computer_use.py — 桌面动作执行器（"手"）

使用方式：
  python3 computer_use.py click 245 312
  python3 computer_use.py click 245 312 --double
  python3 computer_use.py click 245 312 --right
  python3 computer_use.py type "Hello 你好"
  python3 computer_use.py press enter
  python3 computer_use.py press command+space
  python3 computer_use.py scroll 400 300 down 3
"""

import argparse
import random
import subprocess
import sys
import time

import pyautogui
from Quartz.CoreGraphics import (
    CGEventCreateScrollWheelEvent,
    CGEventPost,
    kCGHIDEventTap,
    kCGScrollEventUnitPixel,
)

pyautogui.FAILSAFE = True   # 鼠标移到左上角紧急停止
pyautogui.PAUSE = 0.05


# ── 动作函数 ──────────────────────────────────────────────────────────────────

def click(x: int, y: int, double: bool = False, right: bool = False):
    if double:
        pyautogui.doubleClick(x, y)
        print(f"双击 ({x}, {y})")
    elif right:
        pyautogui.rightClick(x, y)
        print(f"右键 ({x}, {y})")
    else:
        pyautogui.click(x, y)
        print(f"点击 ({x}, {y})")


def type_text(text: str):
    """输入文字。中文/特殊字符通过剪贴板粘贴，ASCII 直接输入。"""
    has_non_ascii = any(ord(c) > 127 for c in text)
    if has_non_ascii:
        # 剪贴板粘贴（支持中文）
        proc = subprocess.run(
            ["pbcopy"], input=text.encode("utf-8"), check=True
        )
        pyautogui.hotkey("command", "v")
        print(f"粘贴文字: {text!r}")
    else:
        pyautogui.typewrite(text, interval=0.04)
        print(f"输入文字: {text!r}")
    time.sleep(0.1)


def press_key(key: str):
    """按键。支持组合键如 command+space、ctrl+c 等。"""
    if "+" in key:
        parts = key.split("+")
        pyautogui.hotkey(*parts)
    else:
        pyautogui.press(key)
    print(f"按键: {key}")


def scroll(x: int, y: int, direction: str, clicks: int = 3):
    delta = -clicks if direction == "down" else clicks
    pyautogui.scroll(delta, x=x, y=y)
    print(f"滚动 ({x}, {y}) {direction} {clicks}格")


def smooth_scroll(x: int, y: int, direction: str, distance: int = 200):
    """
    平滑滚动，模拟真实触摸板行为。
    使用 CGEvent 像素级滚动，以达到精准滚动1页的效果。
    """
    pyautogui.moveTo(x, y)
    time.sleep(0.1)

    # 计算滚动方向（正值向上滚动看旧消息，负值向下滚动看新消息）
    delta = distance if direction == "up" else -distance

    # 分解为多个小滚动事件（10 步）实现平滑过渡
    steps = 10
    per_step = delta // steps
    rem = delta % steps

    for i in range(steps):
        scroll_delta = per_step + (rem if i == steps - 1 else 0)
        # 创建像素级滚动事件
        event = CGEventCreateScrollWheelEvent(
            None,
            kCGScrollEventUnitPixel,
            1,
            scroll_delta
        )
        CGEventPost(kCGHIDEventTap, event)
        time.sleep(0.01)

    # 等待 UI 刷新
    time.sleep(1.0)
    print(f"平滑像素滚动 ({x}, {y}) {direction} {distance}px")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="桌面动作执行器")
    sub = parser.add_subparsers(dest="cmd")

    p_click = sub.add_parser("click")
    p_click.add_argument("x", type=int)
    p_click.add_argument("y", type=int)
    p_click.add_argument("--double", action="store_true")
    p_click.add_argument("--right", action="store_true")

    p_type = sub.add_parser("type")
    p_type.add_argument("text")

    p_press = sub.add_parser("press")
    p_press.add_argument("key")

    p_scroll = sub.add_parser("scroll")
    p_scroll.add_argument("x", type=int)
    p_scroll.add_argument("y", type=int)
    p_scroll.add_argument("direction", choices=["up", "down"])
    p_scroll.add_argument("clicks", type=int, nargs="?", default=3)

    args = parser.parse_args()

    if args.cmd == "click":
        click(args.x, args.y, double=args.double, right=args.right)
    elif args.cmd == "type":
        type_text(args.text)
    elif args.cmd == "press":
        press_key(args.key)
    elif args.cmd == "scroll":
        scroll(args.x, args.y, args.direction, args.clicks)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
