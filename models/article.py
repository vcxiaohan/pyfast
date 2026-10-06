from enum import StrEnum

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import Base


class ArticleStatus(StrEnum):
    DRAFT = "draft"  # 草稿
    PUBLISHED = "published"  # 已发布


# 和User是多对一关系
class Article(Base):
    __tablename__ = "article"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(100))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default=ArticleStatus.DRAFT, comment="状态")
    view_count: Mapped[int] = mapped_column(Integer, default=0, comment="阅读量")
    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), index=True)

    author: Mapped["User"] = relationship(back_populates="articles")
    tags: Mapped[list["ArticleTag"]] = relationship(secondary="article_and_tag", back_populates="articles")


# 文章标签，和Article是多对多关系
class ArticleTag(Base):
    __tablename__ = "article_tag"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)

    articles: Mapped[list["Article"]] = relationship(secondary="article_and_tag", back_populates="tags")


# Article和ArticleTag多对多关系的中间表，删文章或删标签时数据库自动删掉对应的关联记录
class ArticleAndTag(Base):
    __tablename__ = "article_and_tag"
    article_id: Mapped[int] = mapped_column(Integer, ForeignKey("article.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(Integer, ForeignKey("article_tag.id", ondelete="CASCADE"), primary_key=True)
