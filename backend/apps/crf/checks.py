from django.core.checks import Error, register

from apps.crf.registry_loader import CrfAssetError, check_crf_assets


@register("crf_assets")
def check_runtime_assets(app_configs, **kwargs):
    try:
        check_crf_assets()
    except CrfAssetError as exc:
        return [Error(str(exc), id="crf.E001")]
    return []
