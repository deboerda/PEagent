# -*- coding: utf-8 -*-
"""Behavior-graph CRUD for PE (.rg), offline-first.

Why offline-first:
- HTTP /api/graph/read|node/create opens the graph editor and stalls the 3D tick.
- RelaGraph inspect_rg loads a .rg via DLL without touching the live PE UI.

Capabilities:
  list     - peproj UIObject ID=49 entries + main/*.rg files
  read     - RelaGraph field table + string parse (programs/includes)
  create   - rg_create boot template -> main/<name>.rg + peproj register
  update   - replace length-prefixed program/include strings in .rg
  delete   - unregister peproj + remove .rg (optional)
  query    - filter nodes/links from read()

Native mutate (via tools/rg_native_mutate.exe + RelaGraph.dll):
  add_program / remove_node (WriteToBuffer round-trip)

Also (P0):
  update_graph_text_by_id - SetText by node id (safe with duplicate PROGRAM texts)
  boot_chain - follow BOOT.next (+ HUB CURVE notes)

Also (P2):
  index_project - offline Insight-style project .rg index (JSON)
  search_index - substring search over an index (Unicode-safe)

Not yet:
  full relink UX, TYPE_19 identity, live HTTP edit; VARIABLE InitialValue via set_variable_value (disk blob)
"""
from __future__ import annotations

import json
import re
import subprocess
import os
import shutil
import struct
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(r"E:\PEagent")
sys.path.insert(0, str(ROOT / "tools"))

from rg_create import create_boot_graph  # noqa: E402
from rg_parse import parse_rg  # noqa: E402
from rg_inspect_fields import run_inspect  # noqa: E402
from rg_fields_from_inspect import parse_inspect  # noqa: E402

GRAPH_UI_ID = "49"
UI_OBJECT_RE = re.compile(
    r'\s*<UIObject\s+Name="([^"]+\.rg)"\s+OnlyID="[^"]*"\s+ID="49"\s+Enable="([^"]*)"\s*/>',
    re.I,
)


def _project_dir(project: str | Path) -> Path:
    p = Path(project)
    if p.is_file() and p.suffix.lower() == ".peproj":
        return p.parent
    return p


def _peproj_path(project: str | Path) -> Path:
    d = _project_dir(project)
    hits = list(d.glob("*.peproj"))
    if not hits:
        raise FileNotFoundError(f"no .peproj under {d}")
    return hits[0]


