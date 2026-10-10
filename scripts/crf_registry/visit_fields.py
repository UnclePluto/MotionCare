"""访视字段合约：独立原位绑定、旧值兼容、数值规则及条件元数据。"""

from __future__ import annotations

from .baseline_fields import field
from .schema import source_position

A = "visit.form_data.assessments."
C = "visit.form_data.crf."
ALL_VISITS = ["T0", "T1", "T2"]
VISIT_TABLE_TITLES = {
    **{f"#T{t}": "访视信息" for t in (3, 15, 22)},
    "#T4": "知情同意",
    "#T5": "纳入标准",
    "#T6": "排除标准",
    "#T7": "筛选结论",
    **{f"#T{t}": "身体机能" for t in (13, 17, 24)},
    **{f"#T{t}": "MoCA评估" for t in (14, 18, 25)},
    **{f"#T{t}": "干预依从性" for t in (16, 23)},
    **{f"#T{t}": "平台满意度" for t in (19, 26)},
    **{f"#T{t}": "合并用药变化" for t in (20, 27)},
    **{f"#T{t}": "不良事件" for t in (21, 28)},
    "#T29": "完成与退出",
    "#T30": "质控核查",
}
MOCA = [
    ("visuospatial", "视空间与执行功能", 5),
    ("naming", "命名", 3),
    ("attention", "注意", 6),
    ("language", "语言", 3),
    ("abstraction", "抽象", 2),
    ("delayed_recall", "延迟回忆", 5),
    ("orientation", "定向", 6),
    ("education_bonus", "教育修正加分", 1),
]


# 已发布字段标签保持兼容；录入页只使用简短 ui_label。
LEGACY_LABELS = {
    "as_VISIT_sppb_balance": "SPPB 平衡得分",
    "as_VISIT_sppb_gait": "SPPB 步速得分",
    "as_VISIT_sppb_chair": "SPPB 坐立得分",
    "as_VISIT_sppb_total": "SPPB总分",
    "as_VISIT_tug": "TUG（秒）",
    "as_VISIT_grip": "握力最大值（kg）",
    "as_VISIT_frailty": "衰弱判定",
    "as_VISIT_physical_free_text": "身体机能评估（原文长字段：围度/分项描述等）",
    "as_VISIT_moca_visuospatial": "MoCA 视空间与执行功能（原始分）",
    "as_VISIT_moca_naming": "MoCA 命名（原始分）",
    "as_VISIT_moca_attention": "MoCA 注意（原始分）",
    "as_VISIT_moca_language": "MoCA 语言（原始分）",
    "as_VISIT_moca_abstraction": "MoCA 抽象（原始分）",
    "as_VISIT_moca_delayed_recall": "MoCA 延迟回忆（原始分）",
    "as_VISIT_moca_orientation": "MoCA 定向（原始分）",
    "as_VISIT_moca_education_bonus": "MoCA 教育修正加分（原始分）",
    "as_VISIT_moca_total": "MoCA总分",
    "as_VISIT_moca_leq22": "MoCA 是否≤22分",
    "vd_VISIT_visit_date": "访视日期",
    "scr_visit_visit_meta": "T0 访视信息（周数/时间窗/评估者等，原文）",
    "scr_visit_icf": "知情同意签署信息（原文）",
    "scr_visit_inclusion": "纳入标准判定（原文）",
    "scr_visit_exclusion": "排除标准判定（原文）",
    "scr_visit_enrollment": "筛选结论（入选/筛选失败等，原文）",
    "adh_VISIT_accept_continue": "是否接受/继续数字疗法干预",
    "adh_VISIT_platform_id": "平台账号/编号",
    "adh_VISIT_planned": "计划训练/使用次数与时长",
    "adh_VISIT_actual": "实际完成次数与时长",
    "adh_VISIT_completion_rate": "完成率（%）",
    "adh_VISIT_incomplete_reason": "主要未完成原因",
    "adh_VISIT_investigator_action": "研究者处理",
    "sat_VISIT_matrix_note": "数字疗法平台满意度（条目与总分，原文记录）",
    "crf_med_change_note_visit": "合并用药变化（{visit_type}）",
    "crf_ae_note_visit": "不良事件（{visit_type}）",
    "crf_completion": "完成/退出记录",
    "crf_qc": "质控核查",
}


def condition(storage, value=None, op="eq"):
    return {"storage": storage, "op": op, "value": value}


