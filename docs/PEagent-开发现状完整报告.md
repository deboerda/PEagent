# PEagent 开发现状完整报告（AI 交接版）

## v0.25 — Native RelaGraph hot-reload (2026-09-14)

### 中文摘要
- **P3 已解锁**：原生管道 `cmd=rg_reload` / `graph_reload`，走 `CRelationGraph::BuildGraph`（Release RVA `0xB1C0`），**不开**图编辑器 UI，**不**走 live `/api/graph/read|node/create`。
- CLI：`python pe_cli.py graph reload-native --path|--filename|--name`
- 推荐工作流：离线 `update-text-id` / `set-var` → `reload-native` →（需要时）`debug_start` → 控制台验收。
- MVP e2e：marker `RG_NATIVE_RELOAD_222036` 命中；重载前后 `tick_alive=True`。
- 产物：`data/exports/rg_native_reload/re_notes.json`、`e2e_log.json`；原 blocker 文档已翻转为 UNBLOCKED：`docs/rg-p3-blocker.md`。
- 残留风险：每次 BuildGraph 可能有 CRg* 列表小泄漏；debug 进行中不重新 debug_start 的热替换未单独证明。
- **仍禁止**：`GlobalUtils::LoadGraph`、OpenEditDialog、live HTTP 图 API。

### English
- **UNBLOCKED P3**: PEAgentNative `rg_reload` / `graph_reload` via `CRelationGraph::BuildGraph` (Release RVA `0xB1C0`), no graph-editor UI / no live `/api/graph/read|node/create`.
- CLI: `pe graph reload-native --path|--filename|--name`
- MVP E2E: offline PROGRAM text mutate → native reload → `debug_start` → console marker hit; `tick_alive` stayed true around reload.
- Notes: `data/exports/rg_native_reload/re_notes.json`, `e2e_log.json`; blocker flipped in `docs/rg-p3-blocker.md`.
- Residual: CRg* list leak per call; mid-debug swap without debug_start not separately proven.



## v0.26 — UI 对象通用删除 obj_delete（2026-09-17）

### 中文摘要
- **通用删除命令**：`cmd=obj_delete` / `pe_client.native_pipe.obj_delete(name, obj_type, field_path)`，与 `CreateUIObject` **对称**——优先 `FxPluginMgr_RunNameCmd("ProjectMgr","DeleteUIObject", …)`，必要时再补 VsMVO `DeleteObject(ptr)`。
- **已验收**：`按钮_1`（button/4→UI11）、`图片_1`（image/9→UI21）、`图表_1`（curve/69→UI53）。query 空、field_key=-1、引擎存活。
- **图表特例（内部）**：curve/chart 等禁止 `DeleteObject(ptr)`（必崩）；客户端先单独 `field_delete`（SEH 吞 AV），再 `tree=2` 只走 DeleteUIObject。调用方仍只调一条 `obj_delete`。
- **通道**：删除走 **Native pipe**（非 HTTP `/api/obj/delete`，PEHelloMCP 源码加密未实现）。创建/列表仍可用 HTTP MCP :8080。
- **持久化**：无自动保存 API——用户必须在 PE 里 **保存工程**，否则重开从 `.peo` 恢复。
- **详档**：`docs/codex-handoffs/2026-09-17-obj-delete-v1.md`；产物 `data/exports/obj_delete/`。

### English
- Generic UI delete: ProjectMgr `DeleteUIObject` first (CreateUIObject-symmetric), optional VsMVO `DeleteObject(ptr)` for safe types.
- E2E OK: button_1 / image_1 / chart curve_1; charts must not call `DeleteObject(ptr)` (crash); use tree=2 only.
- Persistence: manual Save Project still required.

### 关键 RVA（Release x64）
| 符号 | 模块 | RVA |
|------|------|-----|
| `CVsModule::FindObject` | VsMVO | `0x2D1950` |
| `CVsModule::DeleteObject(ptr)` | VsMVO | `0x2D3DB0` |
| `funcDeleteUIObject` | ProjectMgr.plu | `0xC1810` |

### 类型映射（摘录）
| alias | MVO | UI | 策略 |
|-------|-----|-----|------|
| button | 4 | 11 | DeleteUIObject → DeleteObject |
| image | 9 | 21 | 同按钮 |
| curve / chart / … | 69/70/… | 53 | **仅** DeleteUIObject（tree=2） |

### 红线补充
- 图表类：**禁止** `DeleteObject(ptr)`；field_delete 与 DeleteUIObject **分两次**管道往返。
- 重建 `PEAgentNative.plu` 前结束 PostEngineer（文件锁）。
- 管道占满时结束卡住的 Python；必要时再重启 PE（运维重启 ≠ API 必然闪退）。

---
> 版本: v0.26 ｜ 更新: 2026-09-17（UI obj_delete 通用删除：按钮/图片/曲线已验收；CreateUIObject 对称 DeleteUIObject）｜ 前版 v0.25：2026-09-14 rg_reload UNBLOCKED ｜ 文档性质: **自包含交接文档**——新 AI 会话读完本文件即可继续开发，无需历史对话
> 目标: 为 PostEngineer (PE) 三维引擎（武汉创景）构建对标 Tuanjie Cowork 的全功能 AI 开发助手
> 对标分析: `docs/benchmark-vs-tuanjie-cowork.md`（Tuanjie = Insight 离线索引 + Codely Live 控制 + C# 执行）
> 验证基线: 真实生产工程 GDZ23 卷绕式真空蒸镀设备可视化系统（印钞机 9.10.vis；117 文字标签/21 变量/14 按钮/10 图片/8 曲线）

---

## 〇、给下一个 AI 的快速上手（先读这里）

