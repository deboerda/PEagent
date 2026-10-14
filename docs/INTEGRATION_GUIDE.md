# PEHelloMCP 新增脚本执行路由 — 集成指南

## 概述

新增 3 个 HTTP API 路由，对应 PE 引擎的脚本执行能力：

| 路由 | 方法 | 对应 PE API | 用途 |
|------|------|------------|------|
| `/api/script/execute` | POST | `executeScript(str)` | 执行脚本字符串 |
| `/api/script/execute_file` | POST | `executeScriptFile(filename)` | 执行脚本文件 |
| `/api/script/validate` | POST | `loadScript(filename)` | 验证脚本语法 |

## 需要改动的文件

### 1. `HelloMCPCommon.h` — 添加 3 个 EngineAction 枚举值

在 `EngineAction` 枚举中新增：

```cpp
// 在现有枚举值后面添加：
ScriptExecute,       // 执行脚本字符串
ScriptExecuteFile,   // 执行脚本文件
ScriptValidate,      // 验证脚本语法
```

同时更新 `EngineActionName()` 函数，添加对应的名称映射：

```cpp
// 在 switch/if-else 中新增：
case EngineAction::ScriptExecute:       return "script_execute";
case EngineAction::ScriptExecuteFile:   return "script_execute_file";
case EngineAction::ScriptValidate:      return "script_validate";
```

### 2. `HelloMCPEngineExecutor.h` / `HelloMCPEngineExecutor.cpp` — 添加脚本执行处理

在引擎执行器（`EnqueueAndWait` 的实现函数）中，添加对 `ScriptExecute`、`ScriptExecuteFile`、`ScriptValidate` 的处理分支。

参考现有的 `SceneEffectQuery`/`SceneEffectApply` 处理模式，新增：

```cpp
// 在 EnqueueAndWait 的实现中，action 分发处新增：
case EngineAction::ScriptExecute:
case EngineAction::ScriptExecuteFile:
case EngineAction::ScriptValidate: {
    ScriptExecuteService service;
    response = service.ProcessScriptAction(actionName, payload);
    break;
}
```

### 3. `HelloMCP.cpp`（或主路由注册文件）— 注册 3 个新路由

在 CivetWeb 服务器路由注册处新增：

```cpp
// 照着现有路由的注册方式添加：
server.addHandler("/api/script/execute",       new ActionHandler(EngineAction::ScriptExecute));
server.addHandler("/api/script/execute_file",  new ActionHandler(EngineAction::ScriptExecuteFile));
server.addHandler("/api/script/validate",      new ActionHandler(EngineAction::ScriptValidate));
```

### 4. `PEHelloMCP.vcxproj` — 添加新头文件

在 `<ItemGroup>` 的 `<ClInclude>` 列表中添加：

```xml
<ClInclude Include="HelloMCPScript.h" />
```

### 5. 新增文件：`HelloMCPScript.h`（已写好，放在同目录）

包含 `ScriptExecuteService` 类的完整实现（header-only，照着 `HelloMCPSceneEffects.h` 的模式）。

## API 请求/响应格式

### POST /api/script/execute

请求：
```json
{
    "script": "module demo\nbegin\n    VsInsertSphere(0.0, 0.0, 0.0, 1.0, 32, [1.0, 0.0, 0.0])\nend\n",
    "script_name": "create_red_sphere"
}
```

响应（成功）：
```json
{
    "success": true,
    "action": "script_execute",
    "message": "script executed successfully",
    "script_name": "create_red_sphere",
    "script_length": 85
}
```

响应（失败）：
```json
{
    "success": false,
    "action": "script_execute",
    "message": "script execution failed",
    "error": "PE engine executeScript() returned false",
    "error_code": "engine_execute_failed",
    "script_name": "create_red_sphere",
    "script_length": 85
}
```

### POST /api/script/execute_file

请求：
```json
{
    "filename": "D:\\scripts\\demo.scr"
}
```

### POST /api/script/validate

请求：
```json
{
    "script": "module demo\nbegin\n    VsInsertSphere(0.0, 0.0, 0.0, 1.0, 32)\nend\n"
}
```

响应（成功）：
```json
{
    "success": true,
    "action": "script_validate",
    "message": "script is valid",
    "script_length": 72
}
```

## 依赖的 PE API

以下 3 个函数已在 PE 引擎的 ScriptReader.dll 中导出，无需额外链接：

| 函数 | 签名 | 来源 |
|------|------|------|
| `executeScript` | `bool(const char* strScript)` | ScriptReader.dll |
| `executeScriptFile` | `bool(const char* filename)` | ScriptReader.dll |
| `loadScript` | `bool(const char* filename)` | ScriptReader.dll |

## 验证方法

编译部署后，用 curl 验证：

```bash
# 1. 健康检查
curl http://127.0.0.1:8080/api/health

# 2. 执行简单脚本
curl -X POST http://127.0.0.1:8080/api/script/execute \
  -H "Content-Type: application/json" \
  -d '{"script":"module test\nbegin\nend\n"}'

# 3. 验证脚本
curl -X POST http://127.0.0.1:8080/api/script/validate \
  -H "Content-Type: application/json" \
  -d '{"script":"module test\nbegin\nend\n"}'
```

## 与 Python 端的对接

Python 端（`pe_client/client.py`）需要新增 2 个 HTTP 调用函数：

```python
def script_execute(script: str, script_name: str = "") -> dict:
    return _post_json("/api/script/execute", {
        "script": script,
        "script_name": script_name or "inline_script",
    })

def script_validate(script: str) -> dict:
    return _post_json("/api/script/validate", {"script": script})
```

MCP 端（`mcpServer.py`）对应的 2 个 MCP tool 已准备好，只需在 C++ 端就绪后取消注释即可激活。