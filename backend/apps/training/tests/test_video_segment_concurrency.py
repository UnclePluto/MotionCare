import os
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections, connection
from django.db.models.query import QuerySet
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.patients.models import Patient
from apps.prescriptions.models import ActionLibraryItem, Prescription
from apps.studies.models import ProjectPatient, StudyGroup, StudyProject
from apps.training.models import TrainingVideo, TrainingVideoSegment
from apps.training import video_services
from apps.training.video_services import (
    SessionConflict,
    create_training_video_session,
    store_training_video_segment,
)
from apps.training.video_staging import segment_install_lock, segment_path


class SegmentInstallLockTests(SimpleTestCase):
    def test_failed_install_cleanup_cannot_delete_a_waiting_retry_file(self):
        with TemporaryDirectory() as staging_root:
            video = SimpleNamespace(
                client_session_id=uuid.UUID("8cf99c30-9b03-4bda-b4d3-b492f3a2db12")
            )
            destination = Path(staging_root) / video.client_session_id.hex / "segments" / "000000.mp4"
            failed_install_ready = threading.Event()
            retry_attempted = threading.Event()
            retry_installed = threading.Event()
            allow_cleanup = threading.Event()
            errors = []

            def failed_upload():
                try:
                    temporary = destination.with_suffix(".failed.part")
                    temporary.parent.mkdir(parents=True, exist_ok=True)
                    temporary.write_bytes(b"failed-content")
                    with segment_install_lock(video, 0):
                        os.replace(temporary, destination)
                        failed_install_ready.set()
                        self.assertTrue(retry_attempted.wait(5))
                        self.assertTrue(allow_cleanup.wait(5))
                        self.assertFalse(retry_installed.is_set())
                        destination.unlink()
                except Exception as exc:  # pragma: no branch - thread result capture
                    errors.append(exc)

            def retry_upload():
                try:
                    self.assertTrue(failed_install_ready.wait(5))
                    retry_attempted.set()
                    with segment_install_lock(video, 0):
                        temporary = destination.with_suffix(".retry.part")
                        temporary.write_bytes(b"successful-content")
                        os.replace(temporary, destination)
                        retry_installed.set()
                except Exception as exc:  # pragma: no branch - thread result capture
                    errors.append(exc)

            with override_settings(TRAINING_VIDEO_STAGING_ROOT=staging_root):
                failing = threading.Thread(target=failed_upload)
                retrying = threading.Thread(target=retry_upload)
                failing.start()
                self.assertTrue(failed_install_ready.wait(5))
                retrying.start()
                self.assertTrue(retry_attempted.wait(5))
                allow_cleanup.set()
                failing.join(10)
                retrying.join(10)

            self.assertFalse(failing.is_alive())
            self.assertFalse(retrying.is_alive())
            self.assertEqual(errors, [])
            self.assertTrue(retry_installed.is_set())
            self.assertEqual(destination.read_bytes(), b"successful-content")


