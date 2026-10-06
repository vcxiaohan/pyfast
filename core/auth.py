from datetime import datetime, timezone

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
