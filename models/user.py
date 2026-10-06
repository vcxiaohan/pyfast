from enum import StrEnum

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import Base


class UserRole(StrEnum):
    VIEWER = "viewer"  # 浏览者：只能看文章
    AUTHOR = "author"  # 作者：能发文章，只能改删自己的
    ADMIN = "admin"  # 管理员：能改删所有文章


class User(Base):
    __tablename__ = "user"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(100))
    password: Mapped[str] = mapped_column(String(200))
    # 数据库里存普通字符串，取值范围由 UserRole 约束
    role: Mapped[str] = mapped_column(String(20), default=UserRole.VIEWER, comment="角色")

    # 用户有文章时不允许删除：passive_deletes="all" 让 ORM 不去改文章的 author_id，交给数据库的 RESTRICT 拦截
    articles: Mapped[list["Article"]] = relationship(back_populates="author", passive_deletes="all")
