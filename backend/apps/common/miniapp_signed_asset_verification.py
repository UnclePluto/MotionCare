"""只读验收固定私有素材；所有外部错误均在边界脱敏。"""

import hashlib
import hmac
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qsl, quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, build_opener

from django.conf import settings
from django.core.management.base import CommandError

from apps.common.miniapp_static_asset_registry import load_registered_static_assets
from apps.common.miniapp_static_assets import PreparedStaticAsset, validate_miniapp_static_assets
from apps.training.qiniu import private_download_url


MAX_BODY_BYTES = 32 * 1024 * 1024
MAX_MANIFEST_BYTES = 256 * 1024


@dataclass(frozen=True)
class VerificationResponse:
    status: int
    content_type: str
    body: bytes


@dataclass(frozen=True)
class VerifiedSignedAsset:
    key: str
    size_bytes: int
    sha256: str


class SignedAssetVerificationError(Exception):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_verification_response(url: str) -> VerificationResponse:
    """20 秒超时，禁止自动重定向，HTTP 错误返回状态，不泄露 URL。"""
    try:
        opener = build_opener(_NoRedirect())
        try:
            response = opener.open(url, timeout=20)
        except HTTPError as error:
            response = error
        with response:
            body = response.read(MAX_BODY_BYTES + 1)
            if len(body) > MAX_BODY_BYTES:
                raise SignedAssetVerificationError("素材响应正文超过大小限制")
            return VerificationResponse(
                response.status, response.headers.get("Content-Type", ""), body,
            )
    except SignedAssetVerificationError:
        raise
    except Exception:
        raise SignedAssetVerificationError("素材网络请求失败") from None


def _fetch(fetch: Callable[[str], VerificationResponse], url: str, key: str) -> VerificationResponse:
    try:
        return fetch(url)
    except Exception:
        raise SignedAssetVerificationError(key + " 网络请求失败") from None


def _https_base(value: str) -> str:
    if not isinstance(value, str) or re.search(r"[\\\s?#]", value):
        raise ValueError
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https" or not parsed.netloc or not parsed.hostname
        or parsed.username is not None or parsed.password is not None
        or parsed.port == 0
    ):
        raise ValueError
    return value.rstrip("/")


def _registered_assets(source_root: Path) -> tuple[str, list[PreparedStaticAsset], dict]:
    try:
        prepared = validate_miniapp_static_assets(source_root)
        version = Path(source_root).resolve().name
        if not re.fullmatch(r"v-[0-9a-f]{12}", version):
            raise ValueError
        manifest = load_registered_static_assets(version)
        entries = {entry["key"]: entry for entry in manifest["entries"]}
        for asset in prepared:
            entry = entries[asset.key]
            if (
                entry["relativePath"] != asset.object_key.removeprefix("motioncare/static-assets/")
                or entry["contentType"] != asset.content_type
                or entry["sizeBytes"] != asset.size_bytes or entry["sha256"] != asset.sha256
            ):
                raise ValueError
        return version, prepared, entries
    except (CommandError, OSError, ValueError, KeyError, TypeError):
        raise SignedAssetVerificationError("本地素材与已登记清单不一致或无法校验") from None


