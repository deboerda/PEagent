# PE .rg 节点字段表（v0.9）

> 来源: `tools/inspect_rg.exe` + Release `RelaGraph.dll` 运行时读图；样本 helloworld.rg / GDZ23 行为图_main.rg；CreateByType 矩阵 `rg_type_probe`
> 工具: `python tools/rg_inspect_fields.py <graph.rg> -o out.json`

## RgType（`tools/rg_enums.txt`）

| 值 | 名 | 语义 |
|---:|---|---|
| 1 | STEP | UI/事件步骤（按钮、键盘等） |
| 2 | CURVE | **连线/边**；`prev=from_id`, `next=to_id` |
| 4 | HUB | 汇合/分叉节点 |
| 6 | PROGRAM | 可执行 DSL 文本（`m_string`） |
| 7 | COMPLEX | 根图容器 |
| 9 | INSTRUCT | 指令节点（GDZ23 退出等） |
| 11 | BOOT | 启动入口 |
| 14 | SCRIPT | include/脚本路径（`m_string`，inspect 已打印） |
| 19 | BUTTON | **CRgButton**（CreateByType `case 0x12`）；不在 RgType 0..17 枚举内 |

## CRgObject 关键运行时字段（Release）

| 偏移 | 字段 | 说明 |
|---:|---|---|
| +0x08 | `m_type` | RgType |
| +0x0C | `m_ID` | 对象 id |
| +0x10 | `m_primitiveID` | 常与 id 相同 |
| +0x14 | `m_flag` | |
| +0x18 | `m_matrix[6]` | 常见 `1,0,0,1,tx,ty`（画布坐标） |
| +0x30 | `m_string` | wchar* 文本（PROGRAM/SCRIPT） |
| +0x38 | `m_status` | |
| +0x3C/40 | width/height | |
| +0x80/84/88 | prevID/nextID/fatherID | 拓扑；CURVE 的 prev/next 是边的两端 |

COMPLEX 子对象列表（Release）在 root `+0xE0` 的 `std::list`。

## 文件头（磁盘）

```
[u32 3]["RG\0"] [u32 version=0x73|0x74]
[u32 objectCount]          # version > 0x66
[u32 status]               # version > 0x72
然后进入 root COMPLEX 的 WriteToBuffer…
```

注意：旧解析里把多处 `3b 00 00 00` 当成“节点分隔符”——在 helloworld 里 **0x3b=59 恰是 root id**，会误报。应以 RelaGraph 读图结果为准。

## helloworld 拓扑（验收样本）

```
BOOT(64) --CURVE(66)--> HUB(65) --CURVE(69)--> PROGRAM(67)   # helloworld();
SCRIPT(70) = main\Script\include.script
TYPE_19(68) 旁路未知节点
root COMPLEX id=59
```

## GDZ23 行为图_main（摘要）

- 30 objects = 21 nodes + 9 links
- SCRIPT include = `main\Scripts\include.script`
- BOOT → HUB → … → PROGRAM 链（主页面初始状态 / astart 背景图）
- 多个 STEP → PROGRAM/INSTRUCT（按钮、键盘）

导出: `data/exports/rg_inspect_*.fields.json`

## 仍缺

- PROGRAM 文本在 inspect 里未统一打印（仅 SCRIPT 打了 script text）——可改 DumpTail 或读 +0x30
- 磁盘逐字段 WriteToBuffer 布局（坐标/连线如何精确落盘）仍需对照字节；当前字段表以**运行时权威**为准
- TIP(15)/BEHAVIOR(17)：CreateByType 无 case，返回空
- 各类型专有字段（ANIM/VARIABLE/TIMER…）尚未逐字段 dump
- RelaGraph 管道 `rg_load/rg_nodes/rg_save`


## CreateByType 矩阵（v0.13 / 逆向）

来源: `tools/rg_createbytype.txt`（Ghidra）+ `tools/rg_type_probe.exe` 实机打样。
导出: `data/exports/rg_type_matrix/`（每类型一份 .rg + `matrix.csv` + `readback.json`）。

