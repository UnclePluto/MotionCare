from django.test import override_settings

from apps.training.qiniu import private_download_url


@override_settings(QINIU_ACCESS_KEY="ak-test", QINIU_SECRET_KEY="sk-test")
def test_private_download_url_is_signed():
    url = private_download_url("https://cdn.example.com/a.mp4", expires_at=1783692000)
    assert url.startswith("https://cdn.example.com/a.mp4?e=1783692000&token=ak-test%3A")