def _validated_urls(response: VerificationResponse, version: str, entries: dict) -> dict[str, str]:
    try:
        if (
            response.status != 200
            or response.content_type.split(";", 1)[0].strip().lower() != "application/json"
            or len(response.body) > MAX_MANIFEST_BYTES
        ):
            raise ValueError
        payload = json.loads(response.body)
        if not isinstance(payload, dict) or payload.get("asset_version") != version:
            raise ValueError
        issued_at, expires_at = payload.get("issued_at"), payload.get("expires_at")
        if (
            type(issued_at) is not int or type(expires_at) is not int
            or not 120 <= expires_at - issued_at <= 3600
            or abs(issued_at) > 2**53 - 1 or abs(expires_at) > 2**53 - 1
        ):
            raise ValueError
        assets = payload.get("assets")
        if not isinstance(assets, list) or len(assets) != len(entries):
            raise ValueError
        base = _https_base(settings.MINIAPP_STATIC_ASSET_BASE_URL)
        if not settings.QINIU_ACCESS_KEY or not settings.QINIU_SECRET_KEY:
            raise ValueError
    except Exception:
        raise SignedAssetVerificationError("签名清单响应无效") from None

    urls = {}
    for asset in assets:
        # 先取受信任的业务 key，错误文本不得引用任何不受信任字段。
        key = asset.get("key") if isinstance(asset, dict) else None
        if not isinstance(key, str) or key not in entries or key in urls:
            raise SignedAssetVerificationError("签名清单素材项目无效")
        entry = entries[key]
        try:
            if (
                asset.get("relative_path") != entry["relativePath"]
                or asset.get("content_type") != entry["contentType"]
                or type(asset.get("size_bytes")) is not int
                or asset["size_bytes"] != entry["sizeBytes"]
                or asset.get("sha256") != entry["sha256"]
            ):
                raise ValueError
            url = asset.get("url")
            if not isinstance(url, str) or re.search(r"[\\#\s]", url):
                raise ValueError
            unsigned, separator, raw_query = url.partition("?")
            expected_unsigned = base + "/" + entry["relativePath"]
            # 原始来源和路径必须完全一致，不允许 URL 归一化掩盖点路径/转义。
            if not separator or unsigned != expected_unsigned:
                raise ValueError
            pairs = parse_qsl(raw_query, keep_blank_values=True, strict_parsing=True)
            if len(pairs) != 2 or {name for name, _ in pairs} != {"e", "token"}:
                raise ValueError
            query = dict(pairs)
            if query["e"] != str(expires_at) or not re.fullmatch(
                r"[A-Za-z0-9_-]+:[A-Za-z0-9_-]+=*", query["token"],
            ):
                raise ValueError
            expected = private_download_url(expected_unsigned, expires_at=expires_at)
            expected_token = dict(parse_qsl(urlsplit(expected).query))["token"]
            if not hmac.compare_digest(query["token"], expected_token):
                raise ValueError
            urls[key] = url
        except Exception:
            raise SignedAssetVerificationError(key + " 签名清单元数据或地址无效") from None
    return urls


def verify_signed_static_assets(
    source_root: Path,
    api_base_url: str,
    *,
    fetch: Callable[[str], VerificationResponse] = fetch_verification_response,
) -> list[VerifiedSignedAsset]:
    """固定 23 项正文验收及同对象无签名、篡改、过期拒绝检查。"""
    version, prepared, entries = _registered_assets(source_root)
    try:
        api_base = _https_base(api_base_url)
        if not urlsplit(api_base).path.endswith("/api"):
            raise ValueError
    except (ValueError, TypeError):
        raise SignedAssetVerificationError("API 基础地址必须为以 /api 结尾的绝对 HTTPS 地址") from None
    manifest_url = api_base + "/patient-app/static-assets/?version=" + quote(version, safe="")
    urls = _validated_urls(_fetch(fetch, manifest_url, "签名清单"), version, entries)

    verified = []
    for asset in prepared:
        response = _fetch(fetch, urls[asset.key], asset.key)
        if response.status != 200:
            raise SignedAssetVerificationError(asset.key + " 下载状态不正确")
        if response.content_type.split(";", 1)[0].strip().lower() != asset.content_type:
            raise SignedAssetVerificationError(asset.key + " 媒体类型不一致")
        if len(response.body) != asset.size_bytes:
            raise SignedAssetVerificationError(asset.key + " 字节数不一致")
        if hashlib.sha256(response.body).hexdigest() != asset.sha256:
            raise SignedAssetVerificationError(asset.key + " SHA-256 不一致")
        verified.append(VerifiedSignedAsset(asset.key, asset.size_bytes, asset.sha256))

    first = prepared[0]
    unsigned = urls[first.key].split("?", 1)[0]
    query = dict(parse_qsl(urlsplit(urls[first.key]).query))
    query["token"] = "invalid"
    try:
        expired = private_download_url(unsigned, expires_at=int(time.time()) - 60)
    except Exception:
        raise SignedAssetVerificationError(first.key + " 过期签名无法生成") from None
    probes = (
        (unsigned, "匿名"),
        (unsigned + "?" + urlencode(query), "篡改"),
        (expired, "过期"),
    )
    for url, label in probes:
        response = _fetch(fetch, url, first.key)
        if response.status not in (401, 403):
            raise SignedAssetVerificationError(first.key + " " + label + "访问未被鉴权拒绝")
    return verified
