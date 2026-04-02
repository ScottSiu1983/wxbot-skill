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
    """
    拟人化输入文字。
    通过 macOS 底层 CGEvent 模拟真实按键，支持中文，且带有随机击键延迟以规避机器人检测。
    """
    from Quartz import (
        CGEventCreateKeyboardEvent,
        CGEventKeyboardSetUnicodeString,
        CGEventPost,
        kCGHIDEventTap
    )
    
    print(f"拟人化键入: {text!r}")
    
    for char in text:
        # 创建一个空键位的键盘事件
        # 128 是一个不存在的虚拟键位，我们主要通过 UnicodeString 注入内容
        event = CGEventCreateKeyboardEvent(None, 0, True)
        # 将字符注入事件
        CGEventKeyboardSetUnicodeString(event, len(char), char)
        # 投递按键按下事件
        CGEventPost(kCGHIDEventTap, event)
        
        # 模拟真实的打字节奏 (0.05s - 0.2s 的随机停顿)
        time.sleep(random.uniform(0.05, 0.15))
        
    time.sleep(0.3) # 完成后稍作停顿以稳固输入状态



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
        # 恢复为原始的 0.01s 间隔，提供更快速的物理滚动响应
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
