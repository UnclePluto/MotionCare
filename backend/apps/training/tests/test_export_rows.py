import json
import os
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.patients.models import Patient
from apps.prescriptions.models import ActionLibraryItem, Prescription
from apps.studies.models import ProjectPatient, StudyProject
from apps.training._export_mapping import motion_row
from apps.training.export_rows import (
    ExportDeadlineError,
    ExportLimitError,
    ExportRows,
    prepare_export_rows,
)
from apps.training.export_schema import FIELD_DEFINITIONS, SHEET_HEADERS
from apps.training.export_scope import ExportFilter
from apps.training.models import (
    GameQuestionResult,
    MotionAnalysisJob,
    TrainingRecord,
    TrainingVideo,
)
from apps.wearables.models import WearableDevice, WearableMeasurement


@pytest.fixture
def export_sample(project_patient, doctor, active_prescription):
    game = ActionLibraryItem.objects.get(source_key="game-executive-inhibition")
    motion = ActionLibraryItem.objects.get(source_key="motion-resistance-shoulder-press")
    old = Prescription.objects.create(
        project_patient=project_patient, version=2, opened_by=doctor, status="superseded"
    )
    game_action = old.add_action_snapshot(game, duration_minutes=1, difficulty="简单")
    motion_action = active_prescription.add_action_snapshot(motion, duration_minutes=3)

    def record(action, **kwargs):
        return TrainingRecord.objects.create(
            project_patient=project_patient,
            prescription=action.prescription,
            prescription_action=action,
            training_date=date(2026, 9, 9),
            status="completed",
            **kwargs,
        )

    current = record(
        game_action,
        client_session_id=uuid.uuid4(),
        score=0,
        form_data={
            "difficulty": "困难",
            "accuracy_rate": 99,
            "error_count": 1,
            "raw_detail": {
                "completed_units": 2,
                "correct_units": 1,
                "session_duration_seconds": 30,
                "ended_early": False,
                "ended_by": "timer",
                "rounds": [{"round_index": 90, "response_ms": 90, "correct": True}],
            },
        },
    )
    for index, ms, correct, result in [(1, 0, True, "answered"), (2, 1200, False, "timeout")]:
        GameQuestionResult.objects.create(
            training_record=current,
            question_index=index,
            game_code=game.source_key,
            difficulty="困难",
            response_duration_ms=ms,
            is_correct=correct,
            result_type=result,
            capture_version="active_response_v1",
        )
    legacy = record(
        game_action,
        actual_duration_minutes=2,
        form_data={
            "difficulty": "简单",
            "accuracy_rate": 75,
            "error_count": 3,
            "raw_detail": {
                "completed_units": 4,
                "correct_units": 3,
                "rounds": [{"round_index": 3, "response_ms": 0, "correct": False}],
            },
        },
    )
    revised = record(
        motion_action,
        motion_total_count=5,
        motion_standard_count=4,
        motion_nonstandard_count=1,
        motion_result_source="doctor",
        motion_result_updated_by=doctor,
        motion_result_updated_at=datetime(2026, 9, 9, tzinfo=UTC),
        motion_quality_data={
            "doctor_note": "=医生说明",
            "confidence_level": "high",
            "object_key": "SECRET_OBJECT",
            "raw_payload": {"secret": "SECRET_RAW"},
        },
    )
    empty = record(motion_action)
    started = datetime(2026, 9, 8, 16, 0, tzinfo=UTC)
    videos = []
    for r in (revised, empty):
        videos.append(
            TrainingVideo.objects.create(
                project_patient=project_patient,
                prescription=r.prescription,
                prescription_action=r.prescription_action,
                training_record=r,
                training_date=r.training_date,
                training_started_at=started,
                training_ended_at=started + timedelta(seconds=20),
                expected_duration_seconds=180,
                actual_duration_seconds=0,
                duration_seconds=77,
                object_key=f"SECRET_VIDEO/{uuid.uuid4()}",
                status="attached",
            )
        )
    MotionAnalysisJob.objects.create(
        training_video=videos[0],
        training_record=revised,
        prescription_action=motion_action,
        project_patient=project_patient,
        status="failed",
        failure_reason="SECRET_STACK",
    )
    other_project = StudyProject.objects.create(name="其他项目")
    other_pp = ProjectPatient.objects.create(project=other_project, patient=project_patient.patient)
    other_patient = Patient.objects.create(
        name="其他患者", gender="unknown", age=60, primary_doctor=doctor
    )
    other_patient_pp = ProjectPatient.objects.create(project=other_project, patient=other_patient)
    for pp in (other_pp, other_patient_pp):
        TrainingRecord.objects.create(
            project_patient=pp,
            prescription=old,
            prescription_action=game_action,
            training_date=date(2026, 9, 9),
            status="completed",
        )
    device = WearableDevice.objects.create(
        provider="miwitracker",
        external_device_id="export-fixture",
        identifier_type="device_id",
        short_code="9009",
    )

    def measure(at, metric="heart_rate", patient=None, attribution="attributed", **values):
        return WearableMeasurement.objects.create(
            provider="miwitracker",
            patient=patient or project_patient.patient,
            device=device,
            metric_type=metric,
            measured_at=at,
            attribution_status=attribution,
            source_fingerprint=str(uuid.uuid4()),
            raw_payload={"secret": "SECRET_MEASUREMENT"},
            **values,
        )

    measurements = [
        measure(started, heart_rate=60),
        measure(started + timedelta(seconds=480), heart_rate=81),
    ]
    for at in (
        started - timedelta(microseconds=1),
        started + timedelta(seconds=480, microseconds=1),
    ):
        measure(at, heart_rate=200)
    measure(started, heart_rate=199, attribution="ambiguous")
    measure(started, heart_rate=198, patient=other_patient)
    measure(started, metric="blood_pressure", systolic=120)
    measure(started, metric="blood_pressure", systolic=120, diastolic=80)
    measure(started, metric="blood_oxygen", blood_oxygen=0)
    return SimpleNamespace(
        project_patient=project_patient,
        filters=ExportFilter(project_patient.pk, "all", None, None),
        record_id=current.pk,
        current=current,
        legacy=legacy,
        revised=revised,
        empty=empty,
        videos=videos,
        measurements=measurements,
        started=started,
        game_action=game_action,
        motion_action=motion_action,
    )


