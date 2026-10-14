# PE 行为图 CLI 说明

本文档说明当前 PE 行为图 CLI 已具备的能力、实现链路、实现原理和使用限制。

## 1. CLI 的定位

当前实现分为两层：

1. `pe_graph_cli.py`：行为图原子操作 CLI。
2. `pe_cli.py`：面向 PE 引擎、项目、脚本、调试和行为图的综合 CLI。

行为图原子 CLI 的目标是把人工拖拽操作拆成可组合步骤：

```text
创建会话
  -> 创建节点
  -> 修改节点
  -> 创建连线
  -> 原生物化 .rg
  -> 注册到 PE 项目
  -> 启动调试
  -> 查询输出
```

## 2. 已具备的行为图功能

入口文件：

```text
E:\PEagent\pe_graph_cli.py
```

### 2.1 创建会话

```powershell
python E:\PEagent\pe_graph_cli.py session-new `
  --output E:\PEagent\PeProject\MVP\main\demo.rg
```

该命令创建：

- `demo.rg`：PE 原生 RelaGraph 文件；
- `demo.rg.session.json`：可编辑的组合会话；
- `demo.rg.session.plan`：供原生构造器读取的操作计划。

会话初始化时自动包含一个 root 节点。

### 2.2 创建节点

```powershell
python E:\PEagent\pe_graph_cli.py node-create `
  --session E:\PEagent\PeProject\MVP\main\demo.rg `
  --type boot
```

支持的节点类型：

```text
root       根节点
boot       启动节点
hub        带叉圆点的 Hub 节点
script     脚本引用节点
program    程序/脚本执行节点
curve      连线对象
button     按钮对象
```

可通过 `--id`、`--x`、`--y` 和 `--text` 指定节点信息。

### 2.3 移动节点

```powershell
python E:\PEagent\pe_graph_cli.py node-move `
  --session E:\PEagent\PeProject\MVP\main\demo.rg `
  --id 3 --x 300 --y 120
```

### 2.4 修改节点文本

```powershell
python E:\PEagent\pe_graph_cli.py node-set-text `
  --session E:\PEagent\PeProject\MVP\main\demo.rg `
  --id 6 `
  --text "main\\Script\\include.script"
```

脚本节点默认文本为：

```text
main\Script\include.script
```

程序节点默认文本为：

```text
helloworld();
```

### 2.5 创建连线

```powershell
python E:\PEagent\pe_graph_cli.py link `
  --session E:\PEagent\PeProject\MVP\main\demo.rg `
  --from 2 --to 3
```

CLI 会检查两个端点是否存在，并拒绝重复连线。

### 2.6 查看会话

```powershell
python E:\PEagent\pe_graph_cli.py show `
  --session E:\PEagent\PeProject\MVP\main\demo.rg
```

### 2.7 注册已有 `.rg`

```powershell
python E:\PEagent\pe_graph_cli.py register `
  --name demo.rg `
  E:\PEagent\PeProject\MVP\main\demo.rg
```

注册操作的含义是：

- 校验 `.rg` 文件存在；
- 使用 Release RelaGraph 原生解析器读取文件；
- 调用 PE Release ProjectMgr 的行为图注册链；
- 将图元登记到当前项目树；
- 保存项目文件；
- 不改写、不替换已有 `.rg` 文件。

注册是幂等的。同一名称和同一路径重复注册时，返回
`already_registered=true`，不会重复创建注册项。

## 3. 综合 PE CLI

入口文件：

```text
E:\PEagent\pe_cli.py
```

### 3.1 行为图命令

```powershell
pe graph create <name> --filename <file.rg>
pe graph read <file.rg>
pe graph register <file.rg> --name <name>
pe graph create-boot <project> <script> --name <name>
pe graph node-create <file.rg> --type <type> --name <name>
```

### 3.2 脚本命令

```powershell
pe script load-file ...
pe script deploy-and-run ...
pe script native-flow ...
```

### 3.3 调试和输出命令

```powershell
pe debug start
pe debug stop
pe output
pe console
```

### 3.4 引擎和 UI 诊断

```powershell
pe daemon status
pe daemon start
pe daemon stop
pe connect
pe status
pe health
pe ui inspect
```

### 3.5 对象、场景和效果

```powershell
pe types
pe template <type>
pe create <type>
pe list <type>
pe modify <type> <name>
pe scene
pe screenshot
pe effect list
pe effect get <name>
pe effect set <name>
pe effect batch
pe toggle <effect> on|off
```

## 4. 实现链路

### 4.1 原子构造链路

```text
pe_graph_cli.py
  -> 修改 session.json
  -> 生成 session.plan
  -> build_graph_from_plan.exe
  -> RelaGraph.dll
  -> CRelationGraph 原生对象
  -> WriteToBuffer
  -> .rg