1. **当前环境**：PostEngineer.exe 编辑模式运行中，已加载 工程（）。HTTP 控制通道 `localhost:8080`；原生管道 `\\.\pipe\PE.NativeScript`。
2. **探活**：`curl -s -X POST http://localhost:8080/api/engine/status`（accepting\_commands=true 即可用）。
3. **必读红线**：第六章（违反 = 崩溃引擎/挂起/乱码，全部实测实锤）。
4. **改 C++ 插件**：改 `PEAgentNative/PEAgentNative.cpp`（明文，MSBuild 直编）→ 杀 PE → 等 5s → MSBuild → 启动 PE。**PEHelloMCP 源码被同元加密**，只能经 VS DTE COM 读写（VS2017 在加密白名单），编译用 devenv.com。
5. **验证纪律**：动画/渲染类功能必须以 PEPlayer 运行态 + PrintWindow 截图或肉眼确认为准；脚本"解析成功/加载成功" ≠ 运行有效。
6. **工作目录**：`E:\PEagent`（Python 环境直接 `import pe_client`，需 `sys.path.insert(0, r'E:\PEagent')`）。
7. **UI 对象删除**：`from pe_client import native_pipe; native_pipe.obj_delete('图片_1','image','/scene/modules/main/images/图片_1')`（GBK 管道；图表用 obj\_type=`curve`）。详档 `docs/codex-handoffs/2026-09-17-obj-delete-v1.md`。须手动保存工程。
8. **行为图离线改节点**：`python pe_cli.py graph add-program <file.rg> "foo();" --link-from <id>`；删：`graph remove-node <file.rg> <id>`。底层 `tools/rg_native_mutate.exe`，cwd 需能加载 `bin/Release-x64/RelaGraph.dll`。

---

## 一、里程碑与项目概述

**已交付验收的功能里程碑**：「运行项目时，自动旋转模型 360° 持续 5s」（2026-09-14）。
最终方案：帧动画编辑器预置 `Ani_整机旋转`（挂 印钞机9.10.vis，0s→5s 竖直轴 360°）+ 启动钩子（Animation.script 的 `主页面初始状态()` 末尾 `astart("Ani_整机旋转")`）。运行链：启动调试 → 行为图_main.rg → include.script → 主页面初始状态() → astart → 引擎播放。

PEagent = 让 AI Agent 全栈操控 PE 的工具链：MCP（37 工具）+ CLI + 三层引擎通路（HTTP / DSL 脚本桥 / 原生管道），已在对标分析中定位与 Tuanjie Cowork 的差距并完成部分深度解包（第五章）。

---

## 二、总体架构

```
AI Agent ── MCP stdio(~39工具) / CLI(pe 命令)
   └── pe_client/（唯一业务逻辑层）
        client.py          HTTP 传输（localhost:8080, PEHelloMCP.plu 29 路由）
        script_bridge.py   DSL program 模式执行器 + 文件回传（camera_get/scene_children_dsl/节点操作）
        native_pipe.py     原生管道客户端（\\.\pipe\PE.NativeScript，12 命令）
        scene_tools.py     PrintWindow 全窗截图 / 控制台直读 / apply_camera(GBK通道)
        registry/models/resolver/script_search  15对象+17效果注册表/1927函数搜索
        native_flow/script_project               启动图编排/工程脚本管理
   ── 三层通路
        层1 HTTP: PEHelloMCP.plu（CivetWeb；源码同元加密，改它需 VS DTE）
        层2 DSL:  ScriptReader 解释器（语法词汇表已破解；1927 函数文档库）
        层3 原生: PEAgentNative.plu（明文 C++；GetProcAddress 按修饰名直调 3dgs/VsMVO 导出）
```

---

## 三、能力全景与验证状态（42 项矩阵：39 通过）

| 层 | 能力 | 状态 |
|----|------|------|
| HTTP | 引擎状态机/健康 | ✅ |
| HTTP | 对象查询（15 类型） | ✅（remark 117/变量 21/按钮 14/图片 10/曲线 8；vis 为场景资源按设计拒绝枚举） |
| HTTP | 对象创建/修改/回读 | ✅ |
| HTTP | 效果查询/设置（fog/sun/ao/bloom/postprocess/ssr 等 17 种 × 4 域） | ✅ 含往返恢复 |
| HTTP | 光照探针 | ❌ 路由存在、后端 not implemented |
| HTTP | 脚本 execute/execute_file/validate | ✅ |
| HTTP | 行为图 build_boot/register（MVP 验证）；read 在图编辑模式会停 Tick | ⚠️ |
| 离线 | .rg CRUD（list/read/create_boot/update_text/delete + 字段表 inspect） | ✅ |
| 离线 | .rg 原生节点 add_program / remove_node（可选 link_from） | ✅ |
| 离线 | .rg CreateByType 全类型打样（16/19 可建） | ✅ |
| 离线 | .rg 多类型增删 + link/unlink | ✅ |
| 离线 | 类型专有字段 / TIP / 原生热重载 | ⚠️字段 / ❌TIP / ✅rg_reload |
| HTTP | 调试启停（运行项目 = PEPlayer 进程内窗口） | ✅（启动 ~30s；运行态编辑命令队列冻结） |
| HTTP | 帧截图（253 裁剪）/输出读取（失效） | ⚠️ 已被 scene_tools 替代 |
| DSL | program 模式执行 + 文件回传 | ✅ |
| DSL | 相机读取 camGetCamera | ✅ |
| DSL | 运行时创建动画（move/rotate 全变体） | ❌ 不绑定模型——预置动画是唯一机制（见 5.3/第六章） |
| DSL | 单层子节点枚举 | ✅（count 不可测，尾部垃圾占位；禁嵌套——挂起引擎 30s+） |
| 原生 | scene_key/field_info/field_key/field_create/field_rename/field_flush | ✅（中文 GBK 全通；create→DSL 枚举同树交叉验证） |
| 原生 | field_delete | ⚠️ 实验性（命令成功但可能延迟到重载生效） |
| 原生 | scene_children（Contents 语义） | ⚠️ 本工程返回 0（≠子节点枚举，保留观察） |
| 视图 | pe_snapshot(1721×1051)/pe_console_read/pe_apply_camera | ✅ |
| 原生 | obj_delete（ProjectMgr DeleteUIObject ± VsMVO DeleteObject） | ✅ 按钮/图片；曲线 tree=2 |
| 原生 | obj_probe / field_delete（图表 SEH） | ✅ |