def _field(fid, table, label, storage, vt, widget="text", positions=(), **attrs):
    result = field(
        fid,
        f"#T{table}",
        label,
        widget,
        storage,
        visit_types=[vt] if isinstance(vt, str) else vt,
        doc_table_index=table,
    )
    result.update(
        section=f"#T{table}",
        ui_label=label,
        source_positions=list(positions),
        validation={},
        visible_when=None,
        required_when=None,
        include_in_completeness=True,
    )
    result.update(attrs)
    label_key = fid
    for visit_type in ALL_VISITS:
        label_key = label_key.replace("_" + visit_type + "_", "_VISIT_").replace(
            "_" + visit_type.lower(), "_visit"
        )
    if label_key in LEGACY_LABELS:
        result["label_zh"] = LEGACY_LABELS[label_key].format(visit_type=vt)
    if widget == "number":
        result["validation"] = {"min": 0, "finite": True, **result["validation"]}
    elif widget in ("text", "textarea"):
        result["validation"] = {"max_length": 4000, **result["validation"]}
    if widget == "date":
        result.update(date_precision="day", allow_partial_date=True)
    # 顶层数值元信息也供现有控件读取；validation 是新校验消费的完整合约。
    for key in ("min", "max", "integer", "max_length"):
        if key in result["validation"]:
            result[key] = result["validation"][key]
    result["metadata"] = {
        "storage": C + "_field_meta" if "." in storage else "_field_meta",
        "key": storage,
        "states": ["value", "unknown", "not_applicable"],
        "reason_required_for_handled": True,
    }
    if result.get("canonical_storage"):
        result["metadata"]["storage"] = "patient_baseline.demographics._crf_field_meta"
    if (
        result["visible_when"] is not None
        and result["include_in_completeness"]
        and "required_when" not in attrs
    ):
        result["required_when"] = result["visible_when"]
    return result


