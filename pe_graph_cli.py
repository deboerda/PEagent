#!/usr/bin/env python3
"""Atomic RelaGraph CLI.

Each mutation changes one session object and immediately materializes the
session through the native Release RelaGraph writer.  The session JSON is the
editable composition layer; the .rg file is always native serialization.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_DLL = ROOT / "bin" / "Release-x64" / "RelaGraph.dll"
DEFAULT_BUILDER = ROOT / "tools" / "build_graph_from_plan.exe"


def fail(message: str) -> None:
    print(json.dumps({"success": False, "error": message}, ensure_ascii=False, indent=2))
    raise SystemExit(1)


def register_existing(name: str, filename: str, base_url: str) -> dict:
    """Register an existing native .rg without rewriting its bytes."""
    graph_file = Path(filename).resolve()
    if not graph_file.is_file():
        fail(f"graph file not found: {graph_file}")
    payload = json.dumps({"name": name, "filename": str(graph_file)}).encode("utf-8")
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/graph/register",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            fail(f"graph registration HTTP {exc.code}: {body[:300]}")
    except (urllib.error.URLError, TimeoutError) as exc:
        fail(f"cannot reach PEHelloMCP at {base_url}: {exc}")


def session_file(value: str) -> Path:
    path = Path(value).resolve()
    if path.suffix != ".json":
        path = Path(str(path) + ".session.json")
    return path


def load_session(value: str) -> tuple[Path, dict]:
    path = session_file(value)
    if not path.exists():
        fail(f"session not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"invalid session: {exc}")
    return path, data


def write_session(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def node_map(data: dict) -> dict[int, dict]:
    return {int(n["id"]): n for n in data.get("nodes", [])}


def materialize(session_path: Path, data: dict, builder: Path, dll: Path) -> dict:
    output = Path(data["graph_file"]).resolve()
    plan = session_path.with_suffix(".plan")
    lines = []
    for node in data.get("nodes", []):
        if node["type"] == "root":
            continue
        text = str(node.get("text", "")).replace("|", " ")
        lines.append("node|{id}|{type}|{x}|{y}|{text}".format(
            id=node["id"], type=node["type"], x=node.get("x", 0),
            y=node.get("y", 0), text=text,
        ))
    for link in data.get("links", []):
        lines.append(f"link|{link['from']}|{link['to']}")
    plan.write_text("\n".join(lines) + "\n", encoding="utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    child_env = os.environ.copy()
    child_env["PATH"] = str(dll.parent) + os.pathsep + child_env.get("PATH", "")
    completed = subprocess.run(
        [str(builder), str(output), str(dll), str(plan)],
        cwd=str(ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        env=child_env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    result = {
        "materialized": completed.returncode == 0,
        "graph_file": str(output),
        "plan_file": str(plan),
        "builder_exit_code": completed.returncode,
        "builder_output": (completed.stdout + completed.stderr).strip(),
    }
    if completed.returncode != 0:
        fail(json.dumps(result, ensure_ascii=False))
    return result


def mutate(args: argparse.Namespace, operation: str) -> None:
    path, data = load_session(args.session)
    nodes = node_map(data)
    if operation == "node-create":
        node_type = args.type.lower()
        if node_type == "root":
            if 1 not in nodes:
                data.setdefault("nodes", []).insert(0, {"id": 1, "type": "root", "x": 0, "y": 0, "text": "root"})
                node_id = 1
            else:
                node_id = 1
        else:
            node_id = args.id if args.id is not None else max(nodes or {1}) + 1
            if node_id in nodes:
                fail(f"node id already exists: {node_id}")
            default_text = {
                "script": "main\\Script\\include.script",
                "program": "helloworld();",
            }.get(node_type, "")
            data.setdefault("nodes", []).append({
                "id": node_id, "type": node_type, "x": args.x,
                "y": args.y, "text": args.text if args.text is not None else default_text,
            })
    elif operation == "node-move":
        if args.id not in nodes:
            fail(f"node id not found: {args.id}")
        nodes[args.id]["x"], nodes[args.id]["y"] = args.x, args.y
    elif operation == "node-set-text":
        if args.id not in nodes:
            fail(f"node id not found: {args.id}")
        nodes[args.id]["text"] = args.text
    elif operation == "link":
        if args.from_id not in nodes or args.to_id not in nodes:
            fail("link endpoint node id not found")
        if any(l["from"] == args.from_id and l["to"] == args.to_id for l in data.get("links", [])):
            fail("link already exists")
        data.setdefault("links", []).append({"from": args.from_id, "to": args.to_id})
    write_session(path, data)
    build_result = materialize(path, data, Path(args.builder), Path(args.dll))
    print(json.dumps({
        "success": True, "operation": operation, "session": str(path),
        "nodes": data.get("nodes", []), "links": data.get("links", []),
        **build_result,
    }, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Atomic native RelaGraph CLI")
    parser.add_argument("--builder", default=str(DEFAULT_BUILDER))
    parser.add_argument("--dll", default=str(DEFAULT_DLL))
    parser.add_argument("--url", default=os.environ.get("PE_MCP_URL", "http://127.0.0.1:8080"),
                        help="PEHelloMCP base URL for registration")
    sub = parser.add_subparsers(dest="command", required=True)

    new = sub.add_parser("session-new", help="create an empty graph session")
    new.add_argument("--output", required=True, help="target .rg file")

    node = sub.add_parser("node-create", help="create exactly one graph node")
    node.add_argument("--session", required=True)
    node.add_argument("--type", required=True, choices=["root", "boot", "hub", "script", "program", "curve", "button"])
    node.add_argument("--id", type=int)
    node.add_argument("--x", type=float, default=120)
    node.add_argument("--y", type=float, default=120)
    node.add_argument("--text")

    move = sub.add_parser("node-move", help="move exactly one node")
    move.add_argument("--session", required=True); move.add_argument("--id", type=int, required=True)
    move.add_argument("--x", type=float, required=True); move.add_argument("--y", type=float, required=True)

    text = sub.add_parser("node-set-text", help="set exactly one node text")
    text.add_argument("--session", required=True); text.add_argument("--id", type=int, required=True); text.add_argument("--text", required=True)

    link = sub.add_parser("link", help="create exactly one connection")
    link.add_argument("--session", required=True); link.add_argument("--from", dest="from_id", type=int, required=True); link.add_argument("--to", dest="to_id", type=int, required=True)

    show = sub.add_parser("show", help="show current session")
    show.add_argument("--session", required=True)

    register = sub.add_parser("register", help="register an existing .rg without replacing it")
    register.add_argument("--name", required=True, help="name shown in the PE project tree")
    register.add_argument("filename", help="existing native .rg file")

    args = parser.parse_args()
    if args.command == "register":
        result = register_existing(args.name, args.filename, args.url)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("success") else 1
    if not Path(args.builder).exists(): fail(f"builder not found: {args.builder}")
    if not Path(args.dll).exists(): fail(f"RelaGraph.dll not found: {args.dll}")
    if args.command == "session-new":
        output = Path(args.output).resolve()
        path = session_file(str(output))
        data = {"version": 1, "graph_file": str(output), "nodes": [{"id": 1, "type": "root", "x": 0, "y": 0, "text": "root"}], "links": []}
        write_session(path, data)
        result = materialize(path, data, Path(args.builder), Path(args.dll))
        print(json.dumps({"success": True, "operation": "session-new", "session": str(path), **result}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "show":
        path, data = load_session(args.session)
        print(json.dumps({"success": True, "session": str(path), **data}, ensure_ascii=False, indent=2)); return 0
    if args.command in {"node-create", "node-move", "node-set-text", "link"}:
        mutate(args, args.command); return 0
    return 2


if __name__ == "__main__":
    main()
