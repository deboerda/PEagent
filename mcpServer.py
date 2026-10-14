"""PE MCP Server — 引擎对象工具 + PE 效果工具

基于 pe_client 共享库，通过 FastMCP 暴露为 MCP tools。
所有业务逻辑（HTTP 调用、校验、注册表）在 pe_client 中。
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from pe_client import (
    list_types,
    get_template,
    create_object,
    list_objects,
    modify_object,
    get_output,
    get_status,
    list_capabilities,
    get_capability_template,
    get_scene_effect,
    set_scene_effect,
    set_scene_effects,
    capture_frame,
    models,
    registry,
    resolver,
    client,
    search_functions,
    get_function,
    get_module_index,
    get_module_functions,
    get_functions,
    prepare_project_script,
    camera_get,
    node_set_position,
    node_move,
    bridge_run_script,
)

mcp = FastMCP("pe-engine")

# ======================================================================
# 对象 MCP Tools
# ======================================================================


@mcp.tool(
    description=(
        "【第1步】列出所有可用的引擎对象类型及描述。"
        "返回精简列表（类型名 + 一句话描述），不包含字段详情。"
        "需要了解某类型的详细字段时，请调用 engine_get_template。"
    )
)
def engine_list_types() -> dict:
    return list_types()


@mcp.tool(
    description=(
        "【第2步】获取指定对象类型的字段模板。"
        "返回所有字段名、类型、默认值、描述。"
        "创建对象前应先调用此工具了解有哪些可填字段及其默认值。"
        "也支持传入中文别名（如 '按钮'）作为 obj_type。"
    )
)
def engine_get_template(obj_type: str) -> dict:
    return get_template(obj_type)


@mcp.tool(
    description=(
        "【第3步】创建引擎对象。"
        "请按照 engine_get_template 返回的模板填写 data 字典。"
        "重要规则：\n"
        "1. name 在引擎中唯一，重名会创建失败（引擎返回错误）\n"
        "2. 不确定的字段不要猜测，使用默认值或留空\n"
        "3. 路径类字段（node_path, path_normal 等）留空表示不设置，不要编造路径\n"
    )
)
def engine_create_object(obj_type: str, data: dict[str, Any]) -> dict:
    return create_object(obj_type, data)


@mcp.tool(
    description=(
        "按对象类型导出该类型全部对象，并返回导出的 JSON 文件路径。"
        "必须指定 obj_type（和 create 一致）。"
        "返回结果包含 file_path 和 count，AI 可按路径继续读取对象详情。"
    )
)
def engine_list_objects(obj_type: str) -> dict:
    return list_objects(obj_type)


@mcp.tool(
    description=(
        "读取 PostEngineer 输出窗口中的引擎输出。"
        "重要限制：只有当 PEPlayer 顶层窗口没有运行时，这些输出才可读取。"
        "limit=0 表示返回全部输出；limit>0 表示只返回最近 limit 条。"
    )
)
def engine_get_output(limit: int = 0) -> dict:
    return get_output(limit)


@mcp.tool(
    description=(
        "查询 PE HTTP 服务、活动引擎视图、命令队列和最近一次 Tick 状态。"
        "当其他引擎工具连接失败或超时时，应先调用此工具区分服务器未启动和引擎视图不可用。"
    )
)
def engine_get_status() -> dict:
    return get_status()


@mcp.tool(
    description=(
        "修改引擎中已有对象的属性。"
        "obj_type 和 name 必填：obj_type 和 create 一致，"
        "name 必须是查询到的名字（不能修改名字本身）。"
        "data 字典只包含要修改的属性，未列出的属性保持不变。"
        "修改前请先用 engine_list_objects 确认对象存在。"
    )
)
def engine_modify_object(obj_type: str, name: str, data: dict[str, Any]) -> dict:
    return modify_object(obj_type, name, data)


# ======================================================================
# PE MCP Tools
# ======================================================================


@mcp.tool(
    description=(
        "【PE 第1步】列出所有可用的 PE capability。"
        "domain 可选：scene_effect / node_effect / appearance / light_probe。"
        "拿到 capability 名称后，再调用 pe_get_template 查看参数模板。"
    )
)
def pe_list_capabilities(domain: str = "") -> dict:
    return list_capabilities(domain)


@mcp.tool(
    description=(
        "【PE 第2步】获取 PE capability 的参数模板。"
        "普通效果默认 operation='set'；"
        "light_probe 支持 create / list / get / modify / delete / render。"
    )
)
def pe_get_template(capability: str, operation: str = "set") -> dict:
    return get_capability_template(capability, operation)


@mcp.tool(
    description=(
        "【PE 第3步】查询场景级效果状态。"
        "effect_name 必须是 scene_effect 域的 capability。"
        "建议先用 pe_list_capabilities 或 pe_get_template 确认 capability 名称。"
    )
)
def pe_get_scene_effect(effect_name: str) -> dict:
    return get_scene_effect(effect_name)


@mcp.tool(
    description=(
        "【PE 第4步】设置场景级效果。"
        "effect_name 必须是 scene_effect 域的 capability。"
        "data 只传要修改的字段，MCP 会按 partial-update 语义校验。"
    )
)
def pe_set_scene_effect(effect_name: str, data: dict[str, Any]) -> dict:
    return set_scene_effect(effect_name, data)


@mcp.tool(
    description=(
        "截图当前活动渲染画面。"
        "用于在多次调参之后单独请求一张当前画面，而不是每一步都返回截图。"
    )
)
def pe_capture_current_frame(label: str = "") -> dict:
    return capture_frame(label)


@mcp.tool(
    description=(
        "批量设置多个 scene_effect。"
        "每个 item 包含 effect_name 和 data。"
        "该工具只负责批量调参，不会自动截图；如需画面请单独调用 pe_capture_current_frame。"
    )
)
def pe_set_scene_effects(items: list[models.SceneEffectBatchItem]) -> dict:
    return set_scene_effects([item.model_dump() for item in items])


# ======================================================================
# 通用效果工具（覆盖 node_effect / appearance 域）
# ======================================================================


@mcp.tool(
    description=(
        "按域查询效果状态，支持 scene_effect / node_effect / appearance 域。"
        "scene_effect 域（雾/阳光/AO 等）target 留空；"
        "node_effect 域（阴影/节点SSR/镜面）和 appearance 域（材质/纹理）"
        "必须提供 target（节点路径）。"
        "effect_name 可用中文别名（如 '阴影'、'材质'）。"
    )
)
def pe_get_effect(effect_name: str, domain: str = "", target: str = "") -> dict:
    return client.get_effect(effect_name, domain=domain, target=target)


@mcp.tool(
    description=(
        "按域设置效果状态（partial update，只传要改的字段）。"
        "支持 scene_effect / node_effect / appearance 域。"
        "node_effect 和 appearance 域必须提供 target（节点路径）。"
        "建议先用 pe_get_template 确认字段，再调用本工具。"
    )
)
def pe_set_effect(effect_name: str, data: dict[str, Any],
                  domain: str = "", target: str = "") -> dict:
    return client.set_effect(effect_name, data, domain=domain, target=target)


# ======================================================================
# 光照探针工具（C++ 路由已实现）
# ======================================================================


@mcp.tool(
    description=(
        "光照探针生命周期管理。"
        "action 可选：create / list / get / modify / delete / render。"
        "create/modify 需要 payload（字段见 pe_get_template('light_probe', operation=action)）；"
        "list 无需 payload；get/delete/render 需要 payload 中的 name。"
    )
)
def pe_light_probe(action: str, payload: dict[str, Any] | None = None) -> dict:
    action = action.lower().strip()
    if action not in ("create", "list", "get", "modify", "delete", "render"):
        return {"success": False,
                "error": f"未知 action: {action}，可选 create/list/get/modify/delete/render"}
    return client.light_probe(action, payload or {})


# ======================================================================
# 脚本桥工具（program 模式 + 文件回传，实测验证）
# ======================================================================


@mcp.tool(
    description=(
        "【相机读取】读取指定视口的相机参数，返回 eye/target/up 坐标和原始 12 值。"
        "vport 默认 'main'。用于截图对照、场景定位、自动化前后的状态记录。"
        "注意：相机写入当前不可靠（camSetCamera 会破坏相机状态），本工具只读。"
    )
)
def pe_camera_get(vport: str = "main") -> dict:
    return camera_get(vport)


@mcp.tool(
    description=(
        "【节点变换】按场路径设置节点位置 setPosition(path, x, y, z)。"
        "path 是场对象路径（可通过脚本 getFieldPath 或已有对象查询获得）。"
        "执行后无异常即生效；DSL 无精确旋转接口，旋转请用 pe_bridge_run_script "
        "调用 resetFieldRotation 或等待原生通路。"
    )
)
def pe_node_set_position(path: str, x: float, y: float, z: float) -> dict:
    return node_set_position(path, x, y, z)


@mcp.tool(
    description=(
        "【节点变换】按场路径增量移动节点 moveField(path, dx, dy, dz)。"
        "适合相对位移（如动画预演、对位微调）。"
    )
)
def pe_node_move(path: str, dx: float, dy: float, dz: float) -> dict:
    return node_move(path, dx, dy, dz)


@mcp.tool(
    description=(
        "【场景树·单层枚举】列出模块模型根（或指定模块）下一层的子节点名。"
        "module 默认 'main'。已知限制：DSL 层无法测子节点精确数量，"
        "返回列表尾部可能含垃圾占位条目（unknown+数字）；不要用于深层遍历"
        "（嵌套枚举曾实测挂起引擎）。节点操作请用 pe_field_* 系列工具。"
    )
)
def pe_scene_children(module: str = "", cap: int = 32) -> dict:
    from pe_client.script_bridge import scene_children_dsl
    return scene_children_dsl(module, cap=cap)


@mcp.tool(
    description=(
        "【场景树·原生查询】查询节点信息：key -> name + 完整路径。"
        "key 是引擎原生 i64 key（十进制字符串），可从 pe_field_create 返回或"
        "pe_field_key 由路径反查获得。"
    )
)
def pe_field_info(key: str) -> dict:
    from pe_client import native_pipe
    return native_pipe.field_info(key)


@mcp.tool(
    description=(
        "【场景树·原生查询】路径 -> key。路径形如 /scene/modules/main/model/main。"
    )
)
def pe_field_key(path: str) -> dict:
    from pe_client import native_pipe
    return native_pipe.field_key(path)


@mcp.tool(
    description=(
        "【场景树·原生创建】创建子场节点。father 留空则挂在模块模型根下；"
        "也可传父节点 i64 key（十进制）。返回新节点 key。"
        "可配合 pe_field_rename / pe_field_info 使用。"
    )
)
def pe_field_create(name: str, father: str = "") -> dict:
    from pe_client import native_pipe
    return native_pipe.field_create(name, father=father)


@mcp.tool(
    description=("【场景树·原生修改】按 key 重命名场节点。")
)
def pe_field_rename(key: str, name: str) -> dict:
    from pe_client import native_pipe
    return native_pipe.field_rename(key, name)


@mcp.tool(
    description=("【引擎】读取场景根 key 和 PEAgentNative 原生桥状态。")
)
def pe_scene_key() -> dict:
    from pe_client import native_pipe
    return native_pipe.scene_key()


@mcp.tool(
    description=(
        "【截图】抓取 PostEngineer 主窗口完整画面（PrintWindow，后台可用、"
        "不受其他窗口遮挡影响），返回 PNG 路径和尺寸。"
        "比 /api/frame/capture 的 253x253 裁剪画面可靠得多。"
        "窗口最小化时内容可能不完整，建议保持窗口还原状态。"
    )
)
def pe_snapshot(name: str = "snap") -> dict:
    from pe_client import scene_tools
    return scene_tools.snapshot(name)


@mcp.tool(
    description=(
        "【控制台】直读 PE 底部控制台（Win32 控件方式，绕过失效的"
        " /api/output/query）。channel 可选 auto/info/debug/output。"
        "脚本执行失败时用本工具查看引擎报错详情。"
    )
)
def pe_console_read(limit: int = 20, channel: str = "auto") -> dict:
    from pe_client import scene_tools
    return scene_tools.console_read(limit=limit, channel=channel)


@mcp.tool(
    description=(
        "【相机】切换到工程中指定名称的相机（applyCamera 机制，工程验证安全）。"
        "相机名如 '相机_初始化视角'。比 camSetCamera 安全（后者会损坏相机状态）。"
    )
)
def pe_apply_camera(camera_name: str) -> dict:
    from pe_client import scene_tools
    return scene_tools.apply_camera(camera_name)


@mcp.tool(
    description=(
        "【场景树·原生删除】按完整路径删除场节点。"
        "实验性：命令返回成功但删除可能延迟到工程重载才生效（VsDeleteField "
        "第二参数语义未文档化）。路径形如 /scene/modules/main/model/.../节点名。"
    )
)
def pe_field_delete(path: str) -> dict:
    from pe_client import native_pipe
    return native_pipe.field_delete(path)

@mcp.tool(
    description=(
        "删除 ProjectMgr/MVO UI 对象（真实对象销毁，不是 field_delete）。"
        "通过 PEAgentNative 命名管道调用 CVsModule::FindObject + DeleteObject。"
        "obj_type 默认 button（MVO_OBJ_TYPE_BUT=4）；name 为对象名如 按钮_1（GBK）。"
        "成功后 /api/obj/query 不再列出该对象；scene field_key 变为 -1。"
        "ProjectMgr 工程树节点可能需刷新/保存才消失（DeleteUIObject 尚未接线）。"
        "可选 field_path 同时调用 VsDeleteField。"
    )
)
def pe_obj_delete(name: str, obj_type: str = "button", field_path: str = "") -> dict:
    from pe_client import native_pipe
    return native_pipe.obj_delete(name=name, obj_type=obj_type, field_path=field_path)


@mcp.tool(
    description="pe_obj_delete 的按钮别名：删除名为 name 的 button 对象。"
)
def pe_button_delete(name: str, field_path: str = "") -> dict:
    from pe_client import native_pipe
    return native_pipe.button_delete(name=name, field_path=field_path)



@mcp.tool(
    description=(
        "【脚本桥】执行一段 PE DSL 函数体并通过文件回传结果。\n"
        "函数体中用 __OUT__ 占位回传文件路径（不要自己写 fileOpen 路径）。\n"
        "实测可用的 DSL 惯用法：\n"
        "1. 输出文本：fileWriteLine(fp, \"前缀:\" + 字符串变量)\n"
        "2. 数值转字符串：float f[1]; f[0]=数值; string s=\"\"; "
        "valuesToString(f, 1, s);（fileWrite 直接写数值是二进制！）\n"
        "3. 循环：for(i = 0; i < n; i = i + 1){...}\n"
        "硬性禁令：不得调用 char* 出参的 Vs* 函数（如 VsShowFieldPathName）"
        "——会使引擎崩溃；不得调用 camSetCamera 写相机；"
        "不得调用 VsSearchFieldByKey（崩引擎进程）。\n"
        "脚本错误不出现在 HTTP 返回中，无回传文件即代表运行时失败，"
        "可用 `pe console` 或 MCP 读取 PE 底部控制台排查。"
    )
)
def pe_bridge_run_script(body: str, name: str = "agent") -> dict:
    return bridge_run_script(body, name=name)


# ======================================================================
# PE Script Agent Tools
# ======================================================================


@mcp.tool(
    description=(
        "【脚本搜索】搜索 PE 引擎的 1927 个原生脚本函数。\n"
        "支持中英文混合搜索，如 \"创建球体 设置颜色\"、\"camera move fog\"。\n"
        "返回紧凑列表（函数名、模块、描述、参数预览），不包含完整参数详情。\n"
        "找到候选函数后，用 pe_script_get_function 获取完整签名和参数说明。\n"
        "也可先用 pe_script_module_index 了解有哪些模块。"
    )
)
def pe_script_search_functions(query: str, module: str = "", limit: int = 10) -> dict:
    results = search_functions(query, module=module, limit=limit)
    return {
        "success": True,
        "query": query,
        "count": len(results),
        "functions": results,
        "hint": "Use pe_script_get_function(name) to get full signature and parameter details for any function above.",
    }


@mcp.tool(
    description=(
        "【脚本函数详情】获取单个 PE 脚本函数的完整信息：返回值、参数列表、描述、参数说明。\n"
        "name 必须是 pe_script_search_functions 返回的精确函数名。\n"
    )
)
def pe_script_get_function(name: str) -> dict:
    func = get_function(name)
    if func is None:
        return {"success": False, "error": f"Function not found: {name}"}
    return {"success": True, **func}


@mcp.tool(
    description=(
        "【脚本模块索引】列出 PE 引擎所有 63 个 API 模块及其函数数量。\n"
        "用于初步了解有哪些模块可用（如 Camera、Light、Animation、Math 等）。\n"
        "每行格式：ModuleName (N funcs) func1, func2, func3 +M more\n"
        "返回约 1,600 tokens 的紧凑文本。"
    )
)
def pe_script_module_index() -> dict:
    index = get_module_index()
    return {"success": True, "index": index}


@mcp.tool(
    description=(
        "【脚本模块展开】获取某个模块下的函数列表（紧凑格式，每行一个函数名+描述）。\n"
        "module 必须是 pe_script_module_index 返回的模块名之一。\n"
        "limit 默认 20，超出部分会提示 +N more。"
    )
)
def pe_script_module_functions(module: str, limit: int = 20) -> dict:
    funcs = get_module_functions(module, limit=limit)
    return {"success": True, "module": module, "count": len(funcs), "functions": funcs}


@mcp.tool(
    description=(
        "【脚本准备】在 PE 项目中创建功能 .script，并幂等维护 include.script。\n"
        "同名脚本内容一致时不会重复写入；include 已存在时不会重复包含；\n"
        "发现完全重复的 include 会保留一条并在写入前创建备份。\n"
        "body 只填写函数体语句，不要包含 Script{}；项目目录或 .peproj 必须是本机路径。"
    )
)
def pe_script_prepare(
    project: str,
    function_name: str,
    script_name: str = "",
    message: str = "",
    body: str = "",
    include_file: str = "",
    script_file: str = "",
    overwrite: bool = False,
    dry_run: bool = False,
) -> dict:
    return prepare_project_script(
        project=project,
        function_name=function_name,
        script_name=script_name,
        message=message,
        body=body,
        include_file=include_file,
        script_file=script_file,
        overwrite=overwrite,
        dry_run=dry_run,
    )


@mcp.tool(
    description=(
        "【脚本执行】执�?PE 原生脚本字符串。\n"
        "脚本使用 PE DSL 语法（module/begin/end）。\n"
        "生成脚本前请先用 pe_script_search_functions 和 pe_script_get_function 确认函数签名。\n"
        "需�?PE 引擎运行�?PEHelloMCP 插件已加载�?"
    )
)
def pe_script_execute(script: str, script_name: str = "") -> dict:
    from pe_client.client import script_execute as _exec
    return _exec(script, script_name)


@mcp.tool(
    description=(
        "【脚本验证】验证 PE 脚本语法，返回是否有效。\n"
        "执行前建议先用此工具检查语法错误。"
    )
)
def pe_script_validate(script: str) -> dict:
    from pe_client.client import script_validate as _validate
    return _validate(script)


# ======================================================================
# 入口
# ======================================================================



# ======================================================================
# Rotate / preset animation (peo-backed)
# ======================================================================

@mcp.tool(
    description=(
        "列出工程 .peo 索引中的预置动画名（Ani_/动画_/sysanim_）。\n"
        "query 可选，子串过滤。"
    )
)
def pe_list_anims(query: str = "") -> dict:
    from pe_client.rotate_model import list_anims
    return list_anims(query=query)


@mcp.tool(
    description=(
        "检查预置动画在 .peo 中的绑定：时长、事件、field 路径。\n"
        "用于 pe_rotate_model 通用化前的对照。"
    )
)
def pe_inspect_anim(name: str) -> dict:
    from pe_client.rotate_model import inspect_anim
    return inspect_anim(name)


@mcp.tool(
    description=(
        "播放预置动画（astart，经 GBK 文件通道）。\n"
        "子模块动画请用限定名 main:模块:动画名。"
    )
)
def pe_play_anim(name: str) -> dict:
    from pe_client.rotate_model import play_anim
    return play_anim(name)


@mcp.tool(
    description=(
        "模型旋转通用入口。\n"
        "- anim_name: 直接 astart 该预置动画\n"
        "- field: 在 .peo 中查找绑定到该路径的预置动画并播放\n"
        "- mode=create: 明确拒绝（运行时创建动画不绑定模型，见红线）\n"
        "degrees/duration_s/axis 目前用于匹配与 create 提示，不能凭空生成有效视觉旋转。"
    )
)
def pe_rotate_model(
    field: str = "",
    degrees: float = 360.0,
    duration_s: float = 5.0,
    axis_x: float = 0.0,
    axis_y: float = 1.0,
    axis_z: float = 0.0,
    anim_name: str = "",
    mode: str = "auto",
) -> dict:
    from pe_client.rotate_model import rotate_model
    return rotate_model(
        field=field,
        degrees=degrees,
        duration_s=duration_s,
        axis=(axis_x, axis_y, axis_z),
        anim_name=anim_name,
        mode=mode,
    )




@mcp.tool(description="行为图能力矩阵（哪些 CRUD 可用/不可用）")
def pe_graph_caps() -> dict:
    from pe_client import rg_crud
    return rg_crud.capabilities()


@mcp.tool(description="列出工程 peproj 已注册的 .rg 与 main 目录文件。project=工程目录或.peproj")
def pe_graph_list(project: str) -> dict:
    from pe_client import rg_crud
    return rg_crud.list_graphs(project)


@mcp.tool(description="读取行为图：RelaGraph 字段表+字符串解析。不会打开 PE 图编辑器。")
def pe_graph_read(rg_path: str, with_inspect: bool = True) -> dict:
    from pe_client import rg_crud
    return rg_crud.read_graph(rg_path, with_inspect=with_inspect)


@mcp.tool(description="查询行为图节点/连线。type_name 如 PROGRAM/BOOT/STEP；node_id 可选。")
def pe_graph_query(rg_path: str, type_name: str = "", node_id: int | None = None) -> dict:
    from pe_client import rg_crud
    return rg_crud.query_graph(rg_path, type_name=type_name, node_id=node_id)


@mcp.tool(description="创建启动型行为图并注册到 peproj（ID=49）。calls 为启动调用列表。")
def pe_graph_create(project: str, name: str, calls: list[str] | None = None,
                    include: str = "main\\Script\\include.script", overwrite: bool = False) -> dict:
    from pe_client import rg_crud
    return rg_crud.create_graph(project, name, calls=calls, include=include, overwrite=overwrite)


@mcp.tool(description="替换 .rg 内一条长度前缀字符串（program/include）。old_text/new_text 须完整匹配含 CRLF。")
def pe_graph_update_text(rg_path: str, old_text: str, new_text: str) -> dict:
    from pe_client import rg_crud
    return rg_crud.update_graph_text(rg_path, old_text=old_text, new_text=new_text)


@mcp.tool(description="从 peproj 注销行为图并可删除 main 下文件。")
def pe_graph_delete(project: str, name: str, delete_file: bool = True) -> dict:
    from pe_client import rg_crud
    return rg_crud.delete_graph(project, name, delete_file=delete_file)


@mcp.tool(description="按 node id 改写 .rg 节点文本（原生 SetText；同文案多节点只改目标 id）。离线，不开图编辑器。")
def pe_graph_update_text_by_id(rg_path: str, node_id: int, new_text: str, out_path: str = "") -> dict:
    from pe_client import rg_crud
    return rg_crud.update_graph_text_by_id(
        rg_path, node_id, new_text, out_path=out_path or None, inplace=not out_path,
    )


@mcp.tool(description="发现启动链：从 BOOT 跟随 next；附带 HUB 出边 CURVE 说明。离线只读。")
def pe_graph_boot_chain(rg_path: str, include_curves_from_hub: bool = True) -> dict:
    from pe_client import rg_crud
    return rg_crud.boot_chain(rg_path, include_curves_from_hub=include_curves_from_hub)




@mcp.tool(description="Offline add PROGRAM node to .rg via RelaGraph CreateByType+WriteToBuffer. Does not open graph editor.")
def pe_graph_add_program(rg_path: str, text: str, x: float = 520.0, y: float = 220.0,
                         link_from_id: int = 0, out_path: str = "") -> dict:
    from pe_client import rg_crud
    return rg_crud.add_program(
        rg_path, text, x=x, y=y, link_from_id=link_from_id,
        out_path=out_path or None, inplace=not out_path,
    )


@mcp.tool(description="Offline remove .rg node by id via RelaGraph RemoveObject+WriteToBuffer. Does not open graph editor.")
def pe_graph_remove_node(rg_path: str, node_id: int, out_path: str = "") -> dict:
    from pe_client import rg_crud
    return rg_crud.remove_node(
        rg_path, node_id, out_path=out_path or None, inplace=not out_path,
    )


@mcp.tool(description="Offline add .rg node by RgType via CreateByType+WriteToBuffer. Types: 1-14,16,19 (BUTTON). TIP=15/BEHAVIOR=17 unsupported. Does not open graph editor.")
def pe_graph_add_node(rg_path: str, node_type: int, text: str = "", x: float = 520.0, y: float = 220.0,
                      link_from_id: int = 0, out_path: str = "") -> dict:
    from pe_client import rg_crud
    return rg_crud.add_node(
        rg_path, node_type, text=text, x=x, y=y, link_from_id=link_from_id,
        out_path=out_path or None, inplace=not out_path,
    )


@mcp.tool(description="Offline link two .rg nodes with a CURVE edge (WriteToBuffer). Does not open graph editor.")
def pe_graph_link(rg_path: str, from_id: int, to_id: int, out_path: str = "") -> dict:
    from pe_client import rg_crud
    return rg_crud.link_nodes(
        rg_path, from_id, to_id, out_path=out_path or None, inplace=not out_path,
    )

@mcp.tool(description="Offline remove CURVE edge between two .rg node ids. Does not open graph editor.")
def pe_graph_unlink(rg_path: str, from_id: int, to_id: int, out_path: str = "") -> dict:
    from pe_client import rg_crud
    return rg_crud.unlink_nodes(
        rg_path, from_id, to_id, out_path=out_path or None, inplace=not out_path,
    )



@mcp.tool(description="离线 Insight 风格：索引工程下全部 .rg（main/** + peproj）。只读，不改 .rg。可选 out_path 写 JSON；grep 子串搜索。")
def pe_graph_index(project: str, out_path: str = "", with_inspect: bool = True,
                   with_boot_chain: bool = True, grep: str = "") -> dict:
    from pe_client import rg_crud
    return rg_crud.index_project(
        project,
        with_inspect=with_inspect,
        with_boot_chain=with_boot_chain,
        out_path=out_path or None,
        grep=grep or None,
    )


@mcp.tool(description="在工程 .rg 索引中子串搜索（节点/程序/启动链文本；中文 Unicode 安全）。可复用 index_path JSON，否则临时建索引。")
def pe_graph_grep(project: str, query: str, index_path: str = "") -> dict:
    from pe_client import rg_crud
    if index_path:
        return rg_crud.search_index(index_path, query)
    idx = rg_crud.index_project(project, grep=query)
    return idx.get("grep") or {"success": False, "error": "no grep result"}


if __name__ == "__main__":
    mcp.run(transport="stdio")