```

每次修改都会重新从 session 状态生成计划，并通过原生 RelaGraph 序列化生成 `.rg`。CLI 不直接拼接或修改 RelaGraph 二进制结构。

### 4.2 `.rg` 解析和验证链路

```text
.rg
  -> RelaGraph.dll
  -> CRelationGraph::ReadFromBuffer
  -> Session::Open
  -> 原生节点/连线描述
```

读取成功说明文件可以被当前 Release RelaGraph 解析。对于原子构造流程，保存后还会再次打开文件进行原生回读验证。

### 4.3 已有图注册链路

```text
graph_register
  -> 检查文件存在
  -> Release RelaGraph 原生解析
  -> 读取原文件字节快照
  -> ProjectMgr Release 注册辅助函数
  -> CVsModule::AddGraphInfo
  -> ProjectMgr 保存项目
  -> 对比注册前后 .rg 字节
  -> 返回注册结果
```

注册过程中会记录文件字节快照。若 ProjectMgr 注册辅助函数意外修改文件，CLI 会恢复原始字节并返回失败，避免已有图被覆盖。

### 4.4 PE 项目树持久化链路

```text
CVsModule::AddGraphInfo
  -> ProjectMgr 图元注册
  -> PEM_MAIN_SET_MODIFY
  -> ProjectMgr 保存
  -> <Project>.peproj 的 UIObject
  -> PE 项目树显示 .rg
```

因此，注册已有图不是复制文件，也不是替换文件，而是为现有文件增加项目级注册信息。

## 5. 关键实现原理

### 5.1 session 与 `.rg` 分层

CLI 不把 `.rg` 当作高层编辑模型，而是采用两层结构：

```text
session.json  = 可组合、可修改的逻辑模型
session.plan  = 一次物化操作的中间计划
.rg           = PE RelaGraph 原生序列化结果
```

这样可以把创建 root、创建 Hub、创建脚本节点和连线分别暴露为独立命令，同时仍然使用 PE 自己的二进制格式。

### 5.2 原生 DLL 调用

`build_graph_from_plan.exe` 通过 RelaGraph 的原生导出符号和已验证的 ABI 调用：

- `CRelationGraph` 构造/析构；
- `ReadFromBuffer`；
- `WriteToBuffer`；
- `Initialize`；
- `Graph`；
- `Operator`；
- `CreateObject`；
- `FindByID`；
- `RemoveObject`。

因此，生成的 `.rg` 由 RelaGraph 原生对象序列化，而不是由 CLI 自定义格式模拟。

### 5.3 Release ProjectMgr 注册

Release 版没有可直接使用的 PDB，因此 ProjectMgr 内部调用通过当前 Release 版本已验证的 RVA 和调用约定访问。注册路径使用 PE 自己的图创建/注册辅助函数，再通过 `CVsModule::FindGraphInfo` 验证注册结果。

这些 RVA 与 Release 二进制版本绑定。PostEngineer 或 ProjectMgr 升级后需要重新验证。

## 6. 当前验证结果

MVP 项目：

```text
E:\PEagent\PeProject\MVP
```

已验证：

- `atomized.rg` 可以被 Release RelaGraph 解析；
- root、boot、Hub、脚本、程序节点和连线存在；
- `atomized.rg` 已加入 MVP 项目树；
- `MVP.peproj` 已保存 `atomized.rg` 注册项；
- 注册前后 `.rg` SHA-256 保持不变；
- 重复注册返回幂等成功；
- 图中脚本节点可以引用 `main\Script\include.script`。

## 7. 重复脚本包含说明

如果项目同时注册两个都引用同一个 `include.script` 的启动图，PE 可能报告：

```text
文件 main\Script\include.script 在同一个模块中被重复包含
```

这表示脚本被两个行为图重复加载，不表示 `.rg` 注册失败。测试启动执行时，应只保留一个引用该脚本的启动图，或让不同图引用不同的脚本入口。

## 8. 当前限制

1. 原子 CLI 已支持节点和连线的组合构造，但 `pe_cli graph node-create` 仍依赖 PE 原生编辑器会话。
2. Release 版 ProjectMgr 编辑器会话尚未完全绑定，因此 CLI 的稳定构造路径是 session + 原生 RelaGraph 物化。
3. 当前 RVA 只适用于已验证的 Release 版本。
4. CLI 当前没有提供完整的行为图删除、分支批量编辑和复杂连线属性编辑命令。
5. 多个启动图同时引用同一个脚本时，需要由项目配置避免重复包含。

## 9. 后续扩展方向

```text
graph session-new
graph node-create
graph link
graph node-set-text
graph register
```

后续可以继续抽象为：

- `graph root create`；
- `graph boot create`；
- `graph hub create`；
- `graph script create`；
- `graph program create`；
- `graph link create`；
- 分支节点和条件连线；
- 节点属性修改；
- 图的复制、导入和删除；
- 版本化 RVA 适配器；
- MCP action 与 CLI 参数的统一 schema。

## P0 commands (v0.21)

```bash
# Change PROGRAM text by node id (duplicate-safe)
python pe_cli.py graph update-text-id path\to\file.rg 11 "agent_ok();主页面初始状态();"