def prepared(sample):
    return prepare_export_rows(
        project_patient=sample.project_patient,
        filters=sample.filters,
        deadline=time.monotonic() + 60,
    )


@pytest.mark.django_db
def test_all_rows_use_authorized_scope_and_snapshot_values(export_sample):
    s = export_sample
    with prepared(s) as rows:
        sessions = {r["训练记录编号"]: r for r in rows.iter_rows("训练场次")}
        questions = list(rows.iter_rows("游戏逐题"))
        assert list(sessions) == [s.current.pk, s.legacy.pk, s.revised.pk, s.empty.pk]
        own = [r for r in questions if r["训练记录编号"] == s.record_id]
        assert len(own) == 2
        assert own[0]["有效作答时间（毫秒）"] == 0
        assert "历史作答时间（毫秒）" not in own[0]
        assert own[1]["判定"] == "超时"
        assert not [r for r in questions if r["训练记录编号"] == s.legacy.pk]
        assert rows.row_counts["游戏逐题"] == 2
        assert sessions[s.legacy.pk]["逐题记录数"] == 0
        assert sessions[s.legacy.pk]["规范计时题数"] == 0
        assert "规范逐题完整列表" not in sessions[s.legacy.pk]["逐题完整性"]
        assert "历史计时题数" not in sessions[s.legacy.pk]
        current = sessions[s.current.pk]
        assert (
            current["完成题数"],
            current["正确题数"],
            current["错误题数"],
            current["正确率（%）"],
        ) == (2, 1, 1, Decimal("50.0"))
        assert current["游戏得分"] == 0 and current["是否提前结束"] is False
        assert current["结束方式"] == "自动结束"
        assert current["处方版本"] == 2 and current["脱敏手机号"] == "139****1111"
        assert current["训练开始时间"] is None
        assert current["实际训练时长（秒）"] == 30
        assert sessions[s.legacy.pk]["正确率（%）"] == 75
        assert sessions[s.legacy.pk]["实际训练时长（秒）"] == 120
        assert sessions[s.legacy.pk]["时长来源与精度"] == "按分钟记录"
        assert isinstance(current["训练日期"], date)
        assert isinstance(current["提交时间"], datetime)
        assert rows.metadata["actual_start_date"] == date(2026, 9, 9)
        for sheet in SHEET_HEADERS:
            assert set(SHEET_HEADERS[sheet]) <= FIELD_DEFINITIONS.keys()
            for row in rows.iter_rows(sheet):
                assert set(row) == set(SHEET_HEADERS[sheet])


