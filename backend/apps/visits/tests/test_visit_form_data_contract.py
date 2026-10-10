import pytest
from rest_framework.test import APIClient

from apps.visits.models import VisitRecord


@pytest.mark.django_db
def test_get_always_includes_assessments_and_computed_keys(doctor, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")
    visit.form_data = {}
    visit.save(update_fields=["form_data"])

    client = APIClient()
    client.force_authenticate(user=doctor)

    resp = client.get(f"/api/visits/{visit.id}/")
    assert resp.status_code == 200
    form_data = resp.json()["form_data"]
    assert "assessments" in form_data
    assert "computed_assessments" in form_data


@pytest.mark.django_db
def test_patch_drops_external_computed_assessments(doctor, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")

    client = APIClient()
    client.force_authenticate(user=doctor)

    resp = client.patch(
        f"/api/visits/{visit.id}/",
        {
            "form_data": {
                "assessments": {"sppb": {"total": 9}},
                "computed_assessments": {"sppb": {"total": 123}},
            }
        },
        format="json",
    )
    assert resp.status_code == 200

    visit.refresh_from_db()
    assert visit.form_data.get("computed_assessments", {}) == {}


@pytest.mark.django_db
def test_patch_without_assessments_does_not_clear_existing(doctor, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")
    visit.form_data = {"assessments": {"sppb": {"balance": 4}}, "computed_assessments": {}}
    visit.save(update_fields=["form_data"])

    client = APIClient()
    client.force_authenticate(user=doctor)

    resp = client.patch(
        f"/api/visits/{visit.id}/",
        {"visit_date": "2026-05-01"},
        format="json",
    )
    assert resp.status_code == 200

    visit.refresh_from_db()
    assert visit.form_data["assessments"]["sppb"]["balance"] == 4


@pytest.mark.django_db
def test_patch_assessments_deep_merge(doctor, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")
    visit.form_data = {"assessments": {"sppb": {"balance": 4}}, "computed_assessments": {}}
    visit.save(update_fields=["form_data"])

    client = APIClient()
    client.force_authenticate(user=doctor)

    resp = client.patch(
        f"/api/visits/{visit.id}/",
        {"form_data": {"assessments": {"sppb": {"total": 9}}}},
        format="json",
    )
    assert resp.status_code == 200

    visit.refresh_from_db()
    assert visit.form_data["assessments"]["sppb"]["balance"] == 4
    assert visit.form_data["assessments"]["sppb"]["total"] == 9


@pytest.mark.django_db
def test_patch_crf_merges_without_dropping_assessments(doctor, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")

    client = APIClient()
    client.force_authenticate(user=doctor)

    resp = client.patch(
        f"/api/visits/{visit.id}/",
        {"form_data": {"assessments": {"sppb": {"total": 9}}}},
        format="json",
    )
    assert resp.status_code == 200

    resp = client.patch(
        f"/api/visits/{visit.id}/",
        {"form_data": {"crf": {"adherence": {"platform_id": "P1"}}}},
        format="json",
    )
    assert resp.status_code == 200

    resp = client.get(f"/api/visits/{visit.id}/")
    assert resp.status_code == 200
    form_data = resp.json()["form_data"]
    assert form_data["assessments"]["sppb"]["total"] == 9
    assert form_data["crf"]["adherence"]["platform_id"] == "P1"


@pytest.mark.django_db
def test_patch_assessments_merges_without_dropping_crf(doctor, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")

    client = APIClient()
    client.force_authenticate(user=doctor)

    resp = client.patch(
        f"/api/visits/{visit.id}/",
        {"form_data": {"crf": {"adherence": {"platform_id": "P1"}}}},
        format="json",
    )
    assert resp.status_code == 200

    resp = client.patch(
        f"/api/visits/{visit.id}/",
        {"form_data": {"assessments": {"sppb": {"total": 9}}}},
        format="json",
    )
    assert resp.status_code == 200

    resp = client.get(f"/api/visits/{visit.id}/")
    assert resp.status_code == 200
    form_data = resp.json()["form_data"]
    assert form_data["crf"]["adherence"]["platform_id"] == "P1"
    assert form_data["assessments"]["sppb"]["total"] == 9


@pytest.mark.django_db
def test_invalid_known_field_type_returns_400_with_path(doctor, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")

    client = APIClient()
    client.force_authenticate(user=doctor)

    resp = client.patch(
        f"/api/visits/{visit.id}/",
        {"form_data": {"assessments": {"sppb": {"total": "bad"}}}},
        format="json",
    )
    assert resp.status_code == 400
    body = resp.json()
    assert "assessments.sppb.total" in body


def test_merge_crf_patch_preserves_zero_replaces_arrays_and_copies():
    from apps.crf import field_values

    assert hasattr(field_values, "merge_crf_patch")
    original = {"a": {"b": 0, "c": 2}, "rows": [{"v": 1}]}
    patch = {"a": {"c": None}, "rows": []}
    merged = field_values.merge_crf_patch(original, patch)
    assert merged == {"a": {"b": 0, "c": None}, "rows": []}
    merged["a"]["b"] = 8
    assert original == {"a": {"b": 0, "c": 2}, "rows": [{"v": 1}]}
    assert patch == {"a": {"c": None}, "rows": []}


def _client(doctor):
    client = APIClient()
    client.force_authenticate(doctor)
    return client


@pytest.mark.django_db
def test_reason_only_patch_preserves_unchanged_historical_invalid_scores(doctor, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T1")
    key = "visit.form_data.assessments.sppb.total"
    visit.form_data = {
        "assessments": {"sppb": {"total": "旧文本"}},
        "crf": {"_field_meta": {key: {"state": "unknown", "reason": "旧原因"}}},
    }
    visit.save()
    response = _client(doctor).patch(
        f"/api/visits/{visit.id}/",
        {
            "form_data": {
                "assessments": {"sppb": {"total": "旧文本"}},
                "crf": {"_field_meta": {key: {"reason": "新原因"}}},
            }
        },
        format="json",
    )
    assert response.status_code == 200, response.data
    visit.refresh_from_db()
    assert visit.form_data["assessments"]["sppb"]["total"] == "旧文本"
    assert visit.form_data["crf"]["_field_meta"] == {key: {"state": "unknown", "reason": "新原因"}}


@pytest.mark.django_db
@pytest.mark.parametrize(
    "form_data",
    [
        {"assessments": {"sppb": {"balance": 5}}},
        {"crf": {"adverse_events": {"entries": [{"_row_id": "new", "severity": "非法"}]}}},
        {"crf": {"_field_meta": {"visit.form_data.assessments.sppb.total": {"state": "非法"}}}},
    ],
)
def test_create_visit_validates_registry_and_writes_nothing_on_error(
    doctor, project_patient, form_data
):
    VisitRecord.objects.filter(project_patient=project_patient, visit_type="T1").delete()
    response = _client(doctor).post(
        "/api/visits/",
        {
            "project_patient": project_patient.id,
            "visit_type": "T1",
            "status": "completed",
            "visit_date": "2026-10-08",
            "form_data": form_data,
        },
        format="json",
    )
    assert response.status_code == 400, response.data
    assert not VisitRecord.objects.filter(project_patient=project_patient, visit_type="T1").exists()


@pytest.mark.django_db
def test_candidate_merged_scores_are_validated_together(doctor, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T1")
    original = {"assessments": {"sppb": {"balance": 3, "gait": 2, "chair_stand": 2, "total": 7}}}
    visit.form_data = original
    visit.save()
    response = _client(doctor).patch(
        f"/api/visits/{visit.id}/",
        {"form_data": {"assessments": {"sppb": {"balance": 4}}}},
        format="json",
    )
    assert response.status_code == 400, response.data
    assert "assessments.sppb.total" in response.data
    visit.refresh_from_db()
    assert visit.form_data == original


@pytest.mark.django_db
@pytest.mark.parametrize(
    "rows",
    [
        [{"_row_id": "b", "severity": "旧非法"}, {"_row_id": "a", "event_name": "旧事件"}],
        [{"_row_id": "b", "severity": "旧非法", "event_name": "新说明"}],
        [],
    ],
)
def test_repeat_reorder_delete_or_edit_preserves_unmodified_historical_columns(
    doctor, project_patient, rows
):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T1")
    visit.form_data = {
        "crf": {
            "adverse_events": {
                "entries": [
                    {"_row_id": "a", "event_name": "旧事件"},
                    {"_row_id": "b", "severity": "旧非法"},
                ]
            }
        }
    }
    visit.save()
    response = _client(doctor).patch(
        f"/api/visits/{visit.id}/",
        {"form_data": {"crf": {"adverse_events": {"entries": rows}}}},
        format="json",
    )
    assert response.status_code == 200, response.data
    visit.refresh_from_db()
    assert visit.form_data["crf"]["adverse_events"]["entries"] == rows


@pytest.mark.django_db
@pytest.mark.parametrize(
    "rows,error",
    [
        ([{"_row_id": "b", "severity": "新非法"}], "0.severity"),
        ([{"_row_id": "b"}, {"_row_id": "b"}], "0._row_id"),
        ([{"_row_id": "a"}, {"_row_id": "a"}], "1._row_id"),
        ([{"_row_id": []}], "0._row_id"),
    ],
)
def test_repeat_new_invalid_values_and_id_conflicts_are_rejected(
    doctor, project_patient, rows, error
):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T1")
    original = {
        "crf": {
            "adverse_events": {
                "entries": [{"_row_id": "a"}, {"_row_id": "b", "severity": "旧非法"}]
            }
        }
    }
    visit.form_data = original
    visit.save()
    response = _client(doctor).patch(
        f"/api/visits/{visit.id}/",
        {"form_data": {"crf": {"adverse_events": {"entries": rows}}}},
        format="json",
    )
    assert response.status_code == 400, response.data
    assert "crf.adverse_events.entries." + error in response.data
    visit.refresh_from_db()
    assert visit.form_data == original


@pytest.mark.django_db
def test_historical_duplicate_row_id_does_not_block_other_column(doctor, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T1")
    visit.form_data = {
        "crf": {
            "adverse_events": {
                "entries": [{"_row_id": "a"}, {"_row_id": "a", "severity": "旧非法"}]
            }
        }
    }
    visit.save()
    response = _client(doctor).patch(
        f"/api/visits/{visit.id}/",
        {
            "form_data": {
                "crf": {
                    "adverse_events": {
                        "entries": [
                            {"_row_id": "a"},
                            {"_row_id": "a", "severity": "旧非法", "event_name": "新说明"},
                        ]
                    }
                }
            }
        },
        format="json",
    )
    assert response.status_code == 200, response.data


@pytest.mark.django_db
def test_partial_visit_date_switches_and_native_date_clears_parts(doctor, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T1")
    visit.visit_date = "2026-10-08"
    visit.save()
    parts = {"year": {"state": "value", "value": 2026}, "month": {"state": "unknown"}}
    client = _client(doctor)
    response = client.patch(
        f"/api/visits/{visit.id}/",
        {"form_data": {"crf": {"meta": {"visit_date_parts": parts}}}},
        format="json",
    )
    assert response.status_code == 200, response.data
    visit.refresh_from_db()
    assert visit.visit_date is None
    assert visit.form_data["crf"]["meta"]["visit_date_parts"] == parts
    response = client.patch(f"/api/visits/{visit.id}/", {"visit_date": "2026-10-09"}, format="json")
    assert response.status_code == 200, response.data
    visit.refresh_from_db()
    assert visit.visit_date.isoformat() == "2026-10-09"
    assert visit.form_data["crf"]["meta"]["visit_date_parts"] is None


@pytest.mark.django_db
@pytest.mark.parametrize(
    "payload",
    [
        {"visit_date": "2026-02-30"},
        {"visit_date": {"year": {"state": "unknown"}}},
        {
            "visit_date": "2026-10-08",
            "form_data": {"crf": {"meta": {"visit_date_parts": {"year": {"state": "unknown"}}}}},
        },
        {
            "form_data": {
                "crf": {
                    "meta": {
                        "visit_date_parts": {
                            "month": {"state": "value", "value": 2},
                            "day": {"state": "value", "value": 30},
                        }
                    }
                }
            }
        },
    ],
)
def test_invalid_dates_roll_back_completion(doctor, project_patient, payload):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T1")
    response = _client(doctor).patch(
        f"/api/visits/{visit.id}/", {**payload, "status": "completed"}, format="json"
    )
    assert response.status_code == 400, response.data
    visit.refresh_from_db()
    assert visit.status == "draft"
    assert visit.visit_date is None
    assert visit.form_data == {}


@pytest.mark.django_db
@pytest.mark.parametrize("ids", [False, True])
@pytest.mark.parametrize("delete", [False, True])
def test_legacy_unidentified_rows_can_be_reordered_or_deleted_without_revalidation(
    doctor, project_patient, ids, delete
):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T1")
    rows = [{"severity": "旧非法甲"}, {"severity": "旧非法乙"}]
    if ids:
        rows = [{**row, "_row_id": "旧重复ID"} for row in rows]
    visit.form_data = {"crf": {"adverse_events": {"entries": rows}}}
    visit.save()
    incoming = [rows[1]] if delete else list(reversed(rows))
    response = _client(doctor).patch(
        f"/api/visits/{visit.id}/",
        {"form_data": {"crf": {"adverse_events": {"entries": incoming}}}},
        format="json",
    )
    assert response.status_code == 200, response.data
    visit.refresh_from_db()
    assert visit.form_data["crf"]["adverse_events"]["entries"] == incoming


@pytest.mark.django_db
def test_historical_assessments_container_remains_visible_after_unrelated_patch(
    doctor, project_patient
):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T1")
    visit.form_data = {
        "assessments": "历史量表总文本",
        "computed_assessments": {"source": "server"},
    }
    visit.save()
    response = _client(doctor).patch(
        f"/api/visits/{visit.id}/",
        {
            "form_data": {
                "crf": {"adherence": {"platform_id": "P1"}},
                "computed_assessments": {"source": "client"},
            }
        },
        format="json",
    )
    assert response.status_code == 200, response.data
    assert response.data["form_data"]["assessments"] == "历史量表总文本"
    visit.refresh_from_db()
    assert visit.form_data["assessments"] == "历史量表总文本"
    assert visit.form_data["computed_assessments"] == {"source": "server"}


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("target", ["visit", "baseline_existing", "baseline_new"])
def test_concurrent_partial_writes_validate_locked_current_record(
    doctor, project_patient, monkeypatch, target
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event, current_thread

    from django.db import close_old_connections, connection

    from apps.patients.models import PatientBaseline
    from apps.patients.serializers import PatientBaselineSerializer
    from apps.visits.serializers import VisitRecordSerializer

    if target == "visit":
        record = VisitRecord.objects.get(project_patient=project_patient, visit_type="T1")
        url = f"/api/visits/{record.pk}/"
        payloads = [
            {"form_data": {"assessments": {"sppb": {"balance": 3}}}},
            {"form_data": {"assessments": {"sppb": {"gait": 2}}}},
        ]
        serializer_class = VisitRecordSerializer
        table = "visits_visitrecord"
    else:
        if target == "baseline_existing":
            PatientBaseline.objects.create(patient=project_patient.patient)
        url = f"/api/patients/{project_patient.patient_id}/baseline/"
        payloads = [{"demographics": {"education_years": 9}}, {"demographics": {"gender": "男"}}]
        serializer_class = PatientBaselineSerializer
        table = "patients_patient"
    first_validating, release_first, second_query, second_validating = (Event() for _ in range(4))
    first_thread = []
    real_validate = serializer_class.validate

    def paused_validate(self, attrs):
        if current_thread().name == first_thread[0]:
            first_validating.set()
            assert release_first.wait(10), "首个请求等待释放超时"
        else:
            second_validating.set()
        return real_validate(self, attrs)

    monkeypatch.setattr(serializer_class, "validate", paused_validate)

    def write(index):
        close_old_connections()
        if index == 0:
            first_thread.append(current_thread().name)

        def observe_query(execute, sql, params, many, context):
            if index == 1 and sql.lstrip().upper().startswith("SELECT") and table in sql:
                second_query.set()
            return execute(sql, params, many, context)

        try:
            with connection.execute_wrapper(observe_query):
                response = _client(doctor).patch(url, payloads[index], format="json")
            return response.status_code, response.data
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(write, 0)
        try:
            assert first_validating.wait(10)
            second = executor.submit(write, 1)
            assert second_query.wait(10)
            # First request holds its row lock throughout candidate validation.
            assert not second_validating.wait(0.2)
        finally:
            release_first.set()
        first_result, second_result = first.result(timeout=10), second.result(timeout=10)
    assert first_result[0] == second_result[0] == 200, (first_result, second_result)
    if target == "visit":
        record.refresh_from_db()
        assert record.form_data["assessments"]["sppb"] == {"balance": 3, "gait": 2}
    else:
        assert PatientBaseline.objects.get(patient=project_patient.patient).demographics == {
            "education_years": 9,
            "gender": "男",
        }


@pytest.mark.django_db
@pytest.mark.parametrize("role", [None, "patient"])
@pytest.mark.parametrize("method", ["post", "patch", "delete"])
def test_visit_write_permissions_are_preserved(doctor, project_patient, role, method):
    from apps.accounts.models import User

    client = APIClient()
    if role:
        user = User.objects.create_user(
            phone="13900007777", password="pass123456", name="患者端", role=role
        )
        client.force_authenticate(user)
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T1")
    url = "/api/visits/" if method == "post" else f"/api/visits/{visit.pk}/"
    response = getattr(client, method)(
        url,
        {"project_patient": project_patient.id, "visit_type": "T1", "status": "completed"},
        format="json",
    )
    assert response.status_code in (401, 403)
    visit.refresh_from_db()
    assert visit.status == "draft"
    assert visit.form_data == {}


@pytest.mark.django_db
def test_create_preserves_only_server_computed_assessments(doctor, project_patient):
    VisitRecord.objects.filter(project_patient=project_patient, visit_type="T1").delete()
    response = _client(doctor).post(
        "/api/visits/",
        {
            "project_patient": project_patient.id,
            "visit_type": "T1",
            "form_data": {"computed_assessments": {"sppb": {"total": 123}}},
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    assert (
        VisitRecord.objects.get(pk=response.data["id"]).form_data.get("computed_assessments", {})
        == {}
    )


@pytest.mark.django_db
def test_resubmitted_legacy_container_is_not_a_new_invalid_value(doctor, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T1")
    visit.form_data = {"assessments": "历史量表总文本"}
    visit.save()
    response = _client(doctor).patch(
        f"/api/visits/{visit.id}/",
        {
            "form_data": {
                "assessments": "历史量表总文本",
                "crf": {"adherence": {"platform_id": "P1"}},
            }
        },
        format="json",
    )
    assert response.status_code == 200, response.data
    visit.refresh_from_db()
    assert visit.form_data["assessments"] == "历史量表总文本"
    assert visit.form_data["crf"]["adherence"]["platform_id"] == "P1"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "old,patch,error",
    [
        (
            {"assessments": "历史量表总文本"},
            {"assessments": {"sppb": {"balance": 3}}},
            "assessments",
        ),
        (
            {"crf": {"adverse_events": {"entries": "历史事件原文"}}},
            {"crf": {"adverse_events": {"entries": [{"_row_id": "new", "event_name": "新事件"}]}}},
            "crf.adverse_events.entries",
        ),
        (
            {"crf": {"meta": {"assessed_on": "旧日期说明"}}},
            {"crf": {"meta": {"assessed_on": {"year": {"state": "unknown"}}}}},
            "crf.meta.assessed_on",
        ),
    ],
)
def test_visit_structure_patch_cannot_erase_historical_scalar(
    doctor, project_patient, old, patch, error
):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T1")
    visit.form_data = old
    visit.save()
    response = _client(doctor).patch(
        f"/api/visits/{visit.pk}/", {"status": "completed", "form_data": patch}, format="json"
    )
    assert response.status_code == 400, response.data
    assert error in response.data
    visit.refresh_from_db()
    assert visit.form_data == old
    assert visit.status == "draft"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "old,error",
    [
        ("历史完整表单原文", "form_data"),
        ({"crf": "历史CRF原文"}, "crf"),
        ({"crf": {"meta": "历史访视信息原文"}}, "crf.meta"),
    ],
)
def test_native_date_autoclear_preserves_historical_parent(doctor, project_patient, old, error):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T1")
    visit.form_data = old
    visit.visit_date = "2026-10-07"
    visit.save()
    response = _client(doctor).patch(
        f"/api/visits/{visit.pk}/",
        {"visit_date": "2026-10-08", "status": "completed"},
        format="json",
    )
    assert response.status_code == 200, response.data
    visit.refresh_from_db()
    assert visit.form_data == old
    assert visit.visit_date.isoformat() == "2026-10-08"
    assert visit.status == "completed"


@pytest.mark.django_db
def test_visit_controlled_date_and_explicit_clear_keep_supported_semantics(doctor, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T1")
    visit.form_data = {
        "crf": {
            "meta": {"assessed_on": "2026-10-08"},
            "adverse_events": {
                "entries": [{"_row_id": "a", "occurred_on": "2026-10-08", "event_name": "旧说明"}]
            },
        }
    }
    visit.save()
    parts = {"year": {"state": "value", "value": 2026}, "month": {"state": "unknown"}}
    response = _client(doctor).patch(
        f"/api/visits/{visit.pk}/",
        {
            "form_data": {
                "crf": {
                    "meta": {"assessed_on": parts},
                    "adverse_events": {
                        "entries": [{"_row_id": "a", "occurred_on": parts, "event_name": None}]
                    },
                }
            }
        },
        format="json",
    )
    assert response.status_code == 200, response.data
    visit.refresh_from_db()
    assert visit.form_data["crf"]["meta"]["assessed_on"] == parts
    assert visit.form_data["crf"]["adverse_events"]["entries"] == [
        {"_row_id": "a", "occurred_on": parts, "event_name": None}
    ]


@pytest.mark.django_db
@pytest.mark.parametrize("explicit", [False, True])
def test_native_date_preserves_user_patch_when_autoclear_parent_is_legacy(
    doctor, project_patient, explicit
):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T1")
    visit.form_data = {"crf": "历史CRF原文", "assessments": {"sppb": {"balance": 2}}}
    visit.save()
    payload = {"visit_date": "2026-10-08", "form_data": {"assessments": {"sppb": {"balance": 3}}}}
    if explicit:
        payload["form_data"]["crf"] = {"meta": {"visit_date_parts": None}}
    response = _client(doctor).patch(f"/api/visits/{visit.pk}/", payload, format="json")
    assert response.status_code == (400 if explicit else 200), response.data
    visit.refresh_from_db()
    assert visit.form_data["crf"] == "历史CRF原文"
    assert visit.form_data["assessments"]["sppb"]["balance"] == (2 if explicit else 3)
    assert visit.visit_date is None if explicit else visit.visit_date.isoformat() == "2026-10-08"


@pytest.mark.django_db
def test_visit_date_answer_round_trip_and_projection(doctor,project_patient):
    from datetime import date
    v=VisitRecord.objects.get(project_patient=project_patient,visit_type='T0')
    c=APIClient();c.force_authenticate(doctor);url=f'/api/visits/{v.pk}/'
    unknown={'__crf_answer__':1,'state':'unknown','value':'2026-10-10','reason':None}
    for answer,projection in [('2026-10-10',date(2026,10,10)),(unknown,None),('2026',None),('2026-10',None),('2026-10-10',date(2026,10,10)),(None,None)]:
        response=c.patch(url,{'visit_date':answer},format='json')
        assert response.status_code==200,response.data
        v.refresh_from_db()
        assert v.visit_date==projection
        assert v.form_data['crf']['meta']['visit_date_answer']==answer
        assert c.get(url).data['visit_date']==answer

@pytest.mark.django_db
def test_visit_date_answer_conflict_rejected_and_unrelated_old_parts_retained(doctor,project_patient):
    from datetime import date
    v=VisitRecord.objects.get(project_patient=project_patient,visit_type='T0')
    old={'year':{'state':'value','value':2020},'month':{'state':'unknown'}}
    v.visit_date=date(2020,1,2);v.form_data={'crf':{'meta':{'visit_date_parts':old}}};v.save()
    c=APIClient();c.force_authenticate(doctor);url=f'/api/visits/{v.pk}/'
    response=c.patch(url,{'form_data':{'crf':{'meta':{'assessor_name':'新姓名'}}}},format='json')
    assert response.status_code==200,response.data
    v.refresh_from_db();assert v.form_data['crf']['meta']['visit_date_parts']==old and v.visit_date==date(2020,1,2)
    response=c.patch(url,{'visit_date':'2026-10-10','form_data':{'crf':{'meta':{'visit_date_answer':'2026-10-11'}}}},format='json')
    assert response.status_code==400
    v.refresh_from_db();assert v.visit_date==date(2020,1,2)
    response=c.patch(url,{'visit_date':'2026-10'},format='json')
    assert response.status_code==200,response.data
    v.refresh_from_db();assert v.visit_date is None and v.form_data['crf']['meta']['visit_date_parts'] is None

@pytest.mark.django_db
@pytest.mark.parametrize('answer',['2026-02-31','2026-13','0000',{'__crf_answer__':True,'state':'unknown','value':None,'reason':None}])
def test_visit_date_answer_rejects_invalid_calendar_or_core(doctor,project_patient,answer):
    v=VisitRecord.objects.get(project_patient=project_patient,visit_type='T0')
    c=APIClient();c.force_authenticate(doctor)
    response=c.patch(f'/api/visits/{v.pk}/',{'visit_date':answer},format='json')
    assert response.status_code==400 and 'visit_date' in response.data


@pytest.mark.django_db
def test_legacy_explicit_parts_with_native_null_remain_the_logical_date(doctor,project_patient):
    from rest_framework.test import APIClient
    from apps.visits.models import VisitRecord
    from apps.crf.services.aggregate import build_crf_preview
    client=APIClient();client.force_authenticate(doctor)
    visit=VisitRecord.objects.get(project_patient=project_patient,visit_type='T0')
    parts={'year':{'state':'value','value':2020},'month':{'state':'unknown'},'day':{'state':'unknown'}}
    response=client.patch(f'/api/visits/{visit.pk}/',{'visit_date':None,'form_data':{'crf':{'meta':{'visit_date_parts':parts}}}},format='json')
    assert response.status_code==200,response.data
    visit.refresh_from_db();assert visit.visit_date is None
    assert response.data['visit_date']==parts
    assert visit.form_data['crf']['meta']['visit_date_answer']==parts
    preview=build_crf_preview(project_patient)
    item=next(f for section in preview['sections'] for f in section['fields'] if f['field_id']=='vd_T0_visit_date')
    assert item['state']=='unknown' and not item['issues']
