# -*- coding: utf-8 -*-
"""PE behavior graph (.rg) structural parser v0.2

Observed format (samples: helloworld 774B / mcp_boot 105B / release_combo 344B /
GDZ23 行为图_main.rg 3420B):
- Header: [u32 version=3]["RG\\0"][u8 variant 0x74 or 0x73][00 00 00][u32 ...]
  Fixed-ish preamble to ~0x47 then node records.
- Variant 0x74 (cleantest/MVP) often has 0x3b 00 00 00 node separators.
- Variant 0x73 (GDZ23 production) may have no 0x3b markers; strings still length-prefixed.
- Confirmed record kinds (length-prefixed GBK, len includes trailing NUL, len is BYTE count):
    * node name
    * program call text (may contain \\r\\n), e.g. helloworld();\\r\\n
    * include path, e.g. main\\Script\\include.script
- Usage:
    python tools/rg_parse.py <path.rg> [<path.rg> ...]
    python tools/rg_parse.py --json out.json <path.rg>
"""
from __future__ import annotations

import json
import re
import struct
import sys
from pathlib import Path


def extract_strings(data: bytes):
    """Length-prefixed strings: u32 len includes trailing NUL. Allow CR/LF/TAB."""
    out = []
    i = 0
    while i < len(data) - 4:
        l = struct.unpack_from("<I", data, i)[0]
        if 2 <= l <= 4096 and i + 4 + l <= len(data):
            chunk = data[i + 4 : i + 4 + l]
            if chunk[-1] == 0 and all(
                (32 <= b < 127) or b >= 128 or b in (9, 10, 13) for b in chunk[:-1]
            ):
                out.append((i, chunk[:-1].decode("gbk", errors="replace"), l))
                i += 4 + l
                continue
        i += 1
    return out


def extract_3b(data: bytes):
    return [
        i
        for i in range(len(data) - 4)
        if data[i] == 0x3B and data[i + 1 : i + 4] == b"\x00\x00\x00"
    ]


def classify(s: str) -> str:
    stripped = s.replace("\r", "").replace("\n", "").strip()
    if stripped.endswith(");") or "();" in stripped or stripped.endswith(")"):
        # program-like: calls or expression statements
        if any(ch in stripped for ch in ('(', '"', "'")) or stripped.endswith(";"):
            return "program"
    if stripped.lower().endswith((".script", ".rg")):
        return "include"
    if re.fullmatch(r"[A-Za-z_]\w{0,63}", stripped):
        return "node_name"
    if stripped.startswith("按钮_") or stripped.startswith("键盘_") or stripped.startswith("Ani_"):
        return "ui_label"
    return "text"


def parse_rg(path: str | Path) -> dict:
    path = Path(path)
    data = path.read_bytes()
    version = struct.unpack_from("<I", data, 0)[0] if len(data) >= 4 else None
    magic = data[4:7] if len(data) >= 7 else b""
    variant = data[7] if len(data) >= 8 else None
    strs = extract_strings(data)
    markers = extract_3b(data)
    records = [
        {"off": off, "len": ln, "kind": classify(s), "text": s}
        for off, s, ln in strs
    ]
    programs = [r["text"] for r in records if r["kind"] == "program"]
    includes = [r["text"] for r in records if r["kind"] == "include"]
    return {
        "path": str(path),
        "size": len(data),
        "version": version,
        "magic": magic.decode("latin1", errors="replace"),
        "variant": variant,
        "variant_hex": f"0x{variant:02x}" if variant is not None else None,
        "header_hex": " ".join(f"{b:02x}" for b in data[:16]),
        "markers_3b": [hex(x) for x in markers],
        "records": records,
        "programs": programs,
        "includes": includes,
    }


def print_parse(info: dict) -> None:
    print(f"== {info['path']}")
    print(
        f"   size {info['size']}B | header: {info['header_hex']} | "
        f"version={info['version']} magic={info['magic']!r} variant={info['variant_hex']}"
    )
    print(f"   0x3b markers: {info['markers_3b']}")
    for r in info["records"]:
        preview = r["text"][:70].replace("\r", "\\r").replace("\n", "\\n")
        print(f"   [{r['kind']:<10}] @{r['off']:04x} len={r['len']:3d}  \"{preview}\"")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    out_json = None
    paths = []
    i = 0
    while i < len(args):
        if args[i] == "--json" and i + 1 < len(args):
            out_json = args[i + 1]
            i += 2
        else:
            paths.append(args[i])
            i += 1
    results = []
    for p in paths:
        info = parse_rg(p)
        print_parse(info)
        print()
        results.append(info)
    if out_json:
        Path(out_json).parent.mkdir(parents=True, exist_ok=True)
        Path(out_json).write_text(
            json.dumps(results if len(results) != 1 else results[0], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"wrote {out_json}")
