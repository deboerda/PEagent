# PEAgent v0.6 — 脚本桥（Script Bridge）落地记录

> 日期: 2026-09-14 ｜ 引擎实测环境: PostEngineer Release-x64 + PEHelloMCP.plu + MVP.peproj

## 一、本次交付

| 模块 | 内容 |
|------|------|
| `pe_client/script_bridge.py`（新） | DSL program 模式执行器：`run_script`（函数体 + `__OUT__` 占位 + 文件回传解析）、`camera_get`、`node_set_position`、`node_move`、`node_set_rotation_reset` |
| `pe_client/client.py` | 新增域通用 `get_effect` / `set_effect`（覆盖 node_effect / appearance 域，强制 target 校验）；修复端口文件 GBK UnicodeDecodeError；修复 tasklist 输出解码 |
| `mcpServer.py` | 20 → **27 个 MCP tools**，新增：`pe_camera_get`、`pe_bridge_run_script`、`pe_node_set_position`、`pe_node_move`、`pe_get_effect`、`pe_set_effect`、`pe_light_probe` |
| `pe_cli.py` | 新增 `pe camera`（读相机）、`pe run <file>`（脚本桥执行 DSL 文件） |

**验证状态**：MCP stdio 实调 `pe_camera_get` 返回引擎真实相机数据 ✅；`pe run` 端到端回传 ✅；`pe camera` ✅；`get_effect('阴影')` 正确要求 target、`get_effect('fog')` 返回状态 ✅。

## 二、DSL 实测约束（写桥接代码前必读，全部用引擎崩溃/静默失败换来的）

**可用（实测 ✅）**
- program 模式单次提交 `void fn(){...} fn();`；load 模式只加载不执行；**函数定义跨 execute 不持久**
- `for(i = 0; i < n; i = i + 1){...}` C 风格循环；字符串 `+` 拼接
- `valuesToString(float array, count, string &s)` 数值→文本（唯一可靠的数值输出路径）
- 数组元素读写 `keys[i]`；`getChildrenKeys(key, arr)` 手工索引读子节点
- `camGetCamera(vport, cam[16])` 相机读取（前 9 值 = eye/target/up）
- 文本写文件 `fileWriteLine(fp, str)`；**`fileWrite(fp, int/float)` 是二进制写入**

**禁用（实测 💥）**
- `VsShowFieldPathName` 等 **char\* 出参的 Vs\* 函数 → 引擎直接崩溃退出**
- `camSetCamera(vport, 0, ...9 参数)` 全参数写相机 → 相机状态永久置零（只能重启引擎恢复）
- `VsSetCameraTarget` → 静默失败（脚本中断，无文件产出）
- `VsSearchContents` / `getBoxByKey` 的 **int/float 标量引用出参 → 不可靠**（count 返回 0 / 静默中断）
- `getArraySize` 对填充后的 dword 数组 → 返回 0（容量而非长度），**子节点数量不可知**
- 读数组越界元素（超过 getChildrenKeys 实填数量）→ 脚本静默中断

**推论**：纯 DSL 无法安全枚举场景树（无可靠 count）。场景树快照定为 **P1：在 PEHelloMCP 加 `/api/scene/children` 原生路由**（VS DTE + devenv 链路，CVsView/CVsModule 已有全部所需方法）。

## 三、意外收获

插件二进制 strings 发现 9 条未在技术总结中记录的路由：`/api/graph/{create,create_native,read,save,register,remove,build_boot,node/create,node/delete}`（行为图管理，`pe_client.graph_*` 封装已存在）。

## 四、下一步（P1 排期建议）

1. `/api/scene/children` + `/api/scene/tree` 原生路由（解场景树，P0 级价值）
2. `peSetTransformByKey` 签名探针（3dgs pe* 家族 114 个 C 导出，解锁精确旋转）
3. 拾取服务（`CVsView.GetPickedKey/GetPickedPoint` → HTTP）
4. `/api/output/query` 修复（当前找的是 PEPlayer 窗口；CLI 侧 `pe console` 已可用 a11y 兜底）
5. 插件 partial-config 创建对象崩溃加固（curl 直发缺字段 payload 曾致引擎崩溃）
