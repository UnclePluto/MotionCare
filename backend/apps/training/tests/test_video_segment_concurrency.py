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
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.patients.models import Patient
from apps.prescriptions.models import ActionLibraryItem, Prescription
from apps.studies.models import ProjectPatient, StudyGroup, StudyProject
from apps.training import video_services
from apps.training.models import TrainingVideo, TrainingVideoSegment
from apps.training.video_services import (
    SessionConflict,
    create_training_video_session,
    store_training_video_segment,
)
from apps.training.video_staging import segment_install_lock, segment_path


def _start_database_thread(name, operation, results, errors, backend_pids=None):
    def runner():
        close_old_connections()
        try:
            if backend_pids is not None:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    backend_pids[name] = cursor.fetchone()[0]
            results[name] = operation()
        except Exception as exc:  # pragma: no branch - thread result capture
            errors[name] = exc
        finally:
            close_old_connections()

    return threading.Thread(target=runner, name=name)


def _join_threads(test_case, *threads):
    for thread in threads:
        thread.join(10)
        test_case.assertFalse(thread.is_alive())


class SegmentInstallLockTests(SimpleTestCase):
    def test_second_thread_waits_for_first_lock_holder(self):
        video = SimpleNamespace(
            pk=1,
            client_session_id=uuid.UUID("8cf99c30-9b03-4bda-b4d3-b492f3a2db12"),
        )
        first_entered = threading.Event()
        release_first = threading.Event()
        second_entered = threading.Event()
        errors = []

        def first_holder():
            try:
                with segment_install_lock(video, 0):
                    first_entered.set()
                    self.assertTrue(release_first.wait(5))
            except Exception as exc:  # pragma: no branch - thread result capture
                errors.append(exc)

        def second_holder():
            try:
                self.assertTrue(first_entered.wait(5))
                with segment_install_lock(video, 0):
                    second_entered.set()
            except Exception as exc:  # pragma: no branch - thread result capture
                errors.append(exc)

        with TemporaryDirectory() as staging_root, override_settings(
            TRAINING_VIDEO_STAGING_ROOT=staging_root
        ):
            first = threading.Thread(target=first_holder)
            second = threading.Thread(target=second_holder)
            first.start()
            self.assertTrue(first_entered.wait(5))
            second.start()
            self.assertFalse(second_entered.wait(0.25))
            release_first.set()
            _join_threads(self, first, second)

        self.assertEqual(errors, [])
        self.assertTrue(second_entered.is_set())


class VideoSegmentServiceFixture:
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
        group = StudyGroup.objects.create(project=project, name="干预组", target_ratio=1)
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
        action = prescription.add_action_snapshot(
            ActionLibraryItem.objects.get(
                source_key="motion-resistance-shoulder-press"
            ),
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

    def store_segment(self, index, content):
        return store_training_video_segment(
            project_patient=ProjectPatient.objects.get(pk=self.project_patient.pk),
            video_id=self.video.pk,
            index=index,
            uploaded_file=SimpleUploadedFile(
                f"segment-{index}.mp4", content, content_type="video/mp4"
            ),
            duration_ms=1000,
            declared_size_bytes=len(content),
        )


class SegmentInstallCleanupTests(VideoSegmentServiceFixture, TestCase):
    def test_failed_segment_save_unlinks_while_install_lock_is_active(self):
        destination = segment_path(self.video, 0)
        lock_active = False
        original_lock = video_services.segment_install_lock
        original_unlink = Path.unlink

        @contextmanager
        def observed_lock(video, index):
            nonlocal lock_active
            with original_lock(video, index):
                lock_active = True
                try:
                    yield
                finally:
                    lock_active = False

        def fail_segment_create(**kwargs):
            raise RuntimeError("模拟分段数据库保存失败")

        def assert_cleanup_holds_lock(path, *args, **kwargs):
            if path == destination:
                self.assertTrue(lock_active)
            return original_unlink(path, *args, **kwargs)

        with (
            patch.object(video_services, "segment_install_lock", observed_lock),
            patch.object(
                TrainingVideoSegment.objects,
                "create",
                side_effect=fail_segment_create,
            ),
            patch.object(Path, "unlink", new=assert_cleanup_holds_lock),
        ):
            with self.assertRaisesRegex(RuntimeError, "数据库保存失败"):
                self.store_segment(0, b"failed-content")

        self.assertFalse(destination.exists())
        self.assertFalse(TrainingVideoSegment.objects.exists())


@skipUnless(
    connection.vendor == "postgresql",
    "需要 PostgreSQL 验证 select_for_update 行锁语义",
)
class TrainingVideoPostgresConcurrencyTests(
    VideoSegmentServiceFixture, TransactionTestCase
):
    serialized_rollback = True

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
            if threading.current_thread().name == "first":
                first_inserted.set()
                self.assertTrue(release_first.wait(10))
            return segment

        def observed_fetch_all(queryset):
            if (
                threading.current_thread().name == "second"
                and queryset.model is TrainingVideo
                and queryset.query.select_for_update
            ):
                second_select_started.set()
            return original_fetch_all(queryset)

        first = _start_database_thread(
            "first",
            lambda: self.store_segment(0, b"first"),
            results,
            errors,
            backend_pids,
        )
        second = _start_database_thread(
            "second",
            lambda: self._store_second_segment(second_done),
            results,
            errors,
            backend_pids,
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
                _join_threads(self, first, second)

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

    def _store_second_segment(self, second_done):
        try:
            return self.store_segment(1, b"second")
        finally:
            second_done.set()

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

        def create_session(expected_duration_seconds):
            return create_training_video_session(
                project_patient=ProjectPatient.objects.get(pk=self.project_patient.pk),
                client_session_id=session_id,
                prescription_action_id=self.video.prescription_action_id,
                training_date=self.video.training_date,
                expected_duration_seconds=expected_duration_seconds,
            )

        first = _start_database_thread(
            "first",
            lambda: create_session(4),
            results,
            errors,
            backend_pids,
        )
        second = _start_database_thread(
            "second",
            lambda: create_session(5),
            results,
            errors,
            backend_pids,
        )

        with patch.object(TrainingVideo.objects, "create", side_effect=synchronized_create):
            first.start()
            second.start()
            _join_threads(self, first, second)

        self.assertEqual(len(set(backend_pids.values())), 2)
        self.assertEqual(len(results), 1)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(next(iter(errors.values())), SessionConflict)
        winner, created = next(iter(results.values()))
        self.assertTrue(created)
        self.assertEqual(
            TrainingVideo.objects.get(
                project_patient=self.project_patient,
                client_session_id=session_id,
            ),
            winner,
        )