---

## 四、工具链清单

### MCP（mcpServer.py，FastMCP，约 39 工具，stdio；含 pe_graph_*）
- 引擎: engine_get_status / engine_get_output（失效，留兼容）
- 对象: engine_list_types / engine_get_template / engine_create_object / engine_list_objects / engine_modify_object
- 效果: pe_list_capabilities / pe_get_template / pe_get_scene_effect / pe_set_scene_effect / pe_set_scene_effects / pe_get_effect / pe_set_effect（域通用：scene/node/appearance）
- 探针: pe_light_probe（后端未实现）
- 脚本: pe_script_search_functions / pe_script_get_function / pe_script_module_index / pe_script_module_functions / pe_script_prepare / pe_script_execute / pe_script_validate
- 脚本桥: pe_bridge_run_script / pe_camera_get / pe_node_set_position / pe_node_move
- 场景树: pe_scene_children / pe_scene_key / pe_field_info / pe_field_key / pe_field_create / pe_field_rename / pe_field_delete
- 视图诊断: pe_snapshot / pe_console_read / pe_apply_camera
- 截图: pe_capture_current_frame

### CLI（pe_cli.py；dist/PeCli.exe 可 PyInstaller 重打包）
`pe status/health/connect/daemon` ｜ `pe types/template/create/list/modify/scene` ｜ `pe effect…/toggle` ｜ `pe run <file>` ｜ `pe console` ｜ `pe script native-flow` ｜ `pe scene-children` ｜ `pe field <info|key|create|rename|flush|delete|scene-key>` ｜ `pe snapshot` ｜ `pe camera-apply` ｜ `pe camera`（读）｜ `pe_daemon.py`（:9090 自动加速）

### PEAgentNative 管道协议（\\.\pipe\PE.NativeScript）
- 请求 `cmd=<命令>|<参数>=<值>...`（**GBK 编码**）；回包首行 `key=value|...`，scene_children 子节点按行 `序号:key:名称:路径`
- 命令（12）: status / scene_key / scene_children(key,filter,max) / field_info(key) / field_key(path) / field_create(father,name) / field_rename(key,name) / field_flush(key) / field_delete(path) / load_function(file,name) / execute_function(name)
- 原理: MSVC 修饰名 GetProcAddress 直调 3dgs/VsMVO 导出（签名自导出表恢复）；x64 thiscall = cdecl+this（CVsModule 方法传 FxGetMainVsModule() 作 self）
- 源码: `PEAgentNative/PEAgentNative.cpp`（明文；**新增注释一律英文**——UTF-8 无 BOM 中文注释会吞下一行代码）

### PEHelloMCP.plu（29 路由）
帧截图(253裁剪)/输出读取(失效)/light_probe(后端未实现)/graph 9 路由/debug 启停/obj CRUD/effect/script/graph——修改需 VS DTE + devenv.com 链路。

---

## 五、逆向工程成果与资源索引 ★核心资产★

### 5.0 资源索引总表

| 资源 | 位置 | 内容 |
|------|------|------|
| 语法词汇表全量 | 本章 5.1 + `docs/re-notes-vsMVO-scriptreader.md` | Act 类型全集/事件约定/参数簇/错误格式 |
| RE 方法论 | `docs/re-notes-vsMVO-scriptreader.md` 第四章 | LEA 字节模式扫描/关键字簇/EventLog 定位法/差分破解 |
| 函数实现映射 | `data/exports/function_impl_map.json` | VsMVO+3dgs 双 DLL 名字定位与代码引用（97/1716 真相） |
| 分发块坐标 | `data/exports/dispatcher_blocks.json` | 55 函数的代码块 VA |
| 原生导出索引 | `data/exports/native_index.json` + `docs/native-api-index-v0.md` | 5 DLL 全量导出、322 类反修饰、四大缺口域解法清单 |
| 导出转储 | `data/exports/{VsMVO,3dgs,ScriptReader,RelaGraph,PluginManager}.exports.txt` | dumpbin 原始输出 |
| PE-Insight v0 | `data/peo_index_gdz23.json` | 44.9MB .peo 7 秒离线索引（11146 串，分类计数） |
| .rg CRUD | `pe_client/rg_crud.py` + `pe graph …` / MCP `pe_graph_*`；字段表见 `docs/rg-field-table.md` | 离线 list/read/create/update/delete 已通；任意节点 CRUD 未通 |
| 管道命令源码 | `PEAgentNative/PEAgentNative.cpp` | 12 命令实现（明文可扩展） |
| 语法索引工具 | `tools/build_native_index.py` | 导出表→undname→差分（可复用模式） |

### 5.1 ScriptReader.dll 语法词汇表（完整提取；位置 .rdata 0x415000-0x465000 簇）

**动画 Action 的 Act Type 全集**（`controller{Action{Act{Type{...}}}}`）：
`rotatefieldworld / rotatefieldlocal / movefieldworld / movefieldlocal / setfieldmatrix / setfieldposition / setfieldworldposition / scalefield / settransparency / setcamera / cameraaround(相机环绕) / moveforward / turnaround / orbit / pan / pick / grasp / walk / setfog / enablefog / setbackground / startanimation / stopanimation / resetanimation / reverseanimation / continuousplayanimation / pauseanimation / continueanimation / setanimationspeed / callfunction / plugincall / command / message / createfield / createpipe / createrope / drawline2d / drawpolyline2d / drawrect2d / setdiffuse / setemission / setambient / setspecular / setcolor / light系列 / pointlight / setbox / rebuildbox / recordcamera / replayscene / recordscene / page / fadeinpage / fadeoutpage / switchtopage / enable|disablecut_plane / enable|disableshadow / loadfile / openfile / unloadfield / loadfield / show|hidefield(local) / hilightfield / unhilightfield / flushfield / graspfield / zoomfield / settexturename / settextureparam / loadavi / openmovie / playmovie / updatewindow / showwindow / setvariable / addvariable / setstring / settextcontent / opendatabase`

