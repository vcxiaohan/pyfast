"""阿里云 OSS：导出的 Excel 存在这里。多台机器部署时，哪台生成的文件都能从任意一台拿到下载链接。"""

import asyncio
from datetime import timedelta
from urllib.parse import quote

import alibabacloud_oss_v2 as oss

from settings import settings


def _create_client(internal: bool) -> oss.Client:
    cfg = oss.config.load_default()
    cfg.credentials_provider = oss.credentials.StaticCredentialsProvider(
        settings.OSS_ACCESS_KEY_ID, settings.OSS_ACCESS_KEY_SECRET
    )
    cfg.region = settings.OSS_REGION
    cfg.use_internal_endpoint = internal
    return oss.Client(cfg)


# 上传在 ECS 上走内网地址，不收流量费；签名链接是给用户浏览器打开的，必须用公网地址，所以分成两个客户端
_upload_client = _create_client(settings.OSS_INTERNAL)
_sign_client = _create_client(False)


async def upload(key: str, data: bytes, content_type: str) -> None:
    request = oss.PutObjectRequest(bucket=settings.OSS_BUCKET, key=key, body=data, content_type=content_type)
    # SDK 的同步客户端会阻塞，放到线程里执行，不卡住事件循环
    await asyncio.to_thread(_upload_client.put_object, request)


def sign_download_url(key: str, filename: str, expires: timedelta) -> str:
    """生成临时下载链接，bucket 保持私有。签名在本地计算，不发网络请求。"""
    request = oss.GetObjectRequest(
        bucket=settings.OSS_BUCKET,
        key=key,
        # 让浏览器直接下载，并用中文文件名保存；文件名要按 RFC 5987 编码
        response_content_disposition=f"attachment; filename*=UTF-8''{quote(filename)}",
    )
    return _sign_client.presign(request, expires=expires).url
