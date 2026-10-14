"""Preset animation rotate helpers for PE.

Runtime-created Rotate/move animations do NOT bind to models (redline).
Working path: play preset animations stored in .peo via astart(), or inspect
their .peo binding (field path / duration). Creating new presets still needs
the frame-animation editor (or a future .peo writer).
"""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

from . import scene_tools

DEFAULT_PEO_INDEX = Path(r"E:\PEagent\data\peo_index_gdz23.json")


def _peo_path_from_index(index_path: Path | None = None) -> Path:
    idx = Path(index_path or DEFAULT_PEO_INDEX)
    data = json.loads(idx.read_text(encoding="utf-8"))
    return Path(data["source"])


def list_anims(index_path: Path | None = None, query: str = "") -> dict[str, Any]:
    """List animation-like strings from PE-Insight peo index."""
    idx = Path(index_path or DEFAULT_PEO_INDEX)
    data = json.loads(idx.read_text(encoding="utf-8"))
    texts = [s["text"] for s in data.get("strings", []) if isinstance(s, dict) and "text" in s]
    names: list[str] = []
    seen: set[str] = set()
    for t in texts:
        if not t or len(t) < 2:
            continue
        if t.startswith("Ani_") or t.startswith("动画_") or t.startswith("sysanim_"):
            if t not in seen:
                seen.add(t)
                names.append(t)
    if query:
        q = query.lower()
        names = [n for n in names if q in n.lower()]
    names.sort()
    return {"success": True, "count": len(names), "anims": names, "source": str(idx)}


def _read_u32(buf: bytes, off: int) -> tuple[int, int]:
    return struct.unpack_from("<I", buf, off)[0], off + 4


def _read_f32(buf: bytes, off: int) -> tuple[float, int]:
    return struct.unpack_from("<f", buf, off)[0], off + 4


def _read_str(buf: bytes, off: int) -> tuple[str, int]:
    n, off = _read_u32(buf, off)
    raw = buf[off : off + n]
    off += n
    text = raw.split(b"\x00", 1)[0].decode("gbk", errors="replace")
    return text, off


def inspect_anim(name: str, peo_path: Path | str | None = None) -> dict[str, Any]:
    """Decode one preset animation record from .peo (best-effort)."""
    peo = Path(peo_path) if peo_path else _peo_path_from_index()
    if not peo.exists():
        return {"success": False, "error": f"peo missing: {peo}"}
    data = peo.read_bytes()
    enc = name.encode("gbk")
    name_off = data.find(enc)
    if name_off < 0:
        return {"success": False, "error": f"animation name not found in peo: {name}"}
    # length prefix sits 4 bytes before name content
    name_len = struct.unpack_from("<I", data, name_off - 4)[0]
    obj_id = struct.unpack_from("<I", data, name_off - 8)[0]
    off = name_off + name_len
    flag_a, off = _read_u32(data, off)
    flag_b, off = _read_u32(data, off)
    duration_ms, off = _read_f32(data, off)
    speed, off = _read_f32(data, off)
    n_events, off = _read_u32(data, off)
    events: list[dict[str, Any]] = []
    for _ in range(min(n_events, 16)):
        ev_id, off = _read_str(data, off)
        marker = data[off]
        off += 1
        ctx, off = _read_str(data, off)
        # observed: 1 padding byte before path length
        pad = data[off]
        off += 1
        path, off = _read_str(data, off)
        # following block starts with float 1.0 identity-ish; keep offset only
        events.append(
            {
                "id": ev_id,
                "marker": marker,
                "pad": pad,
                "ctx": ctx,
                "path": path,
                "payload_off": off,
            }
        )
        # stop deep-parsing payload (quaternion keyframes) for v0
        break
    return {
        "success": True,
        "name": name,
        "obj_id": obj_id,
        "name_off": name_off,
        "flag_a": flag_a,
        "flag_b": flag_b,
        "duration_ms": duration_ms,
        "duration_s": duration_ms / 1000.0 if duration_ms else 0.0,
        "speed": speed,
        "n_events": n_events,
        "events": events,
        "field_path": events[0]["path"] if events else "",
        "peo": str(peo),
        "note": "Payload/keyframe body not fully decoded in v0; path+duration are authoritative.",
    }


