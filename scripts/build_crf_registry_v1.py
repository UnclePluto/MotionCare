#!/usr/bin/env python3
"""Generate specs/patient-rehab-system/crf/registry.v1.json from CRF docx dump.

真源：docs/other/认知衰弱数字疗法研究_CRF表_修订稿.docx
对照：specs/patient-rehab-system/crf/_docx_table_dump.txt（由 dump_crf_docx_tables.py 生成）

运行：python scripts/build_crf_registry_v1.py
输出：specs/patient-rehab-system/crf/registry.v1.json
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "specs/patient-rehab-system/crf/registry.v1.json"

TABLE_TITLES = {
    "#T0": "筛选与受试者标识",
    "#T8": "人口学信息",
    "#T9": "手术史与过敏史",
    "#T10": "合并症、既往史与家族史",
    "#T11": "生活方式",
    "#T12": "合并用药",
}
BASELINE_SECTION_ORDER = ["#T0", "#T8", "#T9", "#T10", "#T11", "#T12"]

DISEASES: list[tuple[str, str]] = [
    ("cm_coronary", "冠心病"),
    ("cm_stroke", "脑卒中"),
    ("cm_hypertension", "高血压"),
    ("cm_diabetes", "糖尿病"),
    ("cm_hyperlipidemia", "高脂血症"),
    ("cm_gout", "痛风/高尿酸血症"),
    ("cm_copd", "慢性阻塞性肺疾病（COPD）"),
    ("cm_asthma", "支气管哮喘"),
    ("cm_kidney_stone", "肾结石"),
    ("cm_ckd", "慢性肾脏病"),
    ("cm_anemia", "贫血"),
    ("cm_osteo", "骨关节炎/骨质疏松"),
    ("cm_mood", "抑郁/焦虑"),
    ("cm_other", "其他"),
]

# 国家认定的 56 个民族（名称与常见统计口径一致）；选项末尾保留「其他」以配合 other_remark。
CHINA_56_ETHNICITIES: list[str] = [
    "汉族",
    "蒙古族",
    "回族",
    "藏族",
    "维吾尔族",
    "苗族",
    "彝族",
    "壮族",
    "布依族",
    "朝鲜族",
    "满族",
    "侗族",
    "瑶族",
    "白族",
    "土家族",
    "哈尼族",
    "哈萨克族",
    "傣族",
    "黎族",
    "傈僳族",
    "佤族",
    "畲族",
    "高山族",
    "拉祜族",
    "水族",
    "东乡族",
    "纳西族",
    "景颇族",
    "柯尔克孜族",
    "土族",
    "达斡尔族",
    "仫佬族",
    "羌族",
    "布朗族",
    "撒拉族",
    "毛南族",
    "仡佬族",
    "锡伯族",
    "阿昌族",
    "普米族",
    "塔吉克族",
    "怒族",
    "乌孜别克族",
    "俄罗斯族",
    "鄂温克族",
    "德昂族",
    "保安族",
    "裕固族",
    "京族",
    "塔塔尔族",
    "独龙族",
    "鄂伦春族",
    "赫哲族",
    "门巴族",
    "珞巴族",
    "基诺族",
]

MED_CATS: list[tuple[str, str]] = [
    ("med_antihypertensive", "降压药"),
    ("med_antidiabetic", "降糖药"),
    ("med_lipid", "降脂药"),
    ("med_inhaler", "支气管舒张剂/激素类吸入剂"),
    ("med_antiplatelet", "抗血小板/抗凝药"),
    ("med_cardiac", "心脏相关药物"),
    ("med_sedative", "镇静催眠药"),
    ("med_psych", "抗抑郁/抗焦虑药"),
    ("med_cognitive", "抗痴呆/改善认知药物"),
    ("med_bone", "骨质疏松/钙剂/维生素D"),
    ("med_pain", "止痛/抗炎/尿酸异常药物"),
    ("med_other_long", "其他长期药物"),
]


def field(
    field_id: str,
    table_ref: str,
    label_zh: str,
    widget: str,
    storage: str,
    *,
    required_for_complete: bool = False,
    visit_types: list[str] | None = None,
    options: list[str] | None = None,
    hint: str | None = None,
    doc_table_index: int | None = None,
    other_remark_storage: str | None = None,
    other_remark_widget: str | None = None,
) -> dict:
    d: dict = {
        "field_id": field_id,
        "table_ref": table_ref,
        "label_zh": label_zh,
        "widget": widget,
        "storage": storage,
        "required_for_complete": required_for_complete,
        "visit_types": visit_types,
    }
    if options is not None:
        d["options"] = options
    if hint:
        d["hint"] = hint
    if doc_table_index is not None:
        d["doc_table_index"] = doc_table_index
    if other_remark_storage is not None:
        d["other_remark_storage"] = other_remark_storage
    if other_remark_widget is not None:
        d["other_remark_widget"] = other_remark_widget
    return d


def baseline_table_layout() -> dict:
    """与 _docx_table_dump TABLE 9–13 对齐；TABLE 9 前两行字段在 #T0，#T8 从年龄起。"""
    t8_rows: list[dict] = [
        {
            "cells": [
                {"field_id": "dm_age_years"},
                {"field_id": "dm_birth_date"},
                {"field_id": "dm_ethnicity"},
            ]
        },
        {
            "cells": [
                {"field_id": "dm_gender"},
                {"field_id": "dm_marital"},
                {"blank": True},
            ]
        },
        {"cells": [{"field_id": "dm_address", "colspan": 3}]},
        {"cells": [{"field_id": "dm_insurance", "colspan": 3}]},
        {"cells": [{"field_id": "dm_education_level", "colspan": 3}]},
        {"cells": [{"field_id": "dm_education_years", "colspan": 3}]},
        {
            "cells": [
                {"field_id": "dm_children"},
                {"field_id": "dm_caregiver"},
                {"field_id": "dm_phone"},
            ]
        },
        {"cells": [{"field_id": "dm_income_band", "colspan": 3}]},
        {"cells": [{"field_id": "dm_income_afford", "colspan": 3}]},
        {"cells": [{"field_id": "dm_self_health", "colspan": 3}]},
    ]

    t10_rows: list[dict] = []
    for fid, _zh in DISEASES:
        t10_rows.append(
            {
                "cells": [
                    {"field_id": f"{fid}_family"},
                    {"field_id": f"{fid}_personal"},
                    {"field_id": f"{fid}_diagnosed_at"},
                ]
            }
        )
    t10_rows.append(
        {
            "cells": [
                {"field_id": "cm_gout_attack_1m"},
                {"field_id": "cm_other_history", "colspan": 2},
            ]
        }
    )

    t11_rows: list[dict] = [
        {"cells": [{"field_id": "ls_smoking"}, {"field_id": "ls_smoking_detail", "colspan": 2}]},
        {"cells": [{"field_id": "ls_drinking"}, {"field_id": "ls_drinking_detail", "colspan": 2}]},
        {"cells": [{"field_id": "ls_exercise", "colspan": 3}]},
        {"cells": [{"field_id": "ls_ipaq", "colspan": 3}]},
    ]

    t12_rows: list[dict] = []
    for slug, _zh in MED_CATS:
        t12_rows.append(
            {
                "cells": [
                    {"field_id": f"{slug}_uses"},
                    {"field_id": f"{slug}_detail", "colspan": 2},
                ]
            }
        )
    t12_rows.append(
        {
            "cells": [
                {"field_id": "med_count_regular"},
                {"blank": True},
                {"blank": True},
            ]
        }
    )

    return {
        "#T0": {
            "rows": [
                {"cells": [{"field_id": "pb_subject_id"}, {"field_id": "pb_name_initials"}]},
            ]
        },
        "#T8": {"rows": t8_rows},
        "#T9": {
            "rows": [
                {"cells": [{"field_id": "sa_has_surgery", "colspan": 2}]},
                {"cells": [{"field_id": "sa_surgeries_note", "colspan": 2}]},
                {"cells": [{"field_id": "sa_has_allergy", "colspan": 2}]},
                {"cells": [{"field_id": "sa_allergies_note", "colspan": 2}]},
            ]
        },
        "#T10": {"rows": t10_rows},
        "#T11": {"rows": t11_rows},
        "#T12": {"rows": t12_rows},
    }


