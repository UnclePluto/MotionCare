from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.common.miniapp_signed_asset_verification import (
    SignedAssetVerificationError,
    verify_signed_static_assets,
)


class Command(BaseCommand):
    help = "只读验收小程序私有素材正文和匿名、篡改、过期访问拒绝"

    def add_arguments(self, parser):
        parser.add_argument("--source-root", required=True, type=Path)
        parser.add_argument("--api-base-url", required=True)

    def handle(self, *args, **options):
        try:
            assets = verify_signed_static_assets(options["source_root"], options["api_base_url"])
        except SignedAssetVerificationError as error:
            raise CommandError(str(error)) from None
        for asset in assets:
            self.stdout.write(f"{asset.key} {asset.size_bytes} 字节 SHA-256 已校验")
        self.stdout.write("匿名、篡改、过期访问拒绝检查通过")
