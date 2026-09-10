"""授权场次固定窗口关联流；只保留每场的有限统计累加器。"""

from decimal import Decimal, ROUND_HALF_UP

from django.db import connection

from apps.wearables.models import WearableMeasurement
from ._export_mapping import WINDOW_DESCRIPTION


class _Statistic:
    def __init__(self):
        self.count = 0
        self.total = Decimal(0)
        self.minimum = None
        self.maximum = None

    def add(self, value):
        self.count += 1
        self.total += Decimal(value)
        self.minimum = value if self.minimum is None else min(self.minimum, value)
        self.maximum = value if self.maximum is None else max(self.maximum, value)

    def fields(self, name, unit):
        return {
            f"{name}均值（{unit}）": (self.total / self.count).quantize(
                Decimal("0.1"), rounding=ROUND_HALF_UP
            )
            if self.count
            else None,
            f"{name}最小值（{unit}）": self.minimum,
            f"{name}最大值（{unit}）": self.maximum,
        }


def summary_fields(stats, *, has_window):
    stats = stats or {
        key: _Statistic() for key in ("heart_rate", "systolic", "diastolic", "blood_oxygen")
    }
    fields = {}
    for key, name, unit in (
        ("heart_rate", "心率", "次/分"),
        ("systolic", "收缩压", "mmHg"),
        ("diastolic", "舒张压", "mmHg"),
        ("blood_oxygen", "血氧", "%"),
    ):
        fields.update(stats[key].fields(name, unit))
    for key, name, count_name in (
        ("heart_rate", "心率", "心率读数数量"),
        ("systolic", "血压", "血压配对数量"),
        ("blood_oxygen", "血氧", "血氧读数数量"),
    ):
        count = stats[key].count
        fields[count_name] = count
        fields[f"{name}数据可用性"] = (
            "可用" if count else ("窗口内无有效测量" if has_window else "无可用观察窗口")
        )
    return fields


def stream_measurements(*, patient_id, windows, rows):
    if not windows:
        return {}
    table = connection.ops.quote_name(WearableMeasurement._meta.db_table)
    values = ",".join(
        ["(%s::bigint,%s::bigint,%s::integer,%s::timestamptz,%s::timestamptz)"] * len(windows)
    )
    params = []
    for order, (record_id, video_id, start, end) in enumerate(windows):
        params.extend((record_id, video_id, order, start, end))
    params.append(patient_id)
    sql = f"""WITH windows(record_id,video_id,record_order,started_at,ended_at) AS (VALUES {values})
        SELECT w.record_id,w.video_id,m.id,m.measured_at,m.metric_type,
               m.heart_rate,m.systolic,m.diastolic,m.blood_oxygen,w.started_at,w.ended_at
        FROM windows w JOIN {table} m ON
             m.patient_id=%s AND m.attribution_status='attributed'
             AND m.measured_at>=w.started_at AND m.measured_at<=w.ended_at
             AND ((m.metric_type='heart_rate' AND m.heart_rate IS NOT NULL)
               OR (m.metric_type='blood_pressure' AND m.systolic IS NOT NULL AND m.diastolic IS NOT NULL)
               OR (m.metric_type='blood_oxygen' AND m.blood_oxygen IS NOT NULL))
        ORDER BY w.record_order,m.measured_at,m.id"""
    stats = {}
    with connection.chunked_cursor() as cursor:
        cursor.execute(sql, params)
        while True:
            rows.check_deadline()
            chunk = cursor.fetchmany(500)
            if not chunk:
                break
            for (
                record_id,
                video_id,
                measurement_id,
                measured_at,
                metric,
                hr,
                sys,
                dia,
                oxygen,
                start,
                end,
            ) in chunk:
                if record_id not in stats:
                    stats[record_id] = {
                        key: _Statistic()
                        for key in ("heart_rate", "systolic", "diastolic", "blood_oxygen")
                    }
                summary = stats[record_id]
                # Other columns can contain unrelated provider values; only the declared metric is exported.
                hr = hr if metric == "heart_rate" else None
                sys = sys if metric == "blood_pressure" else None
                dia = dia if metric == "blood_pressure" else None
                oxygen = oxygen if metric == "blood_oxygen" else None
                for key, value in (
                    ("heart_rate", hr),
                    ("systolic", sys),
                    ("diastolic", dia),
                    ("blood_oxygen", oxygen),
                ):
                    if value is not None:
                        summary[key].add(value)
                rows.append(
                    "训练期间生理数据",
                    {
                        "训练记录编号": record_id,
                        "录像编号": video_id,
                        "测量记录编号": measurement_id,
                        "测量时间": measured_at,
                        "指标类型": {
                            "heart_rate": "心率",
                            "blood_pressure": "血压",
                            "blood_oxygen": "血氧",
                        }[metric],
                        "心率（次/分）": hr,
                        "收缩压（mmHg）": sys,
                        "舒张压（mmHg）": dia,
                        "血氧（%）": oxygen,
                        "窗口开始": start,
                        "窗口结束": end,
                        "窗口口径": WINDOW_DESCRIPTION,
                    },
                )
    return stats