**事件脚本命名约定**（行为触发）: `On + {mousemovein/out, lbuttondown/up, lbuttondblclk, rbuttondown/up, keydown, keyup, char, global}` + `anim_trigger / check_trigger / timer / window`（OnUdpReceived 同理已实证存在于工程对象）

**动画事件参数簇**: Rotate 事件 = `field, values, axis`（DLL 邻接串）；`group/id/from/to/speedup/reverse/continuous`、`serial/parallel`、`life`、`interpolation: squad/sline`、相机轨迹 `around/rotation/advance/fov`、`nocycle/loop/dial/cycle`

**错误格式**: `%s: invalid keyword %s, ignored`（文件+行号+关键字——`pe console` 可读，语法迭代靠它）

**类型系统**: int/long/float/double/bool/string/string2/string3/byte/dword/handle/intblock/floatblock/doubleblock/longarray/floatarray/doublearray/stringarray

### 5.2 动画 DSL 语法（破解完成；解析通过但视觉无效，见 5.3）

```cpp
Script{
Animation{'''Ani_AgentSpin            // ''' 前缀照抄
	name{Ani_AgentSpin}
	controller{
		Rotate{                        // Rotate 事件子键: field, values, axis（无 center，绕字段自身原点）
			field{/scene/modules/main/model/印钞机9.10.vis}
			values{360.000000 5.000000}   // 空格分隔（逗号报"'1.488000' 不是关键字"）
			axis{0.000000 1.000000 0.000000}
		}
		// Act 形式（同样解析通过）:
		// Action{ Act{ Type{rotatefieldworld} field{...} values{360.000000 5.000000} } }
		// 注意: axis/time/angle 都不是 Act 子键，values 是
	}
}
}
```

### 5.3 .peo 动画二进制结构（已解码，生产样本：动画_主鼓旋转）

```
[对象id int32][名称长度][名称 GBK\0]
[float 时长 1004.0][float 速度 1.0][int 事件数 2]
per event:
  [id长度]"event220\0" [04][上下文长度]"main:模块_蒸镀系统\0" [路径长度]"/scene/.../第二部分06\0"
  [float 块: 1.0/0.5 + 大量 0 + 1.0（细节待 v1）]
  [四元数关键帧]: (0.0491,1.7066,1.1362,-0.7078)… 与 (0, 0.7078, 0, 0.7078)=绕Y 90°
  [float 时长 1004.0]
```
**结论**: 引擎旋转运行时表示 = 四元数关键帧；预置动画存于 .peo，可解码可对照。

### 5.4 VsMVO 分发区（按名分发的解释器主循环）

- 位置: VA `0x1800d7300` 起的长函数群；343KB 栈帧（[rsp+0x53c38]）= 一切内联的解释器主循环
- 每个引擎函数一个查找块: `mov rax,[ctx+0x20]; mov rcx,[rax]; lea rdx,"函数名"; call 0x180001a90(按名查找); test rax; je 失败`
- **函数面真相**: 1927 文档函数仅 **97 个**以字符串存在于二进制（VsMVO 95 + 3dgs 24，去重 97）→ 文档库源自手册而非引擎；实现内联于解释器，无干净 name→impl 表；权威清单须运行时 dump 注册表（线索: ctx+0x90 处 8 字节步长条目表）
- 分发块样本: getBoxByKey@0x1800a081d、pick2DObject@0x1800a51a0、getObjectName@0x1800a530a、modifyFieldPath@0x1800a627a、getChildrenKeys@0x1800d7b62

### 5.5 .rg 行为图格式（字段表 v0.8 + 离线 CRUD v0.21 + 工程索引 v0.23）

- 权威字段表: `docs/rg-field-table.md`
- **CRUD 层**: `pe_client/rg_crud.py`（离线优先，不打开图编辑器）
  - list / read / query / create_boot / update_text / **update_text_by_id** / **boot_chain** / delete / add_program / add_node / link / unlink
  - CLI: `pe graph caps|list|read|query|create|update-text|update-text-id|boot-chain|delete|add-program|...`
  - MCP: `pe_graph_*` 同步（含 `update_text_by_id` / `boot_chain`）
- 验收: cleantest 上 create→update→delete 全通过；GDZ23 `行为图_main.rg` 可 read（RelaGraph inspect）
- 红线: **禁止**在活的 3D 会话上调 `/api/graph/read|node/create`（会开图编辑器并停 Tick）
- 仍缺: 任意节点增删改连线（需 WriteToBuffer / 原生管道）；HTTP live edit；TYPE_19


### 5.6 .peo 场景数据库与 PE-Insight（对标 Tuanjie Insight 的自建物）

- .peo = 序列化场景数据库（44.9MB/GDZ23）：MVOOBJ 记录、函数定义（`名@id`+参数签名串）、动画、UI 对象、场路径
- **PE-Insight v0 已交付**: `data/peo_index_gdz23.json`（11146 串：440 场景全路径 / 1805 MVOOBJ / 520 函数绑定 / 47 动画 / 352 UI 对象 / 359 模块引用；7 秒索引）
- 已即刻解锁: **离线深层场景树**（印钞机内部 23 条路径：主鼓组件/张力辊/扩散泵组/收卷机构…与工程动画绑定节点吻合——引擎侧深层枚举被卡的问题离线绕过）+ 离线 grep
- v1 方向: .peo 记录结构解析（父子关系/属性块）→ 完整层级 + 对象属性；v0.25 已用 pe_client/peo_index.py + tools/build_peo_index.py 固化（长度前缀 GBK；v1 仍待记录结构）

- **v0.25 首切片已固化代码**：`pe_client/peo_index.py`、`tools/build_peo_index.py`、`pe peo info|grep|index`；导出 `data/exports/peo_index/`（长度前缀 GBK + 前缀分类；不完整解码 MVOOBJ）。

### 5.7 逆向方法论（可复用）

