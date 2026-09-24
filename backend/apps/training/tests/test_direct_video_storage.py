from contextlib import contextmanager

import pytest
from django.core.exceptions import ValidationError
from apps.training.qiniu import read_private_video_info


@pytest.mark.parametrize("chunks", [[b'[]'], [b'{bad'], [b'x' * (1024 * 1024 + 1)]])
def test_metadata_reader_rejects_invalid_or_oversized_response(settings, monkeypatch, chunks):
    settings.QINIU_DOWNLOAD_DOMAIN = "https://media.example.test"
    class Response:
        def raise_for_status(self): pass
        def iter_bytes(self): return iter(chunks)
    @contextmanager
    def request(method, url, **kwargs):
        assert method == "GET"
        assert "/training-videos/direct/test.mp4?avinfo&e=" in url
        assert kwargs["follow_redirects"] is False
        yield Response()
    monkeypatch.setattr("apps.training.qiniu.httpx.stream", request)
    with pytest.raises(ValidationError, match="暂时无法核验"):
        read_private_video_info("training-videos/direct/test.mp4")


def test_metadata_reader_does_not_accept_client_urls(settings):
    settings.QINIU_DOWNLOAD_DOMAIN = "https://media.example.test"
    with pytest.raises(ValidationError):
        read_private_video_info("https://untrusted.invalid/a.mp4")
