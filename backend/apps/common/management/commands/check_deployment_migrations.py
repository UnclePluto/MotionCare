from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.loader import MigrationLoader


class Command(BaseCommand):
    help = "拒绝发布缺少线上已应用迁移的代码版本"

    def handle(self, *args, **options):
        loader = MigrationLoader(connection)
        known = set(loader.disk_migrations)
        for migration in loader.disk_migrations.values():
            known.update(migration.replaces)
        missing = set(loader.applied_migrations) - known
        if missing:
            names = ", ".join(f"{app}.{name}" for app, name in sorted(missing))
            raise CommandError(f"发布版本缺少数据库已应用的迁移，停止切换服务：{names}")
        loader.check_consistent_history(connection)
        self.stdout.write(self.style.SUCCESS("发布迁移兼容性检查通过"))