1. **LEA 字节模式扫描**: `(48|4C) 8D {05,0D,…,3D} disp32` → 目标=VA+7+disp32；0.2s/4MB
2. **关键字簇挖掘**: 定位已知关键字 → ±150B 邻接字符串簇（同函数字面量相邻）→ 完整参数表
3. **EventLog 定位**: 崩溃 faulting offset 对回导出函数 RVA（VsSearchFieldByKey 实锤: offset 0x1d51fa - RVA 0x1d51b0）
4. **差分破解**: 已知语义差异的成对二进制样本（.rg 变体/.peo 动画）
5. **运行时符号**: 修饰名 GetProcAddress；x64 thiscall = cdecl+this

---

## 六、红线约束（违反 = 崩溃/挂起/乱码，全部实测实锤）

**崩溃类**
1. DSL 调 char\* 出参的 Vs\* 函数（VsShowFieldPathName 等）→ 引擎崩溃退出
2. 原生调 VsSearchFieldByKey → 崩溃进程（EventLog offset 0x1d51fa）
3. 原生 VsShowFieldContentsByKey 传 NULL filter → 终止调用线程（管道消失、引擎存活）
4. DSL camSetCamera 全参写相机 → 相机状态永久置零（重启恢复）；切换相机用 applyCamera
5. DSL 嵌套 getChildrenKeys → 挂起引擎 30s+

**编码类**
6. 管道/脚本文件 = GBK 边界：中文必须 GBK 编解码（UTF-8 → 乱码，引擎弹"找不到动画'鍔一散…'"）
7. 含中文的 DSL → 写 GBK 临时文件走 execute_file（`scene_tools._run_via_gbk_file` 已封装）；execute_file 要求 ASCII 路径（中文+空格路径失败）
8. C++ 源码（UTF-8 无 BOM）中文注释吞下一行代码（MSVC 报诡异 C2065）→ 注释一律英文

**语义类**
9. DSL 数值输出必须 `valuesToString(float[], n, string&)`；`fileWrite(fp, int/float)` 是二进制写入
10. DSL 数组越界读返回垃圾不报错；`getArraySize` 恒 0；标量引用出参不回传（getBoxByKey/splitDword 实测）
11. **运行时创建的动画不绑定模型**（moveFieldAnim/rotateFieldAnim/Rotate{}声明/rotatefieldworld Act，全变体实测；含 359° 规避测试）——预置动画（帧动画编辑器 + .peo 四元数关键帧）+ astart 是唯一生效机制
12. 运行时创建动画的启动必须 `playAnimation(name, time)`（astart 无效）；工程预置动画用 astart（子模块动画需 `main:模块名:动画名` 限定名，且中文限定名经内联脚本会乱码——走 GBK 文件）
13. 脚本中断泄漏回传文件句柄（锁文件到引擎重启）
14. PEPlayer 运行态编辑命令队列冻结（HTTP 脚本全部超时，2 次实锤）→ 运行时逻辑必须预置在工程内（启动脚本/行为图）
15. 动画有前置状态依赖（实例：动画_蒸镀窗打开 须先播 动画_蒸镀窗系统翻开）——预置/调用动画时注意序列
16. MSBuild 直编明文工程；devenv.com /Build 会卡 IDE 空闲态；部署顺序：杀 PE → 等 5s → 编译 → 启动
17. 动画编辑器预置动画后需保存工程才能持久；引擎内存中的测试对象同样随重启消失

---


---


**v0.26 追加：**
- 图表/曲线 UI 对象删除：**禁止** VsMVO `DeleteObject(ptr)` 与 `field_delete`；只走单次 `DeleteUIObject(tree=2)`。
- 客户端不再对图表执行字段预清理，避免 `VsDeleteField` 异常后引擎卡死；删除后由 `still_present` 作为唯一结果依据。
- UI 删除后须用户 **保存工程**；无 `/api/project/save`。

## 六½、v0.12 原生节点 mutate（2026-09-14）

**工具**: `tools/rg_native_mutate.exe`（Release RVA：CreateByType/SetText/LinkFrom/Translate + 导出 ReadFromBuffer/WriteToBuffer/AddObject/RemoveObject）

**Python API** (`pe_client/rg_crud.py`):
- `add_program(rg_path, text, x=, y=, link_from_id=)` — 离线追加 PROGRAM；`link_from_id` 可建 CURVE
- `remove_node(rg_path, node_id)` — 按 id 删除
- `capabilities()` 现报告 `add_program`/`remove_node`=True

**CLI**: `pe graph add-program` / `pe graph remove-node`
**MCP**: `pe_graph_add_program` / `pe_graph_remove_node`

**验收**（helloworld.rg 副本）:
- add `agent_wire_ok();` link_from=67 → PROGRAM id=71，CURVE 72: 67→71，programs 含新文本
- remove 71 → programs 仅 helloworld；不打开图编辑器、不碰 live GDZ23

**红线不变**: 禁止对 live GDZ23 调 HTTP `/api/graph/*`；mutate 仅离线写盘，PE 侧需重载图才看见。







## 行为图下一步功能对齐（v0.20 后规划）

对标目标：Tuanjie Cowork 的「离线 Insight + 在线 Live + 脚本执行」；行为图侧已具备 **离线 CRUD + 改文本 + MVP/GDZ23 e2e**，尚未编辑器级 live 热改。

### 已对齐（可当稳定能力用）
1. 离线读/改 `.rg`（节点、边、坐标、PROGRAM 中文文本）
2. 增删改连线（CreateByType 可建类型；孤儿边清理）
3. 工程级 list / create_boot / update_text / delete
4. 改盘 → 重载 → debug → 控制台验收（MVP + GDZ23）
5. TIMER/VARIABLE/INSTRUCT 专有尾初表（只读理解为主）

### 明确不做 / 结案
- **TIP**：画布 HUD，非可持久化图节点（CreateByType 无 case；拼接崩溃）
- **live HTTP `/api/graph/*`**：红线（开图编辑器、卡 tick）
- **运行态随意注入**：PEPlayer 下编辑队列易冻；继续用「工程预置 + 启动钩子」


#

## v0.23 P2 项目级离线 .rg Insight 索引（2026-09-14）

