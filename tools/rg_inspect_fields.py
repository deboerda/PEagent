# -*- coding: utf-8 -*-
"""Run RelaGraph inspect_rg and emit a structured field table JSON.

Usage:
  python tools/rg_inspect_fields.py <graph.rg> [-o out.json]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from rg_fields_from_inspect import parse_inspect, RG  # noqa: E402

DEFAULT_DLL = ROOT / "bin" / "Release-x64" / "RelaGraph.dll"
INSPECT = ROOT / "tools" / "inspect_rg.exe"


def run_inspect(rg_path: Path, dll: Path = DEFAULT_DLL) -> Path:
    rg_path = rg_path.resolve()
    dll = dll.resolve()
    out = ROOT / "data" / "exports" / f"rg_inspect_{rg_path.stem}.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    # Must run with cwd=dll dir so dependent DLLs resolve
    proc = subprocess.run(
        [str(INSPECT), str(rg_path), str(dll)],
        cwd=str(dll.parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    # inspect prints to stderr
    out.write_bytes(proc.stderr or proc.stdout)
    if proc.returncode != 0 and not out.stat().st_size:
        raise SystemExit(f"inspect_rg failed rc={proc.returncode}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rg")
    ap.add_argument("-o", "--output", default="")
    ap.add_argument("--dll", default=str(DEFAULT_DLL))
    args = ap.parse_args()
    rg = Path(args.rg)
    raw = run_inspect(rg, Path(args.dll))
    info = parse_inspect(raw)
    info["rg_path"] = str(rg.resolve())
    info["rg_types"] = RG
    info["notes"] = {
        "matrix": "float6 affine-ish: [1,0,0,1,tx,ty] editor canvas position",
        "CURVE": "edge/link object; prev=from_id, next=to_id",
        "SCRIPT": "include/script path in m_string (wchar); type=14",
        "PROGRAM": "callable DSL text in m_string; type=6",
        "BOOT": "startup entry; type=11",
        "HUB": "fan-in/out junction; type=4",
        "STEP": "UI/event step node (buttons/keys); type=1",
        "father": "parent COMPLEX object id (root)",
        "type_19": "seen in MVP helloworld; not in RgType 0..17 enum — keep as TYPE_19",
    }
    out = Path(args.output) if args.output else raw.with_suffix(".fields.json")
    out.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "success": True,
        "output": str(out),
        "root": info.get("root"),
        "list_size": info.get("list_size"),
        "type_histogram": info.get("type_histogram"),
        "nodes": len(info.get("nodes") or []),
        "links": len(info.get("links") or []),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