| type | 名 | CreateByType | Write+Inspect | 类 / 备注 |
|---:|---|---|---|---|
| 0 | UNKNOWN | ❌ | — | |
| 1 | STEP | ✅ | ✅ | CRgStep 0xf8 |
| 2 | CURVE | ✅ | ⚠️ 孤立边可能被写回丢掉 | CRgCurve 0x120；边需端点 |
| 3 | ANIM | ✅ | ✅ | CRgAnimation 0xf8 |
| 4 | HUB | ✅ | ✅ | CRgHub 0x148 |
| 5 | CONDITIONS | ✅ | ✅ | CRgConditions 0xf0 |
| 6 | PROGRAM | ✅ | ✅ | CRgProgram 0x100 |
| 7 | COMPLEX | ✅ | ✅ | CRgComplexObject 0x170 |
| 8 | TIMER | ✅ | ✅ | CRgTimer 0xf0 |
| 9 | INSTRUCT | ✅ | ✅ | CRgInstruction 0x508 |
| 10 | BRANCH | ✅ | ✅ | CRgBranch 0x138 |
| 11 | BOOT | ✅ | ✅ | CRgBoot 0xf0 |
| 12 | VARIABLE | ✅ | ✅ | CRgVarDef 0x120 |
| 13 | COMMENT | ✅ | ✅ | CRgComment 0xf0 |
| 14 | SCRIPT | ✅ | ✅ | CRgScrDef 0x510 |
| 15 | TIP | ❌ | — | switch 无 case |
| 16 | INTERRUPT | ✅ | ✅ | CRgInterruption 0x508 |
| 17 | BEHAVIOR | ❌ | — | switch 无 case |
| 19 | BUTTON | ✅ | ✅ | **CRgButton** 0x108（原 TYPE_19）|

工具: `tools/rg_type_probe.exe <template.rg> <out_dir> RelaGraph.dll`（cwd=`bin/Release-x64`）

## CRUD（v0.12+）

```text
pe graph add-program <file.rg> "foo();" --link-from <id>
pe graph remove-node <file.rg> <id>
pe graph caps
```

可用: 工程级增删改查 + 离线 PROGRAM 增删（可选连线）。
下一刀: `add-type` 覆盖上表全部可创建类型。


## inspect 文本修复（v0.5）

- `CRgObject::m_string` @ `+0x30`；`inspect_rg` 现对**所有**对象打印 `text=`（不再仅 SCRIPT）。
- 同步修正：`matrix` 只读 `+0x18..+0x2c` 六浮点；`dims`=`+0x3c/+0x40`；`strdims`=`+0x44/+0x48`。
- helloworld 验收：PROGRAM=`helloworld();`，BOOT=`boot`，SCRIPT=`main\Script\include.script`。

## 磁盘差分（type matrix vs helloworld）

见 `data/exports/rg_type_matrix/byte_diff_vs_helloworld.json`。

- 公共：`first_diff≈offset 93`（对象计数/头字段变化）。
- 体积增量（附加节点大致）：VARIABLE +115、SCRIPT +101、BRANCH +98、PROGRAM +90、INSTRUCT/INTERRUPT +88、STEP +86、BUTTON/COMMENT +83、HUB/COMPLEX +82、ANIM +75、CONDITIONS/TIMER/BOOT +74。
- **CURVE 孤立节点 delta=0**：写回后体积不变，边需端点才保留（与 v0.13 结论一致）。
- COMMENT `diff_spans` 特别多：字符串内容扰动更大。

## TIP / BEHAVIOR（逆向）

- `CreateByType`：**无** TIP(15)/BEHAVIOR(17) case（与 type 18 共享空返回 `0x2bdde`；跳表 `0x2bdf4`）。
- RTTI：DLL 内有 `.?AVCRgTip@@`，**无** `CRgBehavior`。
- 导出：`CRgCanvas::ShowTip`（`0x16680`）+ `CRgCanvas::EndDraw`（`0x11950`）；**无** Tip 节点工厂导出。
- 结论：TIP 是画布 HUD 覆盖物（`canvas+0x50`），不是可持久化图节点；BEHAVIOR 枚举名可能已死或不在本 DLL。


## 磁盘对象记录草图（v0.6 / 差分）

> 已被下方 v0.7 公共前缀取代为权威布局。

来源：`type_XX_*.rg` 相对 helloworld 的追加块；探针 id=`9000+type`。导出：`data/exports/rg_type_matrix/object_record_decode.json`。

追加对象常见前缀（小端）：

```
u32 type
u32 id                 # 探针为 9000+type
float matrix[6]        # 典型 1,0,0,1,tx,ty
float width, height    # 常见 120,32（探针 SetDimensions）
... 拓扑/标志 ...
[u32 len][bytes ... 0] # m_string 的 GBK/ASCII 长度前缀串（PROGRAM 等）
```

PROGRAM 样本可见 `probe_t6`；VARIABLE/INSTRUCT 等无文本时字符串块为空或极短。