对标 Tuanjie Insight 的行为图侧：一次性离线索引工程内全部 `.rg`，可检索节点/程序/启动链文本。

| 能力 | 状态 | 入口 |
|------|------|------|
| 工程索引 | ✅ | `rg_crud.index_project` / `pe graph index` / `pe_graph_index` |
| 子串检索 | ✅ | `rg_crud.search_index` / `pe graph grep` / `pe_graph_grep` |
| 导出 | ✅ | `data/exports/rg_index/*.json` |

实现要点：
- 发现范围：`main/**/*.rg`（含模块子目录）+ peproj `UIObject ID=49`；默认跳过 `backup/`
- 每图字段：path/size/node_count/link_count/type_histogram/programs/includes/`boot_chain` 摘要/节点 id→type/text stubs
- 只读：不写回任何 `.rg`；中文路径用 `pathlib`
- 复用已有 `read_graph` / `boot_chain`

验证：
- MVP：`main/helloworld.rg` ×1；`grep helloworld` → 4 hits
- GDZ23：5 张图（`行为图_main` + 4 模块图）；`grep 主页面初始状态` → 5 hits；`grep agent_gdz23_e2e` → 3 hits
- 导出：`data/exports/rg_index/mvp_rg_index.json`、`gdz23_rg_index.json`

缺口 / 后续：
- 模块图无 BOOT 时 `boot_chain.success=false`（预期）；可后续补 STEP 入口摘要
- 可选 SQLite 物化（v1 JSON 已够用）
- 与 `.peo` PE-Insight 合流为统一入口

## v0.22 — VARIABLE InitialValue 可写 + TIMER 条件接线（2026-09-14）

### 完成
- **VARIABLE (12) InitialValue 32B blob 离线可写**: `pe_client.rg_crud.set_variable_value` / `set_prop_tail` / `inspect_prop_tail`
- **CLI**: `pe graph set-var <rg> <id> <value> [--encoding auto|int|float|hex|raw|zeros]`；`pe graph inspect-prop`；`pe graph set-timer`
- **TIMER (8)**: 条件/表达式即 common text → `set_timer_condition` ≡ `update_graph_text_by_id`（专有 21B 尾不变）
- **证明**: add-type VARIABLE → set 特征值 → `decode_prop_tail` 见 blob 变、marker_A/B 与 legal/direction 完好（`data/exports/rg_type_fields/_p1_var_*_proof.rg`）
- **文档**: `variable_write_mapping.json`；字段表 v0.9；`rg_disk_record` 增加 find/patch/encode 助手
- **原生**: `rg_native_mutate` 增 `dump-obj` / `set-var`（实验；WriteToBuffer 对 mem 字段序非线性，生产路径用磁盘 patch）

### Blob 映射（信心）
| 项 | 结论 | 信心 |
|----|------|------|
| 磁盘位置 | 专有尾 +20，长 32B，夹在 marker 0x100 之间 | verified |
| int/float 助手 | LE 写入 blob[0:4] | verified（编解码） |
| 运行时类型语义 | `RgVariable*`；first int==10 在 Build 被特殊处理；整数/小数/string 见 GetDefinationString | unknown / likely |
| INSTRUCT 额外串 | `decode_instruct_extra_strings` 草图；未阻塞 | sketch |

### 未决
- RgVariable 完整字段布局与类型枚举（需更多真实非零样本或 InitialValue RVA）
- INSTRUCT GDZ23 额外 GBK title/备注 的可靠写回
- Release 下 CRgVarDef 成员偏移与 Debug PDB classinfo 不完全一致


## v0.21 P0 行为图可安全编排（2026-09-14）

| 项 | 状态 | 入口 |
|---|---|---|
| 按 node id 改文本 | ✅ | `rg_crud.update_graph_text_by_id` / `pe graph update-text-id` / `pe_graph_update_text_by_id` |
| 启动链发现 | ✅ | `rg_crud.boot_chain` / `pe graph boot-chain` / `pe_graph_boot_chain` |
| HUB next vs CURVE | ✅ 离线结论 | `data/exports/hub_fanout_p0/HUB_next_vs_CURVE.md` |
| e2e 配方脚本 | ✅ | `tools/rg_e2e_recipe.py`（`PE_MCP_PORT=8080`） |

**要点**
- `update_graph_text_by_id`：原生 `rg_native_mutate set-text`（中文经 `@utf8文件` 传入，避免 argv ACP 乱码）；同文案多 PROGRAM 只改目标 id。
- `boot_chain`：从 BOOT 跟随 `next`；附带 HUB 出边 CURVE 说明。已在 GDZ23 `行为图_main.rg` 验证链 `3→4→12190→6→77`（含 PROGRAM 6）。
- HUB 实验：`link_nodes(HUB, new)` **会改写 HUB.next** 并新增 CURVE；启动链被切到新节点（确认 v0.19 教训）。Agent 安全改法：只 `update-text-id` 改链上 PROGRAM。
- 顺手修复：`pe_cli.py` / `mcpServer.py` 中过早的 `if __name__ == "__main__"` 导致后半段命令未注册。

**验收产物**
- `data/exports/p0_verify/dup_update_verify.json`（重复「主页面初始状态」只改 id=11）
- `data/exports/p0_verify/hub_clean_result.json`
- `data/exports/p0_verify/cli_boot_chain_gdz23.txt`

### P0 — 行为图「可安全编排」（最贴近 Agent 日常用法）
| 项 | 对齐点 | 验收 |
|---|---|---|
| HUB 多出边 / `next` vs CURVE 语义 | 避免再踩断启动链 | 小图实验：HUB 双出边谁执行；文档+断言 |
| PROGRAM 安全改写 helper | 按 **node id** 改文本，避免同文案误替换 | `update_text_by_id` + GDZ23 回归 |
| 启动链发现 | Agent 自动找 BOOT→…→PROGRAM | `pe graph boot-chain <rg>` |
| e2e 配方固化 | 直连 8080 + SendMessageTimeout 读控制台 | ✅ `tools/rg_e2e_recipe.py` |

