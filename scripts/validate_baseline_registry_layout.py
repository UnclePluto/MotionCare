#!/usr/bin/env python3
"""校验 registry.v1.json 中基线 layout 与 fields 一致。

Task 5 完成后（registry 含完整 baseline_table_layout）本脚本预期退出码 0。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "specs" / "patient-rehab-system" / "crf" / "registry.v1.json"


def main() -> int:
    doc = json.loads(REG.read_text(encoding="utf-8"))
    fields = doc.get("fields", [])
    by_id = {f["field_id"]: f for f in fields if isinstance(f, dict) and "field_id" in f}
    baseline_ids = {
        f["field_id"]
        for f in fields
        if isinstance(f.get("storage"), str) and f["storage"].startswith("patient_baseline.")
    }
    order = doc.get("baseline_section_order")
    layout = doc.get("baseline_table_layout") or {}
    if not isinstance(order, list) or not all(isinstance(x, str) for x in order):
        print("ERROR: baseline_section_order 必须是非空字符串数组", file=sys.stderr)
        return 1
    seen: set[str] = set()
    for ref in order:
        block = layout.get(ref)
        if not block or not isinstance(block.get("rows"), list):
            print(f"ERROR: baseline_table_layout 缺少节 {ref}", file=sys.stderr)
            return 1
        for row in block["rows"]:
            for cell in row.get("cells", []):
                fid = cell.get("field_id")
                if not fid:
                    continue
                if fid in seen:
                    print(f"ERROR: field_id 重复出现在 layout 中: {fid}", file=sys.stderr)
                    return 1
                seen.add(fid)
                if fid not in by_id:
                    print(f"ERROR: layout 引用未知 field_id: {fid}", file=sys.stderr)
                    return 1
    missing = baseline_ids - seen
    if missing:
        print(f"ERROR: 下列基线字段未出现在 layout 中: {sorted(missing)}", file=sys.stderr)
        return 1
    extra = seen - baseline_ids
    if extra:
        print(f"ERROR: layout 出现非基线 field_id: {sorted(extra)}", file=sys.stderr)
        return 1
    print("OK baseline layout covers", len(baseline_ids), "fields")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