@pytest.mark.django_db
def test_motion_quality_export_rows_preserve_string_and_finite_number_types(export_sample):
    sample = export_sample
    sample.revised.motion_quality_data = {
        "doctor_note": "=医生说明",
        "confidence_level": 0.98,
        "quality_flags": ["stable"],
        "object_key": "SECRET_OBJECT",
        "raw_payload": {"secret": "SECRET_RAW"},
    }
    sample.revised.save(update_fields=["motion_quality_data"])
    sample.empty.motion_quality_data = {"confidence_level": 0}
    sample.empty.save(update_fields=["motion_quality_data"])
    string_confidence = TrainingRecord.objects.create(
        project_patient=sample.project_patient,
        prescription=sample.motion_action.prescription,
        prescription_action=sample.motion_action,
        training_date=date(2026, 9, 9),
        status="completed",
        motion_quality_data={"confidence_level": "high"},
    )

    with prepared(sample) as rows:
        motion = list(rows.iter_rows("运动明细"))
        by_record = {row["训练记录编号"]: row for row in motion}
        revised = by_record[sample.revised.pk]
        assert revised["动作总次数"] == 5 and revised["结果来源"] == "医生"
        assert revised["实际训练秒数"] == 0 and revised["视频文件秒数"] == 77
        assert revised["修订医生姓名"] == "测试医生"
        assert by_record[sample.empty.pk]["动作总次数"] is None
        assert revised["分析状态"] == "分析失败"
        assert json.loads(revised["动作质量详情1"]) == {
            "confidence_level": 0.98,
            "doctor_note": "=医生说明",
            "quality_flags": ["stable"],
        }
        assert json.loads(by_record[sample.empty.pk]["动作质量详情1"]) == {"confidence_level": 0}
        assert json.loads(by_record[string_confidence.pk]["动作质量详情1"]) == {
            "confidence_level": "high"
        }
        serialized = "".join(
            json.dumps(list(rows.iter_rows(name)), default=str, ensure_ascii=False)
            for name in SHEET_HEADERS
        )
        assert "SECRET_" not in serialized


@pytest.mark.django_db
def test_motion_quality_export_row_rejects_bool_non_finite_and_nested_values(export_sample):
    record = export_sample.revised
    record.export_analysis_status = None
    unsafe_values = (
        {
            "confidence_level": True,
            "doctor_note": {"nested": "SECRET_NOTE"},
            "quality_flags": ["stable", 1, {"nested": "SECRET_FLAG"}],
            "object_key": "SECRET_OBJECT",
            "raw_payload": {"nested": "SECRET_RAW"},
        },
        {"confidence_level": float("nan")},
        {"confidence_level": float("inf")},
        {"confidence_level": {"nested": "SECRET_CONFIDENCE"}},
    )

    exported = []
    for value in unsafe_values:
        record.motion_quality_data = value
        exported.append(motion_row(record, export_sample.videos[0])["动作质量详情1"])

    assert json.loads(exported[0]) == {"quality_flags": ["stable"]}
    assert exported[1:] == [None, None, None]
    assert "SECRET_" not in json.dumps(exported, ensure_ascii=False)


@pytest.mark.django_db
def test_measurements_use_closed_overlapping_windows_and_matching_summaries(export_sample):
    s = export_sample
    with prepared(s) as rows:
        physiology = list(rows.iter_rows("训练期间生理数据"))
        for measurement in s.measurements:
            assert sum(r["测量记录编号"] == measurement.pk for r in physiology) == 2
        assert len(physiology) == 8
        for record in (s.revised, s.empty):
            points = [
                r for r in physiology if r["训练记录编号"] == record.pk and r["指标类型"] == "心率"
            ]
            assert [p["心率（次/分）"] for p in points] == [60, 81]
            summary = next(r for r in rows.iter_rows("训练场次") if r["训练记录编号"] == record.pk)
            assert summary["心率均值（次/分）"] == Decimal("70.5")
            assert summary["心率读数数量"] == 2 and summary["血压配对数量"] == 1
            assert summary["血氧均值（%）"] == Decimal("0.0")
        before = physiology
    TrainingVideo.objects.filter(pk=s.videos[0].pk).update(training_ended_at=None)
    with prepared(s) as rows:
        assert list(rows.iter_rows("训练期间生理数据")) == before


@pytest.mark.django_db
def test_uuid_empty_questions_never_falls_back_and_puzzle_accuracy_is_null(export_sample):
    s = export_sample
    s.current.question_results.all().delete()
    # 本用例模拟规范空列表写入，保存对应的规范0题摘要。
    s.current.form_data["raw_detail"].update(completed_units=0, correct_units=0)
    s.current.form_data.update(error_count=0, accuracy_rate=0)
    s.current.save(update_fields=["form_data"])
    s.game_action.action_library_item = ActionLibraryItem.objects.get(
        source_key="game-audiovisual-puzzle"
    )
    s.game_action.save()
    with prepared(s) as rows:
        assert not [r for r in rows.iter_rows("游戏逐题") if r["训练记录编号"] == s.record_id]
        current = next(r for r in rows.iter_rows("训练场次") if r["训练记录编号"] == s.record_id)
        assert current["完成题数"] == 0 and current["正确率（%）"] is None
        assert "不适用" in current["逐题完整性"]


