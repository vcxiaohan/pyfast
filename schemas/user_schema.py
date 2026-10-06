from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

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
    # 示例是 init_data.py 里的作者张三，方便在 /docs 里直接登录测试
    email: EmailStr = Field(examples=["zhangsan@test.com"])
    password: str = Field(examples=["123456"])


class TokenSchema(BaseModel):
    access_token: str
    # 固定是 "bearer"，告诉前端请求时要写成 Authorization: Bearer <access_token>
    token_type: str = "bearer"