def build_visit_fields() -> list[dict]:
    fields = []

    def add(fid, table, row, slot, label, storage, vt, widget="text", **attrs):
        positions = [source_position(table, row, slot)] if row is not None else []
        value = _field(fid, table, label, storage, vt, widget, positions, **attrs)
        fields.append(value)
        return value

    def legacy(fid, table, label, storage, vt):
        widget = "textarea"
        if fid.startswith("adh_"):
            widget = (
                "number"
                if fid.endswith("_completion_rate")
                else "textarea"
                if fid.endswith("_incomplete_reason")
                else "text"
            )
        return add(
            fid,
            table,
            None,
            0,
            label,
            storage,
            vt,
            widget,
            legacy=True,
            include_in_completeness=False,
        )

    for vt, meta_table, physical_table, moca_table in [
        ("T0", 3, 13, 14),
        ("T1", 15, 17, 18),
        ("T2", 22, 24, 25),
    ]:
        # 重复标识与基线同源；仅用于该访视的纸面原位，不新建第二个患者编号。
        add(
            f"vd_{vt}_subject_id",
            meta_table,
            0,
            0,
            "受试者编号",
            "patient_baseline.subject_id",
            vt,
            canonical_storage="patient_baseline.subject_id",
            edit_scope="patient_baseline",
        )
        date = add(
            f"vd_{vt}_visit_date",
            meta_table,
            1,
            0,
            "访视日期",
            "visit.visit_date",
            vt,
            "date",
        )
        date.update(
            partial_date_storage=C + "meta.visit_date_parts", required_for_complete=True
        )
        for key, label, row, slot, widget in [
            ("actual_week", "实际访视周数", 2, 0, "number"),
            ("days_since_enrollment", "距入组天数", 2, 1, "number"),
            ("in_window", "在访视时间窗内", 3, 0, "single_choice"),
            ("out_of_window_reason", "超窗原因", 3, 1, "text"),
            ("assessor_name", "评估者姓名", 4, 0, "text"),
            ("assessed_on", "评估日期", 4, 1, "date"),
        ]:
            attrs = {}
            if key == "in_window":
                attrs["options"] = ["是", "否"]
            if key == "days_since_enrollment":
                attrs["validation"] = {"integer": True}
            if key == "out_of_window_reason":
                attrs["visible_when"] = condition(C + "meta.in_window", "否")
            add(
                f"vd_{vt}_{key}",
                meta_table,
                row,
                slot,
                label,
                C + "meta." + key,
                vt,
                widget,
                **attrs,
            )

        # 物理测量新增独立子树；评分、TUG、握力与衰弱仍用原有标量路径。
        def physical(key, row, slot, label, widget="number", **attrs):
            return add(
                f"as_{vt}_physical_{key.replace('.', '_')}",
                physical_table,
                row,
                slot,
                label,
                A + "physical." + key,
                vt,
                widget,
                **attrs,
            )

        for slot, (key, label) in enumerate(
            [
                ("neck", "颈围"),
                ("upper_arm", "中臂围"),
                ("waist", "腰围"),
                ("hip", "臀围"),
                ("calf", "小腿围"),
            ]
        ):
            physical("circumference." + key, 1, slot, label, unit="cm")
        for index, (key, label) in enumerate(
            [
                ("side_by_side", "并脚站立"),
                ("semi_tandem", "半串联站立"),
                ("tandem", "串联站立"),
            ]
        ):
            physical(
                "balance." + key + ".able",
                2,
                index * 2,
                label + "10秒",
                "single_choice",
                options=["能", "不能"],
            )
            physical(
                "balance." + key + ".seconds",
                2,
                index * 2 + 1,
                label + "实际时间",
                unit="秒",
            )
        for suffix, path, row, slot, label in [
            ("sppb_balance", "sppb.balance", 2, 6, "SPPB平衡得分"),
            ("sppb_gait", "sppb.gait", 3, 6, "SPPB步速得分"),
            ("sppb_chair", "sppb.chair_stand", 4, 4, "SPPB坐立得分"),
            ("sppb_total", "sppb.total", 5, 0, "SPPB总分"),
        ]:
            total = suffix == "sppb_total"
            attrs = {"validation": {"integer": True, "max": 12 if total else 4}}
            if total:
                attrs["validation"]["consistency"] = {
                    "operation": "sum",
                    "operands": [
                        A + "sppb." + k for k in ["balance", "gait", "chair_stand"]
                    ],
                    "when": "all_present",
                }
                attrs["required_for_complete"] = True
            add(
                f"as_{vt}_{suffix}",
                physical_table,
                row,
                slot,
                label,
                A + path,
                vt,
                "number",
                **attrs,
            )
        for slot, (key, label, unit) in enumerate(
            [
                ("first_seconds", "4米步行第1次", "秒"),
                ("second_seconds", "4米步行第2次", "秒"),
                ("fastest_seconds", "较快时间", "秒"),
                ("speed_m_s", "4米步速", "m/s"),
            ]
        ):
            value = physical("gait." + key, 3, slot, label, unit=unit)
            if key == "fastest_seconds":
                value["validation"]["consistency"] = {
                    "operation": "min",
                    "operands": [
                        A + "physical.gait.first_seconds",
                        A + "physical.gait.second_seconds",
                    ],
                    "when": "all_present",
                }
        physical(
            "gait.uses_aid", 3, 4, "使用辅助工具", "single_choice", options=["无", "有"]
        )
        physical(
            "gait.aid_type",
            3,
            5,
            "辅助工具类型",
            "text",
            visible_when=condition(A + "physical.gait.uses_aid", "有"),
        )
        unable_chair = condition(A + "physical.chair.unable", "不能完成5次")
        physical(
            "chair.seconds",
            4,
            0,
            "5次坐立完成时间",
            unit="秒",
            visible_when=condition(A + "physical.chair.unable", "不能完成5次", "ne"),
        )
        physical(
            "chair.unable",
            4,
            1,
            "不能完成5次",
            "single_choice",
            options=["能完成5次", "不能完成5次"],
            export_choice_mapping={"能完成5次": {"value": None}},
        )
        physical(
            "chair.completed_count",
            4,
            2,
            "可完成次数",
            validation={"integer": True, "max": 4},
            visible_when=unable_chair,
        )
        physical(
            "chair.unable_reason",
            4,
            3,
            "坐立不能完成原因",
            "text",
            visible_when=unable_chair,
        )
        add(
            f"as_{vt}_tug",
            physical_table,
            6,
            0,
            "TUG时间",
            A + "tug_seconds",
            vt,
            "number",
            unit="秒",
            visible_when=condition(A + "physical.tug.unable", "不能完成", "ne"),
        )
        physical(
            "tug.unable",
            6,
            1,
            "TUG能否完成",
            "single_choice",
            options=["能完成", "不能完成"],
            export_choice_mapping={"能完成": {"value": None}},
        )
        physical(
            "tug.unable_reason",
            6,
            2,
            "TUG不能完成原因",
            "text",
            visible_when=condition(A + "physical.tug.unable", "不能完成"),
        )
        physical("grip.hand", 7, 0, "测试手", "single_choice", options=["左手", "右手"])
        physical(
            "grip.has_limitation",
            7,
            1,
            "动静脉瘘、外伤或疼痛等",
            "single_choice",
            options=["无", "有"],
        )
        physical(
            "grip.limitation_note",
            7,
            2,
            "影响说明",
            "text",
            visible_when=condition(A + "physical.grip.has_limitation", "有"),
        )
        for index in range(1, 4):
            physical(
                f"grip.trial_{index}_kg", 7, index + 2, f"握力第{index}次", unit="kg"
            )
        add(
            f"as_{vt}_grip",
            physical_table,
            7,
            6,
            "握力最大值",
            A + "grip_strength_kg",
            vt,
            "number",
            unit="kg",
            validation={
                "consistency": {
                    "operation": "max",
                    "operands": [
                        A + f"physical.grip.trial_{i}_kg" for i in range(1, 4)
                    ],
                    "when": "all_present",
                }
            },
        )
        physical(
            "frailty.walk_15ft_seconds", 8, 0, "15英尺（4.57米）步行时间", unit="秒"
        )
        physical(
            "frailty.slow_walking",
            8,
            1,
            "按方案判定行走缓慢",
            "single_choice",
            options=["否", "是"],
        )
        physical(
            "frailty.unintentional_weight_loss",
            9,
            0,
            "过去1年非故意体重下降>4.5kg或>5%",
            "single_choice",
            options=["否", "是"],
        )
        for slot, key, label, unit in [
            (1, "weight_loss_kg", "体重下降", "kg"),
            (2, "weight_loss_percent", "体重下降比例", "%"),
        ]:
            physical(
                "frailty." + key,
                9,
                slot,
                label,
                unit=unit,
            )
        physical(
            "frailty.cesd_frequency",
            10,
            0,
            "CES-D近1周疲乏出现天数",
            "single_choice",
            options=["0分<1天", "1分1-2天", "2分3-4天", "3分>4天"],
        )
        physical(
            "frailty.exhaustion",
            10,
            1,
            "按方案疲乏判定",
            "single_choice",
            options=["否", "是"],
        )
        physical(
            "frailty.low_activity",
            11,
            0,
            "低体力活动（男性散步<2.5h/周或女性<2h/周/其他依据）",
            "single_choice",
            options=["否", "是"],
        )
        physical(
            "frailty.low_activity_basis",
            11,
            1,
            "低体力活动其他依据",
            "text",
            include_in_completeness=False,
        )
        physical(
            "frailty.positive_count",
            12,
            0,
            "5项标准阳性数",
            validation={"integer": True, "max": 5},
        )
        add(
            f"as_{vt}_frailty",
            physical_table,
            12,
            1,
            "衰弱判定",
            A + "frailty",
            vt,
            "single_choice",
            options=["robust", "pre_frail", "frail"],
            hint="存储为 robust/pre_frail/frail，与后端现有一致",
            option_labels={
                "robust": "无衰弱（0项）",
                "pre_frail": "衰弱前期（1-2项）",
                "frail": "衰弱（≥3项）",
            },
            export_choice_mapping={
                key: {"value": label}
                for key, label in [
                    ("robust", "无衰弱（0项）"),
                    ("pre_frail", "衰弱前期（1-2项）"),
                    ("frail", "衰弱（≥3项）"),
                ]
            },
        )
        legacy(
            f"as_{vt}_physical_free_text",
            physical_table,
            "身体机能旧记录",
            A + "physical_free_text",
            vt,
        )
        for row, (key, label, maximum) in enumerate(MOCA, 1):
            value = add(
                f"as_{vt}_moca_{key}",
                moca_table,
                row,
                0,
                label,
                A + "moca.subscores." + key,
                vt,
                "number",
                validation={"integer": True, "max": maximum},
            )
            if key == "education_bonus":
                value["validation"]["consistency"] = {
                    "operation": "education_bonus",
                    "comparison": "leq",
                    "matched_value": 1,
                    "otherwise_value": 0,
                    "operands": ["patient_baseline.demographics.education_years"],
                    "threshold": 12,
                    "when": "all_present",
                }
            if key in ("naming", "abstraction"):
                add(
                    f"as_{vt}_moca_{key}_remark",
                    moca_table,
                    row,
                    1,
                    label + "备注",
                    A + "moca.remarks." + key,
                    vt,
                    include_in_completeness=False,
                )
        add(
            f"as_{vt}_moca_total",
            moca_table,
            9,
            0,
            "MoCA总分",
            A + "moca.total",
            vt,
            "number",
            required_for_complete=True,
            validation={
                "integer": True,
                "max": 30,
                "consistency": {
                    "operation": "sum",
                    "operands": [A + "moca.subscores." + k for k, _, _ in MOCA],
                    "cap": 30,
                    "when": "all_present",
                },
            },
        )
        add(
            f"as_{vt}_moca_leq22",
            moca_table,
            9,
            1,
            "MoCA是否≤22分",
            A + "moca.leq22",
            vt,
            "single_choice",
            options=["否", "是"],
            validation={
                "consistency": {
                    "operation": "leq",
                    "operands": [A + "moca.total"],
                    "threshold": 22,
                    "true_value": "是",
                    "false_value": "否",
                    "when": "all_present",
                }
            },
        )

    _screening(add, legacy)
    _feedback(add, legacy)
    _completion_and_qc(add, legacy)
    return fields


