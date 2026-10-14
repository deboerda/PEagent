"""PE Client — HTTP 传输层

封装与 PEHelloMCP 插件 HTTP API 的所有通信。
提供高级 API 调用函数，CLI 和 MCP 共同使用。

自动连接机制：
  1. 读取端口文件 (PEHelloMCP 启动时写入)
  2. 检测 PostEngineer.exe 进程是否在运行
  3. 自动探测已知端口
  4. 首次使用时自动连接，无需手动配置
"""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import Any

import requests

from .registry import PE_REGISTRY

# ── 自动发现 ──────────────────────────────────────────────

DEFAULT_PORT = 8080
_PORT_FILE_NAME = ".pe_mcp_port"

# 端口文件查找顺序
_PORT_FILE_PATHS = [
    # PE 引擎工作目录
    Path(os.environ.get("PE_WORK_DIR", "")) / _PORT_FILE_NAME,
    # 临时目录
    Path(os.environ.get("TEMP", "/tmp")) / _PORT_FILE_NAME,
    # 当前目录
    Path.cwd() / _PORT_FILE_NAME,
]

_engine_url: str | None = None


def _discover_port() -> int | None:
    """自动发现 PEHelloMCP 端口。

    查找顺序：
    1. 环境变量 PE_MCP_PORT
    2. 端口文件（PEHelloMCP 启动时写入）
    3. 进程检测 + 端口探测
    """
    # 1. 环境变量
    env_port = os.environ.get("PE_MCP_PORT")
    if env_port:
        try:
            return int(env_port)
        except ValueError:
            pass

    # 2. 端口文件
    for path in _PORT_FILE_PATHS:
        if path.exists():
            try:
                # 端口文件由引擎以 ANSI/GBK 写入，errors 忽略避免 UnicodeDecodeError
                return int(path.read_text(encoding="utf-8", errors="ignore").strip())
            except (ValueError, OSError):
                pass

    # 3. 进程检测 — 如果 PostEngineer.exe 在运行，用默认端口
    if _is_pe_running():
        for candidate in (DEFAULT_PORT, 18080, 8081, 8082, 8083, 8084):
            try:
                response = requests.get(f"http://127.0.0.1:{candidate}/api/health", timeout=0.35)
                data = response.json()
                if data.get("success") and data.get("service") == "PEHelloMCP":
                    return candidate
            except (requests.RequestException, ValueError):
                pass

    return None


def _is_pe_running() -> bool:
    """检测 PostEngineer.exe 进程是否在运行"""
    try:
        import subprocess
        result = subprocess.run(
            ["tasklist", "/fi", "imagename eq PostEngineer*.exe", "/nh"],
            capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=5,
        )
        return "PostEngineer.exe" in result.stdout or "PostEngineerd.exe" in result.stdout
    except Exception:
        return False


def discover_engine_url() -> str | None:
    """自动发现引擎 URL，失败返回 None"""
    port = _discover_port()
    if port:
        return f"http://127.0.0.1:{port}"
    return None


def get_engine_url() -> str:
    """获取引擎 URL，自动发现 + 缓存"""
    global _engine_url
    if _engine_url is None:
        discovered = discover_engine_url()
        if discovered:
            _engine_url = discovered
        else:
            _engine_url = f"http://127.0.0.1:{DEFAULT_PORT}"
    return _engine_url


def reset_engine_url() -> None:
    """重置缓存的 URL（下次调用重新发现）"""
    global _engine_url
    _engine_url = None


def write_port_file(port: int = DEFAULT_PORT) -> bool:
    """写入端口文件供 CLI 发现（由 PEHelloMCP 插件调用）"""
    try:
        temp_dir = Path(os.environ.get("TEMP", "/tmp"))
        port_file = temp_dir / _PORT_FILE_NAME
        port_file.write_text(str(port))
        return True
    except OSError:
        return False


# ── 配置 ──────────────────────────────────────────────────

_IDEMPOTENT_PATHS: set[str] = {
    "/api/engine/status",
    "/api/obj/query",
    "/api/output/query",
    "/api/effect/query",
    "/api/pe/light_probe/query",
}


# ── 底层 HTTP ────────────────────────────────────────────