def _main_dir(project: str | Path) -> Path:
    d = _project_dir(project) / "main"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _backup_file(path: Path) -> str:
    bak = path.with_suffix(path.suffix + f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    shutil.copy2(path, bak)
    return str(bak)


def _read_text_auto(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8-replace"


def list_graphs(project: str | Path) -> dict[str, Any]:
    """List registered graphs (peproj) and files under main/."""
    proj = _project_dir(project)
    peproj = _peproj_path(proj)
    text, enc = _read_text_auto(peproj)
    registered = []
    main = _main_dir(proj)
    main_names = {f.name for f in main.glob("*.rg")}
    for m in UI_OBJECT_RE.finditer(text):
        name = m.group(1)
        registered.append({
            "name": name,
            "enable": m.group(2),
            "path": str((main / name).resolve()),
            "exists": name in main_names,
        })
    files = []
    for rg in sorted(_main_dir(proj).glob("*.rg")):
        files.append({"name": rg.name, "path": str(rg.resolve()), "size": rg.stat().st_size})
    return {
        "success": True,
        "project": str(proj.resolve()),
        "peproj": str(peproj.resolve()),
        "registered": registered,
        "files": files,
        "registered_count": len(registered),
        "file_count": len(files),
    }


def read_graph(rg_path: str | Path, *, with_inspect: bool = True) -> dict[str, Any]:
    """Read one .rg: string parse always; RelaGraph inspect when with_inspect."""
    path = Path(rg_path)
    if not path.exists():
        return {"success": False, "error": f"missing {path}"}
    parsed = parse_rg(path)
    out: dict[str, Any] = {
        "success": True,
        "path": str(path.resolve()),
        "size": parsed["size"],
        "version": parsed.get("variant"),
        "variant_hex": parsed.get("variant_hex"),
        "programs": parsed.get("programs") or [],
        "includes": parsed.get("includes") or [],
        "records": parsed.get("records") or [],
        "mode": "parse",
    }
    if with_inspect:
        try:
            raw = run_inspect(path)
            fields = parse_inspect(raw)
            out["mode"] = "inspect+parse"
            out["root"] = fields.get("root")
            out["nodes"] = fields.get("nodes")
            out["links"] = fields.get("links")
            out["type_histogram"] = fields.get("type_histogram")
            out["list_size"] = fields.get("list_size")
            out["inspect_raw"] = str(raw)
            # Overlay length-prefixed parse programs onto PROGRAM nodes with empty/junk text.
            progs = list(out.get("programs") or [])
            pi = 0
            for n in out.get("nodes") or []:
                if n.get("type") == 6 or str(n.get("type_name", "")).upper() == "PROGRAM":
                    st = n.get("script_text")
                    if (not st) and pi < len(progs):
                        n["script_text"] = progs[pi]
                        n["script_text_source"] = "parse_overlay"
                        pi += 1
                    elif st:
                        pi += 1  # keep alignment when inspect already had text
            # overlay_programs
        except Exception as e:
            out["inspect_error"] = str(e)
            out["success"] = True  # parse still ok
            out["warning"] = "inspect failed; returning parse-only"
    return out


def query_graph(
    rg_path: str | Path,
    *,
    type_name: str = "",
    node_id: int | None = None,
) -> dict[str, Any]:
    """Filter nodes/links from read_graph(inspect)."""
    info = read_graph(rg_path, with_inspect=True)
    if not info.get("success"):
        return info
    nodes = list(info.get("nodes") or [])
    links = list(info.get("links") or [])
    if type_name:
        tn = type_name.upper()
        nodes = [n for n in nodes if str(n.get("type_name", "")).upper() == tn or str(n.get("type")) == type_name]
    if node_id is not None:
        nodes = [n for n in nodes if n.get("id") == node_id]
        links = [l for l in links if l.get("from") == node_id or l.get("to") == node_id or l.get("id") == node_id]
    return {
        "success": True,
        "path": info.get("path"),
        "root": info.get("root"),
        "nodes": nodes,
        "links": links,
        "programs": info.get("programs"),
        "includes": info.get("includes"),
        "count_nodes": len(nodes),
        "count_links": len(links),
    }


def _register_peproj(peproj: Path, rg_name: str, *, enable: str = "1") -> dict[str, Any]:
    text = _read_text_auto(peproj)[0]
    if re.search(rf'Name="{re.escape(rg_name)}"[^>]*ID="49"', text):
        return {"success": True, "already": True, "name": rg_name}
    line = f'                    <UIObject Name="{rg_name}" OnlyID="" ID="49" Enable="{enable}" />\n'
    # insert before UI_OBJ_TYPE_GRAPH id declaration block's last UIObject area:
    # place after last ID=49 UIObject, else before <ID Name="UI_OBJ_TYPE_GRAPH"
    m_all = list(UI_OBJECT_RE.finditer(text))
    bak = _backup_file(peproj)
    if m_all:
        last = m_all[-1]
        insert_at = last.end()
        # keep newline after
        if not text[insert_at:insert_at + 1].startswith("\n"):
            pass
        text = text[:insert_at] + "\n" + line.rstrip() + text[insert_at:]
    else:
        marker = '<ID Name="UI_OBJ_TYPE_GRAPH"'
        i = text.find(marker)
        if i < 0:
            return {"success": False, "error": "UI_OBJ_TYPE_GRAPH marker missing", "backup": bak}
        text = text[:i] + line + text[i:]
    peproj.write_text(text, encoding=_read_text_auto(peproj)[1] if False else "utf-8")
    return {"success": True, "already": False, "name": rg_name, "backup": bak}


def _unregister_peproj(peproj: Path, rg_name: str) -> dict[str, Any]:
    text = _read_text_auto(peproj)[0]
    pat = re.compile(
        rf'\s*<UIObject\s+Name="{re.escape(rg_name)}"\s+OnlyID="[^"]*"\s+ID="49"\s+Enable="[^"]*"\s*/>\s*',
        re.I,
    )
    if not pat.search(text):
        return {"success": True, "removed": False, "name": rg_name}
    bak = _backup_file(peproj)
    text2, n = pat.subn("\n", text, count=1)
    peproj.write_text(text2, encoding="utf-8")
    return {"success": True, "removed": n > 0, "name": rg_name, "backup": bak}


def create_graph(
    project: str | Path,
    name: str,
    *,
    calls: list[str] | None = None,
    include: str = r"main\Script\include.script",
    register: bool = True,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Create a boot .rg in project/main and optionally register in peproj."""
    proj = _project_dir(project)
    main = _main_dir(proj)
    rg_name = name if name.lower().endswith(".rg") else f"{name}.rg"
    dest = main / rg_name
    if dest.exists() and not overwrite:
        return {"success": False, "error": f"exists: {dest} (pass overwrite=True)"}
    tmp = Path(r"E:\AI\temp") / f"rg_crud_{rg_name}"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    created = create_boot_graph(str(tmp), include, calls or ["helloworld();"])
    if dest.exists():
        _backup_file(dest)
    shutil.copy2(tmp, dest)
    reg = _register_peproj(_peproj_path(proj), rg_name) if register else {"skipped": True}
    # verify readable
    verify = read_graph(dest, with_inspect=True)
    return {
        "success": bool(verify.get("success")) and bool(created.get("success")),
        "rg_path": str(dest.resolve()),
        "created": created,
        "register": reg,
        "readback": {
            "programs": verify.get("programs"),
            "includes": verify.get("includes"),
            "root": verify.get("root"),
            "list_size": verify.get("list_size"),
            "type_histogram": verify.get("type_histogram"),
            "inspect_error": verify.get("inspect_error"),
        },
        "note": "Reload/reopen project in PE for registration to appear in UI; avoid HTTP graph_* on live GDZ23.",
    }


def _replace_lenprefixed(data: bytes, old_text: str, new_text: str) -> bytes:
    old_gb = old_text.encode("gbk")
    new_gb = new_text.encode("gbk")
    old_rec = struct.pack("<I", len(old_gb) + 1) + old_gb + b"\x00"
    new_rec = struct.pack("<I", len(new_gb) + 1) + new_gb + b"\x00"
    if old_rec not in data:
        raise ValueError(f"record not found: {old_text!r}")
    return data.replace(old_rec, new_rec, 1)


def update_graph_text(
    rg_path: str | Path,
    *,
    old_text: str,
    new_text: str,
) -> dict[str, Any]:
    """Replace one length-prefixed GBK string record inside .rg (program/include/label)."""
    path = Path(rg_path)
    data = path.read_bytes()
    bak = _backup_file(path)
    try:
        data2 = _replace_lenprefixed(data, old_text, new_text)
    except ValueError as e:
        return {"success": False, "error": str(e), "backup": bak}
    path.write_bytes(data2)
    verify = read_graph(path, with_inspect=False)
    return {
        "success": True,
        "path": str(path.resolve()),
        "backup": bak,
        "old": old_text,
        "new": new_text,
        "size_before": len(data),
        "size_after": len(data2),
        "programs": verify.get("programs"),
        "includes": verify.get("includes"),
    }


def delete_graph(
    project: str | Path,
    name: str,
    *,
    delete_file: bool = True,
) -> dict[str, Any]:
    """Unregister from peproj and optionally delete main/<name>.rg."""
    proj = _project_dir(project)
    rg_name = name if name.lower().endswith(".rg") else f"{name}.rg"
    peproj = _peproj_path(proj)
    unreg = _unregister_peproj(peproj, rg_name)
    path = _main_dir(proj) / rg_name
    removed_file = False
    file_bak = None
    if delete_file and path.exists():
        file_bak = _backup_file(path)
        path.unlink()
        removed_file = True
    return {
        "success": True,
        "name": rg_name,
        "unregister": unreg,
        "removed_file": removed_file,
        "file_backup": file_bak,
        "path": str(path),
    }



NATIVE_MUTATE = ROOT / "tools" / "rg_native_mutate.exe"
RELAGRAPH_DLL = ROOT / "bin" / "Release-x64" / "RelaGraph.dll"
RELAGRAPH_CWD = ROOT / "bin" / "Release-x64"



def _text_arg_for_native(text: str) -> tuple[str, Path | None]:
    """Pass non-ASCII text via UTF-8 @file to avoid Windows argv ACP mangling."""
    if text.isascii():
        return text, None
    tmp = Path(r"E:\AI\temp") / f"rg_native_text_{os.getpid()}.utf8.txt"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(text, encoding="utf-8-sig")
    return f"@{tmp}", tmp


def _run_native_mutate(args: list[str]) -> dict[str, Any]:
    """Run rg_native_mutate.exe with cwd=Release-x64 so DLL deps resolve."""
    if not NATIVE_MUTATE.exists():
        return {"success": False, "error": f"missing {NATIVE_MUTATE}"}
    if not RELAGRAPH_DLL.exists():
        return {"success": False, "error": f"missing {RELAGRAPH_DLL}"}
    cmd = [str(NATIVE_MUTATE), *args]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(RELAGRAPH_CWD),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except Exception as e:
        return {"success": False, "error": str(e), "cmd": cmd}
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    return {
        "success": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": out,
        "stderr": err,
        "cmd": cmd,
    }


def add_program(
    rg_path: str | Path,
    text: str,
    *,
    x: float = 520.0,
    y: float = 220.0,
    link_from_id: int = 0,
    out_path: str | Path | None = None,
    inplace: bool = True,
) -> dict[str, Any]:
    """Add a PROGRAM node via RelaGraph CreateByType + WriteToBuffer (offline)."""
    path = Path(rg_path)
    if not path.exists():
        return {"success": False, "error": f"missing {path}"}
    bak = _backup_file(path) if inplace and out_path is None else None
    dest = Path(out_path) if out_path else path
    if out_path is None and not inplace:
        dest = path.with_suffix(path.suffix + ".mut.rg")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(r"E:\AI\temp") / f"rg_addprog_{path.stem}_{os.getpid()}.rg"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    text_arg, text_file = _text_arg_for_native(text)
    run = _run_native_mutate([
        "add-program",
        str(path.resolve()),
        str(tmp),
        str(RELAGRAPH_DLL),
        text_arg,
        str(x),
        str(y),
        str(int(link_from_id)),
    ])
    if text_file is not None:
        try:
            text_file.unlink(missing_ok=True)
        except Exception:
            pass
    if not run.get("success"):
        return {"success": False, "error": "native add-program failed", "native": run, "backup": bak}
    shutil.copy2(tmp, dest)
    try:
        tmp.unlink(missing_ok=True)
    except Exception:
        pass
    verify = read_graph(dest, with_inspect=True)
    return {
        "success": True,
        "path": str(dest.resolve()),
        "backup": bak,
        "text": text,
        "x": x,
        "y": y,
        "link_from_id": link_from_id,
        "native": {"stdout": run.get("stdout"), "stderr": run.get("stderr")},
        "programs": verify.get("programs"),
        "type_histogram": verify.get("type_histogram"),
        "nodes": verify.get("nodes"),
        "links": verify.get("links"),
        "size": verify.get("size"),
    }



def add_node(
    rg_path: str | Path,
    node_type: int,
    *,
    text: str = "",
    x: float = 520.0,
    y: float = 220.0,
    link_from_id: int = 0,
    out_path: str | Path | None = None,
    inplace: bool = True,
) -> dict[str, Any]:
    """Add a node of arbitrary RgType via CreateByType + WriteToBuffer (offline)."""
    path = Path(rg_path)
    if not path.exists():
        return {"success": False, "error": f"missing {path}"}
    bak = _backup_file(path) if inplace and out_path is None else None
    dest = Path(out_path) if out_path else path
    if out_path is None and not inplace:
        dest = path.with_suffix(path.suffix + ".mut.rg")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(r"E:\AI\temp") / f"rg_addtype_{path.stem}_{os.getpid()}.rg"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    text_arg, text_file = _text_arg_for_native(text)
    run = _run_native_mutate([
        "add-type",
        str(path.resolve()),
        str(tmp),
        str(RELAGRAPH_DLL),
        str(int(node_type)),
        str(x),
        str(y),
        text_arg,
        str(int(link_from_id)),
    ])
    if text_file is not None:
        try:
            text_file.unlink(missing_ok=True)
        except Exception:
            pass
    if not run.get("success"):
        return {"success": False, "error": "native add-type failed", "native": run, "backup": bak}
    shutil.copy2(tmp, dest)
    try:
        tmp.unlink(missing_ok=True)
    except Exception:
        pass
    verify = read_graph(dest, with_inspect=True)
    return {
        "success": True,
        "path": str(dest.resolve()),
        "backup": bak,
        "node_type": int(node_type),
        "text": text,
        "x": x,
        "y": y,
        "link_from_id": link_from_id,
        "native": {"stdout": run.get("stdout"), "stderr": run.get("stderr")},
        "programs": verify.get("programs"),
        "type_histogram": verify.get("type_histogram"),
        "nodes": verify.get("nodes"),
        "links": verify.get("links"),
        "size": verify.get("size"),
    }




def unlink_nodes(
    rg_path: str | Path,
    from_id: int,
    to_id: int,
    *,
    out_path: str | Path | None = None,
    inplace: bool = True,
) -> dict[str, Any]:
    """Remove CURVE edge from_id -> to_id (offline)."""
    path = Path(rg_path)
    if not path.exists():
        return {"success": False, "error": f"missing {path}"}
    bak = _backup_file(path) if inplace and out_path is None else None
    dest = Path(out_path) if out_path else path
    tmp = Path(r"E:\AI\temp") / f"rg_unlink_{path.stem}_{os.getpid()}.rg"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    run = _run_native_mutate([
        "unlink", str(path.resolve()), str(tmp), str(RELAGRAPH_DLL),
        str(int(from_id)), str(int(to_id)),
    ])
    if not run.get("success"):
        return {"success": False, "error": "native unlink failed", "native": run, "backup": bak}
    shutil.copy2(tmp, dest)
    try: tmp.unlink(missing_ok=True)
    except Exception: pass
    verify = read_graph(dest, with_inspect=True)
    return {
        "success": True, "path": str(dest.resolve()), "backup": bak,
        "from_id": int(from_id), "to_id": int(to_id),
        "native": {"stdout": run.get("stdout"), "stderr": run.get("stderr")},
        "links": verify.get("links"), "type_histogram": verify.get("type_histogram"),
        "size": verify.get("size"),
    }


def link_nodes(
    rg_path: str | Path,
    from_id: int,
    to_id: int,
    *,
    out_path: str | Path | None = None,
    inplace: bool = True,
) -> dict[str, Any]:
    """Create a CURVE edge from_id -> to_id via native mutate link (offline)."""
    path = Path(rg_path)
    if not path.exists():
        return {"success": False, "error": f"missing {path}"}
    bak = _backup_file(path) if inplace and out_path is None else None
    dest = Path(out_path) if out_path else path
    if out_path is None and not inplace:
        dest = path.with_suffix(path.suffix + ".mut.rg")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(r"E:\AI\temp") / f"rg_link_{path.stem}_{os.getpid()}.rg"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    run = _run_native_mutate([
        "link",
        str(path.resolve()),
        str(tmp),
        str(RELAGRAPH_DLL),
        str(int(from_id)),
        str(int(to_id)),
    ])
    if not run.get("success"):
        return {"success": False, "error": "native link failed", "native": run, "backup": bak}
    shutil.copy2(tmp, dest)
    try:
        tmp.unlink(missing_ok=True)
    except Exception:
        pass
    verify = read_graph(dest, with_inspect=True)
    return {
        "success": True,
        "path": str(dest.resolve()),
        "backup": bak,
        "from_id": int(from_id),
        "to_id": int(to_id),
        "native": {"stdout": run.get("stdout"), "stderr": run.get("stderr")},
        "links": verify.get("links"),
        "type_histogram": verify.get("type_histogram"),
        "size": verify.get("size"),
    }


def remove_node(
    rg_path: str | Path,
    node_id: int,
    *,
    out_path: str | Path | None = None,
    inplace: bool = True,
) -> dict[str, Any]:
    """Remove a node by id via RelaGraph RemoveObject + WriteToBuffer (offline)."""
    path = Path(rg_path)
    if not path.exists():
        return {"success": False, "error": f"missing {path}"}
    bak = _backup_file(path) if inplace and out_path is None else None
    dest = Path(out_path) if out_path else path
    if out_path is None and not inplace:
        dest = path.with_suffix(path.suffix + ".mut.rg")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(r"E:\AI\temp") / f"rg_rmnode_{path.stem}_{os.getpid()}.rg"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    run = _run_native_mutate([
        "remove-id",
        str(path.resolve()),
        str(tmp),
        str(RELAGRAPH_DLL),
        str(int(node_id)),
    ])
    if not run.get("success"):
        return {"success": False, "error": "native remove-id failed", "native": run, "backup": bak}
    shutil.copy2(tmp, dest)
    try:
        tmp.unlink(missing_ok=True)
    except Exception:
        pass
    verify = read_graph(dest, with_inspect=True)
    return {
        "success": True,
        "path": str(dest.resolve()),
        "backup": bak,
        "removed_id": int(node_id),
        "native": {"stdout": run.get("stdout"), "stderr": run.get("stderr")},
        "programs": verify.get("programs"),
        "type_histogram": verify.get("type_histogram"),
        "nodes": verify.get("nodes"),
        "links": verify.get("links"),
        "size": verify.get("size"),
    }



def _replace_lenprefixed_nth(data: bytes, old_text: str, new_text: str, nth: int = 0) -> bytes:
    """Replace the nth (0-based) length-prefixed GBK string record."""
    old_gb = old_text.encode("gbk")
    new_gb = new_text.encode("gbk")
    old_rec = struct.pack("<I", len(old_gb) + 1) + old_gb + b"\x00"
    new_rec = struct.pack("<I", len(new_gb) + 1) + new_gb + b"\x00"
    start = 0
    found = -1
    pos = -1
    while True:
        i = data.find(old_rec, start)
        if i < 0:
            break
        found += 1
        if found == nth:
            pos = i
            break
        start = i + 1
    if pos < 0:
        raise ValueError(f"record nth={nth} not found for {old_text!r} (matches={found + 1})")
    return data[:pos] + new_rec + data[pos + len(old_rec):]


def _node_display_text(node: dict[str, Any]) -> str:
    for key in ("script_text", "text"):
        v = node.get(key)
        if isinstance(v, str) and v and not v.startswith("vtable="):
            return v
    return ""


def update_graph_text_by_id(
    rg_path: str | Path,
    node_id: int,
    new_text: str,
    *,
    out_path: str | Path | None = None,
    inplace: bool = True,
    prefer_native: bool = True,
) -> dict[str, Any]:
    """Change PROGRAM/node text by node id (not first string match).

    Prefers native SetText via rg_native_mutate set-text so duplicate texts
    (e.g. two 主页面初始状态) only update the target id. Falls back to replacing
    the Nth length-prefixed GBK record among matching PROGRAM overlays.
    """
    path = Path(rg_path)
    if not path.exists():
        return {"success": False, "error": f"missing {path}"}
    before = read_graph(path, with_inspect=True)
    nodes = list(before.get("nodes") or [])
    target = next((n for n in nodes if n.get("id") == int(node_id)), None)
    if target is None:
        return {"success": False, "error": f"node id {node_id} not found", "path": str(path)}

    bak = _backup_file(path) if inplace and out_path is None else None
    dest = Path(out_path) if out_path else path
    if out_path is None and not inplace:
        dest = path.with_suffix(path.suffix + ".settext.rg")
    dest.parent.mkdir(parents=True, exist_ok=True)

    method = None
    native = None
    if prefer_native and NATIVE_MUTATE.exists() and RELAGRAPH_DLL.exists():
        tmp = Path(r"E:\AI\temp") / f"rg_settext_{path.stem}_{os.getpid()}.rg"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        text_arg, text_file = _text_arg_for_native(new_text)
        native = _run_native_mutate([
            "set-text",
            str(path.resolve()),
            str(tmp),
            str(RELAGRAPH_DLL),
            str(int(node_id)),
            text_arg,
        ])
        if text_file is not None:
            try:
                text_file.unlink(missing_ok=True)
            except Exception:
                pass
        if native.get("success"):
            shutil.copy2(tmp, dest)
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            method = "native_set_text"
        else:
            method = "native_failed_fallback_disk"

    if method != "native_set_text":
        # Disk fallback: replace Nth duplicate among PROGRAM/SCRIPT overlays.
        old_text = _node_display_text(target)
        programs = list(before.get("programs") or [])
        includes = list(before.get("includes") or [])
        if not old_text:
            # Align PROGRAM nodes with empty inspect text to programs list order.
            pi = 0
            for n in nodes:
                is_prog = n.get("type") == 6 or str(n.get("type_name", "")).upper() == "PROGRAM"
                if not is_prog:
                    continue
                st = _node_display_text(n)
                if not st and pi < len(programs):
                    if n.get("id") == int(node_id):
                        old_text = programs[pi]
                        break
                    pi += 1
                elif st:
                    if n.get("id") == int(node_id):
                        old_text = st
                        break
                    pi += 1
        if not old_text:
            return {
                "success": False,
                "error": f"cannot resolve old text for id={node_id}",
                "native": native,
                "backup": bak,
            }
        # Occurrence among all identical length-prefixed records in file order
        # approximated by programs+includes order matching old_text.
        all_recs = list(programs) + list(includes)
        # Prefer occurrence index among PROGRAM nodes that share this text,
        # ordered by inspect node order (same as parse overlay walk).
        same_prog_ids = []
        pi = 0
        for n in nodes:
            is_prog = n.get("type") == 6 or str(n.get("type_name", "")).upper() == "PROGRAM"
            if not is_prog:
                continue
            st = _node_display_text(n)
            if not st and pi < len(programs):
                st = programs[pi]
                pi += 1
            elif st:
                pi += 1
            if st == old_text:
                same_prog_ids.append(n.get("id"))
        if int(node_id) in same_prog_ids:
            nth = same_prog_ids.index(int(node_id))
        else:
            # fall back to first matching program record index among all_recs
            try:
                nth = next(i for i, s in enumerate(all_recs) if s == old_text)
            except StopIteration:
                nth = 0
        data = path.read_bytes()
        try:
            data2 = _replace_lenprefixed_nth(data, old_text, new_text, nth=nth)
        except ValueError as e:
            return {
                "success": False,
                "error": str(e),
                "old_text": old_text,
                "nth": nth,
                "native": native,
                "backup": bak,
            }
        dest.write_bytes(data2)
        method = "disk_nth_record"
        native = native

    verify = read_graph(dest, with_inspect=True)
    # Confirm only target id changed among same-old-text peers when possible.
    after_nodes = {n.get("id"): n for n in (verify.get("nodes") or [])}
    target_after = after_nodes.get(int(node_id))
    return {
        "success": True,
        "path": str(dest.resolve()),
        "backup": bak,
        "node_id": int(node_id),
        "new_text": new_text,
        "method": method,
        "native": {"stdout": (native or {}).get("stdout"), "stderr": (native or {}).get("stderr"),
                   "returncode": (native or {}).get("returncode")} if native else None,
        "programs": verify.get("programs"),
        "type_histogram": verify.get("type_histogram"),
        "target_text_after": _node_display_text(target_after) if target_after else None,
        "size": verify.get("size"),
    }


def boot_chain(
    rg_path: str | Path,
    *,
    max_steps: int = 64,
    include_curves_from_hub: bool = True,
) -> dict[str, Any]:
    """Discover startup chain: BOOT --next--> ... ; document HUB CURVE fan-out.

    Follows each node's `next` field from the first BOOT. For HUB nodes, also
    lists outgoing CURVE edges (does not branch the ordered chain — runtime
    primary path is `next`; see hub_fanout experiment notes).
    """
    path = Path(rg_path)
    info = read_graph(path, with_inspect=True)
    if not info.get("success") and not info.get("nodes"):
        return {"success": False, "error": info.get("error") or info.get("inspect_error") or "read failed",
                "path": str(path)}
    nodes = list(info.get("nodes") or [])
    links = list(info.get("links") or [])
    # Prefer real flow types when inspect emits duplicate ids (seen: BOOT+BUTTON share id).
    _pri = {11: 0, 4: 1, 6: 2, 9: 3, 1: 4, 14: 5, 8: 6, 12: 7, 19: 90}
    by_id: dict[Any, dict[str, Any]] = {}
    for n in nodes:
        i = n.get("id")
        if i not in by_id:
            by_id[i] = n
        else:
            if _pri.get(n.get("type"), 50) < _pri.get(by_id[i].get("type"), 50):
                by_id[i] = n
    boots = [n for n in nodes if n.get("type") == 11 or str(n.get("type_name", "")).upper() == "BOOT"]
    if not boots:
        return {"success": False, "error": "no BOOT node", "path": str(path.resolve()),
                "nodes": nodes, "links": links}
    boot = sorted(boots, key=lambda n: n.get("id") or 0)[0]
    by_id[boot.get("id")] = boot  # force BOOT over any duplicate-id collision
    chain: list[dict[str, Any]] = []
    hub_notes: list[dict[str, Any]] = []
    seen: set[int] = set()
    cur_id = boot.get("id")
    steps = 0
    while cur_id and cur_id not in seen and steps < max_steps:
        seen.add(int(cur_id))
        node = by_id.get(cur_id)
        if not node:
            chain.append({"id": cur_id, "type": None, "type_name": "MISSING", "text": None, "next": None})
            break
        text = _node_display_text(node)
        # overlay programs onto PROGRAM with empty text (same as read_graph)
        entry = {
            "id": node.get("id"),
            "type": node.get("type"),
            "type_name": node.get("type_name"),
            "text": text or None,
            "prev": node.get("prev"),
            "next": node.get("next"),
        }
        chain.append(entry)
        tn = str(node.get("type_name", "")).upper()
        if include_curves_from_hub and (node.get("type") == 4 or tn == "HUB"):
            outs = [l for l in links if l.get("from") == node.get("id")]
            hub_notes.append({
                "hub_id": node.get("id"),
                "next": node.get("next"),
                "curve_outs": outs,
                "note": "Ordered boot_chain follows hub.next only; curve_outs are fan-out candidates.",
            })
        nxt = node.get("next") or 0
        if not nxt:
            break
        cur_id = nxt
        steps += 1

    # Fill PROGRAM texts from programs list when inspect text empty
    programs = list(info.get("programs") or [])
    pi = 0
    prog_nodes_all = [n for n in nodes if n.get("type") == 6 or str(n.get("type_name", "")).upper() == "PROGRAM"]
    id_to_prog_text: dict[int, str] = {}
    for n in prog_nodes_all:
        st = _node_display_text(n)
        if st:
            id_to_prog_text[int(n["id"])] = st
            # keep pi aligned roughly when inspect had text — skip one program slot if matches head
            if pi < len(programs) and programs[pi] == st:
                pi += 1
            elif pi < len(programs) and st not in programs[pi:pi+1]:
                pass
        else:
            if pi < len(programs):
                id_to_prog_text[int(n["id"])] = programs[pi]
                pi += 1
    for entry in chain:
        if (entry.get("type") == 6 or str(entry.get("type_name", "")).upper() == "PROGRAM") and not entry.get("text"):
            entry["text"] = id_to_prog_text.get(int(entry["id"]))

    return {
        "success": True,
        "path": str(path.resolve()),
        "boot_id": boot.get("id"),
        "chain": chain,
        "length": len(chain),
        "hub_notes": hub_notes,
        "semantics": {
            "follow": "node.next from BOOT",
            "hub": "HUB.next is primary continuation; outgoing CURVE list is fan-out (see experiment)",
        },
    }



def set_variable_value(
    rg_path: str | Path,
    node_id: int,
    value,
    *,
    encoding: str = "auto",
    out_path: str | Path | None = None,
    inplace: bool = True,
) -> dict[str, Any]:
    """Write VARIABLE InitialValue 32B proprietary blob offline (disk patch).

    Does not use SetText. TIMER conditions stay on update_graph_text_by_id.
    value/encoding: see tools.rg_disk_record.encode_variable_blob.
    """
    from rg_disk_record import (  # noqa: WPS433
        encode_variable_blob,
        patch_variable_blob,
        find_object_by_id,
        decode_prop_tail,
    )

    path = Path(rg_path)
    if not path.exists():
        return {"success": False, "error": f"missing {path}"}
    bak = _backup_file(path) if inplace and out_path is None else None
    dest = Path(out_path) if out_path else path
    if out_path is None and not inplace:
        dest = path.with_suffix(path.suffix + ".var.rg")
    data = path.read_bytes()
    try:
        blob = encode_variable_blob(value, encoding=encoding)
        data2, meta = patch_variable_blob(data, int(node_id), blob)
    except Exception as e:
        return {"success": False, "error": str(e), "backup": bak}
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data2)
    # readback via disk decode (no need inspect for blob)
    verify_hit = find_object_by_id(data2, int(node_id), typ=12)
    prop = (verify_hit or {}).get("prop") or {}
    blob_field = None
    for f in prop.get("fields") or []:
        if f.get("name") == "value_blob":
            blob_field = f
            break
    return {
        "success": True,
        "path": str(dest.resolve()),
        "backup": bak,
        "node_id": int(node_id),
        "encoding": encoding,
        "value": value if not isinstance(value, (bytes, bytearray)) else bytes(value).hex(),
        "blob_hex": blob.hex(),
        "meta": meta,
        "readback_blob_hex": (blob_field or {}).get("value_hex"),
        "readback_prop_hex": prop.get("prop_hex"),
        "text": (verify_hit or {}).get("text"),
        "markers": meta.get("markers"),
        "size_before": len(data),
        "size_after": len(data2),
        "note": "Offline disk patch of prop+20..+51; SetText does not touch this blob.",
    }


def set_prop_tail(
    rg_path: str | Path,
    node_id: int,
    prop_hex: str,
    *,
    typ: int | None = None,
    out_path: str | Path | None = None,
    inplace: bool = True,
) -> dict[str, Any]:
    """Replace full proprietary tail for a node (hex). Length must match type default."""
    from rg_disk_record import patch_prop_tail, find_object_by_id  # noqa: WPS433

    path = Path(rg_path)
    if not path.exists():
        return {"success": False, "error": f"missing {path}"}
    bak = _backup_file(path) if inplace and out_path is None else None
    dest = Path(out_path) if out_path else path
    data = path.read_bytes()
    try:
        prop_bytes = bytes.fromhex(prop_hex.replace(" ", "").replace("0x", ""))
        data2, meta = patch_prop_tail(data, int(node_id), prop_bytes, typ=typ)
    except Exception as e:
        return {"success": False, "error": str(e), "backup": bak}
    dest.write_bytes(data2)
    hit = find_object_by_id(data2, int(node_id))
    return {
        "success": True,
        "path": str(dest.resolve()),
        "backup": bak,
        "meta": meta,
        "readback_prop_hex": (hit or {}).get("prop", {}).get("prop_hex"),
    }


def inspect_prop_tail(rg_path: str | Path, node_id: int) -> dict[str, Any]:
    """Decode proprietary tail for one node id (offline, no DLL)."""
    from rg_disk_record import find_object_by_id, decode_instruct_extra_strings  # noqa: WPS433

    path = Path(rg_path)
    if not path.exists():
        return {"success": False, "error": f"missing {path}"}
    hit = find_object_by_id(path.read_bytes(), int(node_id))
    if not hit:
        return {"success": False, "error": f"id={node_id} not found", "path": str(path)}
    out: dict[str, Any] = {
        "success": True,
        "path": str(path.resolve()),
        "id": hit["id"],
        "type": hit["type"],
        "text": hit.get("text"),
        "abs_offset": hit["abs_offset"],
        "prop_offset": hit["prop_offset"],
        "prop": hit.get("prop"),
    }
    if hit["type"] in (9, 16):
        out["instruct_extras"] = decode_instruct_extra_strings(hit["prop"]["prop_hex"])
    return out


def set_timer_condition(
    rg_path: str | Path,
    node_id: int,
    condition: str,
    *,
    out_path: str | Path | None = None,
    inplace: bool = True,
) -> dict[str, Any]:
    """TIMER condition/expression is the common text field — delegates to update_graph_text_by_id."""
    return update_graph_text_by_id(
        rg_path, int(node_id), condition, out_path=out_path, inplace=inplace
    )




def _is_backup_path(path: Path) -> bool:
    return any(part.lower() == "backup" for part in path.parts)


def _discover_rg_paths(
    project: str | Path,
    *,
    include_backups: bool = False,
) -> list[Path]:
    """Discover .rg files under a PE project (read-only; no mkdir).

    Sources:
      - project/main/**/*.rg (nested module graphs)
      - project/*.rg
      - peproj UIObject ID=49 registered names under main/
    Skips backup/ unless include_backups.
    """
    proj = _project_dir(project)
    found: dict[str, Path] = {}

    def _add(p: Path) -> None:
        try:
            if not p.is_file() or p.suffix.lower() != ".rg":
                return
            if not include_backups and _is_backup_path(p):
                return
            key = str(p.resolve()).casefold()
            found[key] = p.resolve()
        except OSError:
            return

    main = proj / "main"
    if main.is_dir():
        for rg in main.rglob("*.rg"):
            _add(rg)
    for rg in proj.glob("*.rg"):
        _add(rg)

    try:
        peproj = _peproj_path(proj)
        text_pe, _enc = _read_text_auto(peproj)
        for m in UI_OBJECT_RE.finditer(text_pe):
            name = m.group(1)
            _add(main / name)
            # registered basename may live in a nested module folder
            if main.is_dir():
                base = Path(name).name
                for hit in main.rglob(base):
                    _add(hit)
    except FileNotFoundError:
        pass

    return sorted(found.values(), key=lambda p: str(p).casefold())


def _text_stub(text: str | None, limit: int = 120) -> str | None:
    if not text:
        return None
    s = str(text)
    if len(s) <= limit:
        return s
    return s[:limit] + "…"


def _summarize_one_graph(
    rg_path: Path,
    *,
    project: Path | None = None,
    with_inspect: bool = True,
    with_boot_chain: bool = True,
    text_stub_len: int = 120,
) -> dict[str, Any]:
    """Build one Insight-style graph summary (read-only)."""
    path = Path(rg_path)
    info = read_graph(path, with_inspect=with_inspect)
    nodes = list(info.get("nodes") or [])
    links = list(info.get("links") or [])
    programs = list(info.get("programs") or [])
    includes = list(info.get("includes") or [])

    # Prefer inspect histogram; else count from nodes
    hist = info.get("type_histogram")
    if not hist and nodes:
        hist = {}
        for n in nodes:
            key = str(n.get("type_name") or n.get("type") or "?")
            hist[key] = int(hist.get(key, 0)) + 1

    stubs: list[dict[str, Any]] = []
    for n in nodes:
        stubs.append({
            "id": n.get("id"),
            "type": n.get("type"),
            "type_name": n.get("type_name"),
            "text": _text_stub(_node_display_text(n), text_stub_len),
        })

    try:
        rel = str(path.resolve().relative_to(project.resolve())) if project else path.name
    except ValueError:
        rel = path.name

    out: dict[str, Any] = {
        "path": str(path.resolve()),
        "name": path.name,
        "rel_path": rel.replace("\\", "/"),
        "size": info.get("size") or (path.stat().st_size if path.exists() else 0),
        "success": bool(info.get("success")),
        "mode": info.get("mode"),
        "version": info.get("version"),
        "node_count": len(nodes),
        "link_count": len(links),
        "type_histogram": hist or {},
        "programs": programs,
        "includes": includes,
        "nodes": stubs,
    }
    if info.get("inspect_error"):
        out["inspect_error"] = info["inspect_error"]
    if info.get("warning"):
        out["warning"] = info["warning"]

    if with_boot_chain:
        try:
            bc = boot_chain(path, include_curves_from_hub=True)
            chain_sum = []
            for e in bc.get("chain") or []:
                chain_sum.append({
                    "id": e.get("id"),
                    "type": e.get("type"),
                    "type_name": e.get("type_name"),
                    "text": _text_stub(e.get("text"), text_stub_len),
                    "next": e.get("next"),
                })
            out["boot_chain"] = {
                "success": bool(bc.get("success")),
                "boot_id": bc.get("boot_id"),
                "length": bc.get("length"),
                "chain": chain_sum,
                "error": bc.get("error"),
            }
        except Exception as exc:  # noqa: BLE001 — index must continue
            out["boot_chain"] = {"success": False, "error": str(exc)}
    return out


def index_project(
    project_or_peproj_or_dir: str | Path,
    *,
    with_inspect: bool = True,
    with_boot_chain: bool = True,
    include_backups: bool = False,
    out_path: str | Path | None = None,
    text_stub_len: int = 120,
    grep: str | None = None,
) -> dict[str, Any]:
    """Offline Insight-style index of all behavior graphs in a PE project.

    Discovers .rg under main/** and peproj registrations. Never mutates .rg.
    Writes JSON when out_path is set. Optional grep= runs search_index on result.
    """
    proj = _project_dir(project_or_peproj_or_dir)
    peproj_s = None
    try:
        peproj_s = str(_peproj_path(proj).resolve())
    except FileNotFoundError:
        peproj_s = None

    paths = _discover_rg_paths(proj, include_backups=include_backups)
    graphs: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for rg in paths:
        try:
            graphs.append(_summarize_one_graph(
                rg,
                project=proj,
                with_inspect=with_inspect,
                with_boot_chain=with_boot_chain,
                text_stub_len=text_stub_len,
            ))
        except Exception as exc:  # noqa: BLE001
            errors.append({"path": str(rg), "error": str(exc)})

    index: dict[str, Any] = {
        "success": True,
        "version": "rg_index_v1",
        "project": str(proj.resolve()),
        "peproj": peproj_s,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "graph_count": len(graphs),
        "graphs": graphs,
        "errors": errors,
        "offline": True,
        "mutated": False,
    }

    if out_path is not None:
        outp = Path(out_path)
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        index["out_path"] = str(outp.resolve())

    if grep:
        index["grep"] = search_index(index, grep)

    return index


def search_index(
    index: dict[str, Any] | str | Path,
    query: str,
    *,
    ignore_case: bool = True,
) -> dict[str, Any]:
    """Find graphs/nodes whose text contains substring (Unicode / Chinese safe).

    Searches: graph name/path, programs, includes, node text stubs, boot_chain texts.
    """
    if isinstance(index, (str, Path)):
        p = Path(index)
        data = json.loads(p.read_text(encoding="utf-8"))
    else:
        data = index

    if not query:
        return {"success": False, "error": "empty query", "hit_count": 0, "hits": []}

    q = query.casefold() if ignore_case else query
    hits: list[dict[str, Any]] = []

    def _match(s: Any) -> bool:
        if s is None:
            return False
        text = str(s)
        return (q in text.casefold()) if ignore_case else (query in text)

    for g in data.get("graphs") or []:
        gpath = g.get("path") or g.get("rel_path") or g.get("name")
        # graph-level
        if _match(g.get("name")) or _match(g.get("rel_path")) or _match(gpath):
            hits.append({
                "kind": "graph",
                "graph": g.get("rel_path") or g.get("name"),
                "path": gpath,
                "match": g.get("name") or g.get("rel_path"),
            })
        for i, prog in enumerate(g.get("programs") or []):
            if _match(prog):
                hits.append({
                    "kind": "program",
                    "graph": g.get("rel_path") or g.get("name"),
                    "path": gpath,
                    "program_index": i,
                    "text": _text_stub(prog, 200),
                })
        for i, inc in enumerate(g.get("includes") or []):
            if _match(inc):
                hits.append({
                    "kind": "include",
                    "graph": g.get("rel_path") or g.get("name"),
                    "path": gpath,
                    "include_index": i,
                    "text": _text_stub(inc, 200),
                })
        for n in g.get("nodes") or []:
            if _match(n.get("text")):
                hits.append({
                    "kind": "node",
                    "graph": g.get("rel_path") or g.get("name"),
                    "path": gpath,
                    "node_id": n.get("id"),
                    "type": n.get("type"),
                    "type_name": n.get("type_name"),
                    "text": n.get("text"),
                })
        bc = g.get("boot_chain") or {}
        for e in bc.get("chain") or []:
            if _match(e.get("text")):
                hits.append({
                    "kind": "boot_chain",
                    "graph": g.get("rel_path") or g.get("name"),
                    "path": gpath,
                    "node_id": e.get("id"),
                    "type_name": e.get("type_name"),
                    "text": e.get("text"),
                })

    return {
        "success": True,
        "query": query,
        "ignore_case": ignore_case,
        "hit_count": len(hits),
        "hits": hits,
        "project": data.get("project"),
        "graph_count": data.get("graph_count"),
    }



def capabilities() -> dict[str, Any]:
    return {
        "success": True,
        "crud": {
            "list": True,
            "read": True,
            "create_boot": True,
            "update_text": True,
            "update_text_by_id": True,
            "boot_chain": True,
            "delete": True,
            "query_nodes_links": True,
            "add_program": True,
            "add_node": True,
            "remove_node": True,
            "link_nodes": True,
            "unlink_nodes": True,
            "set_variable_value": True,
            "set_prop_tail": True,
            "inspect_prop_tail": True,
            "set_timer_condition": "via update_graph_text_by_id (text field)",
            "index_project": True,
            "search_index": True,
            "add_arbitrary_node": "yes via add_node(type); TIP/BEHAVIOR unsupported",
            "delete_arbitrary_node": "partial (by id via native)",
            "relink": "link_nodes + link_from_id; remove clears orphan curves",
            "http_live_edit": False,
        },
        "native_mutate": {
            "exe": str(NATIVE_MUTATE),
            "dll": str(RELAGRAPH_DLL),
            "exists": NATIVE_MUTATE.exists() and RELAGRAPH_DLL.exists(),
        },
        "redlines": [
            "Do not call /api/graph/read|node/create on a live 3D session — opens graph editor and stalls tick.",
            "Prefer offline rg_crud + RelaGraph inspect_rg.",
            "create_boot uses helloworld.rg template (0x3b framing); release_combo template is unsafe.",
            "add_program/remove_node require tools/rg_native_mutate.exe + bin/Release-x64/RelaGraph.dll; run offline only.",
            "peproj register needs project reload to show in PE UI.",
        ],
    }


def reload_native(path: str = "", filename: str = "", name: str = "") -> dict[str, Any]:
    """Thin wrapper: pe_client.native_pipe.rg_reload (non-UI BuildGraph path)."""
    from pe_client.native_pipe import rg_reload
    return rg_reload(path=path, filename=filename, name=name)