@skipUnless(
    connection.vendor == "postgresql",
    "需要 PostgreSQL 验证 select_for_update 行锁语义",
)
class TrainingVideoPostgresConcurrencyTests(TransactionTestCase):
    serialized_rollback = True

    def setUp(self):
        super().setUp()
        self.staging_directory = TemporaryDirectory()
        self.addCleanup(self.staging_directory.cleanup)
        self.settings_override = override_settings(
            TRAINING_VIDEO_STAGING_ROOT=self.staging_directory.name,
            TRAINING_VIDEO_SEGMENT_MAX_SIZE_BYTES=1024,
            TRAINING_VIDEO_MAX_SIZE_BYTES=4096,
            TRAINING_VIDEO_MAX_DURATION_SECONDS=10,
            TRAINING_VIDEO_MAX_SEGMENTS=4,
            TRAINING_VIDEO_MIN_FREE_BYTES=0,
            FFMPEG_PATH="/usr/bin/true",
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

        doctor = User.objects.create_user(
            phone="13800009991",
            password="pass123456",
            name="并发测试医生",
            role=User.Role.DOCTOR,
        )
        patient = Patient.objects.create(
            name="并发测试患者",
            gender=Patient.Gender.MALE,
            age=70,
            phone="13900009991",
            primary_doctor=doctor,
        )
        project = StudyProject.objects.create(name="并发测试项目", created_by=doctor)
        group = StudyGroup.objects.create(
            project=project,
            name="干预组",
            target_ratio=1,
        )
        self.project_patient = ProjectPatient.objects.create(
            project=project,
            patient=patient,
            group=group,
        )
        prescription = Prescription.objects.create(
            project_patient=self.project_patient,
            version=1,
            opened_by=doctor,
            status=Prescription.Status.ACTIVE,
            effective_at=timezone.now(),
        )
        item = ActionLibraryItem.objects.get(source_key="motion-resistance-shoulder-press")
        action = prescription.add_action_snapshot(
            item,
            weekly_frequency="2 次/周",
            weekly_target_count=2,
            duration_minutes=10,
        )
        self.video = TrainingVideo.objects.create(
            project_patient=self.project_patient,
            prescription=prescription,
            prescription_action=action,
            client_session_id=uuid.UUID("8cf99c30-9b03-4bda-b4d3-b492f3a2db12"),
            training_date="2026-07-11",
            expected_duration_seconds=5,
            status=TrainingVideo.Status.RECORDING,
        )

    def test_two_connections_serialize_segment_totals_on_video_row_lock(self):
        first_inserted = threading.Event()
        release_first = threading.Event()
        second_select_started = threading.Event()
        second_done = threading.Event()
        results = {}
        errors = {}
        backend_pids = {}
        original_create = TrainingVideoSegment.objects.create
        original_fetch_all = QuerySet._fetch_all

        def blocking_create(**kwargs):
            segment = original_create(**kwargs)
            if threading.current_thread().name == "first-segment":
                first_inserted.set()
                if not release_first.wait(10):
                    raise TimeoutError("未收到释放首个事务的信号")
            return segment

        def observed_fetch_all(queryset):
            if (
                threading.current_thread().name == "second-segment"
                and queryset.model is TrainingVideo
                and queryset.query.select_for_update
            ):
                second_select_started.set()
            return original_fetch_all(queryset)

        def upload(name, index, content):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    backend_pids[name] = cursor.fetchone()[0]
                results[name] = store_training_video_segment(
                    project_patient=ProjectPatient.objects.get(pk=self.project_patient.pk),
                    video_id=self.video.pk,
                    index=index,
                    uploaded_file=SimpleUploadedFile(
                        f"{name}.mp4", content, content_type="video/mp4"
                    ),
                    duration_ms=1000,
                    declared_size_bytes=len(content),
                )
            except Exception as exc:  # pragma: no branch - thread result capture
                errors[name] = exc
            finally:
                if name == "second":
                    second_done.set()
                close_old_connections()

        first = threading.Thread(
            target=upload,
            args=("first", 0, b"first"),
            name="first-segment",
        )
        second = threading.Thread(
            target=upload,
            args=("second", 1, b"second"),
            name="second-segment",
        )

        with (
            patch.object(
                TrainingVideoSegment.objects,
                "create",
                side_effect=blocking_create,
            ),
            patch.object(QuerySet, "_fetch_all", new=observed_fetch_all),
        ):
            try:
                first.start()
                self.assertTrue(first_inserted.wait(10))
                second.start()
                self.assertTrue(second_select_started.wait(10))
                self.assertFalse(second_done.wait(0.25))
            finally:
                release_first.set()
                first.join(10)
                second.join(10)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(errors, {})
        self.assertEqual(set(results), {"first", "second"})
        self.assertEqual(len(set(backend_pids.values())), 2)
        self.video.refresh_from_db()
        self.assertEqual(self.video.uploaded_segment_count, 2)
        self.assertEqual(
            set(
                TrainingVideoSegment.objects.filter(training_video=self.video).values_list(
                    "index", flat=True
                )
            ),
            {0, 1},
        )

    def test_two_connections_losing_session_create_checks_winner_payload(self):
        create_barrier = threading.Barrier(2)
        results = {}
        errors = {}
        backend_pids = {}
        original_create = TrainingVideo.objects.create
        session_id = uuid.UUID("8cf99c30-9b03-4bda-b4d3-b492f3a2db13")

        def synchronized_create(**kwargs):
            create_barrier.wait(10)
            return original_create(**kwargs)

        def create_session(name, expected_duration_seconds):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    backend_pids[name] = cursor.fetchone()[0]
                results[name] = create_training_video_session(
                    project_patient=ProjectPatient.objects.get(pk=self.project_patient.pk),
                    client_session_id=session_id,
                    prescription_action_id=self.video.prescription_action_id,
                    training_date=self.video.training_date,
                    expected_duration_seconds=expected_duration_seconds,
                )
            except Exception as exc:  # pragma: no branch - thread result capture
                errors[name] = exc
            finally:
                close_old_connections()

        with patch.object(TrainingVideo.objects, "create", side_effect=synchronized_create):
            first = threading.Thread(target=create_session, args=("first", 4))
            second = threading.Thread(target=create_session, args=("second", 5))
            first.start()
            second.start()
            first.join(10)
            second.join(10)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(len(set(backend_pids.values())), 2)
        self.assertEqual(len(results), 1)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(next(iter(errors.values())), SessionConflict)
        winner, created = next(iter(results.values()))
        self.assertTrue(created)
        self.assertEqual(
            TrainingVideo.objects.filter(
                project_patient=self.project_patient,
                client_session_id=session_id,
            ).get(),
            winner,
        )

    def test_failed_segment_save_cleans_up_before_retry_can_install(self):
        first_create_entered = threading.Event()
        second_attempted_lock = threading.Event()
        second_acquired_lock = threading.Event()
        errors = {}
        results = {}
        original_create = TrainingVideoSegment.objects.create
        original_install_lock = video_services.segment_install_lock
        original_unlink = Path.unlink
        destination = segment_path(self.video, 0)

        @contextmanager
        def observed_install_lock(video, index):
            if threading.current_thread().name == "retry-segment":
                second_attempted_lock.set()
            with original_install_lock(video, index):
                if threading.current_thread().name == "retry-segment":
                    second_acquired_lock.set()
                yield

        def fail_first_create(**kwargs):
            if threading.current_thread().name == "failing-segment":
                first_create_entered.set()
                self.assertTrue(second_attempted_lock.wait(10))
                raise RuntimeError("模拟分段数据库保存失败")
            return original_create(**kwargs)

        def assert_cleanup_holds_install_lock(path, *args, **kwargs):
            if path == destination and threading.current_thread().name == "failing-segment":
                self.assertFalse(second_acquired_lock.is_set())
            return original_unlink(path, *args, **kwargs)

        def upload(name, content):
            close_old_connections()
            try:
                results[name] = store_training_video_segment(
                    project_patient=ProjectPatient.objects.get(pk=self.project_patient.pk),
                    video_id=self.video.pk,
                    index=0,
                    uploaded_file=SimpleUploadedFile(
                        f"{name}.mp4", content, content_type="video/mp4"
                    ),
                    duration_ms=1000,
                    declared_size_bytes=len(content),
                )
            except Exception as exc:  # pragma: no branch - thread result capture
                errors[name] = exc
            finally:
                close_old_connections()

        with (
            patch.object(
                video_services,
                "segment_install_lock",
                observed_install_lock,
            ),
            patch.object(
                TrainingVideoSegment.objects,
                "create",
                side_effect=fail_first_create,
            ),
            patch.object(Path, "unlink", new=assert_cleanup_holds_install_lock),
        ):
            failing = threading.Thread(
                target=upload,
                args=("failing", b"failed-content"),
                name="failing-segment",
            )
            retrying = threading.Thread(
                target=upload,
                args=("retry", b"successful-content"),
                name="retry-segment",
            )
            failing.start()
            self.assertTrue(first_create_entered.wait(10))
            retrying.start()
            failing.join(10)
            retrying.join(10)

        self.assertFalse(failing.is_alive())
        self.assertFalse(retrying.is_alive())
        self.assertIsInstance(errors.get("failing"), RuntimeError)
        self.assertNotIn("retry", errors)
        self.assertTrue(results["retry"][1])
        self.assertTrue(second_acquired_lock.is_set())
        self.assertEqual(destination.read_bytes(), b"successful-content")
        self.assertTrue(
            TrainingVideoSegment.objects.filter(training_video=self.video, index=0).exists()
        )
