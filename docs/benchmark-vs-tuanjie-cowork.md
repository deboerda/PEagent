# PEagent 对标分析与深度解包路线（vs Tuanjie Cowork）

> 日期: 2026-09-14 ｜ 基准: Tuanjie Cowork (ZCode unity-tuanjie 技能, Insight + Codely Bridge)
> 结论先行: Tuanjie 的能力版图 = **离线索引(Insight) + 在线编辑器控制(Live) + 脚本执行(C#)**。PEagent 已覆盖 Live 层的 ~60%，最大差距是 **Insight 等价物（.peo/.peproj 离线索引）**——这恰好也是深度解包的最高价值靶点。

---

## 一、对标能力矩阵

### 1.1 离线层（Tuanjie Insight VFS ↔ PE 无对应物 → 解包主战场）

| Tuanjie 工具 | 能力 | PEagent 现状 | PE 对应物 / 解包靶点 |
|---|---|---|---|
| unity_project_info | 工程识别/版本 | ✅ pe_client 自动发现 + engine_status | .peproj XML 已可解析 |
| unity_index (SQLite) | 工程全量离线索引 | ❌ **无** | **.peo 解码**（.peo = 场景对象数据库，含 MVOOBJ 记录，本会话已在动画区验证可读）→ PE-Insight |
| vfs_ls | 场景/预制体层级 | ⚠️ 单层（DSL 枚举 count 不可测） | .peo 对象树解码（离线全量层级，绕开引擎限制） |
| vfs_glob | 按类型找资产 | ⚠️ 文件级（.vis/.script/.rg 可枚举） | 同上 |
| vfs_read | 对象/组件载荷 | ⚠️ 文本文件可读；.peo 未解码 | .peo 记录解码 |
| vfs_grep | 串/GUID 检索 | ⚠️ 文件级 grep | 索引建立后免费获得 |
| vfs_refs | 引用图/C# 调用图 | ❌ | .peo 字段引用 + Include 关系 |
| unity_cli | 官方 CLI | ❌（PE 无官方 CLI） | pe_cli 即事实 CLI；补 headless 模式（无窗口启动+脚本驱动） |

### 1.2 在线层（Tuanjie Codely Live ↔ PEagent 三层通路）

| Tuanjie 工具 | PEagent 对应 | 状态 |
|---|---|---|
| unity_editor (状态/控制) | engine_status + debug_start/stop + UI 自动化 | ✅ |
| unity_scene | 场景树工具族 | ⚠️ 单层+原生 CRUD（深层枚举待解） |
| unity_gameobject (层级/组件/属性) | field_* 管道命令 + obj_* UI 对象 | ⚠️ 属性读写是短板（Transform 读不到） |
| unity_console | pe_console_read | ✅ |
| unity_script (编译状态) | pe_script_validate + execute_file | ✅ |
| unity_asset (AssetDatabase) | ❌ 资源/模型管理未接（ResourceLib.plu / 模型管理器） | 解包靶点 |
| unity_package | ❌ 插件市场未接 | 低优 |
| unity_bake | ❌（PE 无对应概念） | — |
| unity_menu | ⚠️ DSL Menu 模块 31 函数 + UI 自动化 | 可补工具 |
| unity_screenshot | pe_snapshot（全窗）+ capture(裁剪) | ✅ |
| unity_gameview | ❌ 视口参数（DSL Viewport 模块 38 函数可补） | 可补 |
| exec_editor_script | **DSL 脚本桥** | ✅✅ PEagent 最强资产（1927 函数 + GBK 文件通道） |
| exec_runtime_script | ❌ **运行态注入被引擎冻结**（实测 2 次） | 唯一出路=工程预置+启动钩子（旋转功能已实证此模式） |
| unity_dialog | 桌面自动化 | ⚠️ |

### 1.3 PEagent 独有（Tuanjie 没有的）
原生管道场景 CRUD（field_create/rename/delete 按精确 key）、17 种渲染效果查询/设置、光照探针（待后端）、1927 函数中英文搜索引擎、GBK/加密源码工具链、a11y 控制台直读。

### 1.4 差距总账（P0-P2）
- **P0**: .peo 离线索引（= 自建 PE-Insight，一次解包补齐 ls/glob/read/grep/refs 五项）
- **P0**: 深层场景树（引擎内枚举 count 原语）——若 .peo 解码成功则离线路线已覆盖
- **P1**: 运行态脚本注入（引擎冻结命令队列——需引擎级方案，已实证预置钩子模式可行）
- **P1**: 节点属性读写（Transform/可见性/材质的 get——DSL 只有 set 系）
- **P2**: 资源库/模型管理、菜单/视口工具、插件市场

---

## 二、深度解包进展（本轮）

### 2.1 重大发现：函数数据库 ≠ 引擎二进制
1927 个函数名中仅 **97 个**以字符串形式存在于 VsMVO/3dgs（VsMVO 95 + 3dgs 24，交集后 97）——**函数接口数据库源自文档而非二进制**。已被代码引用（LEA）的仅 56 个函数（ VsMVO 侧 0x1800a081d 起：getBoxByKey/pick2DObject/getObjectName/setBoxByKey/modifyFieldPath…；另有 0x1800d7b62 的 getChildrenKeys 块属 343KB 栈帧的内联解释器主循环）。
→ **推论**：a) 文档函数≠全部可用函数；b) 实现高度内联于解释器，"name→原生实现"无干净表可提取；c) 真实可用函数面的权威提取必须**运行时**做（dump 解释器注册表，PEAgentNative 路线，需先逆出注册表结构 [ctx+0x90]）。
数据: `data/exports/function_impl_map.json`、`dispatcher_blocks.json`

