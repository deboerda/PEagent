"""PE Client — 共享客户端库

PE CLI 和 MCP Server 的共同依赖。
提供 PE 引擎 HTTP API 的类型安全封装。

用法:
    from pe_client import (
        client, registry, resolver, models,
        list_types, get_template, create_object, list_objects, modify_object,
        get_output, get_status,
        list_capabilities, get_capability_template,
        get_scene_effect, set_scene_effect, set_scene_effects,
        capture_frame,
    )
"""

from __future__ import annotations

from typing import Any

from . import models, registry, resolver
from .client import (
    # 底层 HTTP
    engine_status,
    engine_health,
    obj_create,
    obj_query,
    obj_modify,
    output_query,
    effect_query,
    effect_apply,
    frame_capture as _frame_capture_raw,
    light_probe,
    # 脚本
    script_execute,
    script_execute_file,
    script_validate,
    # 行为图
    graph_create,
    graph_build_boot,
    graph_register,
    graph_read,
    graph_node_create,
    # 调试播放器
    debug_start,
    debug_stop,
    # 自动发现
    discover_engine_url,
    get_engine_url,
    reset_engine_url,
    write_port_file,
    # 组合 API
    create_object,
    list_objects,
    modify_object,
    get_scene_effect,
    set_scene_effect,
    capture_frame,
    _normalize_pe_result,
    _normalize_frame_result,
    _post_json,
)
from .native_flow import native_script_flow
from .script_project import prepare_project_script, render_script
from .script_bridge import (
    run_script as bridge_run_script,
    camera_get,
    node_set_position,
    node_move,
    node_set_rotation_reset,
    scene_children_dsl,
)
from . import native_pipe
from . import peo_index
from .registry import (
    OBJECT_REGISTRY,
    PE_REGISTRY,
    PE_DOMAIN_ALIASES,
    DOMAIN_LABELS,
)
from .resolver import (
    resolve_obj_type,
    resolve_capability,
    resolve_domain,
    resolve_capability_for_domains,
    validate_partial,
    validate_full,
    build_model_template,
    build_query_input,
    require_node_path,
)
from .script_search import (
    search_functions,
    get_function,
    get_module_index,
    get_module_functions,
    get_functions,
)


# ── 便利函数 ──────────────────────────────────────────────


def list_types() -> dict:
    """列出所有对象类型（轻量）"""
    object_types = {}
    for key, reg in OBJECT_REGISTRY.items():
        object_types[key] = {
            "description": reg["description"],
            "aliases": reg.get("aliases", []),
        }
    return {"success": True, "object_types": object_types}


def get_template(obj_type: str) -> dict:
    """获取某类型的字段模板"""
    resolved = resolve_obj_type(obj_type)
    if not resolved:
        return {"success": False, "error": f"未知对象类型: {obj_type}"}

    result = build_model_template(OBJECT_REGISTRY[resolved]["data_model"])
    return {"success": True, "obj_type": resolved, **result}


def get_output(limit: int = 0) -> dict:
    """读取引擎输出"""
    if limit < 0:
        return {
            "success": False, "available": False, "peplayer_running": False,
            "line_count": 0, "returned_count": 0, "lines": [], "text": "",
            "error": "limit must be >= 0",
        }
    return output_query(limit)


def get_status() -> dict:
    """查询引擎状态"""
    return engine_status()


def list_capabilities(domain: str = "") -> dict:
    """列出 PE capabilities"""
    resolved_domain = resolve_domain(domain)
    if domain and not resolved_domain:
        return {"success": False, "error": f"未知 PE domain: {domain}"}

    capabilities = {}
    for key, reg in PE_REGISTRY.items():
        if resolved_domain and reg["domain"] != resolved_domain:
            continue
        capabilities[key] = {
            "domain": reg["domain"],
            "description": reg["description"],
            "aliases": reg.get("aliases", []),
            "target_kind": reg["target_kind"],
            "supports_get": reg["supports_get"],
            "supports_set": reg["supports_set"],
            "operations": reg.get("operations", ["get", "set"]),
        }
    return {"success": True, "capabilities": capabilities}


def get_capability_template(capability: str, operation: str = "set") -> dict:
    """获取 PE capability 的参数模板"""
    resolved = resolve_capability(capability)
    if not resolved:
        return {"success": False, "error": f"未知 PE capability: {capability}"}

    reg = PE_REGISTRY[resolved]
    normalized_operation = operation.strip().casefold()
    available_operations = reg.get("operations", ["get", "set"])
    if normalized_operation not in available_operations and normalized_operation not in {"get", "set"}:
        return {
            "success": False,
            "error": f"{resolved} 不支持 operation={operation}",
            "available_operations": available_operations,
        }

    model = None
    if normalized_operation == "set":
        model = reg.get("set_model")
    elif normalized_operation in reg.get("models", {}):
        model = reg["models"][normalized_operation]

    result = {
        "success": True,
        "capability": resolved,
        "operation": normalized_operation,
        "domain": reg["domain"],
        "description": reg["description"],
        "target_kind": reg["target_kind"],
        "supports_get": reg["supports_get"],
        "supports_set": reg["supports_set"],
        "response_keys": list(reg["response_keys"]),
    }

    if model:
        result.update(build_model_template(model))
    else:
        result["query_input"] = build_query_input(reg["target_kind"], normalized_operation)

    return result


def set_scene_effects(items: list[dict[str, Any]]) -> dict:
    """批量设置场景效果"""
    if not items:
        return {"success": False, "error": "items cannot be empty", "results": []}

    results: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        effect_name = item.get("effect_name", "")
        data = item.get("data", {})

        resolved, reg, error = resolve_capability_for_domains(effect_name, {"scene_effect"})
        if error:
            return {
                "success": False, "error": error["error"],
                "failed_index": index, "failed_effect_name": effect_name,
                "results": results,
            }

        changes, validation_error = validate_partial(reg["set_model"], data)
        if validation_error:
            return {
                "success": False, "error": validation_error["error"],
                "failed_index": index, "failed_effect_name": resolved or effect_name,
                "results": results,
            }

        raw_result = effect_apply(reg["domain"], reg["engine_effect_name"], "", changes or {})
        normalized = _normalize_pe_result(raw_result, resolved or effect_name, "")
        results.append(normalized)

        if not normalized.get("success"):
            return {
                "success": False, "error": normalized.get("error", "batch apply failed"),
                "failed_index": index, "failed_effect_name": resolved or effect_name,
                "results": results,
            }

    return {"success": True, "results": results, "count": len(results),
            "message": "scene effects batch applied"}
