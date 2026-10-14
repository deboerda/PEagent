"""PE Native Pipe Client — 与 PEAgentNative.plu 的命名管道协议客户端

协议（key=value| 分隔，首行机器头，scene_children 子节点按行追加）：
  请求: cmd=<command>|<param>=<value>...
  回包: success=true|action=<cmd>|...

可用命令（全部经引擎实测，见 docs/peagent-v0.7-native-scene.md）：
  status                         插件/模块状态
  scene_key                      场景根 key（i64 十进制）
  scene_children key= filter= max=  子节点枚举（Contents 语义，见已知限制）
  field_info key=                节点 name/path 查询
  field_key path=                路径 -> key
  field_create father= name=     创建子场节点（father 空则挂模块模型根）
  field_rename key= name=        重命名
  field_flush key=               刷新节点内容
  obj_delete / button_delete     删除 MVO UI 对象(CVsModule::DeleteObject)
                                 obj_type= name= [field_path=]
  rg_reload / graph_reload       非 UI 热重载 .rg（BuildGraph + GraphInfo nudge）
                                 path= 或 filename= 或 name=

稳定性实测（勿破坏）：
  - 管道线程直接调用 3dgs 导出；VsShowFieldContentsByKey 传 NULL filter
    会终止调用线程（管道消失但引擎存活）；VsSearchFieldByKey 会崩掉整个
    引擎进程（EventLog offset 0x1d51fa 实锤）——两者都已规避。
"""

from __future__ import annotations

import time
from typing import Any

import win32file

PIPE_NAME = "\\\\.\\pipe\\PE.NativeScript"


def _parse_header(line: str) -> dict[str, str]:
    out = {}
    for part in line.split("|"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def pipe_command(payload: str, timeout: float = 15.0) -> dict[str, Any]:
    """发送一条管道命令并解析首行头。多行回包放在 lines 字段。"""
    handle = win32file.CreateFile(
        PIPE_NAME,
        win32file.GENERIC_READ | win32file.GENERIC_WRITE,
        0, None, win32file.OPEN_EXISTING, 0, None,
    )
    try:
        # PE 是 ANSI/GBK 边界：中文路径必须以 GBK 发送（UTF-8 查不到），回包同为 GBK
        win32file.WriteFile(handle, payload.encode("gbk"))
        chunks: list[bytes] = []
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                _, data = win32file.ReadFile(handle, 65536)
                chunks.append(data)
            except Exception:
                break  # ERROR_BROKEN_PIPE = 服务端已发完并断开
        text = b"".join(chunks).decode("gbk", errors="replace")
    finally:
        win32file.CloseHandle(handle)
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return {"success": False, "error": "empty pipe reply", "raw": text}
    header = _parse_header(lines[0])
    header["success"] = header.get("success", "false").lower() == "true"
    header["lines"] = lines[1:]
    return header


def status() -> dict[str, Any]:
    return pipe_command("cmd=status")


def scene_key() -> dict[str, Any]:
    return pipe_command("cmd=scene_key")


def field_info(key: str) -> dict[str, Any]:
    return pipe_command(f"cmd=field_info|key={key}")


def field_key(path: str) -> dict[str, Any]:
    return pipe_command(f"cmd=field_key|path={path}")


def field_create(name: str, father: str = "") -> dict[str, Any]:
    return pipe_command(f"cmd=field_create|father={father}|name={name}")


def field_rename(key: str, name: str) -> dict[str, Any]:
    return pipe_command(f"cmd=field_rename|key={key}|name={name}")


def field_flush(key: str = "") -> dict[str, Any]:
    return pipe_command(f"cmd=field_flush|key={key}")


def field_delete(path: str) -> dict[str, Any]:
    return pipe_command(f"cmd=field_delete|path={path}")


def obj_delete(name: str, obj_type: str = "button", field_path: str = "", tree: "str | int | None" = None) -> dict[str, Any]:
    """Delete a ProjectMgr/MVO UI object.

    Charts (curve/chart/...): use one tree=2 DeleteUIObject transaction.
    DeleteObject(ptr) and VsDeleteField are unsafe for charts and are never called.
    """
    chart_aliases = {
        "curve", "chart", "polyline", "chart_polyline", "dashboard", "histogram",
        "bar", "chart_bar", "progress", "percent", "number", "table", "property",
        "chart_property", "grid", "chart_grid", "65", "66", "67", "69", "70", "71", "74", "92",
    }
    ot = (obj_type or "").strip().lower()
    is_chart = ot in chart_aliases
    steps: list[dict[str, Any]] = []
    # Charts are intentionally handled by one native tree-only transaction.
    # Do NOT call field_delete first: VsDeleteField is unsafe for chart fields and
    # can leave the engine in a corrupted/hung state even when it returns an error.
    # DeleteUIObject performs the authoritative chart/tree cleanup.
    parts = ["cmd=obj_delete", f"obj_type={obj_type}", f"name={name}"]
    if field_path and not is_chart:
        parts.append(f"field_path={field_path}")
    if tree is not None:
        parts.append(f"tree={tree}")
    elif is_chart:
        parts.append("tree=2")
    try:
        result = pipe_command("|".join(parts))
    except Exception as e:
        return {"success": False, "error": "obj_delete_killed_pipe", "detail": str(e), "steps": steps}
    if steps:
        result = {**result, "steps": steps + [dict(result)]}
    return result


def button_delete(name: str, field_path: str = "") -> dict[str, Any]:
    return obj_delete(name=name, obj_type="button", field_path=field_path)


def scene_children(key: str = "", filter_pattern: str = "",
                   max_children: int = 64) -> dict[str, Any]:
    r = pipe_command(f"cmd=scene_children|key={key}|filter={filter_pattern}|max={max_children}")
    children = []
    for line in r.get("lines", []):
        parts = line.split(":", 3)
        if len(parts) == 4:
            children.append({
                "index": int(parts[0]), "key": parts[1],
                "name": parts[2], "path": parts[3],
            })
    r["children"] = children
    return r

def rg_reload(path: str = "", filename: str = "", name: str = "", timeout: float = 30.0) -> dict[str, Any]:
    """Native non-UI .rg reload via PEAgentNative (BuildGraph, no graph editor)."""
    parts = ["cmd=rg_reload"]
    if path:
        parts.append(f"path={path}")
    if filename:
        parts.append(f"filename={filename}")
    if name:
        parts.append(f"name={name}")
    return pipe_command("|".join(parts), timeout=timeout)


def graph_reload(path: str = "", filename: str = "", name: str = "", timeout: float = 30.0) -> dict[str, Any]:
    return rg_reload(path=path, filename=filename, name=name, timeout=timeout)

