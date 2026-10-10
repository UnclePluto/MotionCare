import json

from django.core.management.base import BaseCommand, CommandError

from apps.crf.registry_loader import CrfAssetError, check_crf_assets


class Command(BaseCommand):
    help = "检查 CRF 原表与字段资产的版本、哈希及可读性，不连接数据库。"
    requires_system_checks = []

    def handle(self, *args, **options):
        try:
            result = check_crf_assets()
        except CrfAssetError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, ensure_ascii=False))
