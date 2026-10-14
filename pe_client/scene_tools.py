"""PE 场景辅助工具 — 截图 / 控制台 / 相机切换 / 节点删除

补全验证中发现的能力缺口：
- 插件 /api/frame/capture 只输出 253x253 裁剪画面 → 本模块用 PrintWindow
  抓取 PE 主窗口完整画面（后台可用、不受遮挡影响）
- /api/output/query 找不到输出窗口 → 用 pe_console（Win32 控件直读）兜底
- 相机切换：运行时 camSetCamera 会损坏相机状态（实测），改用工程验证过的
  applyCamera("相机名") 机制；**含中文的 DSL 必须经 GBK 脚本文件执行**
  （HTTP 内联中文会变乱码，实测）
"""

from __future__ import annotations

import os
import re
import time
import uuid
from typing import Any

SNAP_DIR = r"E:\AI\temp\pe_snaps"


def _find_pe_hwnd() -> int | None:
    import win32gui

    found: list[int] = []

    def on_window(h, _):
        if win32gui.GetWindowText(h).startswith("PostEngineer - "):
            found.append(h)
            return False
        return True

    win32gui.EnumWindows(on_window, 0)
    return found[0] if found else None


def snapshot(name: str = "snap") -> dict[str, Any]:
    """PrintWindow 抓取 PE 主窗口完整画面，返回 PNG 路径。"""
    try:
        import ctypes
        import win32gui, win32ui
        from PIL import Image
    except ImportError as e:
        return {"success": False, "error": f"缺少依赖: {e}"}

    hwnd = _find_pe_hwnd()
    if not hwnd:
        return {"success": False, "error": "PostEngineer 主窗口未找到"}

    os.makedirs(SNAP_DIR, exist_ok=True)
    token = re.sub(r"[^\w\-]", "_", name) or "snap"
    path = os.path.join(SNAP_DIR, f"{token}_{int(time.time())}.png")

    l, t, r, b = win32gui.GetWindowRect(hwnd)
    w, h = r - l, b - t
    if w <= 0 or h <= 0:
        return {"success": False, "error": f"窗口尺寸异常: {w}x{h}"}
    hdc = win32gui.GetWindowDC(hwnd)
    mfc = win32ui.CreateDCFromHandle(hdc)
    dc = mfc.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(mfc, w, h)
    dc.SelectObject(bmp)
    PW_RENDERFULLCONTENT = 2  # 含 GPU 合成内容（OpenGL 视口）
    ctypes.WinDLL("user32").PrintWindow(hwnd, dc.GetSafeHdc(), PW_RENDERFULLCONTENT)
    info = bmp.GetInfo()
    data = bmp.GetBitmapBits(True)
    Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]), data, "raw", "BGRX", 0, 1).save(path)
    win32gui.DeleteObject(bmp.GetHandle())
    dc.DeleteDC()
    mfc.DeleteDC()
    win32gui.ReleaseDC(hwnd, hdc)
    return {"success": True, "path": path, "width": w, "height": h,
            "note": "PrintWindow 全窗截图；若窗口最小化内容可能不完整"}


def console_read(limit: int = 20, channel: str = "auto") -> dict[str, Any]:
    """直读 PE 底部控制台（信息/调试/输出），绕过失效的 /api/output/query。"""
    from pe_console import read_bottom_console
    return read_bottom_console(limit=max(0, limit), channel=channel)


def _run_via_gbk_file(body: str, name: str = "scenetool") -> dict[str, Any]:
    """把 DSL 函数体写入 GBK 临时脚本文件后 execute_file（绕开 HTTP 中文乱码）。"""
    from . import client
    os.makedirs(r"E:\AI\temp\pe_tools", exist_ok=True)
    token = f"{name}_{uuid.uuid4().hex[:6]}"
    path = os.path.join(r"E:\AI\temp\pe_tools", f"{token}.script")
    with open(path, "wb") as f:
        f.write((f"void {token}(){{\n{body}\n}} {token}();").replace("\n", "\r\n").encode("gbk"))
    r = client._post_json("/api/script/execute_file", {"filename": path})
    r["script_file"] = path
    return r


def apply_camera(camera_name: str) -> dict[str, Any]:
    """切换到指定名称的相机（工程验证的 applyCamera 机制，安全）。"""
    # 相机名含中文 → 必须走 GBK 文件通道
    body = f'applyCamera("{camera_name}");'
    r = _run_via_gbk_file(body, "applycam")
    ok = bool(r.get("success")) and r.get("engine_return_code", 0) == 1
    return {"success": ok, "action": "apply_camera", "camera": camera_name,
            "engine_return_code": r.get("engine_return_code"),
            "error": None if ok else "切换失败（相机名不存在或引擎未就绪）"}


def field_delete(path: str) -> dict[str, Any]:
    """按路径删除场节点（原生 VsDeleteField，PEAgentNative 管道命令）。"""
    from . import native_pipe
    return native_pipe.pipe_command(f"cmd=field_delete|path={path}")
