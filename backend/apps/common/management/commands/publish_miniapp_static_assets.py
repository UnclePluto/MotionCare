from pathlib import Path

from django.core.management.base import BaseCommand

from apps.common.miniapp_static_assets import (
    publish_miniapp_static_assets,
    validate_miniapp_static_assets,
)


class Command(BaseCommand):
    help = "校验或幂等发布小程序固定素材到七牛"

    def add_arguments(self, parser):
        parser.add_argument("--source-root", required=True, type=Path)
        parser.add_argument("--check-only", action="store_true")

    def handle(self, *args, **options):
        source_root = options["source_root"]
        if options["check_only"]:
            for asset in validate_miniapp_static_assets(source_root):
                self.stdout.write(
                    f"{asset.key} {asset.object_key} {asset.size_bytes} 本地已校验"
                )
            return

        for asset in publish_miniapp_static_assets(source_root):
            status = "已存在" if asset.status == "existing" else "已上传"
            self.stdout.write(
                f"{asset.key} {asset.object_key} {asset.size_bytes} {status}"
            )