@pytest.mark.django_db
def test_date_filter_and_empty_result(export_sample):
    s = export_sample
    s.filters = ExportFilter(s.project_patient.pk, "custom", date(2026, 9, 8), date(2026, 9, 8))
    with prepared(s) as rows:
        assert all(rows.row_counts[name] == 0 for name in SHEET_HEADERS if name != "字段说明")
        assert rows.metadata["actual_start_date"] is None


def test_private_spool_roundtrips_types_and_tracks_text_chunks():
    with ExportRows(deadline=time.monotonic() + 60) as rows:
        path = rows.directory
        rows.append(
            "训练场次",
            {
                "备注": "文" * 32768,
                "训练日期": date(2026, 9, 9),
                "提交时间": datetime(2026, 9, 9, tzinfo=UTC),
                "游戏得分": Decimal("0.0"),
                "是否提前结束": False,
            },
        )
        row = next(rows.iter_rows("训练场次"))
        assert row["训练日期"] == date(2026, 9, 9) and row["游戏得分"] == Decimal("0.0")
        assert row["是否提前结束"] is False
        assert rows.text_chunk_counts["训练场次"]["备注"] == 2
        assert os.stat(path).st_mode & 0o777 == 0o700
        assert all(os.stat(path + "/" + file).st_mode & 0o777 == 0o600 for file in os.listdir(path))
        with pytest.raises(ValueError):
            rows.append("训练场次", {"unknown": "forbidden"})
    assert not os.path.exists(path)
    rows.close()


@pytest.mark.parametrize(
    ("constant", "sheet"),
    [("MAX_RECORDS", "训练场次"), ("MAX_SHEET_ROWS", "游戏逐题"), ("MAX_TOTAL_ROWS", "运动明细")],
)
def test_spool_limits_cleanup(monkeypatch, constant, sheet):
    import apps.training.export_rows as module

    monkeypatch.setattr(module, constant, 1)
    rows = ExportRows(deadline=time.monotonic() + 60)
    path = rows.directory
    with pytest.raises(ExportLimitError), rows:
        rows.append(sheet, {})
        rows.append(sheet, {})
    assert not os.path.exists(path)


def test_deadline_cleanup():
    rows = ExportRows(deadline=time.monotonic() - 1)
    path = rows.directory
    with pytest.raises(ExportDeadlineError), rows:
        rows.append("训练场次", {})
    assert not os.path.exists(path)


@pytest.mark.django_db
def test_query_cost_bounded_per_hundred_records(export_sample):
    s = export_sample

    def capture():
        with CaptureQueriesContext(connection) as queries, prepared(s) as rows:
            for name in SHEET_HEADERS:
                list(rows.iter_rows(name))
        return queries.captured_queries

    first = capture()

    def add(count):
        TrainingRecord.objects.bulk_create(
            [
                TrainingRecord(
                    project_patient=s.project_patient,
                    prescription=s.motion_action.prescription,
                    prescription_action=s.motion_action,
                    training_date=date(2026, 9, 9),
                    status="completed",
                )
                for _ in range(count)
            ]
        )

    add(96)
    hundred = capture()
    add(1)
    hundred_one = capture()
    assert len(hundred) == len(first)
    assert len(hundred_one) <= len(hundred) + 6
    assert len(hundred) <= 12
    measurement_queries = [q["sql"] for q in hundred if "wearables_wearablemeasurement" in q["sql"]]
    assert measurement_queries and all("raw_payload" not in q for q in measurement_queries)


@pytest.mark.django_db
def test_long_quality_has_contiguous_segments_and_no_lazy_queries(export_sample):
    s = export_sample
    note = "长文本😀" * 9000
    s.revised.motion_quality_data = {"doctor_note": note}
    s.revised.save()
    with prepared(s) as rows:
        assert rows.quality_chunk_count == 2
        assert rows.text_chunk_counts["运动明细"]["动作质量详情1"] == 2
        with CaptureQueriesContext(connection) as queries:
            motion = list(rows.iter_rows("运动明细"))
        assert len(queries) == 0
        for item in motion:
            assert set(item) == (set(SHEET_HEADERS["运动明细"]) | {"动作质量详情2"})
            assert len(item["动作质量详情1"] or "") <= 32767
            assert len(item["动作质量详情2"] or "") <= 32767
        quality = "".join(motion[0][f"动作质量详情{i}"] for i in (1, 2))
        assert json.loads(quality) == {"doctor_note": note}


@pytest.mark.django_db
def test_unsupported_motion_can_keep_doctor_result_without_video(export_sample):
    s = export_sample
    high_knee = ActionLibraryItem.objects.get(source_key="motion-aerobic-high-knee")
    s.motion_action.action_library_item = high_knee
    s.motion_action.save()
    s.revised.motion_analysis_jobs.all().delete()
    s.videos[0].delete()
    with prepared(s) as rows:
        item = next(r for r in rows.iter_rows("运动明细") if r["训练记录编号"] == s.revised.pk)
        assert item["分析状态"] == "不支持AI"
        assert item["动作总次数"] == 5 and item["结果来源"] == "医生"
        assert item["实际训练秒数"] is None and item["录像编号"] is None
        session = next(r for r in rows.iter_rows("训练场次") if r["训练记录编号"] == s.revised.pk)
        assert session["心率数据可用性"] == "无可用观察窗口"
        assert session["心率均值（次/分）"] is None


