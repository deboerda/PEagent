"""PE Script Bridge — DSL program 模式执行器 + 结构化文件回传

原理（全部经过引擎实测验证，见 docs/native-api-index-v0.md 与会话记录）：
1. PE 脚本必须以 ``void fn(){...} fn();`` 形式在 execution_mode="program"
   下一次性提交（load 模式只加载定义不执行；函数定义跨调用不持久）。
2. DSL 没有返回值通道，用脚本内 fileWriteLine 写文本文件，Python 端
   轮询读取并解析，形成结构化回传。
3. DSL 语法约束（实测）：
   - for 循环 C 风格可用；字符串 ``+`` 拼接可用
   - 数值输出必须经 valuesToString(float array, count, string&) 转字符串
     （fileWrite(fp, int/float) 是二进制写入）
   - 禁止调用 char* 出参的 Vs* 函数（如 VsShowFieldPathName）——会使引擎崩溃
   - camSetCamera 全参数写相机会把相机置零（状态破坏），v0 只提供相机读取

已知限制：
- DSL 脚本的错误只出现在引擎输出窗口，HTTP 层只返回 accept 与否；
  本模块在"已受理但无回传文件"时会给出排查提示。
- 场景树枚举需要 count 出参/原生路由，v0 不提供（P1）。
"""

from __future__ import annotations

import os
import re
import time
import uuid
from typing import Any

from . import client

OUT_DIR = "E:/AI/temp/pe_bridge"
_FLOAT_RE = re.compile(r"-?\d+(?:\.\d+)?(?:e-?\d+)?", re.IGNORECASE)


def _engine_alive() -> bool:
    try:
        st = client.engine_status()
        return bool(st.get("success"))
    except Exception:
        return False


