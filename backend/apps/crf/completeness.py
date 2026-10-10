"""Read-only, registry-driven CRF projection shared by preview and export.

Counts describe applicable handled/required field instances, not paper slots.
Missing optional remarks and inactive children do not contribute. Raw values are
retained separately; only validated manual observations drive conditions.
"""

from collections import defaultdict
from collections.abc import Mapping
from copy import deepcopy
from datetime import date

from apps.crf.answer_values import decode_crf_answer
from apps.crf.field_rules import evaluate_condition, get_observed_value, is_blank, validate_fields
from apps.crf.field_values import (
    BAD_PARENT,
    MISSING,
    get_field_metadata,
    get_field_value,
    lookup_path,
)

VISIT_TYPES = ("T0", "T1", "T2")
STATES = ("normal", "unknown", "not_applicable", "unresolved")


def _present(value):
    if value is MISSING or value is BAD_PARENT or is_blank(value):
        return False
    if isinstance(value, Mapping):
        return any(_present(v) for v in value.values())
    if isinstance(value, list):
        return bool(value)
    return True


def _json(value):
    if value is MISSING or value is BAD_PARENT:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return deepcopy(value)


def _counts():
    return dict.fromkeys(STATES, 0)


def evaluate_completeness(registry: dict, baseline: dict, visits: dict[str, dict]) -> dict:
    definitions = registry.get("fields", [])
    sections, missing, issues = [], [], []
    counts = _counts()
    contexts = {"patient_baseline": {"patient_baseline": baseline}}
    contexts.update(
        {vt: {"patient_baseline": baseline, "visit": visits.get(vt, {})} for vt in VISIT_TYPES}
    )
    errors = {
        scope: validate_fields(
            registry,
            data,
            scope="patient_baseline" if scope == "patient_baseline" else "visit",
            visit_type=None if scope == "patient_baseline" else scope,
        )
        for scope, data in contexts.items()
    }
    # A selected terminal table is one whole visit group, never a leaf-wise merge.
    shared = defaultdict(list)
    for f in definitions:
        if f.get("export_visit_selection") == "latest_recorded_with_conflict_check":
            shared[f["section"]].append(f)
    chosen = {}
    for table, fields in shared.items():
        path = fields[0]["storage"].rsplit(".", 1)[0]
        # QC leaves are nested; the common prefix identifies the entire record.
        parts = [f["storage"].split(".") for f in fields]
        common = []
        for segments in zip(*parts):
            if len(set(segments)) != 1:
                break
            common.append(segments[0])
        path = ".".join(common)
        recorded = []
        snapshots = {}
        for vt in VISIT_TYPES:
            ctx = contexts[vt]
            raw = lookup_path(ctx, path)
            metadata = {
                f["storage"]: _json(get_field_metadata(ctx, f))
                for f in fields
                if _present(get_field_metadata(ctx, f))
            }
            if _present(raw) or metadata:
                recorded.append(vt)
                snapshots[vt] = {"raw_value": _json(raw), "metadata": metadata}
        chosen[table] = recorded[-1] if recorded else "T2"
        if len(recorded) > 1 and any(
            snapshots[v] != snapshots[recorded[-1]] for v in recorded[:-1]
        ):
            issues.append(
                {
                    "code": "conflicting_records",
                    "scope": chosen[table],
                    "storage": path,
                    "message": f"{'、'.join(recorded)} 的{registry.get('table_titles', {}).get(table, '终末记录')}存在冲突，请复核",
                    "sources": [{"visit_type": v, **snapshots[v]} for v in recorded],
                }
            )

    section_map = {}
    consumed = defaultdict(set)

    def section(scope, table, supplemental=False):
        key = (scope, table, supplemental)
        if key not in section_map:
            result = {
                "key": ":".join(map(str, key)),
                "scope": scope,
                "table_ref": table,
                "title": "补充记录"
                if supplemental
                else registry.get("table_titles", {}).get(table, "研究记录"),
                "supplemental": supplemental,
                "fields": [],
                "counts": _counts(),
            }
            section_map[key] = result
            sections.append(result)
        return section_map[key]

    def issue(code, scope, path, message):
        result = {"code": code, "scope": scope, "storage": path, "message": message}
        if result not in issues:
            issues.append(result)
        return result

    def supplement(scope, path, value, label="补充记录", table=None, review=True):
        if not _present(value):
            return
        own_issues = [issue("legacy_review", scope, path, f"{label}需核对")] if review else []
        section(scope, table, True)["fields"].append(
            {
                "field_id": path,
                "storage": path,
                "label": label,
                "widget": "raw",
                "unit": None,
                "applicable": False,
                "required": False,
                "state": "unresolved",
                "value": _json(value),
                "raw_value": _json(value),
                "partial_date_value": None,
                "metadata": None,
                "reason": "",
                "rows": [],
                "issues": own_issues,
                "source": {
                    "kind": "legacy",
                    "visit_type": None if scope == "patient_baseline" else scope,
                },
                "source_positions": [],
                "counted": False,
            }
        )

    def project(
        field, scope, data, local_fields, *, prefix="", label_prefix="", parent_active=True
    ):
        path = prefix + field["storage"]
        raw = lookup_path(data, field["storage"])
        if field.get('date_answer_storage'):
            canonical=lookup_path(data,field['date_answer_storage'])
            if canonical is not MISSING and canonical is not BAD_PARENT:raw=canonical
        meta = get_field_metadata(data, field)
        value = get_field_value(data, field)
        partial_path = field.get("partial_date_storage")
        partial = lookup_path(data, partial_path) if partial_path else MISSING
        applicable = parent_active and evaluate_condition(
            field.get("visible_when"), data, fields=local_fields
        )
        required = (
            bool(field.get("include_in_completeness", field.get("required_for_complete", False)))
            and (evaluate_condition(field.get("required_when"), data, fields=local_fields))
            and applicable
        )
        answer=decode_crf_answer(value,meta)
        reason = answer["reason"] or ""
        reason = reason if isinstance(reason, str) else ""
        own_issues = []
        paths = [path]
        if field.get("date_answer_storage"):paths.append(field["date_answer_storage"])
        if partial_path:
            paths.append(prefix + partial_path)
        if field.get("metadata"):
            m = field["metadata"]
            paths.append(prefix + m["storage"] + "." + m["key"])
        for error_path, message in errors[scope].items():
            row_id_error = (
                field.get("widget") == "table_repeat"
                and error_path.startswith(path + ".")
                and error_path.endswith("._row_id")
            )
            if error_path in paths or row_id_error:
                own_issues.append(issue("invalid_value", scope, error_path, message))
        state = "unresolved"
        observed = get_observed_value(data, field)
        explicit = answer["state"]
        if not own_issues:
            if explicit in ("unknown", "not_applicable"):
                state = explicit
                value = None
            elif observed is not None and _present(observed):
                state = "normal"
            elif field.get("widget") == "date" and isinstance(value, Mapping):
                names = (
                    ("year", "month")
                    if field.get("date_precision") == "month"
                    else ("year", "month", "day")
                )
                states = [
                    value.get(n, {}).get("state") if isinstance(value.get(n), Mapping) else None
                    for n in names
                ]
                if (
                    all(s in ("value", "unknown") for s in states)
                    and "unknown" in states
                ):
                    state = "unknown"
            if _present(value) and value in field.get("legacy_options", []):
                own_issues.append(
                    issue("legacy_review", scope, path, "旧选项需核对并补充状态及原因")
                )
                state = "unresolved"
        rows = []
        repeated = answer["value"]
        if field.get("widget") == "table_repeat" and isinstance(repeated, list):
            for index, row in enumerate(repeated):
                row_path = f"{path}.{index}"
                if not isinstance(row, Mapping):
                    own_issues.append(issue("invalid_value", scope, row_path, "明细行必须是对象"))
                    rows.append(
                        {"key": str(index), "index": index, "raw_value": _json(row), "fields": []}
                    )
                    state = "unresolved"
                    continue
                children = [
                    project(
                        c,
                        scope,
                        row,
                        field["children"],
                        prefix=row_path + ".",
                        label_prefix=f"{label_prefix}{field.get('ui_label', field['label_zh'])} 第{index + 1}行 · ",
                        parent_active=applicable and explicit not in ("unknown", "not_applicable"),
                    )
                    for c in field["children"]
                ]
                rows.append(
                    {
                        "key": f"{index}:{row.get(field.get('row_id_key', '_row_id'), '')}",
                        "index": index,
                        "raw_value": _json(row),
                        "fields": children,
                    }
                )
                # Consume only metadata actually displayed by a known child. Old
                # keys and extra/malformed leaves need their own readable supplement.
                metadata_key = field.get("row_metadata_key", "_field_meta")
                child_metadata = {
                    c["metadata"]["key"]: c
                    for c in field["children"]
                    if c.get("metadata", {}).get("storage") == metadata_key
                }
                supplement_number = 0

                def preserve_metadata(value, meta_path, child=None):
                    nonlocal supplement_number
                    if isinstance(value, Mapping):
                        for key, leaf in value.items():
                            preserve_metadata(leaf, meta_path + "." + key, child)
                    elif isinstance(value, list):
                        for position, leaf in enumerate(value):
                            preserve_metadata(leaf, f"{meta_path}.{position}", child)
                    elif _present(value):
                        supplement_number += 1
                        child_label = (
                            f"{child.get('ui_label', child['label_zh'])} · " if child else ""
                        )
                        supplement(
                            scope,
                            meta_path,
                            value,
                            f"{field.get('ui_label', field['label_zh'])} 第{index + 1}行 · "
                            f"{child_label}历史补充记录{supplement_number}",
                            field["section"],
                        )

                row_metadata = row.get(metadata_key)
                if isinstance(row_metadata, Mapping):
                    for key, entry in row_metadata.items():
                        child = child_metadata.get(key)
                        meta_path = f"{row_path}.{metadata_key}.{key}"
                        if child and isinstance(entry, Mapping):
                            for leaf_key, leaf in entry.items():
                                if leaf_key == "reason" and isinstance(leaf, str):
                                    continue  # Already shown as the child reason.
                                if leaf_key == "state" and leaf in child["metadata"].get(
                                    "states", ["value", "unknown", "not_applicable"]
                                ):
                                    continue
                                preserve_metadata(leaf, meta_path + "." + leaf_key, child)
                        else:
                            preserve_metadata(entry, meta_path, child)
                else:
                    preserve_metadata(row_metadata, f"{row_path}.{metadata_key}")

                # Other unknown historical row keys remain available for inspection.
                known = {c["storage"].split(".")[0] for c in field["children"]} | {
                    field.get("row_id_key", "_row_id"),
                    metadata_key,
                }
                for key in row.keys() - known:
                    supplement(
                        scope, f"{row_path}.{key}", row[key], "明细补充记录", field["section"]
                    )
        label = field.get("ui_label") or field["label_zh"]
        # Merely selecting normal mode never makes a cleared optional remark required.
        counted = applicable and (
            required
            or _present(value)
            or explicit in ("unknown", "not_applicable")
            or bool(own_issues)
        )
        if counted:
            counts[state] += 1
            section(scope, field["section"])["counts"][state] += 1
        if counted and state == "unresolved":
            missing.append(f"{scope}.{label_prefix}{field['label_zh']}")
        return {
            "field_id": field["field_id"],
            "storage": path,
            "label": label,
            "widget": field["widget"],
            "unit": field.get("unit"),
            "applicable": applicable,
            "required": required,
            "counted": counted,
            "state": state,
            "value": _json(value) if applicable else None,
            "raw_value": _json(raw),
            "partial_date_value": _json(partial),
            "metadata": _json(meta),
            "reason": reason,
            "rows": rows,
            "issues": own_issues,
            "source": {
                "kind": "patient_baseline" if path.startswith("patient_baseline.") else "manual",
                "visit_type": None if scope == "patient_baseline" else scope,
            },
            "source_positions": deepcopy(field.get("source_positions", [])),
        }

    for vt in VISIT_TYPES:
        if vt not in visits or not visits[vt]:
            missing.append(f"{vt}.访视记录")
            issue("missing_visit", vt, "visit", "访视记录缺失")
    for scope, context in contexts.items():
        vt = None if scope == "patient_baseline" else scope
        local = [f for f in definitions if not f.get("visit_types") or vt in f["visit_types"]]
        selected = [
            f
            for f in local
            if (not f.get("visit_types") if vt is None else bool(f.get("visit_types")))
        ]
        for field in selected:
            path = field["storage"]
            consumed[scope].add(path)
            if field.get("date_answer_storage"):consumed[scope].add(field["date_answer_storage"])
            if field.get("partial_date_storage"):
                consumed[scope].add(field["partial_date_storage"])
            m = field.get("metadata")
            if m:
                consumed[scope].add(m["storage"] + "." + m["key"])
            if field.get("legacy"):
                supplement(
                    scope,
                    path,
                    lookup_path(context, path),
                    field.get("ui_label", field["label_zh"]),
                    field["section"],
                )
                continue
            if field.get("export_visit_selection") and chosen[field["section"]] != scope:
                # Preserve every earlier recorded group, including metadata, separately.
                raw = lookup_path(context, path)
                meta = get_field_metadata(context, field)
                if _present(raw) or _present(meta):
                    supplement(
                        scope,
                        path,
                        {"value": _json(raw), "metadata": _json(meta)},
                        field.get("ui_label", field["label_zh"]),
                        field["section"],
                        review=False,
                    )
                continue
            item = project(field, scope, context, local)
            section(scope, field["section"])["fields"].append(item)
            # Core state/reason drive observation; additional historical keys
            # remain independent evidence and must also survive paper export.
            metadata = item["metadata"]
            if metadata is not None and not isinstance(metadata, Mapping) and m:
                supplement(scope,m['storage']+'.'+m['key'],metadata,field.get('ui_label',field['label_zh'])+'历史状态原文',field['section'])
            if isinstance(metadata, Mapping):
                for key, value in metadata.items():
                    if key not in ("state", "reason"):
                        supplement(
                            scope,
                            m["storage"] + "." + m["key"] + "." + key,
                            value,
                            field.get("ui_label", field["label_zh"]) + "历史补充记录",
                            field["section"],
                        )
        # Alternative amount units: one handled value satisfies the group.
        alternatives = defaultdict(list)
        for f in selected:
            if f.get("alternative_group"):
                alternatives[f["alternative_group"]].append(f)
        for group in alternatives.values():
            items = [
                f
                for s in sections
                if s["scope"] == scope and not s["supplemental"]
                for f in s["fields"]
                if f["field_id"] in {definition["field_id"] for definition in group}
            ]
            if any(f["applicable"] and f["state"] != "unresolved" for f in items):
                for f in items:
                    if (
                        f["counted"]
                        and f["state"] == "unresolved"
                        and not _present(f["raw_value"])
                        and not f["issues"]
                        and (
                            not isinstance(f["metadata"], Mapping)
                            or f["metadata"].get("state") in (None, "value")
                        )
                    ):
                        f["required"] = f["counted"] = False
                        counts["unresolved"] -= 1
                        section(scope, group[0]["section"])["counts"]["unresolved"] -= 1
                        label = next(d["label_zh"] for d in group if d["field_id"] == f["field_id"])
                        missing.remove(f"{scope}.{label}")

        def extra(value, path):
            if path in consumed[scope] or path == "visit.form_data.computed_assessments":
                return
            if isinstance(value, Mapping):
                for key, child in value.items():
                    extra(child, path + "." + key if path else key)
            elif _present(value):
                supplement(scope, path, value)

        if vt is None:
            extra(baseline, "patient_baseline")
        elif vt in visits:
            extra(visits[vt].get("form_data"), "visit.form_data")
    return {
        "sections": sections,
        "missing_fields": list(dict.fromkeys(missing)),
        "issues": issues,
        "counts": counts,
    }