@pytest.mark.django_db
def test_prepare_failure_removes_spools(export_sample, monkeypatch, tmp_path):
    import apps.training.export_rows as module
    from tempfile import TemporaryDirectory

    monkeypatch.setattr(
        module, "TemporaryDirectory", lambda **kw: TemporaryDirectory(dir=tmp_path, **kw)
    )
    monkeypatch.setattr(module, "MAX_SHEET_ROWS", 1)
    with pytest.raises(ExportLimitError):
        prepared(export_sample)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.django_db
def test_date_range_includes_both_endpoints_and_all_prescriptions(export_sample):
    s = export_sample
    s.legacy.training_date = date(2026, 9, 3)
    s.legacy.save()
    s.current.training_date = date(2026, 9, 10)
    s.current.save()
    s.filters = ExportFilter(s.project_patient.pk, "7d", date(2026, 9, 3), date(2026, 9, 9))
    with prepared(s) as rows:
        records = list(rows.iter_rows("训练场次"))
        assert [r["训练记录编号"] for r in records] == [s.legacy.pk, s.revised.pk, s.empty.pk]
        assert rows.metadata["actual_start_date"] == date(2026, 9, 3)
        assert rows.metadata["actual_end_date"] == date(2026, 9, 9)


@pytest.mark.django_db
def test_database_statement_cancellation_becomes_export_deadline(
    export_sample, monkeypatch, tmp_path
):
    import apps.training.export_rows as module
    from django.db import OperationalError
    from tempfile import TemporaryDirectory

    monkeypatch.setattr(
        module, "TemporaryDirectory", lambda **kw: TemporaryDirectory(dir=tmp_path, **kw)
    )

    class QueryCanceled(Exception):
        sqlstate = "57014"

    def canceled(*args, **kwargs):
        raise OperationalError("statement canceled") from QueryCanceled()

    monkeypatch.setattr(module, "_prepare_chunk", canceled)
    with pytest.raises(ExportDeadlineError):
        prepared(export_sample)
    assert not list(tmp_path.iterdir())


@pytest.mark.django_db
def test_one_hundred_and_hundred_one_windows_keep_fixed_query_cost(export_sample):
    s = export_sample
    TrainingRecord.objects.filter(project_patient=s.project_patient).exclude(
        pk=s.revised.pk
    ).delete()

    def capture():
        with CaptureQueriesContext(connection) as queries, prepared(s) as rows:
            count = rows.row_counts["训练场次"]
        return count, len(queries)

    one = capture()
    records = TrainingRecord.objects.bulk_create(
        [
            TrainingRecord(
                project_patient=s.project_patient,
                prescription=s.motion_action.prescription,
                prescription_action=s.motion_action,
                training_date=date(2026, 9, 9),
                status="completed",
            )
            for _ in range(99)
        ]
    )
    TrainingVideo.objects.bulk_create(
        [
            TrainingVideo(
                project_patient=s.project_patient,
                prescription=r.prescription,
                prescription_action=s.motion_action,
                training_record=r,
                training_date=r.training_date,
                training_started_at=s.started,
                expected_duration_seconds=180,
            )
            for r in records
        ]
    )
    hundred = capture()
    TrainingRecord.objects.create(
        project_patient=s.project_patient,
        prescription=s.motion_action.prescription,
        prescription_action=s.motion_action,
        training_date=date(2026, 9, 9),
        status="completed",
    )
    hundred_one = capture()
    assert (one[0], hundred[0], hundred_one[0]) == (1, 100, 101)
    assert one[1] == hundred[1] <= 12
    assert hundred_one[1] <= hundred[1] + 6
    print(f"场次数/查询数: {one}, {hundred}, {hundred_one}")


def test_measurement_means_round_half_up():
    from apps.training._export_measurements import _Statistic

    stat = _Statistic()
    for value in (0, 0, 0, 1):
        stat.add(value)
    assert stat.fields("心率", "次/分")["心率均值（次/分）"] == Decimal("0.3")


@pytest.mark.django_db
def test_action_name_comes_from_historical_snapshot(export_sample):
    s = export_sample
    original = s.game_action.action_name_snapshot
    ActionLibraryItem.objects.filter(pk=s.game_action.action_library_item_id).update(
        name="新的动作名称"
    )
    with prepared(s) as rows:
        assert (
            next(r for r in rows.iter_rows("训练场次") if r["训练记录编号"] == s.current.pk)[
                "动作名称"
            ]
            == original
        )
        assert next(rows.iter_rows("游戏逐题"))["游戏名称"] == original


