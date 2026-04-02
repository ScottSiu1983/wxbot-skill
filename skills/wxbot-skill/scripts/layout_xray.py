#!/usr/bin/env python3
import os
import sys
import subprocess
import json
import time
from pathlib import Path
from PIL import Image
import numpy as np

# 加载本地工程模块
CUR_DIR = Path(__file__).resolve().parent
sys.path.append(str(CUR_DIR))
from local_vision import get_screen_text, take_screenshot

def get_wechat_rect():
    # 终极逻辑：从所有窗口中挑个最大的，作为主界面进行解剖
    script = '''
tell application "System Events"
    tell process "WeChat"
        set allW to every window
        set maxA to 0
        set bestW to ""
        repeat with w in allW
            try
                set s to size of w
                set a to (item 1 of s) * (item 2 of s)
                if a > maxA then
                    set maxA to a
                    set p to position of w
                    set bestW to ((item 1 of p) as string) & "," & ((item 2 of p) as string) & "," & ((item 1 of s) as string) & "," & ((item 2 of s) as string)
                end if
            end try
        end repeat
        return bestW
    end tell
end tell'''
    try:
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True).stdout.strip()
        if not res: return None
        return [int(v) for v in res.split(",")]
    except:
        return None

def detect_lines(img_np, axis, start, end, cross_start, cross_end, threshold=20, ratio=0.85):
    """
    通用线段探测。
    axis=0: 找垂直线 (X方向变化)
    axis=1: 找水平线 (Y方向变化)
    """
    lines = []
    # 在交叉轴方向取三个样本位置进行加权验证，提高稳定性
    sample_pts = [
        int(cross_start + (cross_end - cross_start) * 0.25),
        int(cross_start + (cross_end - cross_start) * 0.50),
        int(cross_start + (cross_end - cross_start) * 0.75)
    ]
    
    for val in range(start, end):
        is_candidate = False
        for s_pt in sample_pts:
            if axis == 0: # 垂直
                c1, c2 = img_np[s_pt, val].astype(np.int16), img_np[s_pt, val-1].astype(np.int16)
            else: # 水平
                c1, c2 = img_np[val, s_pt].astype(np.int16), img_np[val-1, s_pt].astype(np.int16)
            
            if np.sum(np.abs(c1 - c2)) > threshold:
                is_candidate = True
                break
        
        if is_candidate:
            # 执行贯穿度校验 (Scanline Validation)
            matches = 0
            check_steps = 15
            for offset in np.linspace(cross_start + 10, cross_end - 10, check_steps):
                off = int(offset)
                if axis == 0:
                    v1, v2 = img_np[off, val], img_np[off, val-1]
                else:
                    v1, v2 = img_np[val, off], img_np[val-1, off]
                
                if np.sum(np.abs(v1.astype(np.int16) - v2.astype(np.int16))) > threshold * 0.5:
                    matches += 1
            
            if matches / check_steps >= ratio:
                # 连通区域排重：5像素内只取一根线
                if not lines or val - lines[-1] > 5:
                    lines.append(val)
    return lines

def run_anatomy():
    print("="*60)
    print("微信全域布局解剖 (Layout X-Ray) 启动中...")
    print("="*60)
    
    rect = get_wechat_rect()
    if not rect:
        print("[ERR] 找不到微信窗口，请确保微信在前台运行。")
        return
    
    wx, wy, ww, wh = rect
    print(f"[*] 捕捉到窗口逻辑 Rect: (x={wx}, y={wy}, w={ww}, h={wh})")
    
    # 强制激活并截图
    subprocess.run(["osascript", "-e", 'tell application "WeChat" to activate'])
    time.sleep(0.5)
    path = take_screenshot()
    img = Image.open(path)
    img_np = np.array(img)
    
    # 探测 Retina 缩放倍率
    import pyautogui
    sw_logic, sh_logic = pyautogui.size()
    scale = img_np.shape[1] / sw_logic
    print(f"[*] 屏幕缩放因子: {scale:.2f} (Retina 模式)")

    def L2P(val): return int(val * scale)
    def P2L(val): return int(val / scale)

    # 1. 扫描垂直泳道 (X轴平行线)
    print("\n[STEP 1] 扫描垂直并行的平行线 (垂直泳道分界)...")
    # 扫描范围：窗口中间高度选取 40% 的区域进行测试
    v_lines = detect_lines(img_np, 0, L2P(wx)+5, L2P(wx+ww)-5, L2P(wy)+L2P(wh)//4, L2P(wy)+L2P(wh)*3//4)
    lane_bounds = [L2P(wx)] + v_lines + [L2P(wx+ww)]
    
    # 获取全能 OCR (Accurate Mode)
    print("[*] 正在解析全窗口 OCR 内容映射...")
    ocr = get_screen_text(mode="accurate")
    
    swimlanes_results = []
    
    for i in range(len(lane_bounds)-1):
        p_lx, p_rx = lane_bounds[i], lane_bounds[i+1]
        lx, rx = P2L(p_lx), P2L(p_rx)
        lane_w = rx - lx
        if lane_w < 10: continue
        
        lane_id = f"Swimlane-S{i+1}"
        print(f"\n{lane_id} [垂直泳道 {i+1}]")
        print(f"  范围: X = {lx:4d} ~ {rx:4d} (逻辑宽度: {lane_w:d}px)")
        
        # 2. 泳道内横向分块 (Y轴分界线)
        h_lines = detect_lines(img_np, 1, L2P(wy)+5, L2P(wy+wh)-5, p_lx, p_rx)
        h_bounds = [L2P(wy)] + h_lines + [L2P(wy+wh)]
        
        for j in range(len(h_bounds)-1):
            p_ty, p_by = h_bounds[j], h_bounds[j+1]
            ty, by = P2L(p_ty), P2L(p_by)
            block_h = by - ty
            if block_h < 10: continue
            
            # 匹配此块内的文字信息
            block_content = []
            for item in ocr:
                # 只要中心点落在此块内
                if lx <= item["x"] <= rx and ty <= item["y"] <= by:
                    block_content.append(item["text"])
            
            snippet = " | ".join(block_content[:8]) if block_content else "(纯色块或无文字图片)"
            print(f"  └─ Block-{i+1}.{j+1}: Y = {ty:3d} ~ {by:3d} (高度: {block_h:3d}) | {snippet}")

    print("\n" + "="*60)
    print("解剖完成。您可以清晰地看到 ymin 是在哪根 Block 分界线上发生了漂移。")
    print("="*60)

if __name__ == "__main__":
    run_anatomy()
