"""基线字段；原标量及历史文本保留，新明细使用独立节点。"""

from __future__ import annotations

from .schema import source_position

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


def _legacy_baseline_fields() -> list[dict]:
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
        field(
            "dm_age_years",
            "#T8",
            "年龄（周岁）",
            "number",
            "patient_baseline.demographics.age_years",
            doc_table_index=9,
        ),
        field(
            "dm_birth_date",
            "#T8",
            "出生日期",
            "date",
            "patient_baseline.demographics.birth_date",
            doc_table_index=9,
        ),
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
        field(
            "dm_address",
            "#T8",
            "居住地址",
            "textarea",
            "patient_baseline.demographics.address",
            doc_table_index=9,
        ),
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
            options=[
                "城镇职工医保",
                "城乡居民医保/新农合",
                "公费医疗",
                "商业保险",
                "自费",
                "其他",
            ],
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
        field(
            "dm_children",
            "#T8",
            "子女情况",
            "text",
            "patient_baseline.demographics.children_note",
            doc_table_index=9,
        ),
        field(
            "dm_caregiver",
            "#T8",
            "主要照护者",
            "text",
            "patient_baseline.demographics.caregiver",
            doc_table_index=9,
        ),
        field(
            "dm_phone",
            "#T8",
            "联系电话",
            "text",
            "patient_baseline.demographics.contact_phones",
            doc_table_index=9,
        ),
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
    fields.append(
        field(
            "ls_smoking_detail",
            "#T11",
            "吸烟详情",
            "textarea",
            "patient_baseline.lifestyle.smoking_detail",
            doc_table_index=12,
        )
    )
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
    fields.append(
        field(
            "ls_drinking_detail",
            "#T11",
            "饮酒详情",
            "textarea",
            "patient_baseline.lifestyle.drinking_detail",
            doc_table_index=12,
        )
    )
    fields.append(
        field(
            "ls_exercise",
            "#T11",
            "规律体育运动",
            "textarea",
            "patient_baseline.lifestyle.exercise",
            doc_table_index=12,
        )
    )
    fields.append(
        field(
            "ls_ipaq",
            "#T11",
            "过去7天活动与静坐",
            "textarea",
            "patient_baseline.lifestyle.ipaq_note",
            doc_table_index=12,
        )
    )

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

    return fields


