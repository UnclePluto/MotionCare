import re
import signal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.training.pose_benchmark import BenchmarkFailure, run_pose_smoke_benchmark

SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
COMMIT_PATTERN = re.compile(r"^[a-f0-9]{7,40}$")


class Command(BaseCommand):
    help = "Run isolated PP-TinyPose smoke benchmark without database access"

    def add_arguments(self, parser):
        parser.add_argument("--video", required=True)
        parser.add_argument("--report", required=True)
        parser.add_argument("--summary", required=True)
        parser.add_argument("--expected-sha256", required=True)
        parser.add_argument("--git-commit", required=True)
        parser.add_argument("--delete-input", action="store_true")

    def handle(self, *args, **options):
        video = Path(options["video"])
        report = Path(options["report"])
        summary = Path(options["summary"])
        expected_sha256 = options["expected_sha256"].lower()
        git_commit = options["git_commit"].lower()
        if video.is_symlink() or not video.is_file():
            raise CommandError("视频必须是普通文件且不能是符号链接")
        if not SHA256_PATTERN.fullmatch(expected_sha256):
            raise CommandError("expected-sha256 格式无效")
        if not COMMIT_PATTERN.fullmatch(git_commit):
            raise CommandError("git-commit 格式无效")
        if report.parent.resolve() == video.parent.resolve():
            raise CommandError("报告不能写入输入目录")
        if summary.parent.resolve() == video.parent.resolve():
            raise CommandError("摘要不能写入输入目录")

        previous_sigterm = signal.getsignal(signal.SIGTERM)

        def interrupt_on_sigterm(signum, frame):
            raise KeyboardInterrupt("received SIGTERM")

        signal.signal(signal.SIGTERM, interrupt_on_sigterm)
        try:
            result = run_pose_smoke_benchmark(
                video,
                report_path=report,
                summary_path=summary,
                expected_sha256=expected_sha256,
                git_commit=git_commit,
            )
        except (BenchmarkFailure, RuntimeError) as exc:
            raise CommandError("冒烟测试失败，详情见脱敏报告") from exc
        finally:
            signal.signal(signal.SIGTERM, previous_sigterm)
            if options["delete_input"]:
                video.unlink(missing_ok=True)

        self.stdout.write(self.style.SUCCESS(f"冒烟测试完成：{result['status']}"))
