from datetime import datetime, timedelta, timezone

import jwt

from settings import settings

ALGORITHM = "HS256"


def create_access_token(user_id: int) -> str:
    # sub 必须是字符串，PyJWT 解析时会校验；exp 到期后 jwt.decode 会自动抛 ExpiredSignatureError
    payload = {"sub": str(user_id), "exp": datetime.now(timezone.utc) + settings.JWT_EXPIRES}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> int:
    """验证签名和有效期，返回用户 id。token 无效或过期时抛 jwt.InvalidTokenError。"""
    payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[ALGORITHM])
    return int(payload["sub"])


# 下载 token 带 aud：decode_access_token 解析时会因为 aud 不匹配直接拒绝，所以它不能冒充登录 token；
# 反过来登录 token 没有 aud，也不能拿来下载
DOWNLOAD_AUDIENCE = "export-download"


def create_download_token(file: str, name: str, expires: timedelta) -> str:
    """file 是服务器上的文件名，name 是用户下载时看到的文件名。"""
    payload = {"file": file, "name": name, "aud": DOWNLOAD_AUDIENCE, "exp": datetime.now(timezone.utc) + expires}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=ALGORITHM)


def decode_download_token(token: str) -> tuple[str, str]:
    """返回 (file, name)。token 无效或过期时抛 jwt.InvalidTokenError。"""
    payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[ALGORITHM], audience=DOWNLOAD_AUDIENCE)
    return payload["file"], payload["name"]
