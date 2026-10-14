from pe_client import native_pipe

def main():
    calls = []
    native_pipe.pipe_command = lambda payload, timeout=15.0: (calls.append(payload) or {"success": True, "still_present": "0"})
    result = native_pipe.obj_delete("图表_1", "curve", "/scene/modules/main/charts/图表_1")
    assert result["success"] is True
    assert calls == ["cmd=obj_delete|obj_type=curve|name=图表_1|tree=2"], calls
    print("SAFE_CHART_DELETE_TEST=PASS")

if __name__ == "__main__":
    main()