def _post_json(path: str, payload: dict[str, Any], timeout: float = 35) -> dict:
    """发送 JSON POST 请求到 PE 引擎。

    自动处理重试（幂等路径）、超时分类、错误探活。
    """
    request_id = uuid.uuid4().hex
    started_at = time.monotonic()
    max_attempts = 2 if path in _IDEMPOTENT_PATHS else 1

    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.post(
                f"{get_engine_url()}{path}",
                json=payload,
                headers={"X-Request-ID": request_id},
                timeout=(2.0, timeout),
            )
            data = resp.json()
            if isinstance(data, dict):
                data.setdefault("success", resp.ok)
                data.setdefault("request_id", resp.headers.get("X-Request-ID", request_id))
                data["client_timing_ms"] = round((time.monotonic() - started_at) * 1000, 3)
                data["transport_attempts"] = attempt
                if not resp.ok:
                    data.setdefault("error_code", "engine_http_error")
                    data.setdefault("retryable", resp.status_code >= 500)
                return data
            return {
                "success": resp.ok,
                "data": data,
                "request_id": request_id,
                "client_timing_ms": round((time.monotonic() - started_at) * 1000, 3),
                "transport_attempts": attempt,
            }
        except requests.ConnectTimeout:
            if attempt < max_attempts:
                continue
            return _transport_error(path, request_id, started_at,
                                    "engine_connect_timeout",
                                    "timed out while connecting to PE engine",
                                    True, attempts=attempt)
        except requests.ReadTimeout:
            return _transport_error(path, request_id, started_at,
                                    "engine_response_timeout",
                                    f"PE engine did not respond within {timeout}s; command outcome is unknown",
                                    False, attempts=attempt)
        except requests.Timeout:
            return _transport_error(path, request_id, started_at,
                                    "engine_transport_timeout",
                                    f"PE engine transport timeout after {timeout}s",
                                    False, attempts=attempt)
        except requests.ConnectionError as exc:
            if attempt < max_attempts:
                continue
            return _transport_error(path, request_id, started_at,
                                    "engine_connection_error",
                                    f"cannot connect to PE engine: {exc}",
                                    True, attempts=attempt)
        except ValueError:
            response_text = resp.text if "resp" in locals() else ""
            return _transport_error(path, request_id, started_at,
                                    "engine_invalid_response",
                                    f"non-JSON response: {response_text[:200]}",
                                    False, include_probe=False, attempts=attempt)
        except Exception as exc:
            return _transport_error(path, request_id, started_at,
                                    "engine_client_error",
                                    str(exc), False, include_probe=False, attempts=attempt)

    return _transport_error(path, request_id, started_at,
                            "engine_client_error",
                            "request loop ended unexpectedly",
                            False, include_probe=False, attempts=max_attempts)


def _transport_error(
    path: str, request_id: str, started_at: float,
    error_code: str, message: str, retryable: bool,
    include_probe: bool = True, attempts: int = 1,
) -> dict:
    """构造统一的传输错误响应"""
    result = {
        "success": False,
        "error": message,
        "error_code": error_code,
        "request_id": request_id,
        "path": path,
        "retryable": retryable,
        "transport_attempts": attempts,
        "client_timing_ms": round((time.monotonic() - started_at) * 1000, 3),
    }
    if include_probe and path != "/api/engine/status":
        result["engine_status_probe"] = _probe_engine_status(request_id)
    return result


