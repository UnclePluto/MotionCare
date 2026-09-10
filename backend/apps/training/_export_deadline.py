"""仅在当前导出连接/事务内保护 execute、DECLARE 与隐式 FETCH 的剩余预算。"""

from time import monotonic as _monotonic

from django.db import connection

from .export_rows import ExportDeadlineError


class StatementBudget:
    def __init__(self, *, deadline):
        self.deadline = deadline
        self._fetch_methods = {}

    def _set_remaining(self):
        remaining = self.deadline - _monotonic()
        if remaining <= 0:
            raise ExportDeadlineError("导出生成超时，请缩小日期范围")
        # Native cursor bypasses our execute wrapper (avoids recursion). This connection
        # is already inside the caller's read-only transaction, so true means SET LOCAL.
        with connection.connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('statement_timeout', %s, true)",
                [f"{max(1, int(remaining * 1000))}ms"],
            )

    def _execute(self, execute, sql, params, many, context):
        cursor = context["cursor"]
        if cursor not in self._fetch_methods:
            original = cursor.fetchmany
            self._fetch_methods[cursor] = original

            def fetchmany(*args, **kwargs):
                self._set_remaining()
                return original(*args, **kwargs)

            # Django delegates fetchmany directly to psycopg; its hidden FETCH does not
            # pass execute_wrapper. Bind to this request's cursor instance only.
            cursor.fetchmany = fetchmany
        self._set_remaining()
        return execute(sql, params, many, context)

    def __enter__(self):
        self._wrapper = connection.execute_wrapper(self._execute)
        self._wrapper.__enter__()
        return self

    def __exit__(self, *exc):
        try:
            return self._wrapper.__exit__(*exc)
        finally:
            for cursor, original in self._fetch_methods.items():
                cursor.fetchmany = original
            self._fetch_methods.clear()