def _screening(add, legacy):
    for key, table, label in [
        ("visit_meta", 3, "访视信息"),
        ("icf", 4, "知情同意"),
        ("inclusion", 5, "纳入标准"),
        ("exclusion", 6, "排除标准"),
        ("enrollment", 7, "筛选结论"),
    ]:
        legacy("scr_t0_" + key, table, label + "旧记录", C + "screening." + key, "T0")
    icf = C + "screening.icf_record."
    for key, row, slot, label, widget, options in [
        ("signed", 0, 0, "已签署知情同意书", "single_choice", ["否", "是"]),
        ("signed_on", 1, 0, "签署日期", "date", None),
        ("protocol_version", 2, 0, "方案版本", "text", None),
        ("icf_version", 3, 0, "ICF版本", "text", None),
        ("icf_version_date", 3, 1, "ICF版本日期", "date", None),
        (
            "signer_type",
            4,
            0,
            "签署主体",
            "single_choice",
            ["受试者本人签署", "法定代理人/照护者协助签署"],
        ),
        ("proxy_relationship", 4, 1, "代理人/照护者关系", "text", None),
    ]:
        attrs = {"options": options} if options else {}
        if key == "proxy_relationship":
            attrs["visible_when"] = condition(
                icf + "signer_type", "法定代理人/照护者协助签署"
            )
        add("scr_t0_icf_" + key, 4, row, slot, label, icf + key, "T0", widget, **attrs)
    criteria = {
        "inclusion": [
            "年龄≥60周岁，海南本地连续居住≥5年",
            "SPPB≤9分、主观记忆下降且家属/照护者证实、MoCA≤22分",
            "拥有智能手机，能独立完成接听电话、打开微信、点击全屏等基础操作",
            "听懂普通话或海南主流方言，可完成沟通和评估",
        ],
        "exclusion": [
            "确诊痴呆或重度抑郁，或明显影响评估/干预配合的精神、神经疾病",
            "近3个月严重心脑血管事件或下肢骨折",
            "严重视力或听力缺陷，无法沟通、评估或使用平台",
            "手机无法安装或运行干预平台",
            "参与其他可能影响研究结果或安全性的临床研究",
            "未来12个月计划离开海南>3个月或预计无法完成随访",
        ],
    }
    for kind, table in [("inclusion", 5), ("exclusion", 6)]:
        for row, label in enumerate(criteria[kind], 1):
            storage = C + f"screening.{kind}_items.item_{row}."
            add(
                f"scr_t0_{kind}_{row}_judgment",
                table,
                row,
                0,
                label,
                storage + "judgment",
                "T0",
                "single_choice",
                options=["是", "否"],
            )
            add(
                f"scr_t0_{kind}_{row}_remark",
                table,
                row,
                1,
                "备注/依据",
                storage + "remark",
                "T0",
                include_in_completeness=False,
            )
    for key, row, slot, label, widget in [
        ("selected", 0, 0, "受试者入选", "single_choice"),
        ("failure_reason", 1, 0, "筛选失败原因", "text"),
        ("enter_followup", 2, 0, "进入干预/随访", "single_choice"),
        ("investigator_name", 3, 0, "研究者姓名", "text"),
        ("signed_on", 3, 1, "研究者签署日期", "date"),
    ]:
        attrs = {"options": ["是", "否"]} if widget == "single_choice" else {}
        if key == "failure_reason":
            attrs["visible_when"] = condition(
                C + "screening.enrollment_record.selected", "否"
            )
        add(
            "scr_t0_enrollment_" + key,
            7,
            row,
            slot,
            label,
            C + "screening.enrollment_record." + key,
            "T0",
            widget,
            **attrs,
        )