### 2.2 .rg 行为图格式（结构观察完成，待差分破解）
- 头: `03 00 00 00 "RG\x00t" <u32 图相关量>`；节点记录以 `3b 00 00 00` 分隔
- 内容: 长度前缀字符串（节点名 root/boot）+ float 属性块（1.0f/坐标）
- 语义要素已在样本中定位：程序文本 `helloworld();\r\n`、包含路径 `main\Script\include.script`
- 破解方法：cleantest 有 10+ 个已知差异的生成图变体（built/mcp_boot/release_*）→ 成对 diff 即可解出字段表
- 产出价值：程序化生成启动图（"运行项目自动执行任意逻辑"的通用化，旋转功能已实证该模式价值）

### 2.3 .peo 场景数据库（已验证可读，PE-Insight 的地基）
- 动画对象解码完成：`名称 + 时长(float) + 速度 + N 事件`；事件 = `id + 模块限定上下文 + 场路径 + 四元数关键帧块`
- 已解码实例：`(0, 0.7078, 0, 0.7078)` = 绕 Y 轴 90°（主鼓旋转）
- 对象记录含 `MVOOBJ38751` 式 ID 与函数定义（setTextureParam@38756 签名串）——**.peo 就是序列化场景数据库**
- 360° 旋转无效果的根因假设（四元数恒等）成立与否可用 .peo 解码对照预置动画验证

### 2.4 引擎分发区（ VsMVO 0x1800d7300）
- 343KB 栈帧的内联解释器主循环；每个引擎函数一个查找块（`mov rcx,[ctx+0x20]; lea rdx,"名"; call 0x180001a90`）
- 实现内联其中 → 原生 name→impl 无干净提取路径 → 运行时注册表 dump 是正道
- 工具沉淀：字节模式 LEA 扫描（0.2s/4MB）替代 capstone 线性反汇编

---

## 二·五、PE-Insight v0（已交付 ✅ 2026-09-14）

`data/peo_index_gdz23.json`：44.9MB .peo 7 秒索引完成。
- 440 条场景全路径（含印钞机模型内部 23 条深层层级：主鼓组件/张力辊/扩散泵组/收卷机构…——与工程动画绑定节点完全吻合，**离线解决了引擎侧深层枚举被卡的问题**）
- 1805 个 MVOOBJ 对象记录、520 个函数定义绑定（数据曲线赋值@39931 等）、47 个动画、352 个 UI 对象、359 个模块引用
- 即刻可用能力：离线场景树、离线 grep（对标 vfs_ls/read/grep）
- v1 方向：.peo 记录结构解析（父子关系/属性块）→ 完整层级树 + 对象属性（对标 vfs_read/refs）

## 三、下一步（解包路线图）

1. **PE-Insight v0**（最高价值）：.peo 对象记录解析器 → 离线场景树 JSON（对标 vfs_ls/read）；用 GDZ23 已知场景（模型/模块/UI 对象清单已在 .peproj+项目树中）验证正确性
2. **.rg 差分破解**：cleantest 生成图两两 diff → 字段表 → PEAgentNative rg_load/rg_save 命令 → 程序化启动图
3. **运行时注册表 dump**：逆 [ctx+0x90] 表结构 → 真实脚本函数清单（含未记载函数）+ 原生调用
4. **节点属性读**：set 系函数的 get 对应物（VsShow* 家族已部分可用）→ Transform 读取补全
