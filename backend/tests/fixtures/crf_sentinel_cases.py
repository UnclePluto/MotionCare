"""DOCX用合法数据及独立几何标记；标记从不提交给临床API。"""


def clinical_case():
    baseline = {
        "subject_id": "S-DOCX-031",
        "name_initials": "ZXY",
        "demographics": {"age_years": 72, "gender": "女", "ethnicity": "蒙古族"},
        "surgery_allergy": {
            "has_surgery": "是",
            "has_allergy": "是",
            "surgery_records": [
                {
                    "_row_id": f"surgery-{i}",
                    "name": f"手术记录{i}",
                    "date": "2025-06-12",
                    "hospital_note": f"医院记录{i}",
                }
                for i in range(5)
            ],
            "allergy_records": [
                {
                    "_row_id": f"allergy-{i}",
                    "category": "食物",
                    "allergen": f"过敏原{i}",
                    "manifestation": f"皮疹{i}",
                    "severity_treatment": f"处理{i}",
                }
                for i in range(4)
            ],
        },
        "comorbidities": {"cm_coronary": {"personal": "是", "diagnosed_at": "2020-07"}},
    }
    visits = {}
    for index, vt in enumerate(("T0", "T1", "T2")):
        crf = {"meta": {"assessor_name": f"评估者{vt}"}}
        if vt != "T0":
            crf.update(
                {
                    "satisfaction": {
                        "items": {
                            name: {"score": (i + index) % 5 + 1, "remark": f"{vt}反馈{i}"}
                            for i, name in enumerate(
                                ("operation", "clarity", "reminders", "burden", "recommendation"), 1
                            )
                        },
                        "overall_score": 4,
                        "total": 15,
                    },
                    "medication_change": {
                        "has_changes": "是",
                        "entries": [
                            {
                                "_row_id": f"med-{i}",
                                "name": f"{vt}药物{i}",
                                "indication": "治疗",
                                "started_on": "2026-01-02",
                                "ongoing": "已停用",
                                "stopped_on": "2026-02-03",
                                "dose_frequency": f"{i + 1}毫克每日",
                                "remark": f"药物备注{i}",
                            }
                            for i in range(5)
                        ],
                    },
                    "adverse_events": {
                        "has_events": "是",
                        "entries": [
                            {
                                "_row_id": f"event-{i}",
                                "occurred_on": "2026-03-04",
                                "event_name": f"{vt}事件{i}",
                                "severity": "轻",
                                "is_sae": "否",
                                "relatedness": "可能",
                                "management_note": f"处理{i}",
                                "outcome_note": f"转归{i}",
                            }
                            for i in range(5)
                        ],
                    },
                }
            )
        visits[vt] = {
            "visit_date": f"2026-0{index + 1}-08",
            "form_data": {"crf": crf, "assessments": {"sppb": {"total": index + 3}}},
        }
    return baseline, visits


def slot_marker(slot_id):
    return "定位_" + slot_id.replace(".", "_")


def binding_projection_case(registry):
    """Renderer boundary fixture with individually legal values, not an API payload.

    Applicability is already resolved by the caller of the binder. End-to-end
    conditional behavior is separately exercised through clinical_case/evaluation.
    """
    sections = []
    expected = []

    def leaf(definition, index=None):
        widget = definition["widget"]
        identity = definition["field_id"] + (f"_{index}" if index is not None else "")
        value = "填写_" + identity
        if definition["storage"] == "patient_baseline.subject_id":
            value = "S-SHARED-051"
        if widget == "number":
            value = max(definition.get("min", 0), 1)
        elif widget in ("single_choice", "multi_choice"):
            value = definition["options"][-1]
            if widget == "multi_choice":
                value = [value]
        elif widget == "date":
            value = "2024-07" if definition.get("date_precision") == "month" else "2024-07-09"
        field = dict(
            field_id=definition["field_id"],
            storage=definition["storage"],
            label=definition["label_zh"],
            widget=widget,
            value=value,
            raw_value=value,
            applicable=True,
            state="normal",
            reason="",
            source_positions=definition.get("source_positions", []),
            source={"kind": "manual"},
            rows=[],
        )
        for position in field["source_positions"]:
            if index is None or position.get("repeat_index") == index:
                expected.append((definition, position, value))
        return field

    for definition in registry["fields"]:
        if definition.get("legacy"):
            continue
        if definition["widget"] == "table_repeat":
            field = leaf(definition)
            field["rows"] = [
                {"index": i, "fields": [leaf(child, i) for child in definition["children"]]}
                for i in range(len(definition["children"][0]["source_positions"]))
            ]
        else:
            field = leaf(definition)
        sections.append(
            {
                "scope": (definition.get("visit_types") or ["patient_baseline"])[-1],
                "title": definition["table_ref"],
                "supplemental": False,
                "fields": [field],
            }
        )
    return {"sections": sections, "issues": []}, expected


def put(data, path, value):
    parts = path.split(".")
    for key in parts[:-1]:
        data = data.setdefault(key, {})
    data[parts[-1]] = value


def complete_known_case():
    """Legal known primitive values; totals below are independently hand-calculated."""
    from apps.crf.registry_loader import load_crf_registry

    registry = load_crf_registry()
    baseline, visits = (
        {},
        {v: {"visit_date": "2026-10-08", "form_data": {}} for v in ("T0", "T1", "T2")},
    )

    def answer(f):
        if f["widget"] == "number":
            return max(0, f.get("min", f.get("validation", {}).get("min", 0)))
        if f["widget"] == "single_choice":
            return next(
                (v for v in ("否", "无", "从不", "从不吸烟", "从不饮酒") if v in f["options"]),
                f["options"][0],
            )
        if f["widget"] == "multi_choice":
            return [f["options"][0]]
        if f["widget"] == "date":
            return "2026-10" if f.get("date_precision") == "month" else "2026-10-08"
        if f["widget"] == "table_repeat":
            return [
                {
                    "_row_id": "row-1",
                    **{
                        c["storage"]: answer(c)
                        for c in f["children"]
                        if c["include_in_completeness"]
                    },
                }
            ]
        return "已记录"

    for f in registry["fields"]:
        if f.get("legacy") or not f["include_in_completeness"] or f.get("canonical_storage"):
            continue
        for vt in f.get("visit_types") or [None]:
            context = {"patient_baseline": baseline, "visit": visits.get(vt)}
            put(context, f["storage"], answer(f))
    for vt in ("T0", "T1"):
        visits[vt]["form_data"]["crf"].pop("completion_record", None)
        visits[vt]["form_data"]["crf"].pop("qc_record", None)
    for visit in visits.values():
        a = visit["form_data"]["assessments"]
        a["moca"]["subscores"]["education_bonus"] = 1
        a["moca"]["total"] = 1
        a["moca"]["leq22"] = "是"
        if "satisfaction" in visit["form_data"]["crf"]:
            visit["form_data"]["crf"]["satisfaction"]["total"] = 5
    return baseline, visits


