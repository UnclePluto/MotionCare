from pathlib import Path

from django.core.management.base import BaseCommand

from apps.prescriptions import motion_video_assets


class Command(BaseCommand):
    help = "校验并幂等上传五个正式动作教学视频"

    def add_arguments(self, parser):
        parser.add_argument("--source-root", required=True)
        parser.add_argument("--check-only", action="store_true")

    def handle(self, *args, **options):
        source_root = Path(options["source_root"])
        if options["check_only"]:
            motion_video_assets.validate_motion_action_assets(source_root)
            return

        for asset in motion_video_assets.upload_motion_action_assets(source_root):
            status = "已存在" if asset.status == "existing" else "已上传"
            self.stdout.write(
                f"{asset.source_key} {asset.object_key} {asset.size_bytes} {status}"
            )