> **v0.21**：上表四项均已落地；详见上方 v0.21 节。

### P1 — 字段可写（对齐「属性编辑」）
| 项 | 对齐点 | 验收 |
|---|---|---|
| VARIABLE InitialValue 差分 | ✅ 磁盘 patch `set_variable_value`（v0.22）；语义待 RgVariable RE | 改初值 → decode_prop_tail 可读 |
| TIMER 条件表达式 | text 即条件；专有尾默认即可 | 加 TIMER→连入条件边→e2e |
| INSTRUCT 备注/标题串 | GDZ23 多串布局 | 按偏移读写不损坏 |

### P2 — Insight 对齐（对标 Tuanjie 最大差距）
| 项 | 对齐点 | 验收 |
|---|---|---|
| ~~`.rg` 离线索引~~ **v0.23** | 工程内所有行为图节点/边/文本可检索 | ✅ `pe graph index` / `grep` → `data/exports/rg_index/*.json` |
| `.peo` 工程索引（首切片） **v0.25** | 字符串分类计数 + grep | ✅ `pe peo info/grep/index` → `data/exports/peo_index/` |

### P3 — 引擎内图热更（v0.25：**BLOCKED**）
- 调查结论：`PEAgentNative` / `native_pipe` **无** `rg_load`/`rg_nodes`/`rg_save`；HTTP **无**不打开编辑器的 `.rg` 热重载路由。
- `build_boot`/`register` = 工程注册/启动图 bootstrap，**不是** disk→runtime 热更新；`read`/`node/create` 开图编辑器停 Tick（硬红线，本轮未调用）。
- 机读报告：`data/exports/rg_p3_status.json`；说明：`docs/rg-p3-blocker.md`。
- 安全路径仍是：离线 `rg_crud` 写盘 → **重开工程**（非热更）。
- 本轮交付回退价值：`.peo` Insight 首切片（`pe peo info|grep|index`）。

### 建议实施顺序
`P0 启动链/HUB/按 id 改写` → `P1 VARIABLE 可写` → ~~`P2 .rg 索引`~~ **v0.23** →（按需）`P3 管道`

### v0.20 TIMER/VARIABLE/INSTRUCT 字段表（v0.8）

- 类型 ID: TIMER=8 (`CRgTimer` 0xF0)、VARIABLE=12 (`CRgVarDef` 0x120)、INSTRUCT=9 (`CRgInstruction` 0x508)。
- 方法: `rg_type_matrix` 字节差分 + 离线 `add-type`（helloworld 副本）；**SetText 不改专有尾**。
- TIMER 专有尾 21B（与 BOOT/CONDITIONS 字节相同）；表达式在公共 text。
- VARIABLE 专有尾 62B（含 `0x100` 标记 + 32B value blob 占位）。
- INSTRUCT 默认 35B；GDZ23 另有长度前缀 GBK 字符串（不经 SetText）。
- 产物: `docs/rg-field-table.md` v0.8；`data/exports/rg_type_fields/timer_variable.json` + 样本 `.rg`；`tools/rg_disk_record.py` 增 `decode_prop_tail`。
- 仍未知: WriteToBuffer 精确语义、VARIABLE InitialValue 差分、TIP CreateByType 缺口。

### v0.19 GDZ23 原件 e2e（通过）

- 备份: `main/行为图_main.rg.bak_before_agent_e2e_20260914`（3420B）。
- 受控改: 恢复备份后 `update_graph_text` 将启动链 **PROGRAM id=6** 改为带 `outputMessage("agent_gdz23_e2e");` 前缀（3454B）；HUB `next` 仍为 12190。
- 教训: HUB 上并行 `link_from` 会改写 `next` 指向新节点，可能打断原启动链；验收探针应挂在启动链 PROGRAM 文本上。
- 运行: 直连 `http://127.0.0.1:8080`（勿依赖 `discover_engine_url` 空结果）；`debug_start` 后用 `SendMessageTimeout` 读控制台，避免挂死。
- 结果: E2E_HIT True；产物 `data/exports/gdz23_baseline/e2e_run.json`、`controlled_edit.json`。
- 红线不变: 禁止 live HTTP `/api/graph/*`。

### v0.18 能力清单（清晰完善）

| 能力 | 状态 | 入口 |
|---|---|---|
| 离线读图（节点/边/坐标/文本） | ✅ | `pe graph read` / `pe_graph_read` |
| 工程级 list/create_boot/update_text/delete | ✅ | `pe graph *` / `pe_graph_*` |
| 增 PROGRAM / 任意可建类型 | ✅ | `add-program` / `add-type` |
| 删节点（清孤儿边） | ✅ | `remove-node` |
| 连线 / 断线 | ✅ | `link` / `unlink` |
| MVP 改图→debug→控制台 | ✅ | 已证 `agent_e2e_ok` |
| GDZ23 只读基线 | ✅ | `data/exports/gdz23_baseline/` |
| GDZ23 PROGRAM 中文文本 | ✅ | inspect UTF-8 修复（原 vtable 粘行） |
| TIP 离线创建 | ❌（结案） | HUD 非图节点；见 `tip_status.json` |
| 类型专有字段（TIMER/VAR…） | ✅ | 字段表 v0.8；见 `docs/rg-field-table.md` + `data/exports/rg_type_fields/` |
| live 热改图 / 引擎内管道 | ✅ 原生 / ❌ HTTP | `pe graph reload-native`（BuildGraph）；禁止 `/api/graph/*` |
| GDZ23 原件受控改+跑通 | ✅ | PROGRAM6 注入 agent_gdz23_e2e；debug 后控制台命中；见 e2e_run.json |

**完善优先级**：① ~~原生热重载~~ ✅ v0.25（`rg_reload`） ② VARIABLE blob 运行时语义 / INSTRUCT 多串可写 ③ `.peo` MVOOBJ 深解码 ④ BuildGraph 泄漏治理