def _feedback(add, legacy):
    # 旧T0曾错误关联T1依从表；保留旧值入口但不让它占据T1原位。
    for key, label in [
        ("accept_continue", "是否接受/继续"),
        ("platform_id", "平台编号"),
        ("planned", "计划次数与时长"),
        ("actual", "实际次数与时长"),
        ("completion_rate", "完成率"),
        ("incomplete_reason", "未完成原因"),
        ("investigator_action", "研究者处理"),
    ]:
        legacy("adh_T0_" + key, 16, label + "旧记录", C + "adherence." + key, "T0")
    for vt, adherence, satisfaction, medication, ae in [
        ("T1", 16, 19, 20, 21),
        ("T2", 23, 26, 27, 28),
    ]:
        for key in ["planned", "actual"]:
            legacy(
                f"adh_{vt}_{key}",
                adherence,
                "训练次数与时长旧记录",
                C + "adherence." + key,
                vt,
            )
        for key, row, slot, label, widget in [
            ("accept_continue", 0, 0, "接受/继续干预", "single_choice"),
            ("decline_reason", 0, 1, "不接受/继续原因", "text"),
            ("platform_id", 1, 0, "平台编号", "text"),
            ("planned_count", 2, 0, "计划次数", "number"),
            ("planned_minutes", 2, 1, "计划时长", "number"),
            ("actual_count", 3, 0, "实际次数", "number"),
            ("actual_minutes", 3, 1, "实际时长", "number"),
            ("completion_rate", 4, 0, "完成率", "number"),
            ("incomplete_reason", 5, 0, "主要未完成原因", "single_choice"),
            ("incomplete_other_remark", 5, 1, "其他未完成原因", "text"),
            ("investigator_action", 6, 0, "研究者处理", "single_choice"),
            ("investigator_other_remark", 6, 1, "其他处理说明", "text"),
        ]:
            attrs = {}
            if key == "accept_continue":
                attrs["options"] = ["是", "否"]
            elif key == "incomplete_reason":
                attrs["options"] = [
                    "身体不适",
                    "不会操作",
                    "忘记",
                    "缺少照护者协助",
                    "设备/网络问题",
                    "其他",
                ]
            elif key == "investigator_action":
                attrs["options"] = [
                    "继续随访",
                    "强化指导",
                    "暂停干预",
                    "退出研究",
                    "其他",
                ]
            elif key in [
                "decline_reason",
                "incomplete_other_remark",
                "investigator_other_remark",
            ]:
                parent, value = {
                    "decline_reason": ("accept_continue", "否"),
                    "incomplete_other_remark": ("incomplete_reason", "其他"),
                    "investigator_other_remark": ("investigator_action", "其他"),
                }[key]
                attrs["visible_when"] = condition(C + "adherence." + parent, value)
            elif key.endswith("_count"):
                attrs.update(validation={"integer": True}, unit="次")
            elif key.endswith("_minutes"):
                attrs["unit"] = "分钟"
            elif key == "completion_rate":
                attrs.update(unit="%", validation={"max": 100})
            # 只在明确有效100%时隐藏。父字段未知/不适用或历史非法值需由
            # 条件执行器屏蔽旧标量；不能因比例待统计就隐藏已知研究原因。
            reason_visible = condition(C + "adherence.completion_rate", 100, "ne")
            if key == "incomplete_reason":
                attrs["visible_when"] = reason_visible
                attrs["required_when"] = {
                    "all": [
                        condition(C + "adherence.completion_rate", op="present"),
                        reason_visible,
                    ]
                }
            elif key == "incomplete_other_remark":
                attrs["visible_when"] = {"all": [reason_visible, attrs["visible_when"]]}
            add(
                f"adh_{vt}_{key}",
                adherence,
                row,
                slot,
                label,
                C + "adherence." + key,
                vt,
                widget,
                **attrs,
            )
        legacy(
            f"sat_{vt}_matrix_note",
            satisfaction,
            "满意度旧记录",
            C + "satisfaction.matrix_note",
            vt,
        )
        score_paths = []
        for row, (key, label) in enumerate(
            [
                ("operation", "操作简单、易学习"),
                ("clarity", "内容清楚、容易理解"),
                ("reminders", "提醒/反馈有助坚持训练"),
                ("burden", "不适或负担较小"),
                ("recommendation", "愿意继续使用或推荐"),
            ],
            1,
        ):
            storage = C + "satisfaction.items." + key + "."
            score_paths.append(storage + "score")
            add(
                f"sat_{vt}_{key}_score",
                satisfaction,
                row,
                0,
                label,
                storage + "score",
                vt,
                "number",
                validation={"integer": True, "min": 1, "max": 5},
                control="radio",
                options=[1, 2, 3, 4, 5],
            )
            add(
                f"sat_{vt}_{key}_remark",
                satisfaction,
                row,
                1,
                label + "备注",
                storage + "remark",
                vt,
                include_in_completeness=False,
            )
        add(
            f"sat_{vt}_overall_score",
            satisfaction,
            6,
            0,
            "总体满意度",
            C + "satisfaction.overall_score",
            vt,
            "number",
            validation={"integer": True, "min": 1, "max": 5},
            control="radio",
            options=[1, 2, 3, 4, 5],
        )
        add(
            f"sat_{vt}_total",
            satisfaction,
            6,
            1,
            "满意度总分",
            C + "satisfaction.total",
            vt,
            "number",
            validation={
                "integer": True,
                "min": 5,
                "max": 25,
                "consistency": {
                    "operation": "sum",
                    "operands": score_paths,
                    "when": "all_present",
                },
            },
        )
        for kind, table, has, label, rows, columns in [
            (
                "medication_change",
                medication,
                "has_changes",
                "用药变化",
                [2, 3],
                [
                    ("name", "药物名称", "text", 0),
                    ("indication", "用途/适应证", "text", 1),
                    ("started_on", "开始日期", "date", 2),
                    ("stopped_on", "停止日期", "date", 3),
                    ("ongoing", "仍在使用", "single_choice", 4),
                    ("dose_frequency", "剂量/频次", "text", 5),
                    ("remark", "备注", "text", 6),
                ],
            ),
            (
                "adverse_events",
                ae,
                "has_events",
                "不良事件",
                [2, 3, 4],
                [
                    ("occurred_on", "发生日期", "date", 0),
                    ("event_name", "事件名称/表现", "text", 1),
                    ("severity", "严重程度", "single_choice", 2),
                    ("is_sae", "是否SAE", "single_choice", 3),
                    ("relatedness", "与干预相关性", "single_choice", 4),
                    ("management_note", "处理", "text", 5),
                    ("outcome_note", "转归", "text", 5),
                ],
            ),
        ]:
            old_id = (
                f"crf_med_change_note_{vt.lower()}"
                if kind == "medication_change"
                else f"crf_ae_note_{vt.lower()}"
            )
            legacy(old_id, table, label + "旧记录", C + kind + ".note", vt)
            add(
                f"crf_{vt}_{has}",
                table,
                0,
                0,
                "有无" + label,
                C + kind + "." + has,
                vt,
                "single_choice",
                options=["否", "是"],
            )
            fid = f"crf_{vt}_{kind}_entries"
            parent = add(
                fid,
                table,
                None,
                0,
                label + "明细",
                C + kind + ".entries",
                vt,
                "table_repeat",
                children=[],
                row_id_key="_row_id",
                row_metadata_key="_field_meta",
                visible_when=condition(C + kind + "." + has, "是"),
                validation={"min_items_when_active": 1},
            )
            for key, col_label, widget, slot in columns:
                attrs = {"include_in_completeness": key != "remark"}
                options = {
                    "severity": ["轻", "中", "重"],
                    "is_sae": ["否", "是"],
                    "relatedness": ["无关", "可能", "很可能"],
                    "ongoing": ["已停用", "仍在使用"],
                }.get(key)
                if options:
                    attrs["options"] = options
                if key == "ongoing":
                    attrs["export_choice_mapping"] = {"已停用": {"value": None}}
                if key == "stopped_on":
                    attrs["visible_when"] = condition("ongoing", "已停用")
                if key in ["management_note", "outcome_note"]:
                    attrs["source_combination"] = {
                        "id": fid + "_management_outcome",
                        "operation": "join_labeled",
                        "separator": "\n",
                        "members": [fid + "_management_note", fid + "_outcome_note"],
                        "order": 0 if key == "management_note" else 1,
                        "label": col_label,
                    }
                child = _field(
                    fid + "_" + key,
                    table,
                    col_label,
                    key,
                    vt,
                    widget,
                    [
                        source_position(table, row, slot, repeat_index=i)
                        for i, row in enumerate(rows)
                    ],
                    **attrs,
                )
                parent["children"].append(child)