## TIP（v0.6 → 2026-09-14 离线复核）

| 项 | 值 |
|---|---|
| 对象大小 | `0xE0`（EndDraw 内 `operator_new(0xE0)`） |
| type 写入 | **仅一处** `0x11A21`：`mov [rbx+8], 15` |
| 构造点 | **`CRgCanvas::EndDraw` `0x11950`–`0x11E1D`** 内联分配（非独立 ctor；`rg_tip_probe` 把 EndDraw 当 ctor 是错的） |
| vftable | `0x3E620`（仅 EndDraw + dtor 两处 LEA） |
| ShowTip | `0x16680`：读写 `[canvas+0x50]` |
| 误判 RVA | `0x36230` = scalar deleting dtor（vftable[0]） |
| CreateByType | 无 case → nullptr（`rg_type_probe` 实证） |
| 磁盘样本 | 全库 83 个 `.rg` **无** type=15 |
| 磁盘拼接 | COMMENT/BOOT 改 type=15 后 `inspect_rg` **AV** |
| Button 对照 | 独立 ctor `0x10490`（CreateByType 可用） |

状态 JSON：`data/exports/rg_type_fields/tip_status.json`

结论：TIP **不能**作图节点离线 Create/拼接；下一步反编译 EndDraw tip 块 + ShowTip 字段，而非补 CreateByType。父代理决定是否 bump v0.21。


## 磁盘对象公共前缀（v0.7 已验证）

工具: 	ools/rg_disk_record.py（扫 helloworld 全对象通过）。

`
u32 type
u32 id
f32 matrix[6]       # 1,0,0,1,tx,ty
f32 width, height
i32 prev, next, father
u32 nbytes          # 含末尾 NUL
char text[nbytes]   # GBK/ASCII，NUL 结尾
`

其后可能还有类型专有尾部；公共前缀已足够定位/改 PROGRAM 文本与拓扑三元组。

## relink（v0.17）

- `rg_native_mutate link <from_id> <to_id>`：建 CURVE，写 prev/next
- `remove-id`：先删所有 prev/next 命中该 id 的 CURVE，再删节点（清孤儿边）
- Python：`rg_crud.link_nodes`；CLI：`pe graph link`；MCP：`pe_graph_link`
- 验收：add 无连线 PROGRAM → link 67→71 → CURVE+1；remove 71 → CURVE 回到 2，无孤儿边


## TIMER / VARIABLE / INSTRUCT 专有尾（v0.8）

> 来源: `data/exports/rg_type_matrix/type_{08,09,12}_*.rg` + 离线 `rg_native_mutate add-type`（helloworld 副本，目录 `data/exports/rg_type_fields/`）  
> JSON: `data/exports/rg_type_fields/timer_variable.json`  
> 方法: 公共前缀之后的字节差分；**禁止** live HTTP `/api/graph/*`。  
> 结论要点: `SetText` **只**改公共 `m_string`；TIMER/VARIABLE/INSTRUCT 的专有尾在 CreateByType 默认态下对 SetText **不变**。

### 类型 ID 映射

| RgType | 名 | 运行时类 | 大小 | 备注 |
|---:|---|---|---:|---|
| 8 | TIMER | `CRgTimer` | 0xF0 | `RG_TRI_TIMER`；表达式在公共 text |
| 9 | INSTRUCT | `CRgInstruction` | 0x508 | 代码在 text；编辑器另有标题/备注串 |
| 12 | VARIABLE | `CRgVarDef` | 0x120 | `InitialValue` / `GetDefinationString`（整数/小数/string） |

偏移均 **相对 text 之后**（即 `common_prefix` 结束后）。公共前缀仍为 v0.7 已验证布局。

### TIMER（type=8）专有尾 — 默认 21 字节

与 **BOOT(11) / CONDITIONS(5)** 默认专有尾 **逐字节相同**。

| 偏移 | 大小 | 类型 | 含义 | 置信度 |
|---:|---:|---|---|---|
| +0 | 4 | u32 | `m_legal`? 默认 1 | likely |
| +4 | 4 | u32 | `m_direction`? 默认 1 | likely |
| +8 | 4 | u32 | unk，默认 0 | unknown |
| +12 | 4 | u32 | unk，默认 0 | unknown |
| +16 | 4 | u32 | unk，默认 0 | unknown |
| +20 | 1 | u8 | unk/BOOL，默认 0 | unknown |

