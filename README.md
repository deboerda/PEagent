# PEagent — MCP + CLI + SDK for a Local 3D Simulation Engine

> Open toolchain that lets **AI agents and developers drive PostEngineer (PE)** — an in-house Unity-class 3D simulation engine — via natural language tool calls and scripts. **Outcome (resume / LinkedIn): ~53% reduction in average project development hours** once users and LLMs could operate the engine through MCP.

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python)](#)
[![MCP](https://img.shields.io/badge/MCP-FastMCP%20stdio-~39%20tools-purple)](#)
[![Windows](https://img.shields.io/badge/Platform-Windows%2010%2F11-0078D4?logo=windows)](#)

## Portfolio one-liner

I designed and shipped the full **agent ↔ engine bridge**: MCP server, CLI, Python SDK, native pipe, behavior-graph offline editor, and hot-reload — so scene building, scripting, and graph work no longer require only click-ops inside the PE GUI.

**v0.26** · 42 capabilities tracked · **39 verified** — see [docs/PEagent-开发现状完整报告.md](docs/PEagent-开发现状完整报告.md).

## What you get

| Surface | Entry | Purpose |
|---------|-------|---------|
| **MCP** | `mcpServer.py` | ~39 tools for Claude / Cline / DeepSeek Harness / etc. |
| **CLI** | `pe_cli.py` (+ daemon `:9090`) | Fast local ops without cold-start tax |
| **SDK** | `pe_client/` | Single business-logic layer (14 modules) |
| **Graphs** | `pe_graph_cli.py` | Offline `.rg` CRUD → native hot-reload |
| **Bridge plugin** | `artifacts/PEHelloMCP.plu` | In-process HTTP API inside PE |

**Not included:** PE engine binary, license, official SDK, or customer projects.

## Architecture

```
AI Agent ── MCP stdio / CLI / SDK
              └── pe_client/   ← only business logic layer
                    ├── HTTP      → PEHelloMCP.plu (:8080, ~29 routes)
                    ├── DSL       → ScriptReader (large PE function library)
                    └── Native    → named pipe PE.NativeScript (GBK, VsMVO exports)
```

Capability groups: `engine_*` objects · scene effects · script search/exec · scene-tree fields · snapshot / console / camera · behavior graphs (`pe_graph_*`).

## Quick start

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
# PE running + PEHelloMCP.plu loaded:
curl.exe -s -X POST http://localhost:8080/api/engine/status
python pe_cli.py status
python pe_cli.py scene
```

MCP client config (stdio):

```json
{ "command": "powershell", "args": ["-ExecutionPolicy","Bypass","-File","<path>\\scripts\\run-mcp.ps1"] }
```

## Impact (cited carefully)

- **~53% fewer average project development hours** after MCP/agent-driven PE workflows (LinkedIn / resume outcome for this PE agent work).
- 42-capability matrix with 39 items verified in-engine (v0.26 report).
- Native `.rg` hot-reload without opening the graph editor (v0.25+).

## Requirements

Windows 10/11 · Python 3.11+ · running PostEngineer with matching `PEHelloMCP.plu` · `fastmcp` / `click` / `pywin32` as needed

## Docs

| Doc | Content |
|-----|---------|
| [PEagent-开发现状完整报告.md](docs/PEagent-开发现状完整报告.md) | Architecture, verification matrix, redlines, version history |
| pe-helloworld-mvp.md · peagent-v0.6 / v0.7 · pe-graph-cli.md | Deep dives |
| INTEGRATION_GUIDE.md | Extending PEHelloMCP routes |

## Safety / redlines (runtime)

Charts must not use raw `DeleteObject` · runtime-created animations cannot bind models · native pipe is GBK · no auto-save API (save project in PE) — details in the status report.

## Role

**Author of the PE AI toolchain** — reverse-engineering bridges, MCP productization, and developer experience for industrial 3D simulation.

---

*Employer-facing: MCP/CLI/SDK for a local 3D sim engine (Unity-alternative workflow). 面向本机三维仿真引擎的 AI 操控工具链。*