def _completion_and_qc(add, legacy):
    legacy("crf_completion", 29, "完成/退出旧记录", C + "completion", ALL_VISITS)
    legacy("crf_qc", 30, "质控旧记录", C + "qc", ALL_VISITS)
    p = C + "completion_record."
    for key, row, slot, label, widget, options in [
        (
            "status",
            0,
            0,
            "研究状态",
            "single_choice",
            ["完成全部随访", "提前退出", "失访", "死亡", "其他"],
        ),
        ("status_other", 0, 1, "其他状态说明", "text", None),
        ("date", 1, 0, "完成/退出日期", "date", None),
        (
            "withdrawal_reason",
            2,
            0,
            "退出/失访原因",
            "single_choice",
            [
                "撤回知情同意",
                "无法继续使用平台",
                "疾病进展/住院",
                "搬离海南/无法联系",
                "研究者判断不宜继续",
                "其他",
            ],
        ),
        ("withdrawal_other", 2, 1, "其他退出原因", "text", None),
        ("safety_followup", 3, 0, "退出前完成安全随访", "single_choice", ["是", "否"]),
        ("safety_note", 3, 1, "安全随访说明", "text", None),
        (
            "include_analysis",
            4,
            0,
            "纳入最终分析",
            "single_choice",
            ["是", "否", "待统计方案判定"],
        ),
    ]:
        attrs = {"export_visit_selection": "latest_recorded_with_conflict_check"}
        if options:
            attrs["options"] = options
        if key == "status_other":
            attrs["visible_when"] = condition(p + "status", "其他")
        if key in ["withdrawal_reason", "safety_followup", "safety_note"]:
            attrs["visible_when"] = condition(p + "status", ["提前退出", "失访"], "in")
        if key == "withdrawal_other":
            attrs["visible_when"] = {
                "all": [
                    condition(p + "status", ["提前退出", "失访"], "in"),
                    condition(p + "withdrawal_reason", "其他"),
                ]
            }
        if key == "safety_note":
            attrs["include_in_completeness"] = False
        add(
            "crf_completion_" + key,
            29,
            row,
            slot,
            label,
            p + key,
            ALL_VISITS,
            widget,
            **attrs,
        )
    for row, label in enumerate(
        [
            "必填项已填或注明不适用/不详",
            "纳排标准与筛选结论一致",
            "访视日期与时间窗记录完整",
            "量表原始分、分项分和总分一致",
            "不良事件和用药变化已核对",
            "修改按规范签名并注明日期",
        ],
        1,
    ):
        storage = C + f"qc_record.items.item_{row}."
        add(
            f"crf_qc_{row}_judgment",
            30,
            row,
            0,
            label,
            storage + "judgment",
            ALL_VISITS,
            "single_choice",
            options=["是", "否"],
            metadata_choice_mapping={"not_applicable": "不适用"},
            export_visit_selection="latest_recorded_with_conflict_check",
        )
        add(
            f"crf_qc_{row}_remark",
            30,
            row,
            1,
            "备注",
            storage + "remark",
            ALL_VISITS,
            include_in_completeness=False,
            export_visit_selection="latest_recorded_with_conflict_check",
        )
    for row, role, label in [
        (8, "investigator", "研究者"),
        (9, "reviewer", "质控人员"),
    ]:
        for slot, key, suffix, widget in [
            (0, "name", "姓名", "text"),
            (1, "signed_on", "日期", "date"),
        ]:
            add(
                f"crf_qc_{role}_{key}",
                30,
                row,
                slot,
                label + suffix,
                C + f"qc_record.{role}_{key}",
                ALL_VISITS,
                widget,
                export_visit_selection="latest_recorded_with_conflict_check",
            )
