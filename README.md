# PEagent — PostEngineer (PE) 三维引擎 AI 开发助手工具链

让 AI Agent（MCP 客户端 / 命令行 / Python 程序）全栈操控本机运行的 **PostEngineer (PE) 三维引擎**：对象查询与增删改、场景效果、脚本执行、场景树字段、截图与控制台、调试启停、行为图（.rg）离线编排与原生热重载。

> 版本 v0.26（2026-09-17）｜ 完整现状与验证矩阵见 [docs/PEagent-开发现状完整报告.md](docs/PEagent-开发现状完整报告.md)（42 项能力 39 项验证通过）

## 包内容

```
PEagentUpload/
├── README.md               ← 本文件
├── requirements.txt        ← Python 依赖（Windows, 3.11+）
├── mcpServer.py            ← MCP 服务器（FastMCP，stdio，约 39 个工具）
├── pe_cli.py               ← CLI（pe 命令，默认走本地 daemon 加速）
├── pe_daemon.py            ← 后台加速服务（HTTP :9090，免每次启动开销）
├── pe_graph_cli.py         ← 行为图（.rg）原子操作 CLI：会话式建图→落盘
├── pe_console.py           ← PE 控制台直读
├── pe_ui_automation.py     ← PE 窗口枚举/命令投递（UI 自动化兜底）
├── pe_client/              ← Python SDK（唯一业务逻辑层，14 个模块）
├── tools/                  ← rg_crud 依赖的 .rg 解析/建图模块
├── artifacts/PEHelloMCP.plu ← PE 侧桥接插件（Release 构建，需放入 PE 插件目录）
├── docs/                   ← 使用说明与设计文档
├── scripts/                ← setup.ps1 / run-mcp.ps1 / run-daemon.ps1
└── tests/                  ← 契约测试示例
```

**不含**：PostEngineer 本体、PE SDK、PE 运行时 DLL（RelaGraph.dll / ProjectMgr.plu 等）、License、用户工程文件。`tools/rg_native_mutate.exe`（离线改节点的原生工具）为可选件，未随包分发。

## 总体架构

```
AI Agent ── MCP stdio(mcpServer.py, ~39 工具) / CLI(pe_cli.py) / SDK(import pe_client)
   └── pe_client/  ← 唯一业务逻辑层
        client.py         HTTP 传输（localhost:8080，PEHelloMCP.plu 29 路由）
        native_pipe.py    原生管道（\\.\pipe\PE.NativeScript，GBK 编码，12 命令）
        script_bridge.py  DSL 脚本桥（program 模式 + 文件回传）
        scene_tools.py    PrintWindow 全窗截图 / 控制台直读 / 相机应用
        registry/models   15 对象 + 17 效果注册表
        rg_crud.py        .rg 行为图离线 CRUD（字段表 v0.8）
   ── 三层引擎通路
        层1 HTTP : PEHelloMCP.plu（CivetWeb 内嵌于 PE 进程）
        层2 DSL : ScriptReader 解释器（1927 函数文档库）
        层3 原生 : PEAgentNative（GetProcAddress 直调 VsMVO 导出）
```

## 环境要求

- Windows 10/11
- Python 3.11+
- 正在运行的 PostEngineer，且已加载 `artifacts/PEHelloMCP.plu`（版本需与 PE 运行时匹配）
- MCP 使用另需 `fastmcp`；CLI 使用另需 `click`；原生管道需 `pywin32`

## 安装

```powershell
# 方式一：一键（建 .venv + 装依赖）
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1

# 方式二：手动
pip install -r requirements.txt
```

## 快速开始

1. **探活引擎**（PE 已启动、插件已加载）：

   ```powershell
   curl.exe -s -X POST http://localhost:8080/api/engine/status
   # accepting_commands=true 即可用
   ```