def main() -> None:
    fields: list[dict] = []

    # --- Patient baseline: 封面/识别（与 PatientBaseline 列 + demographics 混合）---
    fields.append(
        field(
            "pb_subject_id",
            "#T0",
            "受试者编号",
            "text",
            "patient_baseline.subject_id",
            required_for_complete=True,
            doc_table_index=1,
        )
    )
    fields.append(
        field(
            "pb_name_initials",
            "#T0",
            "受试者姓名缩写",
            "text",
            "patient_baseline.name_initials",
            doc_table_index=1,
        )
    )

    # --- #T8 人口学（TABLE 9 in dump）---
    fields += [
        field("dm_age_years", "#T8", "年龄（周岁）", "number", "patient_baseline.demographics.age_years", doc_table_index=9),
        field("dm_birth_date", "#T8", "出生日期", "date", "patient_baseline.demographics.birth_date", doc_table_index=9),
        field(
            "dm_gender",
            "#T8",
            "性别",
            "single_choice",
            "patient_baseline.demographics.gender",
            options=["男", "女"],
            doc_table_index=9,
        ),
        field(
            "dm_marital",
            "#T8",
            "婚姻状况",
            "single_choice",
            "patient_baseline.demographics.marital_status",
            options=["已婚", "未婚", "离异", "丧偶", "其他"],
            doc_table_index=9,
            other_remark_storage="patient_baseline.demographics.marital_status_other_remark",
            other_remark_widget="text",
        ),
        field("dm_address", "#T8", "居住地址", "textarea", "patient_baseline.demographics.address", doc_table_index=9),
        field(
            "dm_ethnicity",
            "#T8",
            "民族",
            "single_choice",
            "patient_baseline.demographics.ethnicity",
            options=[*CHINA_56_ETHNICITIES, "其他"],
            doc_table_index=9,
            other_remark_storage="patient_baseline.demographics.ethnicity_other_remark",
            other_remark_widget="text",
        ),
        field(
            "dm_insurance",
            "#T8",
            "医保类型",
            "single_choice",
            "patient_baseline.demographics.insurance_type",
            options=["城镇职工医保", "城乡居民医保/新农合", "公费医疗", "商业保险", "自费", "其他"],
            doc_table_index=9,
            other_remark_storage="patient_baseline.demographics.insurance_type_other_remark",
            other_remark_widget="text",
        ),
        field(
            "dm_education_level",
            "#T8",
            "文化水平",
            "single_choice",
            "patient_baseline.demographics.education_level",
            options=[
                "无受教育经历",
                "小学",
                "初中",
                "高中/中专",
                "大专/本科",
                "研究生及以上",
            ],
            doc_table_index=9,
        ),
        field(
            "dm_education_years",
            "#T8",
            "教育年限（年）",
            "number",
            "patient_baseline.demographics.education_years",
            required_for_complete=True,
            doc_table_index=9,
        ),
        field("dm_children", "#T8", "子女情况", "text", "patient_baseline.demographics.children_note", doc_table_index=9),
        field("dm_caregiver", "#T8", "主要照护者", "text", "patient_baseline.demographics.caregiver", doc_table_index=9),
        field("dm_phone", "#T8", "联系电话", "text", "patient_baseline.demographics.contact_phones", doc_table_index=9),
        field(
            "dm_income_band",
            "#T8",
            "个人收入水平",
            "single_choice",
            "patient_baseline.demographics.income_band",
            options=[
                "<1000元/月",
                "1000-<2000元/月",
                "2000-<5000元/月",
                "5000-<10000元/月",
                "≥10000元/月",
                "拒答/不详",
            ],
            doc_table_index=9,
        ),
        field(
            "dm_income_afford",
            "#T8",
            "当前收入是否能维持日常开支",
            "single_choice",
            "patient_baseline.demographics.income_afford",
            options=["足够", "刚好", "不够", "很不够", "不详"],
            doc_table_index=9,
        ),
        field(
            "dm_self_health",
            "#T8",
            "自我健康评价",
            "single_choice",
            "patient_baseline.demographics.self_health",
            options=["很好", "好", "一般", "差", "很差"],
            doc_table_index=9,
        ),
    ]

    # --- #T9 手术/过敏（TABLE 10）---
    fields += [
        field(
            "sa_has_surgery",
            "#T9",
            "是否有手术史",
            "single_choice",
            "patient_baseline.surgery_allergy.has_surgery",
            options=["否", "是"],
            doc_table_index=10,
        ),
        field(
            "sa_surgeries_note",
            "#T9",
            "手术史明细（名称/日期/医院）",
            "textarea",
            "patient_baseline.surgery_allergy.surgeries_note",
            doc_table_index=10,
        ),
        field(
            "sa_has_allergy",
            "#T9",
            "是否有过敏史",
            "single_choice",
            "patient_baseline.surgery_allergy.has_allergy",
            options=["否", "是"],
            doc_table_index=10,
        ),
        field(
            "sa_allergies_note",
            "#T9",
            "过敏史明细",
            "textarea",
            "patient_baseline.surgery_allergy.allergies_note",
            doc_table_index=10,
        ),
    ]

    # --- #T10 既往病史与家族史（TABLE 11 疾病行）---
    for fid, zh in DISEASES:
        fields.append(
            field(
                fid + "_family",
                "#T10",
                f"{zh}（家族史）",
                "single_choice",
                f"patient_baseline.comorbidities.{fid}.family",
                options=["不详", "否", "是"],
                doc_table_index=11,
            )
        )
        fields.append(
            field(
                fid + "_personal",
                "#T10",
                f"{zh}（个人疾病史）",
                "single_choice",
                f"patient_baseline.comorbidities.{fid}.personal",
                options=["不详", "否", "是"],
                doc_table_index=11,
            )
        )
        fields.append(
            field(
                fid + "_diagnosed_at",
                "#T10",
                f"{zh} 确诊时间",
                "date",
                f"patient_baseline.comorbidities.{fid}.diagnosed_at",
                doc_table_index=11,
            )
        )

    fields += [
        field(
            "cm_gout_attack_1m",
            "#T10",
            "近1个月内是否急性痛风发作",
            "single_choice",
            "patient_baseline.comorbidities.gout_attack_1m",
            options=["否", "是"],
            doc_table_index=11,
        ),
        field(
            "cm_other_history",
            "#T10",
            "其他重要病史补充",
            "textarea",
            "patient_baseline.comorbidities.other_history",
            doc_table_index=11,
        ),
    ]

    # --- #T11 行为习惯（TABLE 12）---
    fields.append(
        field(
            "ls_smoking",
            "#T11",
            "吸烟状态",
            "single_choice",
            "patient_baseline.lifestyle.smoking_status",
            options=["从不吸烟", "已戒烟", "目前吸烟"],
            doc_table_index=12,
        )
    )
    fields.append(field("ls_smoking_detail", "#T11", "吸烟详情", "textarea", "patient_baseline.lifestyle.smoking_detail", doc_table_index=12))
    fields.append(
        field(
            "ls_drinking",
            "#T11",
            "饮酒状态",
            "single_choice",
            "patient_baseline.lifestyle.drinking_status",
            options=["从不饮酒", "已戒酒", "目前饮酒"],
            doc_table_index=12,
        )
    )
    fields.append(field("ls_drinking_detail", "#T11", "饮酒详情", "textarea", "patient_baseline.lifestyle.drinking_detail", doc_table_index=12))
    fields.append(field("ls_exercise", "#T11", "规律体育运动", "textarea", "patient_baseline.lifestyle.exercise", doc_table_index=12))
    fields.append(field("ls_ipaq", "#T11", "过去7天活动与静坐", "textarea", "patient_baseline.lifestyle.ipaq_note", doc_table_index=12))

    # --- #T12 基线用药（TABLE 13 按类别）---
    for slug, zh in MED_CATS:
        fields.append(
            field(
                slug + "_uses",
                "#T12",
                f"{zh}是否服用",
                "single_choice",
                f"patient_baseline.baseline_medications.{slug}.uses",
                options=["否", "是"],
                doc_table_index=13,
            )
        )
        fields.append(
            field(
                slug + "_detail",
                "#T12",
                f"{zh}药物种类或名称",
                "textarea",
                f"patient_baseline.baseline_medications.{slug}.detail",
                doc_table_index=13,
            )
        )
    fields.append(
        field(
            "med_count_regular",
            "#T12",
            "常用药物数量（近1-2个月规律服用）",
            "number",
            "patient_baseline.baseline_medications.regular_count",
            doc_table_index=13,
        )
    )

    # --- 访视：机能与 MoCA（与现有 assessments 契约对齐）---
    for vt in ("T0", "T1", "T2"):
        fields += [
            field(
                f"as_{vt}_sppb_balance",
                "#T13",
                "SPPB 平衡得分",
                "number",
                "visit.form_data.assessments.sppb.balance",
                visit_types=[vt],
                doc_table_index=14 if vt == "T0" else (18 if vt == "T1" else 25),
            ),
            field(
                f"as_{vt}_sppb_gait",
                "#T13",
                "SPPB 步速得分",
                "number",
                "visit.form_data.assessments.sppb.gait",
                visit_types=[vt],
                doc_table_index=14,
            ),
            field(
                f"as_{vt}_sppb_chair",
                "#T13",
                "SPPB 坐立得分",
                "number",
                "visit.form_data.assessments.sppb.chair_stand",
                visit_types=[vt],
                doc_table_index=14,
            ),
            field(
                f"as_{vt}_sppb_total",
                "#T13",
                "SPPB总分",
                "number",
                "visit.form_data.assessments.sppb.total",
                required_for_complete=True,
                visit_types=[vt],
                doc_table_index=14,
            ),
            field(
                f"as_{vt}_tug",
                "#T13",
                "TUG（秒）",
                "number",
                "visit.form_data.assessments.tug_seconds",
                visit_types=[vt],
                doc_table_index=14,
            ),
            field(
                f"as_{vt}_grip",
                "#T13",
                "握力最大值（kg）",
                "number",
                "visit.form_data.assessments.grip_strength_kg",
                visit_types=[vt],
                doc_table_index=14,
            ),
            field(
                f"as_{vt}_frailty",
                "#T13",
                "衰弱判定",
                "single_choice",
                "visit.form_data.assessments.frailty",
                options=["robust", "pre_frail", "frail"],
                hint="存储为 robust/pre_frail/frail，与后端现有一致",
                visit_types=[vt],
                doc_table_index=14,
            ),
            field(
                f"as_{vt}_physical_free_text",
                "#T13",
                "身体机能评估（原文长字段：围度/分项描述等）",
                "textarea",
                "visit.form_data.assessments.physical_free_text",
                visit_types=[vt],
                doc_table_index=14,
            ),
        ]
        # MoCA 分项 + 总分
        moca_parts = [
            ("visuospatial", "视空间与执行功能"),
            ("naming", "命名"),
            ("attention", "注意"),
            ("language", "语言"),
            ("abstraction", "抽象"),
            ("delayed_recall", "延迟回忆"),
            ("orientation", "定向"),
            ("education_bonus", "教育修正加分"),
        ]
        for key, zh in moca_parts:
            fields.append(
                field(
                    f"as_{vt}_moca_{key}",
                    "#T14",
                    f"MoCA {zh}（原始分）",
                    "number",
                    f"visit.form_data.assessments.moca.subscores.{key}",
                    visit_types=[vt],
                    doc_table_index=15 if vt == "T0" else (19 if vt == "T1" else 26),
                )
            )
        fields.append(
            field(
                f"as_{vt}_moca_total",
                "#T14",
                "MoCA总分",
                "number",
                "visit.form_data.assessments.moca.total",
                required_for_complete=True,
                visit_types=[vt],
                doc_table_index=15,
            )
        )
        fields.append(
            field(
                f"as_{vt}_moca_leq22",
                "#T14",
                "MoCA 是否≤22分",
                "single_choice",
                "visit.form_data.assessments.moca.leq22",
                options=["否", "是"],
                visit_types=[vt],
                doc_table_index=15,
            )
        )

    # --- 访视日期（模型列）---
    for vt in ("T0", "T1", "T2"):
        fields.append(
            field(
                f"vd_{vt}_visit_date",
                "#T3",
                "访视日期",
                "date",
                "visit.visit_date",
                required_for_complete=True,
                visit_types=[vt],
                doc_table_index=4,
            )
        )

    # --- T0 筛选/访视元信息（TABLE 4–8）---
    fields += [
        field(
            "scr_t0_visit_meta",
            "#T4",
            "T0 访视信息（周数/时间窗/评估者等，原文）",
            "textarea",
            "visit.form_data.crf.screening.visit_meta",
            visit_types=["T0"],
            doc_table_index=4,
        ),
        field(
            "scr_t0_icf",
            "#T5",
            "知情同意签署信息（原文）",
            "textarea",
            "visit.form_data.crf.screening.icf",
            visit_types=["T0"],
            doc_table_index=5,
        ),
        field(
            "scr_t0_inclusion",
            "#T6",
            "纳入标准判定（原文）",
            "textarea",
            "visit.form_data.crf.screening.inclusion",
            visit_types=["T0"],
            doc_table_index=6,
        ),
        field(
            "scr_t0_exclusion",
            "#T7",
            "排除标准判定（原文）",
            "textarea",
            "visit.form_data.crf.screening.exclusion",
            visit_types=["T0"],
            doc_table_index=7,
        ),
        field(
            "scr_t0_enrollment",
            "#筛选结论",
            "筛选结论（入选/筛选失败等，原文）",
            "textarea",
            "visit.form_data.crf.screening.enrollment",
            visit_types=["T0"],
            doc_table_index=8,
        ),
    ]

    # --- crf：依从性（T0/T1/T2 均有）、满意度（T1/T2）、合并用药/不良事件/完成 ---
    def crf_adherence(vt: str, table_ref: str, doc_idx: int) -> None:
        p = f"adh_{vt}_"
        fields.extend(
            [
                field(
                    p + "accept_continue",
                    table_ref,
                    "是否接受/继续数字疗法干预",
                    "text",
                    "visit.form_data.crf.adherence.accept_continue",
                    visit_types=[vt],
                    doc_table_index=doc_idx,
                ),
                field(
                    p + "platform_id",
                    table_ref,
                    "平台账号/编号",
                    "text",
                    "visit.form_data.crf.adherence.platform_id",
                    visit_types=[vt],
                    doc_table_index=doc_idx,
                ),
                field(
                    p + "planned",
                    table_ref,
                    "计划训练/使用次数与时长",
                    "text",
                    "visit.form_data.crf.adherence.planned",
                    visit_types=[vt],
                    doc_table_index=doc_idx,
                ),
                field(
                    p + "actual",
                    table_ref,
                    "实际完成次数与时长",
                    "text",
                    "visit.form_data.crf.adherence.actual",
                    visit_types=[vt],
                    doc_table_index=doc_idx,
                ),
                field(
                    p + "completion_rate",
                    table_ref,
                    "完成率（%）",
                    "number",
                    "visit.form_data.crf.adherence.completion_rate",
                    visit_types=[vt],
                    doc_table_index=doc_idx,
                ),
                field(
                    p + "incomplete_reason",
                    table_ref,
                    "主要未完成原因",
                    "textarea",
                    "visit.form_data.crf.adherence.incomplete_reason",
                    visit_types=[vt],
                    doc_table_index=doc_idx,
                ),
                field(
                    p + "investigator_action",
                    table_ref,
                    "研究者处理",
                    "text",
                    "visit.form_data.crf.adherence.investigator_action",
                    visit_types=[vt],
                    doc_table_index=doc_idx,
                ),
            ]
        )

    crf_adherence("T0", "#T16", 17)
    crf_adherence("T1", "#T16", 17)
    crf_adherence("T2", "#T23", 24)

    def crf_satisfaction(vt: str, table_ref: str, doc_idx: int) -> None:
        p = f"sat_{vt}_"
        fields.append(
            field(
                p + "matrix_note",
                table_ref,
                "数字疗法平台满意度（条目与总分，原文记录）",
                "textarea",
                "visit.form_data.crf.satisfaction.matrix_note",
                visit_types=[vt],
                doc_table_index=doc_idx,
            )
        )

    crf_satisfaction("T1", "#T19", 20)
    crf_satisfaction("T2", "#T26", 27)
    fields.append(
        field(
            "crf_med_change_note_t1",
            "#T20",
            "合并用药变化（T1）",
            "textarea",
            "visit.form_data.crf.medication_change.note",
            visit_types=["T1"],
            doc_table_index=21,
        )
    )
    fields.append(
        field(
            "crf_med_change_note_t2",
            "#T27",
            "合并用药变化（T2）",
            "textarea",
            "visit.form_data.crf.medication_change.note",
            visit_types=["T2"],
            doc_table_index=28,
        )
    )
    fields.append(
        field(
            "crf_ae_note_t1",
            "#T21",
            "不良事件（T1）",
            "textarea",
            "visit.form_data.crf.adverse_events.note",
            visit_types=["T1"],
            doc_table_index=22,
        )
    )
    fields.append(
        field(
            "crf_ae_note_t2",
            "#T28",
            "不良事件（T2）",
            "textarea",
            "visit.form_data.crf.adverse_events.note",
            visit_types=["T2"],
            doc_table_index=29,
        )
    )
    fields.append(
        field(
            "crf_completion",
            "#T29",
            "完成/退出记录",
            "textarea",
            "visit.form_data.crf.completion",
            visit_types=["T2"],
            doc_table_index=30,
        )
    )
    fields.append(
        field(
            "crf_qc",
            "#T30",
            "质控核查",
            "textarea",
            "visit.form_data.crf.qc",
            visit_types=["T0", "T1", "T2"],
            doc_table_index=31,
        )
    )

    doc = {
        "template_id": "cognitive_frailty_digital_therapy_crf",
        "template_revision": "1.1（修订稿 2026-04-28）",
        "source_docx": "docs/other/认知衰弱数字疗法研究_CRF表_修订稿.docx",
        "table_titles": TABLE_TITLES,
        "baseline_section_order": BASELINE_SECTION_ORDER,
        "baseline_table_layout": baseline_table_layout(),
        "fields": fields,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Wrote", OUT, "fields:", len(fields))


if __name__ == "__main__":
    main()
