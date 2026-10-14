# -*- coding: utf-8 -*-
import json
import re
from collections import Counter
from pathlib import Path

RG = {
    0: "UNKNOWN",
    1: "STEP",
    2: "CURVE",
    3: "ANIM",
    4: "HUB",
    5: "CONDITIONS",
    6: "PROGRAM",
    7: "COMPLEX",
    8: "TIMER",
    9: "INSTRUCT",
    10: "BRANCH",
    11: "BOOT",
    12: "VARIABLE",
    13: "COMMENT",
    14: "SCRIPT",
    15: "TIP",
    16: "INTERRUPT",
    17: "BEHAVIOR",
    19: "BUTTON",  # CreateByType case 0x12 -> CRgButton; not in RgType 0..17
}


def parse_inspect(path: Path) -> dict:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    root_m = re.search(r"root type=(\d+) id=(\d+) prev=(-?\d+) next=(-?\d+) father=(-?\d+)", text)
    size_m = re.search(r"list sentinel=.*? size=(\d+)", text)
    objs = []
    for m in re.finditer(
        r"object\[(\d+)\]=.*? type=(\d+) id=(\d+) prim=(\d+) flag=0x([0-9a-fA-F]+) status=(\d+) "
        r"prev=(-?\d+) next=(-?\d+) father=(-?\d+) matrix=([^\n]+)",
        text,
    ):
        typ = int(m.group(2))
        mat_raw = m.group(10).split(" matrixTail=")[0].split(" dims=")[0]
        mats = [float(x) for x in mat_raw.split(",")[:6]]
        after = text[m.end() : m.end() + 300]
        sm = re.search(r"(?:script text|text)=(.+)", after)
        objs.append({
            "index": int(m.group(1)),
            "type": typ,
            "type_name": RG.get(typ, f"TYPE_{typ}"),
            "id": int(m.group(3)),
            "prim": int(m.group(4)),
            "flag": m.group(5),
            "status": int(m.group(6)),
            "prev": int(m.group(7)),
            "next": int(m.group(8)),
            "father": int(m.group(9)),
            "matrix": mats,
            "tx": mats[4] if len(mats) > 4 else None,
            "ty": mats[5] if len(mats) > 5 else None,
            "script_text": (
            None
            if (
                not sm
                or sm.group(1).strip() in ("<null>",)
                or sm.group(1).lstrip().startswith("vtable=")
                or " q30=" in sm.group(1)
            )
            else sm.group(1).strip()
        ),
        })
    links = [o for o in objs if o["type"] == 2]
    nodes = [o for o in objs if o["type"] != 2]
    return {
        "source": str(path),
        "root": {
            "type": int(root_m.group(1)),
            "id": int(root_m.group(2)),
            "prev": int(root_m.group(3)),
            "next": int(root_m.group(4)),
            "father": int(root_m.group(5)),
            "type_name": RG.get(int(root_m.group(1)), "?"),
        } if root_m else None,
        "list_size": int(size_m.group(1)) if size_m else None,
        "type_histogram": {
            (RG.get(k) or f"TYPE_{k}"): v
            for k, v in sorted(Counter(o["type"] for o in objs).items())
        },
        "nodes": nodes,
        "links": [
            {"id": o["id"], "from": o["prev"], "to": o["next"], "father": o["father"]}
            for o in links
        ],
        "objects": objs,
    }


if __name__ == "__main__":
    for name in ["rg_inspect_helloworld.txt", "rg_inspect_gdz23_main.txt"]:
        p = Path("data/exports") / name
        if not p.exists():
            print("missing", p)
            continue
        info = parse_inspect(p)
        out = p.with_suffix(".fields.json")
        out.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
        print("wrote", out, "nodes", len(info["nodes"]), "links", len(info["links"]))