def _read_out_file(path: str) -> str:
    for enc in ("utf-8", "gbk"):
        try:
            with open(path, encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
        except OSError:
            return ""
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def run_script(body: str, name: str = "bridge", wait: float = 8.0,
               cleanup: bool = True) -> dict[str, Any]:
    """执行一段 DSL 函数体并回传文件内容。

    body 中用 ``__OUT__`` 占位回传文件路径（正斜杠）。函数体会被包上
    ``void <name>(){...} <name>();`` 以 program 模式提交。
    返回 {success, accepted, output, lines, engine_alive, error?}
    """
    os.makedirs(OUT_DIR, exist_ok=True)
    token = f"{name}_{uuid.uuid4().hex[:8]}"
    out_path = f"{OUT_DIR}/{token}.txt"
    fn = "peBridge_" + uuid.uuid4().hex[:6]
    script = f"void {fn}(){{\n{body.replace('__OUT__', out_path)}\n}} {fn}();"

    result = client.script_execute(script, script_name=token, execution_mode="program")
    accepted = bool(result.get("success")) and result.get("engine_return_code", 0) == 1

    deadline = time.time() + wait
    text = ""
    while time.time() < deadline:
        if os.path.exists(out_path):
            time.sleep(0.3)  # 留给引擎写完/关闭句柄
            text = _read_out_file(out_path)
            break
        time.sleep(0.4)

    if cleanup and os.path.exists(out_path):
        try:
            os.remove(out_path)
        except OSError:
            pass

    ok = accepted and text != ""
    resp: dict[str, Any] = {
        "success": ok,
        "accepted": accepted,
        "output": text,
        "lines": [l for l in text.splitlines() if l.strip()],
        "engine_return_code": result.get("engine_return_code"),
    }
    if not ok:
        resp["engine_alive"] = _engine_alive()
        if not accepted:
            resp["error"] = "脚本未被引擎受理（语法错误或引擎未就绪）"
        elif text == "":
            resp["error"] = (
                "脚本已受理但无回传文件：多为 DSL 运行时错误（参数不匹配/数组越界/"
                "禁用函数）。请到 PE 输出窗口查看错误详情，或用 pe_script_validate 预检。"
            )
    return resp


def _floats_from_line(line: str) -> list[float]:
    return [float(x) for x in _FLOAT_RE.findall(line)]


def camera_get(vport: str = "main") -> dict[str, Any]:
    """读取视口相机参数（eye/target/up + 原始 16 值）。"""
    body = (
        'file fp = fileOpen("__OUT__", "w");\n'
        f"float cam[16];\n"
        f'camGetCamera("{vport}", cam);\n'
        'string cs = "";\n'
        "valuesToString(cam, 12, cs);\n"
        'fileWriteLine(fp, "CAM:" + cs);\n'
        "fileClose(fp);"
    )
    r = run_script(body, name="camget")
    if not r["success"]:
        return {**r, "hint": "camera_get 依赖 camGetCamera+valuesToString（已实测可用）"}
    floats = _floats_from_line(r["lines"][0]) if r["lines"] else []
    if len(floats) < 9:
        return {"success": False, "error": f"回传数据异常: {r['lines']}"}
    return {
        "success": True,
        "vport": vport,
        "eye": floats[0:3],
        "target": floats[3:6],
        "up": floats[6:9],
        "raw": floats,
    }


def node_set_position(path: str, x: float, y: float, z: float) -> dict[str, Any]:
    """按场路径设置节点位置（DSL Field.setPosition）。"""
    body = (
        'file fp = fileOpen("__OUT__", "w");\n'
        f'setPosition("{path}", {x}, {y}, {z});\n'
        'fileWriteLine(fp, "OK");\n'
        "fileClose(fp);"
    )
    return run_script(body, name="setpos")


def node_move(path: str, dx: float, dy: float, dz: float) -> dict[str, Any]:
    """按场路径增量移动节点（DSL moveField）。"""
    body = (
        'file fp = fileOpen("__OUT__", "w");\n'
        f'moveField("{path}", {dx}, {dy}, {dz});\n'
        'fileWriteLine(fp, "OK");\n'
        "fileClose(fp);"
    )
    return run_script(body, name="move")


def node_set_rotation_reset(path: str) -> dict[str, Any]:
    """重置节点旋转。注意：DSL 无 setRotation，精确旋转需原生 pe* 通路（P1）。"""
    body = (
        'file fp = fileOpen("__OUT__", "w");\n'
        f'resetFieldRotation("{path}");\n'
        'fileWriteLine(fp, "OK");\n'
        "fileClose(fp);"
    )
    return run_script(body, name="resetrot")


def scene_children_dsl(key_literal: str = "", cap: int = 32) -> dict[str, Any]:
    """单层子节点名枚举（DSL getChildrenKeys + getFieldName）。

    实测约束（详见 docs/peagent-v0.7-native-scene.md）：
    - 子节点数量在 DSL 层不可测（getArraySize 返回 0、越界读返回垃圾而非中断），
      因此本函数按 cap 截断，返回列表可能包含 count 之后的垃圾占位条目
      （表现为多个 "unknown+数字" 名字）。
    - key_literal 为空时枚举模块模型根（getModuleModelKey("main")）。
    - 不要嵌套调用（嵌套 getChildrenKeys 曾实测挂起引擎 30s+）。
    """
    if cap < 1 or cap > 128:
        cap = 32
    root_expr = f'getModuleModelKey("{key_literal}")' if key_literal else 'getModuleModelKey("main")'
    writes = "\n".join(
        f'fileWriteLine(fp, getFieldName(keys[{i}]));' for i in range(cap)
    )
    body = (
        'file fp = fileOpen("__OUT__", "w");\n'
        f"dword rootKey = {root_expr};\n"
        f"dword keys[{cap}];\n"
        "getChildrenKeys(rootKey, keys);\n"
        f"{writes}\n"
        'fileWriteLine(fp, "__DONE__");\n'
        "fileClose(fp);"
    )
    r = run_script(body, name=f"kids{cap}")
    if not r["success"]:
        return r
    names = [l.split(":", 1)[-1] for l in r["lines"] if l != "__DONE__"]
    return {
        "success": True,
        "root": key_literal or "main",
        "cap": cap,
        "count_exact": False,
        "names": names,
        "note": "列表可能含 count 之后的垃圾占位（unknown+数字）；精确 count 需原生枚举路由",
    }
