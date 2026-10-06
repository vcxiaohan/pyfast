from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from models.user import UserRole


class UserSchema(BaseModel):
    id: int
    email: EmailStr
    username: str
    role: UserRole
    create_time: datetime
    model_config = ConfigDict(from_attributes=True)


# 嵌在文章里展示作者用，不暴露邮箱
class UserBriefSchema(BaseModel):
    id: int
    username: str
    model_config = ConfigDict(from_attributes=True)


class UserLoginSchema(BaseModel):
    email: EmailStr
    password: str


class TokenSchema(BaseModel):
    access_token: str
    # 固定是 "bearer"，告诉前端请求时要写成 Authorization: Bearer <access_token>
    token_type: str = "bearer"
