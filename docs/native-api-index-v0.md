# PE 引擎原生能力索引 v0

> 生成日期: 2026-09-14
> 方法: dumpbin 导出表 + undname 反修饰 + 与 1927 脚本函数库差集比对
> 复现: `python tools/build_native_index.py`（依赖 `data/exports/*.exports.txt`，由 dumpbin //EXPORTS 生成）
> 数据文件: `data/exports/native_index.json`

---

## 一、总量概览

| DLL | 解析导出数 | 说明 |
|-----|-----------|------|
| VsMVO.dll | 8,540 | 对象/场景/编辑核心（修饰 C++ 符号为主） |
| 3dgs.dll | 1,817 | 渲染核心，含 **114 个 `pe*` 扁平 C 导出** |
| RelaGraph.dll | 412 | 行为图（.rg）对象模型 |
| ScriptReader.dll | 148 | 脚本 DSL 解析器 |
| PluginManager.dll | 46 | 插件框架 |

**三层 API 模型（本项目开发深度的坐标系）：**

| 层 | 规模 | 调用方式 | 状态 |
|----|------|---------|------|
| HTTP API | 18 路由 | Python (pe_client) | ✅ 实测可用 |
| DSL 脚本 | 1,927 函数 / 63 模块 | program 模式执行 + 文件回传 | ✅ 实测可用 |
| 原生导出 | **322 个 C++ 类 + 161 个自由函数 + pe* 114** | 原生插件 (PEHelloMCP / PEAgentNative 模式) | 符号+头文件可用，签名部分待实测 |

**差集关键数字：**
- 脚本与原生同名函数: 389（可直接对应验证语义）
- **仅原生层有的函数名: 1,378**（开发深度的主要增量空间）
- 导出 C++ 类: 322 个，其中 VsMVO 的 `CVsModule`(409 方法)、`CVsView`(242 方法) 是两大枢纽类

---

## 二、四大 HTTP 缺口域的原生解法清单

### 2.1 变换 / 旋转（DSL 缺 setRotation → 已解决）

| 条目 | 层 | 说明 |
|------|----|------|
| `peSetTransformByKey` / `peShowTransformByKey` | 3dgs C 导出 | 按 key 直设/读节点变换矩阵 |
| `peSetTransform` / `peShowTransform` | 3dgs | 按当前上下文 |
| `peComputeMatrix` / `peComputeMatrix3dInverse` / `peComputeMatrix3dMulti` | 3dgs | 矩阵数学 |
| `peComputePosition` / `peComputeVector` | 3dgs | 坐标换算 |
| `COpModelRotate` / `COpModelRotateAngle` / `COpModelTransformer` / `COpModelTransform2d` | VsMVO 类 | 交互式旋转操作（含撤销 `CUndoTransformField/Object`） |
| DSL `Field.setPosition(ByKey)` / `scaleField` / `moveField` | 已实测 | 平移/缩放可直用 |

### 2.2 拾取（Pick → 已解决）

| 条目 | 层 | 说明 |
|------|----|------|
| `CVsView.GetPickedKey` / `GetPickedPoint` / `ResetPickedKey` | VsMVO | **视图级拾取结果直接可读**（首选入口） |
| `COpModelPick`（OnLButtonDown/OnMouseMove/OnKeyDown） | VsMVO 类 | 交互拾取操作 |
| `CRgComplexObject.Pick` / `PickQuickly` | RelaGraph | 行为图对象拾取 |
| `CVsEdit.SetPick` | VsMVO | 编辑态拾取设置 |
| DSL `Field.getFieldPathByPos(x,y)` | 已实测 | 屏幕坐标拾取（轻量备选） |

### 2.3 射线求交（Raycast → 已解决）

| 条目 | 层 | 说明 |
|------|----|------|
| `VsAllocRayCluster` / `VsFreeRayCluster` / `VsComputeRayClusterIntersection` | 3dgs | 射线簇批量求交 |
| `VsComputeIntersectionOfLineWithPlane` / `VsComputeIntersectionOfLines` / `VsCalcIntersectionOfClipPlane` | 3dgs | 线/面求交 |

### 2.4 相机（Camera → DSL 已实测 + 原生增强）

| 条目 | 层 | 说明 |
|------|----|------|
| DSL `camGetCamera(vport, &values)` | 已实测 | 读相机参数 ✅ |
| `COpCameraFly/Orbit/Walk/Pan/Zoom/ZoomTo/ZoomDown/OrbitNavi/Cave`（9 类） | VsMVO | 编辑器级相机操作 |
| `CVsView.AddCameraObject` / `OnCameraChanged` / `WalkCamera` / `GetCameraHost` | VsMVO | 相机对象管理 |
| `VsCameraRotate` | 3dgs | 相机旋转 |

### 2.5 场景树 / 节点管理（DSL 已实测 + pe* 系统化）

| 条目 | 层 | 说明 |
|------|----|------|
| DSL `getModuleModelKey("main")` + `getChildrenKeys` + `getFieldName` | 已实测 ✅ | 树遍历机制打通（名称查询需换 `VsShowFieldName`） |
| `peCreateField` / `peOpenField(ByKey)` / `peCloseField` / `peReleaseFieldByKey` / `peFieldExists` | 3dgs | 节点生命周期 |
| `peIsChildOf` / `peShowFieldContents(ByKey)` / `peShowFieldName` / `peShowFieldKey` | 3dgs | 层级关系与内容枚举 |
| `peIncludeFrom(ByKey)` / `peRebuildInclude(ByKey)` | 3dgs | 节点引用/复用 |
| `peSetVisibilityByKey` / `peSetTransparencyByKey` | 3dgs | 节点显示控制 |
| `CVsModule`（409 方法） | VsMVO | 模块/对象枢纽（findObject、变量、回调注册） |