@pytest.mark.django_db
def test_sixteen_questions_one_correct_matches_authoritative_accuracy(export_sample):
    from apps.training.game_questions import normalize_new_question_results

    sample = export_sample
    questions = [
        {
            "question_index": index,
            "game_code": sample.game_action.action_library_item.source_key,
            "difficulty": "困难",
            "response_duration_ms": 0,
            "is_correct": index == 1,
            "result_type": "answered",
            "swap_count": None,
        }
        for index in range(1, 17)
    ]
    authoritative = normalize_new_question_results(
        prescription_action=sample.game_action,
        raw_results=questions,
        form_data=sample.current.form_data,
    )
    assert authoritative.form_data["accuracy_rate"] == 6.2
    # 原场次中的冲突摘要99保持不变，导出必须从正式题目重新汇总。
    assert sample.current.form_data["accuracy_rate"] == 99
    # 保存规范写入产生的题数证据；冲突正确率继续留给导出重算验证。
    sample.current.form_data["raw_detail"].update(completed_units=16, correct_units=1)
    sample.current.form_data["error_count"] = 15
    sample.current.save(update_fields=["form_data"])
    sample.current.question_results.all().delete()
    GameQuestionResult.objects.bulk_create(
        [
            GameQuestionResult(training_record=sample.current, **question)
            for question in authoritative.rows
        ]
    )

    with prepared(sample) as rows:
        session = next(
            row for row in rows.iter_rows("训练场次") if row["训练记录编号"] == sample.current.pk
        )
        assert session["完成题数"] == 16
        assert session["正确题数"] == 1
        assert session["错误题数"] == 15
        assert session["正确率（%）"] == authoritative.form_data["accuracy_rate"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "duration", [None, -1, float("nan"), float("inf"), float("-inf"), True, "1200"]
)
def test_invalid_active_durations_are_omitted_without_losing_valid_answers(
    export_sample, monkeypatch, duration
):
    import apps.training.export_rows as module

    sample = export_sample
    original_reader = module._questions_for_records

    def invalid_read_boundary(records, **kwargs):
        # 数据库字段禁止这些值；在读取边界模拟损坏输入，保留完整真实导出链路。
        grouped = original_reader(records, **kwargs)
        valid = grouped[sample.current.pk]
        valid.append(
            {
                **valid[0],
                "question_index": 3,
                "response_duration_ms": 500,
                "is_correct": False,
                "result_type": "answered",
            }
        )
        valid.append({**valid[0], "question_index": 4, "response_duration_ms": duration})
        return grouped

    monkeypatch.setattr(module, "_questions_for_records", invalid_read_boundary)
    with prepared(sample) as rows:
        questions = [
            r for r in rows.iter_rows("游戏逐题") if r["训练记录编号"] == sample.current.pk
        ]
        assert [(q["题号"], q["有效作答时间（毫秒）"], q["判定"]) for q in questions] == [
            (1, 0, "正确"),
            (2, 1200, "超时"),
            (3, 500, "错误"),
        ]
        session = next(
            r for r in rows.iter_rows("训练场次") if r["训练记录编号"] == sample.current.pk
        )
        assert session["逐题记录数"] == session["规范计时题数"] == 3
        assert "规范逐题完整列表" not in session["逐题完整性"]


@pytest.mark.django_db
def test_stored_legacy_questions_remain_in_database_but_not_exported(export_sample):
    sample = export_sample
    sample.current.question_results.update(capture_version="legacy_wall_clock_v0")
    with prepared(sample) as rows:
        assert list(rows.iter_rows("游戏逐题")) == []
        session = next(
            r for r in rows.iter_rows("训练场次") if r["训练记录编号"] == sample.current.pk
        )
        assert session["逐题记录数"] == session["规范计时题数"] == 0
        assert session["正确率（%）"] == 99
        assert "规范逐题完整列表" not in session["逐题完整性"]
        explanations = json.dumps(list(rows.iter_rows("字段说明")), ensure_ascii=False, default=str)
        assert all(
            term not in explanations
            for term in (
                "历史作答时间",
                "历史计时题数",
                "历史计时口径",
                "墙上时钟",
                "legacy_wall_clock_v0",
            )
        )
    assert sample.current.question_results.count() == 2
    sample.legacy.refresh_from_db()
    assert sample.legacy.form_data["raw_detail"]["rounds"] == [
        {"round_index": 3, "response_ms": 0, "correct": False}
    ]


