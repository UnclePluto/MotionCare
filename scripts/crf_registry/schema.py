"""来源绑定合约：位置来自独立清单，字段必须明确声明其填写目标。

条件语言供前后端共同消费：eq/ne 比较完整值；in 是候选集合包含该值；
contains 仅检查数组成员完全相等，绝不做字符串子串匹配；present 检查非空值；
all/any 递归组合条件。条件引用完整 storage；重复行可引用相对列 storage。
本模块验证来源合约，条件执行与输入校验由服务端/前端共享语义实现。
"""

from __future__ import annotations

from collections import defaultdict
from .source_slots import SOURCE_ROWS


def source_position(
    table: int, row: int, slot: int = 0, *, repeat_index: int | None = None
) -> dict:
    definitions = next(defs for t, r, defs in SOURCE_ROWS if (t, r) == (table, row))
    _, cells, _ = definitions[slot]
    result = {
        "slot_id": f"T{table:02d}.R{row:02d}.S{slot:02d}",
        "index_space": "xml_tc",
        "table_index": table,
        "row_index": row,
        "cell_index": cells[0],
        "cell_indices": cells,
        "slot_order": sum(
            1 for _, previous, _ in definitions[:slot] if previous[0] == cells[0]
        ),
        "visit_type": "T0"
        if table in (3, 4, 5, 6, 7, 13, 14)
        else "T1"
        if 15 <= table <= 21
        else "T2"
        if 22 <= table <= 28
        else None,
    }
    if repeat_index is not None:
        result["repeat_index"] = repeat_index
    return result


def validate_registry_contract(registry: dict, source_slots: dict) -> list[str]:
    """返回所有漏绑、越界/错位及重复绑定错误；不依赖数据库或字段生成器。"""
    errors: list[str] = []
    if registry.get("source_docx_sha256") != source_slots.get("source_sha256"):
        errors.append("字段合约与原表源哈希不符")
    slots = {s["slot_id"]: s for s in source_slots["slots"]}
    if len(slots) != len(source_slots["slots"]):
        errors.append("源清单存在重复 slot_id")
    seen = defaultdict(list)
    field_ids: set[str] = set()

    def check(fields, parent_storage="", in_repeat=False):
        for f in fields:
            fid = f.get("field_id", "<无编号>")
            if fid in field_ids:
                errors.append(f"字段编号重复：{fid}")
            field_ids.add(fid)
            storage = f.get("storage")
            effective = (
                f"{parent_storage}.{storage}" if parent_storage and storage else storage
            )
            for position in f.get("source_positions", []):
                sid = position.get("slot_id")
                slot = slots.get(sid)
                if slot is None:
                    errors.append(f"非法来源位置：{fid} {sid}")
                    continue
                if not effective or f.get("read_only"):
                    errors.append(f"来源无可写字段：{sid} {fid}")
                    continue
                for key in (
                    "index_space",
                    "table_index",
                    "row_index",
                    "cell_index",
                    "cell_indices",
                    "slot_order",
                    "visit_type",
                ):
                    if position.get(key) != slot.get(key):
                        errors.append(f"来源位置不符：{sid} {fid} {key}")
                if f.get("widget") not in {
                    "text",
                    "textarea",
                    "number",
                    "date",
                    "single_choice",
                    "multi_choice",
                }:
                    errors.append(f"来源字段不可渲染：{sid} {fid}")
                if slot.get("visit_type") and slot["visit_type"] not in (
                    f.get("visit_types") or []
                ):
                    errors.append(f"来源绑定访视不符：{sid} {fid}")
                if position["table_index"] != f.get("doc_table_index") and f.get(
                    "visit_types"
                ):
                    errors.append(f"来源绑定表号不符：{sid} {fid}")
                if in_repeat and (
                    not isinstance(position.get("repeat_index"), int)
                    or position["repeat_index"] < 0
                ):
                    errors.append(f"重复行位置缺少有效 repeat_index：{sid} {fid}")
                seen[sid].append(f)
            check(
                f.get("children", []),
                effective or "",
                in_repeat or f.get("widget") == "table_repeat",
            )

    check(registry.get("fields", []))
    for binding in registry.get('document_bindings', []):
        fid = binding.get('binding_id', '<无编号>')
        if fid in field_ids:
            errors.append(f'字段编号重复：{fid}')
        field_ids.add(fid)
        for position in binding.get('source_positions', []):
            sid = position.get('slot_id')
            slot = slots.get(sid)
            if binding.get('kind') != 'template_static' or sid not in {'T01.R01.S00', 'T01.R02.S00'} or slot is None:
                errors.append(f'非法文档静态来源：{fid} {sid}')
                continue
            for key in ('index_space', 'table_index', 'row_index', 'cell_index', 'cell_indices', 'slot_order', 'visit_type'):
                if position.get(key) != slot.get(key):
                    errors.append(f'来源位置不符：{sid} {fid} {key}')
            seen[sid].append({'field_id': fid})
    for sid in slots:
        if not seen[sid]:
            errors.append(f"来源未绑定：{sid}")
        elif len(seen[sid]) > 1:
            bindings = seen[sid]
            combinations = [f.get("source_combination", {}) for f in bindings]
            first = combinations[0]
            members = first.get("members", [])
            # 仅允许明确的同位有序组合；漏成员、重复顺序或不一致声明都不是合法共享。
            valid = (
                first.get("id")
                and first.get("operation") == "join_labeled"
                and isinstance(first.get("separator"), str)
                and len(members) == len(bindings)
                and set(members) == {f["field_id"] for f in bindings}
                and all(
                    all(
                        c.get(key) == first.get(key)
                        for key in ("id", "operation", "separator", "members")
                    )
                    and c.get("order") == members.index(f["field_id"])
                    and isinstance(c.get("label"), str)
                    and c["label"]
                    for f, c in zip(bindings, combinations)
                )
            )
            if not valid:
                errors.append(
                    f"来源绑定歧义：{sid} {', '.join(f['field_id'] for f in bindings)}"
                )
        elif seen[sid][0].get("source_combination"):
            errors.append(f"来源组合成员缺失：{sid}")
    return errors