---

## 三、`pe*` 家族（3dgs.dll，114 个扁平 C 导出）

无符号修饰的 C 接口，**专为程序化访问设计**，是原生桥的第一优先选型池（无需 C++ 头文件即可 GetProcAddress）。按子域分组要点：

- **变换/矩阵** (8): peSetTransform(ByKey), peShowTransform(ByKey), peComputeMatrix*, peComputePosition/Vector
- **节点/场** (15): peCreateField, peOpenField(ByKey), peCloseField, peReleaseFieldByKey, peFieldExists, peIsChildOf, peShowFieldContents(ByKey), peShowFieldName, peShowFieldKey, peExecuteFieldByKey, peIncludeFrom(ByKey), peRebuildInclude(ByKey), peFlushContents(ByKey)
- **几何插入** (10): peInsertMesh(ByKey/Old), peInsertSphere, peInsertSimpleCube, peInsertLine(Array), peInsertCylinder(2), peSetTriMeshData(2)
- **外观** (22): peSetMaterial{Ambient,Diffuse,Specular,Emission,Shininess}(ByKey), peSetTexture(2/MaskFilename), peBindAllTextures, peSetTransparency(2/ByKey), peSetColorf, peAttachShader(ByKey), peSetVisibility(ByKey)
- **包围盒** (8): peSetBoxByKey(2), peResetBox(ByKey), peRebuildBox(ByKey), pePropagateBoxByKey
- **数组/内存** (6): peNewArray, peFreeArray, peFree, peFreeDatabase

> ⚠️ 约束: pe* 为无修饰 C 导出，**导出表不含签名**，头文件中也未检索到声明。签名需按 `ByKey` 变体镜像非 Key 变体 + 实测确定（x64 __cdecl）。建议在 PEAgentNative 中先封装 5-10 个探针函数验证约定。

---

## 四、高价值 C++ 类 TOP（原生桥第二优先：配合 PESdk 头文件）

| 类 | DLL | 方法数 | 用途 |
|----|-----|--------|------|
| CVsModule | VsMVO | 409 | 模块/对象/变量/回调枢纽 |
| CVsView | VsMVO | 242 | 视图/相机/拾取/场景根 (`GetSceneKey`) |
| CVsVolumePool / CVsVolume | VsMVO | 178/75 | 体渲染 |
| CAnimation | VsMVO | 153 | 动画 |
| CVsVariable | VsMVO | 128 | 变量系统 |
| CVsParticle | VsMVO | 109 | 粒子 |
| CVsButton / CVsImage / CVsPopMenu | VsMVO | 103/83/95 | UI 对象（HTTP 层只暴露了部分字段） |
| CChartObject | VsMVO | 94 | 图表 |
| CMvoObject | VsMVO | 93 | 场景对象基类 |
| CVsEdit | VsMVO | 85 | 编辑操作 |
| CRgComplexObject | RelaGraph | 83 | 行为图复合对象（含 Pick） |
| CTEventController / CVsProgram | VsMVO | 79/78 | 事件/程序 |
| 55 个 `COp*` 类 | VsMVO | — | 编辑器交互操作全集（创建图元/灯光/探针、拖拽、裁剪、布局…） |

---

## 五、已知限制与方法说明

1. 解析数略低于 dumpbin 总数（8,540 vs 8,564 等）：正则未匹配个别长名/数据导出行，对结论无影响。
2. C++ 方法名提取自反修饰签名的简单解析，部分构造/析构/运算符仍为修饰形式；v1 可在桥接库选型时逐类精化。
3. 1,327 个脚本函数无同名原生导出——多为 DSL 运行时由解释器内部实现或经 `CVsModule`/`CVsProgram` 入口分发，不代表不可用。
4. `pe*` 与 3dgs `Vs*` 数学函数为 C 导出可直接 GetProcAddress；VsMVO C++ 类导出为修饰符号，须配合 PESdk 头文件（MvoCore/ObjectCore 等）链接或运行时按修饰名解析（PEAgentNative.cpp 已有运行时解析先例）。

---

## 六、桥接库建设优先级建议

| 级 | 内容 | 通路 |
|----|------|------|
| P0 | 场景树快照（DSL 树遍历 + VsShowFieldName 修正 + 文件回传） | 纯 DSL，已打通，零 C++ |
| P0 | 相机读写封装（camGetCamera 读 + VsSetCameraTarget 写） | 纯 DSL |
| P1 | 变换写入（peSetTransformByKey 签名探针 + 旋转） | 原生 pe*（PEAgentNative 或 PEHelloMCP 加路由） |
| P1 | 拾取服务（CVsView.GetPickedKey/Point → HTTP） | 原生 C++（需 SDK 头） |
| P2 | 几何插入（peInsertMesh/Sphere/Cube → 程序化建模） | 原生 pe* |
| P2 | COp* 交互操作编排（录制编辑器动作） | 原生 C++，远期 |

## obj_delete (2026-09-17)
- Pipe: `obj_delete` / `button_delete` via PEAgentNative
- Tree-first: `FxPluginMgr_RunNameCmd(ProjectMgr, DeleteUIObject)` → `funcDeleteUIObject` Release RVA `0xC1810`
- MVO: `CVsModule::FindObject` RVA `0x2D1950` + `DeleteObject(CMvoObject*)` RVA `0x2D3DB0`
- See `data/exports/obj_delete/README.md`