@pytest.mark.django_db
def test_response_duration_above_spec_limit_is_not_exported(export_sample):
    sample = export_sample
    sample.current.question_results.filter(question_index=2).update(response_duration_ms=3600001)
    with prepared(sample) as rows:
        questions = [
            r for r in rows.iter_rows("游戏逐题") if r["训练记录编号"] == sample.current.pk
        ]
        assert [(q["题号"], q["有效作答时间（毫秒）"]) for q in questions] == [(1, 0)]
        session = next(
            r for r in rows.iter_rows("训练场次") if r["训练记录编号"] == sample.current.pk
        )
        assert session["逐题记录数"] == 1
        assert "规范逐题完整列表" not in session["逐题完整性"]


@pytest.mark.django_db
@pytest.mark.parametrize("duration", [1.5, 1.0, 0.0])
def test_finite_non_integer_response_duration_is_not_exported(export_sample, monkeypatch, duration):
    import apps.training.export_rows as module

    sample = export_sample
    original_reader = module._questions_for_records

    def fractional_read_boundary(records, **kwargs):
        grouped = original_reader(records, **kwargs)
        grouped[sample.current.pk][1]["response_duration_ms"] = duration
        return grouped

    monkeypatch.setattr(module, "_questions_for_records", fractional_read_boundary)
    with prepared(sample) as rows:
        questions = [
            r for r in rows.iter_rows("游戏逐题") if r["训练记录编号"] == sample.current.pk
        ]
        assert [(q["题号"], q["有效作答时间（毫秒）"]) for q in questions] == [(1, 0)]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "damage",
    [
        "missing_tail",
        "non_contiguous",
        "missing_evidence",
        "missing_all",
        "incorrect_correct_count",
        "incorrect_error_count",
    ],
)
def test_unproven_question_completeness_preserves_stored_session_summary(export_sample, damage):
    sample = export_sample
    form = sample.current.form_data
    form["raw_detail"].update(completed_units=2, correct_units=1)
    form.update(error_count=1, accuracy_rate=50)
    expected_count = 2
    if damage == "missing_tail":
        sample.current.question_results.filter(question_index=2).delete()
        expected_count = 1
    elif damage == "non_contiguous":
        sample.current.question_results.filter(question_index=2).update(question_index=3)
    elif damage == "missing_evidence":
        form["raw_detail"].pop("completed_units")
    elif damage == "missing_all":
        sample.current.question_results.all().delete()
        expected_count = 0
    elif damage == "incorrect_correct_count":
        form["raw_detail"]["correct_units"] = 2
    else:
        form["error_count"] = 0
    sample.current.save(update_fields=["form_data"])
    with prepared(sample) as rows:
        session = next(
            r for r in rows.iter_rows("训练场次") if r["训练记录编号"] == sample.current.pk
        )
        assert session["完成题数"] == form["raw_detail"].get("completed_units")
        assert session["正确题数"] == form["raw_detail"]["correct_units"]
        assert session["错误题数"] == form["error_count"]
        assert session["正确率（%）"] == 50
        assert session["逐题记录数"] == session["规范计时题数"] == expected_count
        assert "规范逐题完整列表" not in session["逐题完整性"]


@pytest.mark.django_db
def test_exact_maximum_response_duration_is_exported(export_sample):
    sample = export_sample
    sample.current.question_results.filter(question_index=2).update(response_duration_ms=3600000)
    with prepared(sample) as rows:
        questions = [
            r for r in rows.iter_rows("游戏逐题") if r["训练记录编号"] == sample.current.pk
        ]
        assert [q["有效作答时间（毫秒）"] for q in questions] == [0, 3600000]


def selection_question(result="answered"):
    tokens = ["blue", "green", "yellow"]
    size = 3 if result == "answered" else 1
    return {
        "question_index": 1,
        "game_code": "game-memory-color-sequence",
        "difficulty": "简单",
        "response_duration_ms": 900,
        "is_correct": result == "answered",
        "result_type": result,
        "swap_count": None,
        "capture_version": "active_response_v2",
        "expected_step_count": 3,
        "click_count": None,
        "selection_steps": [
            {
                "step_index": i + 1,
                "selected_value": token,
                "expected_value": token,
                "response_duration_ms": 100,
                "is_correct": True,
            }
            for i, token in enumerate(tokens[:size])
        ],
    }


