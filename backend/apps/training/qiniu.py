from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def _credentials():
    if not settings.QINIU_ACCESS_KEY or not settings.QINIU_SECRET_KEY:
        raise ImproperlyConfigured("七牛访问密钥未配置")
    return settings.QINIU_ACCESS_KEY, settings.QINIU_SECRET_KEY


def private_download_url(base_url: str, *, expires_in_seconds: int) -> str:
    access_key, secret_key = _credentials()
    try:
        from qiniu import Auth
    except ImportError as exc:
        raise ImproperlyConfigured("七牛 Python SDK 未安装") from exc
    return Auth(access_key, secret_key).private_download_url(
        base_url,
        expires=expires_in_seconds,
    )


class QiniuStorageClient:
    def __init__(self):
        access_key, secret_key = _credentials()
        try:
            from qiniu import Auth, BucketManager
        except ImportError as exc:
            raise ImproperlyConfigured("七牛 Python SDK 未安装") from exc
        self.auth = Auth(access_key, secret_key)
        self.bucket_manager = BucketManager(self.auth)

    def file_hash(self, file_path):
        from qiniu import etag

        return etag(str(file_path))

    def stat_object(self, bucket, key):
        result, info = self.bucket_manager.stat(bucket, key)
        if result and "hash" in result:
            return {
                "key": key,
                "hash": result["hash"],
                "size": result.get("fsize", 0),
            }
        if getattr(info, "status_code", None) == 612:
            return None
        raise RuntimeError(f"七牛对象查询失败：{getattr(info, 'text_body', info)}")

    def upload_file(self, bucket, key, file_path):
        from qiniu import put_file_v2

        token = self.auth.upload_token(bucket, key, 3600)
        result, info = put_file_v2(token, key, str(file_path), version="v2")
        if not result or result.get("key") != key or not result.get("hash"):
            raise RuntimeError(f"七牛视频上传失败：{getattr(info, 'text_body', info)}")
        return {
            "key": result["key"],
            "hash": result["hash"],
            "size": file_path.stat().st_size,
        }