2. **接入 MCP 客户端**（如 DeepSeek Harness / Claude / Cline 等，stdio 方式）：

   ```json
   { "command": "powershell", "args": ["-ExecutionPolicy","Bypass","-File","<包路径>\\scripts\\run-mcp.ps1"] }
   ```

   工具分组：`engine_*`（对象）、`pe_*effect`（17 种场景效果）、`pe_script_*`（脚本搜索/执行/校验）、`pe_scene_*`/`pe_field_*`（场景树字段）、`pe_snapshot`/`pe_console_read`/`pe_apply_camera`（视图诊断）、`pe_graph_*`（行为图）。

3. **CLI 常用命令**：

   ```powershell
   python pe_cli.py status                # 引擎状态（首次自动拉起 daemon :9090）
   python pe_cli.py scene                 # 列出场景对象
   python pe_cli.py types                 # 列出对象类型
   python pe_cli.py create button -d '{"name":"btn1","text":"点击"}'
   python pe_cli.py effect set ao -d '{"enabled":true}'
   python pe_cli.py debug start           # 启动调试（PEPlayer 运行态）
   python pe_cli.py snapshot              # 全窗截图
   python pe_cli.py obj-delete 按钮_1 --type button    # 稳定删除 UI/MVO 对象
   python pe_cli.py var-delete TEST
   python pe_cli.py graph list|read|add-program|remove-node|reload-native ...
   ```

4. **SDK 调用示例**：

   ```python
   import sys; sys.path.insert(0, r"<包路径>")
   from pe_client import engine_status, obj_query, obj_modify
   from pe_client import native_pipe          # 原生管道（obj_delete / field_* / rg_reload）
   from pe_client import script_bridge        # DSL 脚本桥（相机读取、节点移动）
   from pe_client import scene_tools          # pe_snapshot / pe_console_read

   print(engine_status())
   ```

5. **行为图离线编排**（不进图编辑器）：

   ```powershell
   python pe_graph_cli.py new-session --proj <工程目录>
   python pe_graph_cli.py add-node ...      # 逐节点原子操作
   python pe_graph_cli.py materialize --out xxx.rg
   python pe_cli.py graph reload-native --path xxx.rg   # 引擎内热重载（v0.25）
   ```

## 文档索引（docs/）

| 文档 | 内容 |
|------|------|
| PEagent-开发现状完整报告.md | **主文档**：架构、42 项能力验证矩阵、逆向资产、红线约束、版本史 |
| pe-helloworld-mvp.md | 最小可用闭环（MVP）如何搭起来 |
| peagent-v0.6-script-bridge.md | DSL 脚本桥设计与用法 |
| peagent-v0.7-native-scene.md | 原生管道场景树/字段操作 |
| pe-graph-cli.md | 行为图 CLI 全命令说明 |
| rg-field-table.md | .rg 行为图字段表（v0.8） |
| native-api-index-v0.md | 原生 API 索引 |
| benchmark-vs-tuanjie-cowork.md | 与 Tuanjie Cowork 的对标分析 |
| INTEGRATION_GUIDE.md | PEHelloMCP 新增脚本执行路由的集成指南 |
| pevsbridge-readme.md | VS2017 加密源码读写桥（PEVsBridge VSIX） |

## 使用红线（违反 = 崩溃/挂起，均实测）

- **图表类（curve/chart）禁止 `DeleteObject(ptr)`**——只走 `DeleteUIObject`（CLI/MCP 的 `obj-delete` 已内置处理，直接用即可）。
- **运行时创建动画不可绑定模型**——动画只能用帧动画编辑器预置，再由脚本 `astart()` 触发。
- 原生管道请求为 **GBK 编码**；`scene_children` 禁止嵌套枚举（会挂起引擎）。
- 对象删除/修改后**无自动保存 API**，需在 PE 中手动保存工程，否则重开从 .peo 恢复。
- 删除/重建 PE 侧插件前先结束 PostEngineer（文件锁）。

## 验证

```powershell
.venv\Scripts\python -m pytest tests -q      # 契约测试
python pe_cli.py status                      # 连通性
```
