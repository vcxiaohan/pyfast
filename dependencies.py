import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.auth import decode_access_token
from models import AsyncSession, AsyncSessionFactory
from models.user import User, UserRole


async def get_session():
    session = AsyncSessionFactory()
    try:
        yield session
    finally:
        await session.close()


# 读取 Authorization 请求头的工具，启动时创建一次，本身不存 token；/docs 页面右上角会因此出现 Authorize 按钮。
# auto_error=False：没传或格式不对时返回 None，由下面自己返回中文提示，而不是 FastAPI 默认的英文报错
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
        session: AsyncSession = Depends(get_session),
) -> User:
    # 请求头 Authorization: Bearer eyJhbGciOi...
    # 解析后 credentials 长这样：
    #   credentials.scheme      = "Bearer"
    #   credentials.credentials = "eyJhbGciOi..."   ← 纯 token
    # 没传这个请求头、或前缀不是 Bearer 时，credentials 是 None
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    token = credentials.credentials
    try:
        user_id = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期，请重新登录")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token 无效")

    async with session.begin():
        user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    return user


async def get_author_user(
        user: User = Depends(get_current_user)
) -> User:
    # 浏览者只能看，作者和管理员才能写文章
    if user.role not in (UserRole.AUTHOR, UserRole.ADMIN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    return user


async def get_admin_user(
        user: User = Depends(get_current_user)
) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    return user
