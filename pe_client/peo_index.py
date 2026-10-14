"""Offline PE-Insight first slice: index .peo strings + classify + grep.

Does NOT fully decode MVOOBJ records. Useful slice:
  - length-prefixed GBK string extraction (PE serialization style)
  - category counts (scene_path / mvoobj / func_def / anim / ...)
  - substring grep across extracted strings
  - JSON export under data/exports/peo_index/

Redlines: read-only on .peo; never calls live /api/graph/*.
"""

from __future__ import annotations

import json
import re
import struct
import time
from pathlib import Path
from typing import Any

_FUNC_BARE = re.compile(r"^[^@\s]+@\d+$")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _is_readable(text: str) -> bool:
    if len(text) < 2:
        return False
    if _CTRL.search(text):
        return False
    # reject mostly-replacement garbage
    if text.count("\ufffd") > max(1, len(text) // 4):
        return False
    return True


def extract_strings(data: bytes, min_len: int = 2, max_len: int = 512) -> list[dict[str, Any]]:
    """Extract PE length-prefixed GBK strings (u32le + bytes, optional NUL)."""
    out: list[dict[str, Any]] = []
    i = 0
    n = len(data)
    while i + 4 <= n:
        ln = struct.unpack_from("<I", data, i)[0]
        if min_len <= ln <= max_len and i + 4 + ln <= n:
            raw = data[i + 4 : i + 4 + ln]
            try:
                text = raw.split(b"\x00", 1)[0].decode("gbk", errors="strict")
            except Exception:
                i += 1
                continue
            if _is_readable(text):
                out.append({"off": i + 4, "len": ln, "text": text})
                i += 4 + ln
                continue
        i += 1
    # Also capture short ASCII header if present (e.g. VER9.97)
    if data[:3] == b"VER":
        hdr = data[:32].split(b"\x00", 1)[0].decode("ascii", errors="ignore").strip()
        if hdr and not any(s["off"] == 0 for s in out):
            out.insert(0, {"off": 0, "len": len(hdr), "text": hdr})
    return out


def classify(text: str) -> list[str]:
    """Return zero or more category tags for a string (prefix heuristics)."""
    tags: list[str] = []
    if text.startswith("/scene/"):
        tags.append("scene_path")
    if text.startswith("MVOOBJ"):
        tags.append("mvoobj")
    if _FUNC_BARE.fullmatch(text):
        tags.append("func_def")
    if text.startswith("动画_") or text.startswith("Ani_") or text.startswith("sysanim_"):
        tags.append("anim")
    if (
        text.startswith("On")
        or "事件" in text
        or text.startswith("void On")
        or "Received" in text
        or text.endswith("Event")
    ):
        tags.append("event")
    if (
        text.startswith("按钮_")
        or text.startswith("图片_")
        or text.startswith("备注_")
        or text.startswith("标签_")
        or text.startswith("曲线_")
        or text.startswith("线条_")
        or text.startswith("?buttons")
        or text.startswith("?pipes")
    ):
        tags.append("ui_obj")
    if (
        text.startswith("模块_")
        or "\\模块_" in text
        or "/模块_" in text
        or text.startswith("main:")
        or text.startswith("main\\")
        or text.endswith(".rg")
        or text.endswith(".vis")
        or text.endswith(".script")
    ):
        tags.append("module")
    return tags


def _count_tags(strings: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "scene_path": 0,
        "mvoobj": 0,
        "func_def": 0,
        "anim": 0,
        "event": 0,
        "ui_obj": 0,
        "module": 0,
    }
    for s in strings:
        for tag in s.get("tags") or classify(s["text"]):
            if tag in counts:
                counts[tag] += 1
    return counts


def index_peo(
    peo_path: str | Path,
    *,
    out_path: str | Path | None = None,
    include_tags: bool = True,
    max_strings: int | None = None,
) -> dict[str, Any]:
    """Build offline PE-Insight v0-style index for one .peo file."""
    path = Path(peo_path)
    if not path.exists():
        return {"success": False, "error": f"peo missing: {path}"}
    t0 = time.time()
    data = path.read_bytes()
    strings = extract_strings(data)
    if include_tags:
        for s in strings:
            s["tags"] = classify(s["text"])
    if max_strings is not None:
        strings = strings[: max(0, max_strings)]
    counts = _count_tags(strings)
    result: dict[str, Any] = {
        "success": True,
        "source": str(path.resolve()),
        "size": len(data),
        "generated": time.strftime("%Y-%m-%d"),
        "elapsed_s": round(time.time() - t0, 3),
        "string_count": len(strings),
        "counts": counts,
        "strings": [{"off": s["off"], "text": s["text"]} for s in strings],
        "note": (
            "First-slice Insight: length-prefixed GBK strings + prefix classification. "
            "Does not fully decode MVOOBJ record structure."
        ),
    }
    if include_tags:
        # keep tags only in a compact side channel for grep; omit from default export bulk
        result["tagged_sample"] = [
            {"off": s["off"], "text": s["text"], "tags": s["tags"]}
            for s in strings
            if s.get("tags")
        ][:50]
    if out_path:
        outp = Path(out_path)
        outp.parent.mkdir(parents=True, exist_ok=True)
        # Export without tagged_sample bloat for compatibility with peo_index_gdz23.json shape
        export = {
            "source": result["source"],
            "size": result["size"],
            "generated": result["generated"],
            "elapsed_s": result["elapsed_s"],
            "string_count": result["string_count"],
            "counts": result["counts"],
            "strings": result["strings"],
            "note": result["note"],
            "success": True,
        }
        outp.write_text(json.dumps(export, ensure_ascii=False, indent=2), encoding="utf-8")
        result["out_path"] = str(outp.resolve())
    return result


def info(peo_path: str | Path) -> dict[str, Any]:
    """Compact summary: size + category counts + header sample (no full string dump)."""
    full = index_peo(peo_path, out_path=None, include_tags=True)
    if not full.get("success"):
        return full
    texts = [s["text"] for s in full.get("strings", [])]
    return {
        "success": True,
        "source": full["source"],
        "size": full["size"],
        "elapsed_s": full["elapsed_s"],
        "string_count": full["string_count"],
        "counts": full["counts"],
        "header": texts[:8],
        "anim_names": sorted({t for t in texts if t.startswith("动画_") or t.startswith("Ani_")}),
        "mvoobj_sample": [t for t in texts if t.startswith("MVOOBJ")][:10],
        "note": full["note"],
    }


def grep(
    peo_or_index: str | Path,
    substr: str,
    *,
    ignore_case: bool = True,
    limit: int = 50,
) -> dict[str, Any]:
    """Grep extracted strings from a .peo file or an existing JSON index."""
    path = Path(peo_or_index)
    if not path.exists():
        return {"success": False, "error": f"missing: {path}"}
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        strings = data.get("strings") or []
        source = data.get("source", str(path))
    else:
        built = index_peo(path, include_tags=False)
        if not built.get("success"):
            return built
        strings = built["strings"]
        source = built["source"]
    needle = substr.lower() if ignore_case else substr
    hits = []
    for s in strings:
        text = s.get("text", "")
        hay = text.lower() if ignore_case else text
        if needle in hay:
            hits.append({"off": s.get("off"), "text": text})
            if len(hits) >= limit:
                break
    return {
        "success": True,
        "source": source,
        "query": substr,
        "hit_count": len(hits),
        "hits": hits,
        "truncated": len(hits) >= limit,
    }


def default_export_path(peo_path: str | Path) -> Path:
    stem = Path(peo_path).stem
    safe = re.sub(r"[^\w\-]+", "_", stem, flags=re.UNICODE).strip("_") or "peo"
    return Path(r"E:\PEagent\data\exports\peo_index") / f"{safe}.json"
