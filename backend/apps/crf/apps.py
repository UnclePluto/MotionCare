from django.apps import AppConfig


class CrfConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.crf"

    def ready(self):
        from apps.crf import checks  # noqa: F401
        from apps.crf.registry_loader import check_crf_assets

        check_crf_assets()