def play_anim(name: str, qualified: bool = False) -> dict[str, Any]:
    """Start a preset animation via astart (GBK file channel).

    For submodule anims use qualified names like main:模块_蒸镀系统:动画_主鼓旋转
    and keep Chinese on the GBK file path (already handled by scene_tools).
    """
    body = f'astart("{name}");'
    r = scene_tools._run_via_gbk_file(body, "rotplay")
    ok = bool(r.get("success")) and int(r.get("engine_return_code", 0) or 0) == 1
    return {
        "success": ok,
        "action": "play_anim",
        "name": name,
        "engine_return_code": r.get("engine_return_code"),
        "script_file": r.get("script_file"),
        "error": None if ok else (r.get("error") or "astart failed / engine rejected"),
        "raw": r,
        "note": "Visual confirmation needs PEPlayer run mode + snapshot; edit-mode astart may no-op.",
    }


def rotate_model(
    field: str = "",
    degrees: float = 360.0,
    duration_s: float = 5.0,
    axis: tuple[float, float, float] | list[float] = (0.0, 1.0, 0.0),
    anim_name: str = "",
    mode: str = "auto",
) -> dict[str, Any]:
    """General entry for model rotation.

    mode:
      - play: require anim_name, astart it
      - auto: if anim_name set -> play; else find peo anims whose field_path == field
      - create: refused (runtime create does not bind; use frame editor / future peo writer)
    """
    mode = (mode or "auto").lower()
    if mode == "create":
        return {
            "success": False,
            "error": "create mode not available: runtime Rotate/move animations do not bind to models. Preset via frame animation editor, then play.",
            "hint": {
                "field": field,
                "degrees": degrees,
                "duration_s": duration_s,
                "axis": list(axis),
                "dsl_sketch": (
                    "Animation{'''Ani_X\\n\\tname{Ani_X}\\n\\tcontroller{\\n"
                    f"\\t\\tRotate{{\\n\\t\\t\\tfield{{{field}}}\\n"
                    f"\\t\\t\\tvalues{{{degrees:.6f} {duration_s:.6f}}}\\n"
                    f"\\t\\t\\taxis{{{axis[0]:.6f} {axis[1]:.6f} {axis[2]:.6f}}}\\n"
                    "\\t\\t}}\\n\\t}}\\n}"
                ),
                "limitation": "DSL above parses but does not bind visually; .peo keyframes required.",
            },
        }

    if anim_name:
        return play_anim(anim_name)

    if not field:
        return {"success": False, "error": "need anim_name or field"}

    # Match preset anims by field path (inspect each candidate; keep it bounded)
    listed = list_anims()
    matches: list[dict[str, Any]] = []
    for name in listed.get("anims", []):
        info = inspect_anim(name)
        if not info.get("success"):
            continue
        if info.get("field_path") == field:
            matches.append(
                {
                    "name": name,
                    "duration_ms": info.get("duration_ms"),
                    "obj_id": info.get("obj_id"),
                }
            )
    if not matches:
        return {
            "success": False,
            "error": "no preset animation bound to this field",
            "field": field,
            "next": "Create Ani_* in frame animation editor on that field, save project, then pe_rotate_model(anim_name=...)",
        }
    # Prefer exact duration match when possible
    target_ms = float(duration_s) * 1000.0
    matches.sort(key=lambda m: abs(float(m.get("duration_ms") or 0) - target_ms))
    chosen = matches[0]["name"]
    played = play_anim(chosen)
    played["matched"] = matches
    played["chosen"] = chosen
    played["requested"] = {
        "field": field,
        "degrees": degrees,
        "duration_s": duration_s,
        "axis": list(axis),
    }
    return played