def build_baseline_fields() -> list[dict]:
    fields = _legacy_baseline_fields()
    by_id = {f["field_id"]: f for f in fields}

    def bind(fid, table, row, slot=0):
        by_id[fid].setdefault("source_positions", []).append(
            source_position(table, row, slot)
        )

    def add(fid, table, row, slot, label, storage, widget="text", **attributes):
        value = field(
            fid,
            f"#T{table}",
            label,
            widget,
            "patient_baseline." + storage,
            doc_table_index=table,
        )
        value.update(attributes)
        fields.append(value)
        by_id[fid] = value
        bind(fid, table, row, slot)
        return value

    def condition(storage, value, op="eq"):
        return {"storage": "patient_baseline." + storage, "op": op, "value": value}

    # 被结构化节点替代的历史总文本仍可读取；不猜测和拆解其含义。
    for fid in (
        "dm_address",
        "dm_children",
        "dm_caregiver",
        "dm_phone",
        "sa_surgeries_note",
        "sa_allergies_note",
        "ls_smoking_detail",
        "ls_drinking_detail",
        "ls_exercise",
        "ls_ipaq",
    ):
        by_id[fid]["legacy"] = True
        by_id[fid]["include_in_completeness"] = False
    for slug, _ in MED_CATS:
        if slug not in ("med_sedative", "med_psych"):
            by_id[slug + "_detail"].update(legacy=True, include_in_completeness=False)

    bind("pb_subject_id", 0, 7)
    bind("pb_subject_id", 8, 1)
    bind("pb_name_initials", 0, 8)
    bind("pb_name_initials", 8, 2)
    add(
        "doc_protocol_number",
        0,
        2,
        0,
        "方案编号",
        "demographics.document.protocol_number",
    )
    add(
        "doc_enrolled_on",
        0,
        9,
        0,
        "筛选/入组日期",
        "demographics.document.enrolled_on",
        "date",
    )
    add(
        "doc_investigator_name",
        0,
        10,
        0,
        "研究者姓名",
        "demographics.document.investigator_name",
    )
    add(
        "doc_revision_1_0_name",
        1,
        1,
        0,
        "1.0版修订者/确认者",
        "demographics.document.revision_1_0_name",
    )
    add(
        "doc_revision_1_1_name",
        1,
        2,
        0,
        "1.1版修订者/确认者",
        "demographics.document.revision_1_1_name",
    )
    for fid, row in (
        ("dm_age_years", 3),
        ("dm_birth_date", 4),
        ("dm_gender", 5),
        ("dm_marital", 6),
        ("dm_ethnicity", 8),
        ("dm_insurance", 9),
        ("dm_education_level", 10),
        ("dm_education_years", 11),
        ("dm_income_band", 15),
        ("dm_income_afford", 16),
        ("dm_self_health", 17),
    ):
        bind(fid, 8, row)
    for fid, row, key, label, parent in (
        (
            "dm_marital_other",
            6,
            "marital_status_other_remark",
            "其他婚姻状况",
            "marital_status",
        ),
        ("dm_ethnicity_other", 8, "ethnicity_other_remark", "其他民族", "ethnicity"),
        (
            "dm_insurance_other",
            9,
            "insurance_type_other_remark",
            "其他医保",
            "insurance_type",
        ),
    ):
        add(
            fid,
            8,
            row,
            1,
            label,
            "demographics." + key,
            visible_when=condition("demographics." + parent, "其他"),
        )
    by_id["dm_ethnicity"]["export_choice_mapping"] = {
        name: {"value": "其他", "other_text": name}
        for name in CHINA_56_ETHNICITIES
        if name not in ("汉族", "黎族", "苗族")
    }
    for i, (key, label) in enumerate(
        (
            ("city_county", "市/县"),
            ("district_town", "区/镇/乡"),
            ("village_community", "村/社区"),
            ("detail", "详细地址"),
        )
    ):
        add("dm_address_" + key, 8, 7, i, label, "demographics.address_record." + key)
    add(
        "dm_has_children",
        8,
        12,
        0,
        "子女情况",
        "demographics.children_record.has_children",
        "single_choice",
        options=["有", "无子女"],
    )
    add(
        "dm_children_count",
        8,
        12,
        1,
        "子女数量",
        "demographics.children_record.count",
        "number",
        unit="人",
        integer=True,
        min=0,
        visible_when=condition("demographics.children_record.has_children", "有"),
    )
    add(
        "dm_caregiver_type",
        8,
        13,
        0,
        "主要照护者",
        "demographics.caregiver_record.type",
        "single_choice",
        options=["本人", "配偶", "子女", "亲属", "护工", "其他"],
    )
    add(
        "dm_caregiver_other",
        8,
        13,
        1,
        "其他照护者",
        "demographics.caregiver_record.other",
        visible_when=condition("demographics.caregiver_record.type", "其他"),
    )
    add(
        "dm_caregiver_contact",
        8,
        13,
        2,
        "照护者联系方式",
        "demographics.caregiver_record.contact",
    )
    add(
        "dm_contact_self",
        8,
        14,
        0,
        "本人联系电话",
        "demographics.contact_record.self_phone",
    )
    add(
        "dm_contact_backup",
        8,
        14,
        1,
        "备用联系人电话",
        "demographics.contact_record.backup_phone",
    )

    bind("sa_has_surgery", 9, 0)
    bind("sa_has_allergy", 9, 5)
    for fid, key, label, rows, columns, has in (
        (
            "sa_surgery_records",
            "surgery_records",
            "手术记录",
            [2, 3, 4],
            [
                ("name", "手术名称", "text"),
                ("date", "手术日期", "date"),
                ("hospital_note", "医院/备注", "text"),
            ],
            "has_surgery",
        ),
        (
            "sa_allergy_records",
            "allergy_records",
            "过敏记录",
            [7, 8],
            [
                ("category", "过敏原类别", "single_choice"),
                ("allergen", "具体过敏原", "text"),
                ("manifestation", "过敏表现", "text"),
                ("severity_treatment", "严重程度/处理", "text"),
            ],
            "has_allergy",
        ),
    ):
        parent = field(
            fid,
            "#T9",
            label,
            "table_repeat",
            "patient_baseline.surgery_allergy." + key,
            doc_table_index=9,
        )
        parent.update(
            row_id_key="_row_id",
            row_metadata_key="_field_meta",
            visible_when=condition("surgery_allergy." + has, "是"),
            children=[],
        )
        for slot, (column, col_label, widget) in enumerate(columns):
            child = field(
                fid + "_" + column, "#T9", col_label, widget, column, doc_table_index=9
            )
            child["source_positions"] = [
                source_position(9, row, slot, repeat_index=i)
                for i, row in enumerate(rows)
            ]
            if column == "hospital_note":
                child["include_in_completeness"] = False
            if column == "category":
                child["options"] = ["药物", "食物", "其他"]
            parent["children"].append(child)
        fields.append(parent)
        by_id[fid] = parent

    for row, (fid, label) in enumerate(DISEASES, 1):
        path = "comorbidities." + fid
        bind(fid + "_family", 10, row, 0)
        bind(fid + "_personal", 10, row, 2)
        bind(fid + "_diagnosed_at", 10, row, 3)
        by_id[fid + "_diagnosed_at"].update(
            date_precision="month",
            legacy_date_formats=["YYYY-MM-DD"],
            visible_when=condition(path + ".personal", "是"),
        )
        add(
            fid + "_family_count",
            10,
            row,
            1,
            label + "家族患病人数",
            path + ".family_count",
            "number",
            unit="人",
            integer=True,
            min=0,
            visible_when=condition(path + ".family", "是"),
        )
        add(
            fid + "_note",
            10,
            row,
            4,
            label + "备注",
            path + ".note",
            include_in_completeness=False,
        )
        # “不详”保留为兼容读值；新状态写入 metadata，不能写成数值或中文拼接。
        for suffix in ("_family", "_personal"):
            by_id[fid + suffix]["legacy_options"] = ["不详"]
            by_id[fid + suffix]["options"] = ["否", "是"]
    bind("cm_gout_attack_1m", 10, 15)
    bind("cm_other_history", 10, 16)
    by_id["cm_other_history"]["include_in_completeness"] = False
    add(
        "cm_gout_attack_count",
        10,
        15,
        1,
        "痛风发作次数",
        "comorbidities.gout_attack_count",
        "number",
        unit="次",
        integer=True,
        min=0,
        visible_when=condition("comorbidities.gout_attack_1m", "是"),
    )
    add(
        "cm_gout_attack_treatment",
        10,
        15,
        2,
        "痛风发作处理",
        "comorbidities.gout_attack_treatment",
        visible_when=condition("comorbidities.gout_attack_1m", "是"),
    )

    bind("ls_smoking", 11, 1)
    bind("ls_drinking", 11, 4)
    for fid, row, slot, label, path, widget, attrs in [
        (
            "ls_smoking_daily",
            2,
            0,
            "每日吸烟量",
            "smoking_record.daily_cigarettes",
            "number",
            dict(unit="支/天", integer=True),
        ),
        (
            "ls_smoking_pack_years",
            2,
            1,
            "累计包年",
            "smoking_record.pack_years",
            "number",
            dict(unit="包年"),
        ),
        (
            "ls_smoking_quit_date",
            3,
            0,
            "戒烟日期",
            "smoking_record.quit_date",
            "date",
            {},
        ),
        (
            "ls_smoking_before_quit",
            3,
            1,
            "戒烟前每日吸烟量",
            "smoking_record.before_quit_daily_cigarettes",
            "number",
            dict(unit="支/天", integer=True),
        ),
        (
            "ls_drinking_types",
            5,
            0,
            "饮酒种类",
            "drinking_record.types",
            "multi_choice",
            dict(options=["啤酒", "白酒≥40度", "白酒<40度", "红酒", "黄酒", "其他"]),
        ),
        (
            "ls_drinking_other",
            5,
            1,
            "其他酒类",
            "drinking_record.other_type",
            "text",
            {},
        ),
        (
            "ls_drinking_ml",
            5,
            2,
            "每周饮酒量",
            "drinking_record.weekly_ml",
            "number",
            dict(unit="ml", alternative_group="current_alcohol_amount"),
        ),
        (
            "ls_drinking_units",
            5,
            3,
            "每周饮酒单位",
            "drinking_record.weekly_units",
            "number",
            dict(unit="饮酒单位", alternative_group="current_alcohol_amount"),
        ),
        (
            "ls_drinking_quit_date",
            6,
            0,
            "戒酒日期",
            "drinking_record.quit_date",
            "date",
            {},
        ),
        (
            "ls_drinking_before_ml",
            6,
            1,
            "戒酒前每周饮酒量",
            "drinking_record.before_quit_weekly_ml",
            "number",
            dict(unit="ml", alternative_group="previous_alcohol_amount"),
        ),
        (
            "ls_drinking_before_units",
            6,
            2,
            "戒酒前每周饮酒单位",
            "drinking_record.before_quit_weekly_units",
            "number",
            dict(unit="饮酒单位", alternative_group="previous_alcohol_amount"),
        ),
        (
            "ls_regular_activity",
            7,
            0,
            "规律体育运动",
            "activity_record.regular",
            "single_choice",
            dict(options=["否", "是"]),
        ),
        ("ls_activity_type", 7, 1, "运动类型", "activity_record.type", "text", {}),
        (
            "ls_activity_frequency",
            7,
            2,
            "运动频次",
            "activity_record.frequency_per_week",
            "number",
            dict(unit="次/周", integer=True),
        ),
        (
            "ls_activity_minutes",
            7,
            3,
            "每次运动时长",
            "activity_record.minutes_per_session",
            "number",
            dict(unit="分钟"),
        ),
        (
            "ls_sitting_hours",
            11,
            0,
            "每日静坐时间",
            "activity_record.sitting_hours_per_day",
            "number",
            dict(unit="小时/天", max=24),
        ),
        (
            "ls_sedentary",
            12,
            0,
            "久坐习惯",
            "activity_record.sedentary",
            "single_choice",
            dict(options=["否", "是"]),
        ),
        (
            "ls_sedentary_hours",
            12,
            1,
            "通常久坐时间",
            "activity_record.sedentary_hours_per_day",
            "number",
            dict(unit="小时/天", max=24),
        ),
    ]:
        if row in (2, 3):
            attrs["visible_when"] = condition(
                "lifestyle.smoking_status", "目前吸烟" if row == 2 else "已戒烟"
            )
        if row in (5, 6):
            attrs["visible_when"] = condition(
                "lifestyle.drinking_status", "目前饮酒" if row == 5 else "已戒酒"
            )
        if row == 7 and slot > 0:
            attrs["visible_when"] = condition("lifestyle.activity_record.regular", "是")
        if row == 12 and slot == 1:
            attrs["visible_when"] = condition(
                "lifestyle.activity_record.sedentary", "是"
            )
        add(fid, 11, row, slot, label, "lifestyle." + path, widget, **attrs)
    by_id["ls_drinking_other"]["visible_when"] = {
        "all": [
            condition("lifestyle.drinking_status", "目前饮酒"),
            condition("lifestyle.drinking_record.types", "其他", "contains"),
        ]
    }
    for row, key, label in (
        (8, "vigorous", "重体力活动"),
        (9, "moderate", "中等强度活动"),
        (10, "walking", "步行超过10分钟"),
    ):
        path = "lifestyle.activity_record." + key
        add(
            "ls_" + key + "_present",
            11,
            row,
            0,
            label,
            path + ".present",
            "single_choice",
            options=["没有", "有"],
        )
        add(
            "ls_" + key + "_days",
            11,
            row,
            1,
            label + "天数",
            path + ".days_per_week",
            "number",
            unit="天/周",
            integer=True,
            min=0,
            max=7,
            visible_when=condition(path + ".present", "有"),
        )
        add(
            "ls_" + key + "_minutes",
            11,
            row,
            2,
            label + "每日时长",
            path + ".minutes_per_day",
            "number",
            unit="分钟",
            min=0,
            max=1440,
            visible_when=condition(path + ".present", "有"),
        )

    medication_options = {
        "med_antihypertensive": [
            "ACEI",
            "ARB",
            "β受体阻滞剂",
            "钙通道阻滞剂",
            "利尿剂",
            "α受体阻滞剂",
            "其他",
        ],
        "med_antidiabetic": [
            "磺脲类",
            "双胍类",
            "α-葡萄糖苷酶抑制剂",
            "格列奈类",
            "噻唑烷二酮类",
            "DPP-4抑制剂",
            "SGLT2抑制剂",
            "GLP-1RA",
            "胰岛素",
            "其他",
        ],
        "med_lipid": ["他汀类", "贝特类", "依折麦布", "PCSK9抑制剂", "其他"],
        "med_inhaler": ["沙丁胺醇", "复方异丙托溴铵", "布地奈德", "其他"],
        "med_antiplatelet": [
            "阿司匹林",
            "氯吡格雷",
            "华法林",
            "利伐沙班/阿哌沙班等NOAC",
            "其他",
        ],
        "med_cardiac": ["硝酸酯类", "地高辛", "胺碘酮", "地尔硫卓/维拉帕米", "其他"],
        "med_cognitive": ["多奈哌齐", "美金刚", "卡巴拉汀", "加兰他敏", "其他"],
        "med_bone": ["钙剂", "普通维生素D", "活性维生素D", "双膦酸盐", "其他"],
        "med_pain": [
            "NSAIDs",
            "对乙酰氨基酚",
            "别嘌醇",
            "非布司他",
            "秋水仙碱",
            "其他",
        ],
        "med_other_long": [
            "甲状腺药物",
            "抗癫痫药物",
            "胃药",
            "抗生素",
            "营养/维生素补充剂",
            "其他",
        ],
    }
    for row, (slug, label) in enumerate(MED_CATS, 1):
        path = "baseline_medications." + slug
        bind(slug + "_uses", 12, row, 0)
        if slug not in medication_options:
            bind(slug + "_detail", 12, row, 1)
            by_id[slug + "_detail"]["visible_when"] = condition(path + ".uses", "是")
            continue
        add(
            slug + "_categories",
            12,
            row,
            1,
            label + "种类",
            path + ".categories",
            "multi_choice",
            options=medication_options[slug],
            visible_when=condition(path + ".uses", "是"),
        )
        add(
            slug + "_other_name",
            12,
            row,
            2,
            label + "其他药名",
            path + ".other_name",
            visible_when={
                "all": [
                    condition(path + ".uses", "是"),
                    condition(path + ".categories", "其他", "contains"),
                ]
            },
        )
    bind("med_count_regular", 12, 13)

    for value in fields:
        historical_unknown = [
            option
            for option in value.get("options", [])
            if option in ("不详", "拒答/不详")
        ]
        if historical_unknown:
            value["legacy_options"] = historical_unknown
            value["options"] = [
                option
                for option in value["options"]
                if option not in historical_unknown
            ]
        if value.get("legacy_options"):
            value["legacy_option_states"] = {
                option: "unknown" for option in value["legacy_options"]
            }

    # 共同状态接口；顶层完整存储路径作键，重复行使用自己的元数据及列键。
    def annotate(value, row=False):
        value["section"] = value["table_ref"]
        value["ui_label"] = value["label_zh"]
        value["doc_table_index"] = int(value["table_ref"][2:])
        value.setdefault("include_in_completeness", not value.get("legacy", False))
        value["metadata"] = {
            "storage": "_field_meta"
            if row
            else "patient_baseline.demographics._crf_field_meta",
            "key": value["storage"],
            "states": ["value", "unknown", "not_applicable"],
            "reason_required_for_handled": True,
        }
        if value["widget"] == "date":
            value.setdefault("date_precision", "day")
            value["allow_partial_date"] = True
        if value["widget"] in ("text", "textarea"):
            value["max_length"] = 2000 if value["widget"] == "textarea" else 500
        if value["widget"] == "number":
            value.setdefault("min", 0)
        if value.get("visible_when"):
            value["required_when"] = value["visible_when"]
        for child in value.get("children", []):
            annotate(child, True)

    for order, value in enumerate(fields):
        value["order"] = order
        annotate(value)
    by_id["dm_age_years"].update(integer=True, unit="周岁", max=150)
    by_id["dm_education_years"].update(integer=True, unit="年", max=100)
    by_id["med_count_regular"].update(integer=True, unit="种")
    return fields


TABLE_TITLES["#T1"] = "文档修订信息"
BASELINE_SECTION_ORDER.insert(1, "#T1")


def baseline_table_layout() -> dict:
    fields = build_baseline_fields()
    return {
        ref: {
            "rows": [
                {"cells": [{"field_id": f["field_id"]}]}
                for f in fields
                if f["table_ref"] == ref
            ]
        }
        for ref in BASELINE_SECTION_ORDER
    }