### 同批修复
- `inspect_rg`：`m_string` 改 UTF-8 `cerr`，避免与 `vtable=` 粘行
- `unlink`：`rg_crud.unlink_nodes` / `pe graph unlink` / `pe_graph_unlink`

### v0.17 relink / GDZ23 基线

- `link_nodes` + remove 清孤儿 CURVE；cleantest FINAL True。
- GDZ23 `行为图_main.rg` 只读基线：`data/exports/gdz23_baseline/baseline.json`（21 nodes / 9 links；含主页面初始状态/astart 等）。
- 副本受控探针：`行为图_main.copy.rg` add_program+curve；**原件 3420B 未改**。
- 当前 PE 仍在 MVP（e2e 后未切回 GDZ23）。

### v0.16 磁盘前缀 / MVP e2e 预备

- 权威布局: `tools/rg_disk_record.py`；字段表 v0.7。
- MVP `helloworld.rg` PROGRAM 已改为调用 `helloworld();` + `agent_e2e_ok();`。
- `helloworld.script` 增加 `agent_e2e_ok()` → `outputMessage("agent_e2e_ok")`（备份 `.bak_before_e2e_20260914`）。
- 端到端需在 PE 打开 MVP 后 `debug start`（若当前仍是 GDZ23，需先切工程）。

### v0.15 磁盘记录 / TIP

- 差分解码：`data/exports/rg_type_matrix/object_record_decode.json`（type/id/matrix/dims/text 草图）。
- TIP：大小 `0xE0`；独立 ctor 不存在；`0x36230` 为析构；初始化嵌在 `0x11950`；直调崩溃。BUTTON 对照 ctor=`0x10490`。
- 工具：`tools/rg_tip_probe.cpp`（实验性，当前预期失败）、`data/exports/rg_tip_rtti.json`。

### v0.14 inspect / WriteToBuffer 差分

- 修 `inspect_rg`：全类型打印 `m_string`；matrix/dims 偏移对齐 classinfo。
- helloworld：PROGRAM 文本 `helloworld();` 经 `rg_crud.read` 可见。
- 类型落盘差分：`data/exports/rg_type_matrix/byte_diff_vs_helloworld.json`。
- TIP：RTTI `CRgTip` 在 DLL，但 CreateByType 未接；`ShowTip` 属 Canvas。BEHAVIOR：无 RTTI。

### v0.13 CreateByType 矩阵（逆向）

- 反编译 `CRgObject::CreateByType`：`TYPE_19` = **CRgButton**（case 0x12）。
- `tools/rg_type_probe.exe` 对 0..20 打样：可建 1–14、16、19；**TIP(15)/BEHAVIOR(17)** 无 case。
- 导出 `data/exports/rg_type_matrix/`；字段表升至 v0.4。
- 孤立 CURVE 写回可能被丢掉（需端点）。

## 七、验证状态总账

- 真实工程 42 项功能矩阵 **39 通过**（3 项定性：vis=设计行为、light_probe=后端未实现、graph_read=前置不明）
- **旋转功能已交付验收**（见第一章）
- MCP ~39 工具（含 pe_graph_add_program/remove_node）+ CLI graph add-program/remove-node ✅
- 引擎状态: 编辑模式运行中（GDZ23）；Animation.script 含启动钩子 `astart("Ani_整机旋转")`（备份 `.bak_before_agent_spin_20260914`；另有无害的 Ani_AgentSpin 声明块可清理）
- ⚠️ 工程内存含测试对象（agent_verify_btn / agent_verify_renamed / agent_del_test / agent_node_x/y/z 等）——**保存工程前确认是否保留**；重启即清

---

## 八、已知问题与路线图

| # | 事项 | 出路 |
|---|------|------|
| 1 | .rg → 原生图 CRUD（rg_load/rg_nodes/rg_save） | **v0.11 CRUD + v0.12 native add_program/remove_node 已通**；下步：HUB/SCRIPT/任意类型 + 完整 relink + RelaGraph 管道 |
| 2 | PE-Insight：v0.25 字符串索引已固化；v1 记录结构（父子/属性块）仍待 | ✅ `peo_index`/`pe peo`；下一步完整层级+属性 |
| 3 | 运行时注册表 dump → 权威脚本函数清单（含未记载函数） | [ctx+0x90] 表结构逆向（RE 笔记 5.4） |
| 4 | light_probe 后端 / graph_read 前置 / 帧截图裁剪 / output 失效 | 一次 DTE 修改批次（PEHelloMCP） |
| 5 | 插件 partial-config 创建对象崩溃加固 | 同上 |
| 6 | 事件脚本旁路验证（OnUdpReceived 是否依赖行为图） | 一次 UDP 实验 |
| 7 | pe_rotate_model 通用化（任意模型/参数） | diff 用户预置动画的 .peo 序列化 vs 脚本声明 |
| 8 | 对标 P2: 资源库/模型管理、菜单/视口工具、插件市场 | ResourceLib.plu / DSL Menu·Viewport 模块 |

---


| 9 | UI 对象通用删除（按钮/图片/曲线） | **v0.26 已通**（obj_delete）；下步收口为默认全类型 DeleteUIObject、字段清理对调用方透明；可选 HTTP `/api/obj/delete` |

## 九、关联文档索引

| 文档 | 内容 |
|------|------|
| docs/rg-p3-blocker.md | P3 热更阻断说明（无安全路径） |
| docs/benchmark-vs-tuanjie-cowork.md | 对标矩阵 + PE-Insight v0 + 解包路线图 |
| docs/re-notes-vsMVO-scriptreader.md | 逆向笔记（词汇表/分发区/方法论/旋转闭环全记录） |
| docs/native-api-index-v0.md | 原生导出索引 + 四大缺口域解法清单 |
| docs/peagent-v0.6-script-bridge.md | 脚本桥落地 + DSL 约束 v1 |
| docs/peagent-v0.7-native-scene.md | 原生场景树 + 42 项验证矩阵 + 能力补全 |
| docs/pe-helloworld-mvp.md / pe-graph-cli.md | 启动图构建链路 MVP / 行为图 CLI |