`prop_hex` 默认: `010000000100000000000000000000000000000000`  
验证: `SetText("1.5")` / `SetText("delay(1.5)")` 后专有尾不变；计时条件在公共 text（图编译里作 `RG_TRI_TIMER` 条件串）。

### VARIABLE（type=12）专有尾 — 默认 62 字节

| 偏移 | 大小 | 类型 | 含义 | 置信度 |
|---:|---:|---|---|---|
| +0 | 4 | u32 | `m_legal`? 默认 1 | likely |
| +4 | 4 | u32 | `m_direction`? 默认 1 | likely |
| +8 | 4 | u32 | unk，默认 0 | unknown |
| +12 | 4 | u32 | unk，默认 0 | unknown |
| +16 | 4 | u32 | marker_A = `0x100` | likely |
| +20 | 32 | bytes | value blob（`InitialValue` 载荷？）默认全 0 | unknown |
| +52 | 4 | u32 | marker_B = `0x100` | likely |
| +56 | 4 | u32 | unk，默认 0 | unknown |
| +60 | 2 | bytes | unk tail，默认 0 | unknown |

`prop_hex` 默认: `010000000100000000000000000000000001000000` + 32×`00` + `00010000000000000000`  
验证: `SetText("int x = 1;")` / `SetText("myVar")` 专有尾不变。
**P1 可写 (v0.22):** `rg_crud.set_variable_value` / `pe graph set-var` 离线 patch `value_blob`（prop+20..+51，32B）。
编码助手: int/float LE @blob[0:4]、hex/raw；语义仍 **unknown**（`CRgVarDef::InitialValue`→`RgVariable*`，Build 时 first int==10 特殊；DLL 未导出 setter）。
证明: `data/exports/rg_type_fields/variable_write_mapping.json` + `_p1_var_*_proof.rg`。
原生 `rg_native_mutate set-var` 为实验性 mem poke（WriteToBuffer 字段序非线性）— **优先磁盘 patch**。

### INSTRUCT（type=9）专有尾 — 默认 35 字节（易表）

| 偏移 | 大小 | 类型 | 含义 | 置信度 |
|---:|---:|---|---|---|
| +0 | 4 | u32 | `m_legal`? 默认 1 | likely |
| +4 | 4 | u32 | `m_direction`? 默认 1 | likely |
| +8 | 4 | u32 | unk，默认 0 | unknown |
| +12 | 4 | u32 | unk，默认 0（GDZ23 有额外串时可见 `0x100`） | unknown |
| +16 | 19 | bytes | 默认槽位（含 `0x100`/`0x10000` 标记） | unknown |

默认 `prop_hex`: `0100000001000000000000000000000000010000000001000000000000000000000000`  
GDZ23 实样（id=1133）专有区可见长度前缀 GBK 串：`退出系统`、`appExit("myself")`、`备注`（**likely**；精确字段序待 `CRgInstruction::WriteToBuffer`）。  
`INTERRUPT(16)` 默认专有尾与 INSTRUCT 相同。

### Changelog snippet（→ handoff v0.20）

- field table **v0.7 → v0.8**: TIMER / VARIABLE / INSTRUCT 专有尾初表
- JSON export: `data/exports/rg_type_fields/timer_variable.json`
- 样本: `data/exports/rg_type_fields/timer_*.rg`, `var_*.rg`, `inst_*.rg`
- TIP(15)/BEHAVIOR(17) 仍不可 `CreateByType`；TIP 已确认为 Canvas HUD（见 tip_status.json）。TIMER 条件已可写（`set_timer_condition`/`update_text_by_id`）。VARIABLE blob 已可写（磁盘 patch）。下一步: RgVariable 类型标签语义、INSTRUCT 额外 GBK 串确认写、EndDraw/ShowTip

## P0 helpers (v0.21)

- **`update_graph_text_by_id(rg, node_id, new_text)`** — native `SetText` by id (`rg_native_mutate set-text`); Chinese via `@utf8` file arg. Safe when multiple PROGRAM nodes share the same GBK string (e.g. two `主页面初始状态();`).
- **`boot_chain(rg)`** — walk `BOOT.next` → …; for each HUB also list outgoing CURVE edges. Primary sequential path is `next`.
- **HUB semantics**: `link_nodes(HUB, X)` rewrites `HUB.next` to X **and** adds a CURVE. Do not fan-out from GDZ23 HUB; probe via on-chain PROGRAM text instead. See `data/exports/hub_fanout_p0/HUB_next_vs_CURVE.md`.

