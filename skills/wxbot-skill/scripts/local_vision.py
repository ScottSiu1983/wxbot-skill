#!/usr/bin/env python3
"""
local_vision.py — 本地快速 OCR 模块（macOS Vision 框架）

使用方式：
  python3 local_vision.py find_text "Kent"
  python3 local_vision.py find_text "Kent" --mode accurate
  python3 local_vision.py get_screen_text
  python3 local_vision.py get_screen_text --region 846,33,624,923

输出：JSON 到 stdout，错误到 stderr
坐标：pyautogui 逻辑坐标（1470x956 空间），可直接用于点击
"""

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import objc
import pyautogui
from Quartz import (
    CGDataProviderCreateWithFilename,
    CGImageSourceCreateWithURL,
    CGImageSourceCreateImageAtIndex,
)
from Foundation import NSURL, NSArray

# 加载 Vision 框架
objc.loadBundle(
    "Vision",
    globals(),
    bundle_path="/System/Library/Frameworks/Vision.framework",
)

SCREEN_W, SCREEN_H = pyautogui.size()  # 逻辑分辨率，e.g. 1470x956


# ── 截图 ──────────────────────────────────────────────────────────────────────

def take_screenshot(path: str = None) -> str:
    """截图保存到文件，返回路径。约 176ms。"""
    if path is None:
        path = tempfile.mktemp(suffix=".png")
    subprocess.run(["screencapture", "-x", path], check=True)
    return path


# ── Vision OCR ────────────────────────────────────────────────────────────────

def _run_vision_ocr(image_path: str, mode: str = "fast") -> list[dict]:
    """
    用 macOS Vision 框架对图片做 OCR。
    mode: "fast" (~100ms) 或 "accurate" (~800ms)
    返回: [{"text": str, "x": int, "y": int, "w": int, "h": int, "confidence": float}]
    坐标为 pyautogui 逻辑坐标（中心点），可直接用于点击。
    """
    url = NSURL.fileURLWithPath_(image_path)
    source = CGImageSourceCreateWithURL(url, None)
    if source is None:
        raise RuntimeError(f"无法读取图片：{image_path}")
    cg_image = CGImageSourceCreateImageAtIndex(source, 0, None)
    if cg_image is None:
        raise RuntimeError(f"无法解码图片：{image_path}")

    # 同步方式：创建 request 不带 completion handler，执行后直接读 results()
    req = VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLanguages_(["zh-Hans", "zh-Hant", "en"])
    req.setUsesLanguageCorrection_(True)
    if mode == "fast":
        req.setRecognitionLevel_(1)   # VNRequestTextRecognitionLevelFast = 1
    else:
        req.setRecognitionLevel_(0)   # VNRequestTextRecognitionLevelAccurate = 0

    img_handler = VNImageRequestHandler.alloc().initWithCGImage_options_(cg_image, {})
    err = None
    ok = img_handler.performRequests_error_([req], err)
    if not ok:
        raise RuntimeError(f"Vision OCR 执行失败")

    observations = req.results()
    results = []
    if observations:
        for obs in observations:
            candidates = obs.topCandidates_(1)
            if not candidates:
                continue
            c = candidates[0]
            text = str(c.string())
            confidence = float(c.confidence())
            bbox = obs.boundingBox()  # 归一化坐标，原点左下角
            cx = int((bbox.origin.x + bbox.size.width / 2) * SCREEN_W)
            cy = int((1 - bbox.origin.y - bbox.size.height / 2) * SCREEN_H)
            w = int(bbox.size.width * SCREEN_W)
            h = int(bbox.size.height * SCREEN_H)
            results.append({
                "text": text,
                "x": cx,
                "y": cy,
                "w": w,
                "h": h,
                "confidence": round(confidence, 3),
            })
    return results


# ── 公开 API ──────────────────────────────────────────────────────────────────

def get_screen_text(region=None, mode: str = "fast") -> list[dict]:
    """
    截图并 OCR，返回所有识别到的文字及坐标。
    region: (x, y, w, h) 逻辑坐标，None 表示全屏
    """
    path = take_screenshot()
    try:
        if region:
            from PIL import Image
            img = Image.open(path)
            # 逻辑坐标 -> 物理坐标（2x Retina）
            scale = img.size[0] / SCREEN_W
            rx, ry, rw, rh = region
            img_crop = img.crop((
                int(rx * scale), int(ry * scale),
                int((rx + rw) * scale), int((ry + rh) * scale),
            ))
            crop_path = tempfile.mktemp(suffix=".png")
            img_crop.save(crop_path)
            # OCR 裁剪区域，坐标需要偏移回全屏空间
            raw = _run_vision_ocr(crop_path, mode)
            Path(crop_path).unlink(missing_ok=True)
            # 坐标偏移
            for item in raw:
                item["x"] += rx
                item["y"] += ry
            return raw
        else:
            return _run_vision_ocr(path, mode)
    finally:
        Path(path).unlink(missing_ok=True)


def find_text(target: str, mode: str = "fast", region=None) -> list[dict]:
    """
    在屏幕上查找包含 target 的文字，返回匹配项（按 confidence 降序）。
    匹配为大小写不敏感的子串匹配。
    """
    all_text = get_screen_text(region=region, mode=mode)
    target_lower = target.lower()
    matches = [
        item for item in all_text
        if target_lower in item["text"].lower()
    ]
    matches.sort(key=lambda x: x["confidence"], reverse=True)
    return matches


def screenshot_and_find(target: str) -> dict | None:
    """便捷方法：截图 + 查找，返回最佳匹配或 None。"""
    matches = find_text(target, mode="fast")
    return matches[0] if matches else None


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_region(s: str):
    parts = [int(v.strip()) for v in s.split(",")]
    return tuple(parts)  # (x, y, w, h)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="本地 OCR 工具")
    sub = parser.add_subparsers(dest="cmd")

    p_find = sub.add_parser("find_text")
    p_find.add_argument("target")
    p_find.add_argument("--mode", default="fast", choices=["fast", "accurate"])
    p_find.add_argument("--region", default=None)

    p_all = sub.add_parser("get_screen_text")
    p_all.add_argument("--mode", default="fast", choices=["fast", "accurate"])
    p_all.add_argument("--region", default=None)

    args = parser.parse_args()

    t0 = time.time()
    region = _parse_region(args.region) if args.region else None

    if args.cmd == "find_text":
        result = find_text(args.target, mode=args.mode, region=region)
    elif args.cmd == "get_screen_text":
        result = get_screen_text(region=region, mode=args.mode)
    else:
        parser.print_help()
        sys.exit(1)

    elapsed = int((time.time() - t0) * 1000)
    sys.stderr.write(f"[local_vision] {elapsed}ms\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
