from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select

from core.auth import create_access_token
from dependencies import get_current_user, get_session
from models import AsyncSession
from models.user import User
from schemas.user_schema import TokenSchema, UserLoginSchema, UserSchema

router = APIRouter(prefix="/user", tags=["user"])


@router.get("/list", response_model=list[UserSchema])
async def get_user_list(
        q: str | None = None,
        page: int = Query(1, ge=1),
        size: int = Query(10, ge=1, le=100),
        session: AsyncSession = Depends(get_session),
):
    async with session.begin():
        stmt = select(User)
        if q is not None:
            stmt = stmt.where(or_(User.email.contains(q), User.username.contains(q)))
        stmt = stmt.order_by(User.id.desc()).offset((page - 1) * size).limit(size)
        users = await session.scalars(stmt)
        return users.all()


@router.post("/login", response_model=TokenSchema)
async def user_login(
        payload: UserLoginSchema,
        session: AsyncSession = Depends(get_session),
):
    async with session.begin():
        stmt = select(User).where(User.email == payload.email, User.password == payload.password)
        result = await session.execute(stmt)
        data = result.scalar_one_or_none()
        if data is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误")
        return {"access_token": create_access_token(data.id)}


@router.get("/me", response_model=UserSchema)
async def get_me(user: User = Depends(get_current_user)):
    return user