# Discover BOOT→… startup chain (read-only)
python pe_cli.py graph boot-chain path\to\行为图_main.rg

# e2e recipe (PE open, MCP on 8080; does NOT call /api/graph/*)
$env:PE_MCP_PORT="8080"
python tools/rg_e2e_recipe.py --marker agent_e2e_ok --wait 25
```

Redline unchanged: never call live HTTP `/api/graph/read|node/create` on a 3D session.

## P2 commands (v0.23) — project .rg Insight index

Offline only. Discovers `main/**/*.rg` + peproj registrations; never mutates `.rg`.

```bash
# Build Insight-style JSON index for a PE project
python pe_cli.py graph index path\to\project --out data\exports\rg_index\proj.json

# Substring search (Unicode / Chinese safe); reuse index with --index
python pe_cli.py graph grep path\to\project "主页面初始状态"
python pe_cli.py graph grep path\to\project helloworld --index data\exports\rg_index\mvp_rg_index.json

# One-shot index + grep
python pe_cli.py graph index path\to\project --grep agent_gdz23_e2e --out data\exports\rg_index\proj.json
```

MCP: `pe_graph_index` / `pe_graph_grep`.

Index fields per graph: path, size, node_count, link_count, type_histogram, programs/includes, boot_chain summary, node id→type/text stubs.


## P1 commands (v0.22) — proprietary field writes

```bash
# VARIABLE InitialValue (32B blob at prop +20..+51)
python pe_cli.py graph set-var path\to\file.rg <id> 0x12345678 --encoding int
python pe_cli.py graph inspect-prop path\to\file.rg <id>
# TIMER condition = common text
python pe_cli.py graph set-timer path\to\file.rg <id> "delay(2.5)"
```

## P3 commands (v0.25) — native hot reload (no graph editor)

```bash
# After offline edits, reload .rg into the running editor without opening the graph UI
python pe_cli.py graph reload-native --path E:\PEagent\PeProject\MVP\main\helloworld.rg
# or by registered name/filename
python pe_cli.py graph reload-native --name helloworld.rg
python pe_cli.py graph reload-native --filename helloworld.rg
```

Native pipe protocol:

```text
cmd=rg_reload|path=<abs.rg>|name=helloworld.rg
# aliases: graph_reload; also filename=
```

Implementation: `PEAgentNative` → `CRelationGraph::BuildGraph` (RVA `0xB1C0`).  
**Do not** use live HTTP `/api/graph/read|node/create` (opens editor, stalls tick).  
See `docs/rg-p3-blocker.md` (UNBLOCKED) and `data/exports/rg_native_reload/`.
