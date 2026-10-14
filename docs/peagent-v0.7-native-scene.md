# PEAgent v0.7 — 原生场景树通路（PEAgentNative 扩展）

> 日期: 2026-09-14 ｜ 前置: v0.6 脚本桥（docs/peagent-v0.6-script-bridge.md）

## 一、本次交付

**PEAgentNative.plu 新增 6 条管道命令**（C++ 明文源码直接扩展，MSBuild 构建，未触碰加密的 PEHelloMCP）：

| 命令 | 功能 | 实测状态 |
|------|------|---------|
| `scene_key` | 场景根 key | ✅ |
| `field_info key=` | key → name + 完整路径（如 `/scene/modules/main/model/main`） | ✅ |
| `field_key path=` | 路径 → key | ✅ |
| `field_create father= name=` | 创建子场节点（father 空则挂模块模型根） | ✅（已验证与 DSL 枚举同树） |
| `field_rename key= name=` | 重命名 | ✅ |
| `field_flush key=` | 刷新节点内容 | ✅ |

**Python/工具层**：
- `pe_client/native_pipe.py`（新）：命名管道客户端，稳定命令全封装
- `pe_client/script_bridge.py`：新增 `scene_children_dsl`（单层枚举，DONE 哨兵 + cap 截断）
- MCP 工具 27 → **33 个**：`pe_scene_children`、`pe_scene_key`、`pe_field_info`、`pe_field_key`、`pe_field_create`、`pe_field_rename`
- CLI：`pe scene-children`、`pe field <info|key|create|rename|flush|scene-key>`

**全部经引擎实测**：MCP stdio 实调 `pe_field_info` 返回真实节点路径 ✅；CLI `pe field info` ✅；创建→DSL 枚举同树验证 ✅。

## 二、关键技术结论（本次最价值的产出）

### 2.1 修饰名 = 免解包的签名来源

从 dumpbin 导出表的 MSVC 修饰名直接恢复完整签名，全部通过 GetProcAddress 运行时解析（版本安全，沿用 PEAgentNative 既有模式）：

```
?VsGetSceneKey@@YA_JXZ                      → i64 VsGetSceneKey(void)
?VsShowFieldName@@YAX_JPEAD@Z               → void VsShowFieldName(i64, char*)
?VsShowFieldPathName@@YAX_JPEAD@Z           → void VsShowFieldPathName(i64, char*)
?VsShowFieldKey@@YAXPEBDAEA_J@Z             → void VsShowFieldKey(const char*, i64&)
?VsCreateSubField@@YA_J_JPEBD@Z             → i64 VsCreateSubField(i64, const char*)
?VsRenameFieldByKey@@YAX_JPEBD@Z            → void VsRenameFieldByKey(i64, const char*)
?VsFlushContentsByKey@@YAX_JPEBD@Z          → void VsFlushContentsByKey(i64, const char*)
?GetModuleModelKey@CVsModule@@QEAA_JPEBD@Z  → i64 CVsModule::GetModuleModelKey(const char*)
```

x64 下 thiscall 与 cdecl 同约定，`CVsModule` 方法可传 self 指针直调（self 来自 `FxGetMainVsModule()`）。

### 2.2 两个枚举导出不可用（有实锤，后人勿踩）

| 导出 | 症状 | 证据 |
|------|------|------|
| `VsSearchFieldByKey` | **崩溃整个引擎进程**（0xC0000005） | EventLog: 错误模块 3dgs.dll，faulting offset 0x1d51fa = 函数 RVA 0x1d51b0 + 0x4a |
| `VsShowFieldContentsByKey` | 传 NULL filter → 终止调用线程（管道消失、引擎存活）；空串返回 count=0（"Contents" 是叶子内容语义，不是子节点） | 管道线程反复消失；枚举恒 0 与 DSL 枚举矛盾 |

### 2.3 DSL 层场景枚举的边界（v0.6 结论的修正与补全）

- `getChildrenKeys` 与原生 `field_create` 操作同一棵树（跨通路验证 ✅）
- **数组越界读不中断脚本**：返回垃圾 key，`getFieldName` 输出 `unknown+数字` 占位 → DSL 层无法判定子节点精确数量（getArraySize 恒 0、splitDword/fileWrite 数值通道全部失效）
- **嵌套 getChildrenKeys 曾实测挂起引擎 30s+**（c2/c3 探针）——禁止深层遍历
- 脚本中断会泄漏回传文件句柄（文件被引擎锁定，重启才释放）——探针脚本必须保证 fileClose

### 2.4 工程教训

- **MSVC + UTF-8 无 BOM 中文注释会吞掉下一行代码**（表现为诡异的 C2065），PEAgentNative.cpp 的新增注释一律用英文
- devenv.com /Build 在此环境会卡在 IDE 空闲态不出活；明文工程直接用 MSBuild.exe
- 部署顺序必须严格：杀 PE → 等待 ≥5s → MSBuild → 启动 PE（.plu 被运行中引擎锁定）

## 三、场景树现状与下一步

**已可用**：单层枚举（含垃圾尾部说明）、key/路径互查、创建/重命名/刷新 —— 已覆盖"程序化建模/节点管理"的核心操作。