def _probe_engine_status(request_id: str) -> dict:
    """快速探活"""
    try:
        response = requests.get(
            f"{get_engine_url()}/api/health",
            headers={"X-Request-ID": f"{request_id}.probe"},
            timeout=(0.5, 1.0),
        )
        data = response.json()
        return data if isinstance(data, dict) else {"success": False, "error": "invalid status response"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _normalize_pe_result(result: dict, effect_name: str, target: str = "") -> dict:
    """标准化 PE 效果返回结果"""
    normalized = dict(result) if isinstance(result, dict) else {"success": False, "error": "invalid engine response"}
    normalized["effect_name"] = effect_name
    normalized["target"] = target
    normalized.setdefault("state", None)
    return normalized


def _normalize_frame_result(result: dict) -> dict:
    """标准化截图返回结果"""
    normalized = dict(result) if isinstance(result, dict) else {"success": False, "error": "invalid engine response"}
    normalized.setdefault("frame", None)
    if normalized["frame"] is None and normalized.get("error"):
        normalized["frame"] = {
            "success": False, "path": "", "format": "png",
            "source": "active_view", "error": normalized["error"],
        }
    return normalized


# ── 高层 API ─────────────────────────────────────────────


# --- 引擎 ---

def engine_status() -> dict:
    return _post_json("/api/engine/status", {}, timeout=3)


def engine_health() -> dict:
    try:
        resp = requests.get(f"{get_engine_url()}/api/health", timeout=2)
        return {"success": True, "status_code": resp.status_code, "body": resp.text[:500]}
    except Exception as e:
        return {"success": False, "error": str(e)}


# --- 对象 ---

def obj_create(obj_type: str, config: dict[str, Any]) -> dict:
    return _post_json("/api/obj/data", {"obj_type": obj_type, "config": config})


def obj_query(obj_type: str) -> dict:
    return _post_json("/api/obj/query", {"obj_type": obj_type})


def obj_modify(obj_type: str, name: str, changes: dict[str, Any]) -> dict:
    return _post_json("/api/obj/modify", {"obj_type": obj_type, "name": name, "changes": changes})


# --- 输出 ---

def output_query(limit: int = 0) -> dict:
    return _post_json("/api/output/query", {"limit": limit})


# --- 效果 ---

def effect_query(domain: str, effect_name: str, target: str = "") -> dict:
    return _post_json("/api/effect/query", {
        "domain": domain, "effect_name": effect_name, "target": target,
    })


def effect_apply(domain: str, effect_name: str, target: str, data: dict[str, Any]) -> dict:
    return _post_json("/api/effect/apply", {
        "domain": domain, "effect_name": effect_name, "target": target, "data": data,
    })


# --- 截图 ---

def frame_capture(label: str = "") -> dict:
    payload: dict[str, Any] = {}
    if label:
        payload["label"] = label
    return _post_json("/api/frame/capture", payload)


# --- 光照探针 ---

def light_probe(action: str, payload: dict[str, Any]) -> dict:
    return _post_json(f"/api/pe/light_probe/{action}", payload)


# ── 组合 API（封装注册表 + 校验 + HTTP 调用） ────────────


def create_object(obj_type: str, data: dict[str, Any]) -> dict:
    """创建对象：解析类型 → 全量校验 → 调用引擎"""
    from .resolver import resolve_obj_type, validate_full
    from .registry import OBJECT_REGISTRY

    resolved = resolve_obj_type(obj_type)
    if not resolved:
        return {"success": False, "error": f"未知对象类型: {obj_type}"}

    final_data, error = validate_full(OBJECT_REGISTRY[resolved]["data_model"], data)
    if error:
        return error

    return obj_create(resolved, final_data or {})


def list_objects(obj_type: str) -> dict:
    """列出对象"""
    from .resolver import resolve_obj_type
    resolved = resolve_obj_type(obj_type)
    if not resolved:
        return {"success": False, "error": f"未知对象类型: {obj_type}"}
    return obj_query(resolved)


def modify_object(obj_type: str, name: str, data: dict[str, Any]) -> dict:
    """修改对象：解析类型 → partial 校验 → 调用引擎"""
    from .resolver import resolve_obj_type
    from .registry import OBJECT_REGISTRY
    from pydantic import ValidationError

    resolved = resolve_obj_type(obj_type)
    if not resolved:
        return {"success": False, "error": f"未知对象类型: {obj_type}"}
    if not name:
        return {"success": False, "error": "name 不能为空"}

    try:
        validated = OBJECT_REGISTRY[resolved]["data_model"].model_validate(data)
        changes = validated.model_dump(exclude={"name"}, exclude_unset=True)
    except ValidationError as exc:
        return {"success": False, "error": f"data 格式错误: {exc}"}

    if not changes:
        return {"success": False, "error": "没有需要修改的属性"}

    return obj_modify(resolved, name, changes)


def get_scene_effect(effect_name: str) -> dict:
    """查询场景级效果"""
    from .resolver import resolve_capability
    resolved = resolve_capability(effect_name)
    if not resolved:
        return {"success": False, "error": f"未知 PE capability: {effect_name}"}

    reg = PE_REGISTRY[resolved]
    result = effect_query(reg["domain"], reg["engine_effect_name"], "")
    return _normalize_pe_result(result, resolved, "")


def set_scene_effect(effect_name: str, data: dict[str, Any]) -> dict:
    """设置场景级效果（partial update）"""
    from .resolver import resolve_capability, validate_partial
    resolved = resolve_capability(effect_name)
    if not resolved:
        return {"success": False, "error": f"未知 PE capability: {effect_name}"}

    reg = PE_REGISTRY[resolved]
    changes, validation_error = validate_partial(reg["set_model"], data)
    if validation_error:
        return validation_error

    result = effect_apply(reg["domain"], reg["engine_effect_name"], "", changes or {})
    return _normalize_pe_result(result, resolved, "")


def get_effect(effect_name: str, domain: str = "", target: str = "") -> dict:
    """按域查询效果状态（scene_effect / node_effect / appearance 通用）。

    node_effect / appearance 域必须提供 target（节点路径）。
    """
    from .resolver import resolve_capability
    resolved = resolve_capability(effect_name)
    if not resolved:
        return {"success": False, "error": f"未知 PE capability: {effect_name}"}

    reg = PE_REGISTRY[resolved]
    use_domain = domain or reg["domain"]
    if use_domain in ("node_effect", "appearance") and not target:
        return {"success": False,
                "error": f"{use_domain} 域需要提供 target（节点路径）"}

    result = effect_query(use_domain, reg["engine_effect_name"], target)
    return _normalize_pe_result(result, resolved, target)


def set_effect(effect_name: str, data: dict[str, Any], domain: str = "",
               target: str = "") -> dict:
    """按域设置效果（partial update）。node_effect / appearance 需提供 target。"""
    from .resolver import resolve_capability, validate_partial
    resolved = resolve_capability(effect_name)
    if not resolved:
        return {"success": False, "error": f"未知 PE capability: {effect_name}"}

    reg = PE_REGISTRY[resolved]
    use_domain = domain or reg["domain"]
    if use_domain in ("node_effect", "appearance") and not target:
        return {"success": False,
                "error": f"{use_domain} 域需要提供 target（节点路径）"}

    changes, validation_error = validate_partial(reg["set_model"], data)
    if validation_error:
        return validation_error

    result = effect_apply(use_domain, reg["engine_effect_name"], target, changes or {})
    return _normalize_pe_result(result, resolved, target)


def capture_frame(label: str = "") -> dict:
    """截图并标准化结果"""
    result = frame_capture(label)
    return _normalize_frame_result(result)


# --- 脚本 ---

def script_execute(script: str, script_name: str = "", execution_mode: str = "load") -> dict:
    """执行 PE 脚本字符串"""
    return _post_json("/api/script/execute", {
        "script": script,
        "script_name": script_name or "inline_script",
        "execution_mode": execution_mode or "load",
    })


def script_execute_file(filename: str) -> dict:
    """执行 PE 脚本文件"""
    return _post_json("/api/script/execute_file", {
        "filename": filename,
    })


def script_validate(script: str) -> dict:
    """验证 PE 脚本语法"""
    return _post_json("/api/script/validate", {"script": script})


# --- 行为图 ---

def graph_create(name: str, filename: str) -> dict:
    """通过 PE RelaGraph 创建行为图并注册到当前项目。"""
    return _post_json("/api/graph/create", {"name": name, "filename": filename})


def graph_build_boot(name: str, filename: str, include_file: str = "main\\Script\\include.script") -> dict:
    """用已验证的 RelaGraph 适配器创建 boot 图，并原生注册到当前项目。"""
    return _post_json("/api/graph/build_boot", {
        "name": name, "filename": filename, "include_file": include_file,
    })


def graph_register(name: str, filename: str) -> dict:
    """Register an existing native .rg in the current PE project without rewriting it."""
    return _post_json("/api/graph/register", {
        "name": name, "filename": filename,
    })


def graph_read(filename: str) -> dict:
    """使用 PE RelaGraph 解析并验证行为图。"""
    return _post_json("/api/graph/read", {"filename": filename})


def graph_node_create(filename: str, node_type: str, name: str, x: int = 0, y: int = 0) -> dict:
    """Create and persist a node through PE's native RelaGraph editor context."""
    return _post_json("/api/graph/node/create", {
        "filename": filename, "type": node_type, "name": name, "x": x, "y": y,
    })


# --- 调试启动 ---

def debug_start() -> dict:
    """启动调试 — 创建 PEDATA，启动 PEPlayer"""
    return _post_json("/api/debug/start", {})


def debug_stop() -> dict:
    """停止调试 — 关闭 PEPlayer，释放 PEDATA"""
    return _post_json("/api/debug/stop", {})
