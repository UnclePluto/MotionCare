import json
import uuid

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder

from apps.training.upload_diagnostics import (
    DIAGNOSTIC_FIELDS,
    current_diagnostics,
    sanitize_diagnostic_message,
)


class Command(BaseCommand):
    help = "查询十五天内的脱敏训练上传诊断"

    def add_arguments(self, parser):
        parser.add_argument("--video-id", type=int)
        parser.add_argument("--client-session-id", type=uuid.UUID)
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        if not 1 <= options["limit"] <= 100:
            raise CommandError("查询数量必须在 1 至 100 之间")
        if not options["video_id"] and not options["client_session_id"]:
            raise CommandError("请提供 video-id 或 client-session-id")
        query = current_diagnostics()
        if options["video_id"] is not None:
            query = query.filter(video_id=options["video_id"])
        if options["client_session_id"] is not None:
            query = query.filter(client_session_id=options["client_session_id"])
        result = list(
            query.order_by("-received_at", "-pk").values(*DIAGNOSTIC_FIELDS)[: options["limit"]]
        )
        for row in result:
            row["message"] = sanitize_diagnostic_message(row["message"])
        self.stdout.write(json.dumps(result, cls=DjangoJSONEncoder, ensure_ascii=False))
