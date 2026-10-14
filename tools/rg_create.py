# -*- coding: utf-8 -*-
"""PE behavior graph (.rg) creator v0.2 — template patch on helloworld.rg

Why helloworld.rg (not release_combo):
- Production/MVP boot graphs mark program/include records with 0x3b 00 00 00.
- release_combo uses a looser 0x01 framing; when swapped into MVP as the sole
  graph, include path was fed to ScriptReader as a keyword (console:
  "'main\\Script\\include.script' 不是关键字").

Template preserves: header, root/boot nodes, 0x3b framing.
We only replace length-prefixed GBK string records (byte length, incl. NUL).

Usage:
  python tools/rg_create.py <out.rg> --include "main\\Script\\include.script" --call "helloworld();"
"""
from __future__ import annotations

import os
import struct
import sys

TEMPLATE = os.path.join(
    os.path.dirname(__file__),
    "..",
    "PeProject",
    "MVP",
    "main",
    "helloworld.rg",
)


def _replace_lenprefixed(data: bytes, old_text: str, new_text: str) -> bytes:
    old_gb = old_text.encode("gbk")
    new_gb = new_text.encode("gbk")
    old_rec = struct.pack("<I", len(old_gb) + 1) + old_gb + b"\x00"
    new_rec = struct.pack("<I", len(new_gb) + 1) + new_gb + b"\x00"
    if old_rec not in data:
        raise AssertionError(f"template missing record: {old_text!r}")
    return data.replace(old_rec, new_rec, 1)


def create_boot_graph(out_path: str, include_path: str, calls: list[str]) -> dict:
    data = open(TEMPLATE, "rb").read()
    # helloworld.rg stores the boot call with CRLF
    old_call = "helloworld();\r\n"
    old_inc = "main\\Script\\include.script"
    call_text = "\r\n".join(calls)
    if not call_text.endswith("\r\n"):
        # keep CRLF like template program record
        if not call_text.endswith("\n"):
            call_text += "\r\n"
        elif not call_text.endswith("\r\n"):
            call_text = call_text.replace("\n", "\r\n")
            if not call_text.endswith("\r\n"):
                call_text += "\r\n"
    data = _replace_lenprefixed(data, old_call, call_text)
    if include_path != old_inc:
        data = _replace_lenprefixed(data, old_inc, include_path)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    open(out_path, "wb").write(data)
    # structural sanity: include/program should sit after a 0x3b marker nearby
    inc = include_path.encode("gbk")
    i = data.find(inc)
    has_3b = i >= 8 and data[i - 8 : i - 4] == b"\x3b\x00\x00\x00"
    return {
        "success": True,
        "path": os.path.abspath(out_path),
        "size": len(data),
        "calls": calls,
        "include": include_path,
        "include_has_3b_prefix": has_3b,
        "template": os.path.abspath(TEMPLATE),
        "note": "v0.2 template=helloworld.rg; verify with rg_parse.py then debug_start",
    }


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    out = args[0]
    inc = "main\\Script\\include.script"
    calls: list[str] = []
    i = 1
    while i < len(args):
        if args[i] == "--include":
            inc = args[i + 1]
            i += 2
        elif args[i] == "--call":
            calls.append(args[i + 1])
            i += 2
        else:
            i += 1
    r = create_boot_graph(out, inc, calls or ["helloworld();"])
    for k, v in r.items():
        print(f"{k}: {v}")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from rg_parse import parse_rg, print_parse

    print_parse(parse_rg(out))