def test_v2_selection_export_mapping_and_interrupted_summary():
    from types import SimpleNamespace
    from apps.training._export_mapping import (
        has_valid_response_duration,
        question_row,
        game_summary,
    )

    q = selection_question("interrupted")
    action = SimpleNamespace(
        action_name_snapshot="颜色顺序",
        difficulty="简单",
        action_library_item=SimpleNamespace(source_key=q["game_code"]),
    )
    record = SimpleNamespace(
        pk=1,
        training_date=date(2026, 9, 9),
        prescription_action=action,
        client_session_id="uuid",
        score=0,
        form_data={
            "difficulty": "简单",
            "error_count": 0,
            "accuracy_rate": 99,
            "raw_detail": {"completed_units": 0, "correct_units": 0, "recorded_question_count": 1},
        },
    )
    assert has_valid_response_duration(q)
    row = question_row(record, q)
    assert row["题目状态"] == row["判定"] == "未完成"
    assert row["已选择步数"] == 1 and row["应选择步数"] == 3
    summary = game_summary(record, [q], True)
    assert summary["完成题数"] == summary["错误题数"] == summary["正确率（%）"] == 0
    assert summary["逐题记录数"] == 1 and summary["逐题完整性"] == "规范逐题完整列表"
    record.form_data["raw_detail"]["recorded_question_count"] = 2
    assert "不完整" in game_summary(record, [q], True)["逐题完整性"]


@pytest.mark.parametrize("damage", ["token", "duration", "index", "correct", "missing", "total"])
def test_invalid_v2_selection_parent_is_filtered(damage):
    from apps.training._export_mapping import has_valid_response_duration

    q = selection_question()
    if damage == "token":
        q["selection_steps"][0]["selected_value"] = "=unsafe"
    elif damage == "duration":
        q["selection_steps"][0]["response_duration_ms"] = True
    elif damage == "index":
        q["selection_steps"][0]["step_index"] = 2
    elif damage == "correct":
        q["selection_steps"][0]["is_correct"] = False
    elif damage == "missing":
        q["selection_steps"].pop()
    else:
        q["response_duration_ms"] = 1
    assert not has_valid_response_duration(q)


def test_selection_sheet_limits_include_total_and_per_sheet(monkeypatch):
    import apps.training.export_rows as module

    assert "顺序选择明细" in SHEET_HEADERS
    for limit in ("MAX_TOTAL_ROWS", "MAX_SHEET_ROWS"):
        with monkeypatch.context() as patch:
            patch.setattr(module, limit, 1)
            with ExportRows(deadline=time.monotonic() + 60) as rows:
                rows.append("顺序选择明细", {})
                with pytest.raises(ExportLimitError):
                    rows.append("顺序选择明细", {})


@pytest.mark.django_db
def test_selection_children_prefetch_is_bounded_and_mapping_has_no_queries(
    export_sample, monkeypatch
):
    from apps.training.models import GameQuestionSelectionStep
    import apps.training.export_rows as module

    sample = export_sample
    sample.current.question_results.all().delete()
    q = selection_question()
    steps = q.pop("selection_steps")
    parent = GameQuestionResult.objects.create(training_record=sample.current, **q)
    GameQuestionSelectionStep.objects.bulk_create(
        [GameQuestionSelectionStep(question=parent, **step) for step in steps]
    )
    with CaptureQueriesContext(connection) as queries:
        grouped = module._questions_for_records([sample.current])
    assert len(queries) == 2
    assert len(grouped[sample.current.pk][0]["selection_steps"]) == 3
    with prepared(sample) as rows, CaptureQueriesContext(connection) as queries:
        assert len(list(rows.iter_rows("顺序选择明细"))) == 3
    assert len(queries) == 0
    with ExportRows(deadline=time.monotonic() + 60) as rows:
        rows.row_counts["顺序选择明细"] = module.MAX_SHEET_ROWS - 2
        with pytest.raises(ExportLimitError):
            module._questions_for_records([sample.current], rows=rows)
    with ExportRows(deadline=time.monotonic() + 60) as rows:
        rows._total = module.MAX_TOTAL_ROWS - 2
        with pytest.raises(ExportLimitError):
            module._questions_for_records([sample.current], rows=rows)


def test_v1_cannot_export_synthetic_v2_details():
    from apps.training._export_mapping import has_valid_response_duration

    question = selection_question()
    question["capture_version"] = "active_response_v1"
    assert not has_valid_response_duration(question)


@pytest.mark.django_db
@pytest.mark.parametrize("unknown_count", [0, 99, "legacy-note", {"opaque": True}])
def test_v1_unknown_recorded_count_does_not_change_authoritative_export(
    export_sample, unknown_count
):
    sample = export_sample
    sample.current.form_data["raw_detail"]["recorded_question_count"] = unknown_count
    sample.current.save(update_fields=["form_data"])
    with prepared(sample) as rows:
        summary = next(
            r for r in rows.iter_rows("训练场次") if r["训练记录编号"] == sample.current.pk
        )
        assert summary["逐题完整性"] == "规范逐题完整列表"
        assert summary["完成题数"] == summary["逐题记录数"] == 2
        assert summary["正确题数"] == summary["错误题数"] == 1
        assert summary["正确率（%）"] == 50
    sample.current.refresh_from_db()
    assert sample.current.form_data["raw_detail"]["recorded_question_count"] == unknown_count