**未解决（P1 继续）**：子节点精确枚举的可靠原语。`getChildrenKeys` 的真实后端不在已扫描的 3dgs 平函数中，可能在 VsMVO 的类方法或 ScriptReader 运行时内。候选路径：
1. 在 PEHelloMCP（引擎 tick 线程）内实现枚举路由 —— 线程安全性最好，需 VS DTE + devenv 链路
2. UI Automation 读项目管理器树（所见即所得，零引擎风险，pe_console 已验证 UI 读取可行性）
3. 继续导出表挖掘：VsMVO 类方法中与 Field 树相关的迭代器

## 四、稳定性守则（在结论生效前必须遵守）

1. 管道命令永远不传 NULL filter 给 VsShowFieldContentsByKey
2. 禁止在管道命令中调用 VsSearchFieldByKey
3. DSL 脚本不做嵌套 getChildrenKeys
4. DSL 探针保证 fileClose（否则句柄泄漏锁文件）
5. **管道协议是 GBK 边界**：含中文的路径/名称必须以 GBK 编码发送与解码（UTF-8 查不到节点，实测 field_key 返回 -1）；native_pipe.py 已统一处理

## 五、真实工程验证记录（2026-09-14，印钞机工程）

- 场景根 `/scene`、模型节点 `印钞机9.10.vis`（含中文名路径）全部可寻址
- 完整闭环实测：在模型下 `field_create` → `field_info`（中文路径正确）→ `field_rename` → path→key 往返一致 ✅
- 相机读取返回真实视角（eye=(-9.49, 3.0, 16.16)）✅
- 工程含 14 按钮 / 10 图片 / 21 变量对象，obj/query 全部可导出 ✅
- 效果查询（fog/sun/ao）返回真实状态 ✅
- 截图捕获到工程 UI 面板 ✅


## 七、真实工程全量验证矩阵（2026-09-14，GDZ23 印钞机工程，42 项）

**39 通过 / 3 失败（3 项均已定性）**：

| 结论 | 项目 | 说明 |
|------|------|------|
| 预期行为 | obj_query[vis] | .vis 引用是场景资源，插件明确拒绝按模块对象枚举（"vis imports are scene resources"）——用原生场景树工具寻址 |
| 插件缺口 | light_probe | `/api/pe/light_probe/list` 路由 404（实际存在的是 `/query`），且后端返回 "scene action not implemented"——**路由存在但后端未实现**，修正 v0.6 文档"后端已实现"的说法 |
| 前置不明 | graph_read | 所有路径形式返回 "cannot open behavior graph"——疑似需要图在编辑器中打开，待查 |

**通过清单**：引擎状态×2、对象查询×14 类型（remark 117/variable 21/button 14/image 10/curve 8）、对象创建/修改/回读验证、效果查询×6（fog/sun/ao/bloom/postprocess/ssr）、效果应用+回读+恢复（fog 往返）、光照探针除外、相机读取、DSL 单层枚举、语法校验、原生管道×7（status/scene_key/field_info/field_key/create/rename/rename 回读）、行为图读取除外、截图。

**测试残留**（内存，不保存工程即消失）：按钮 agent_verify_btn、场节点 agent_verify_renamed。


## 八、能力补全（2026-09-14 第二批）

| 新能力 | 实现 | 验证 |
|--------|------|------|
| 全窗截图 | `pe_client/scene_tools.snapshot`（PrintWindow + PW_RENDERFULLCONTENT） | ✅ 1721x1051（对比插件 253x253 裁剪） |
| 控制台直读 | `scene_tools.console_read`（包装 pe_console Win32 直读） | ✅ 绕过失效的 /api/output/query |
| 相机切换 | `scene_tools.apply_camera`（applyCamera 机制 + **GBK 文件通道**） | ✅ 含中文名相机安全切换（camSetCamera 危险，勿用） |
| 节点删除 | PEAgentNative `field_delete`（VsDeleteField） | ⚠️ 实验性：命令成功但节点查询仍在，可能延迟到工程重载生效（int 参数语义无从考证，历史工程无用法） |

**MCP 工具 33 → 37**：新增 `pe_snapshot` / `pe_console_read` / `pe_apply_camera` / `pe_field_delete`；CLI 新增 `pe snapshot` / `pe camera-apply` / `pe field delete`。

**关键工程约束（新增）**：
- HTTP 内联 DSL 脚本中的中文会以 UTF-8 进入 GBK 引擎（动画名/路径变乱码，引擎弹"找不到动画"）→ **凡含中文的 DSL 必须写 GBK 临时脚本文件走 execute_file**（scene_tools._run_via_gbk_file 已封装）
- execute_file 要求 ASCII 路径（中文+空格路径加载失败）
- DSL 动画声明语法（从 ScriptReader.dll 关键字簇 + 解析器报错迭代破解）：`Animation{ '''名字 / name{} / controller{ Rotate{ field{} values{角度 时长} axis{x y z} } } }`，数值空格分隔

**遗留**：旋转动画对 .vis 引用模型不生效（rotateFieldAnim 与声明式 Rotate 均无视觉效果，平移有效）——推荐方案：帧动画编辑器预置动画 + 启动脚本 astart（钩子已就位，Animation.script 已补丁，备份 .bak_before_agent_spin_20260914）
