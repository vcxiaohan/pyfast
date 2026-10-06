"""重置测试数据：清空 pyfast 的所有表，再插入 5 个不同角色的用户、5 个标签、6 篇文章。

在 pyfast 目录下执行：python init_data.py
每次执行都会删掉表里现有的全部数据（包括手动改过的），自增 id 从 1 重新开始。
test.py 建的 book 等表不受影响。
"""

import asyncio

from sqlalchemy import text

from models import AsyncSessionFactory, Base, engine
from models.article import Article, ArticleStatus, ArticleTag
from models.user import User, UserRole


async def init_data():
    async with AsyncSessionFactory() as session:
        async with session.begin():
            # 表名来自模型定义而不是用户输入，所以这里拼 SQL 没有注入风险；表名也没法用 :param 占位符传
            tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
            # 一条 TRUNCATE 同时清多张表，表之间的外键不会互相拦；RESTART IDENTITY 把自增 id 重置为 1
            await session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY"))

            # 密码先存明文，后面练登录时再改成加密存储
            admin = User(email="admin@test.com", username="管理员", password="123456", role=UserRole.ADMIN)
            zhangsan = User(email="zhangsan@test.com", username="张三", password="123456", role=UserRole.AUTHOR)
            lisi = User(email="lisi@test.com", username="李四", password="123456", role=UserRole.AUTHOR)
            wangwu = User(email="wangwu@test.com", username="王五", password="123456")
            zhaoliu = User(email="zhaoliu@test.com", username="赵六", password="123456")

            python = ArticleTag(name="Python")
            fastapi = ArticleTag(name="FastAPI")
            sqlalchemy = ArticleTag(name="SQLAlchemy")
            database = ArticleTag(name="数据库")
            frontend = ArticleTag(name="前端")

            # 先把用户和标签插进去，id 就按上面的书写顺序分配（管理员=1、张三=2 …，Python=1 …），每次重置都一样。
            # 必须在创建文章之前 flush：文章一关联作者，add 作者时会顺带把他的文章、文章的标签一起加进来，顺序就乱了
            session.add_all([admin, zhangsan, lisi, wangwu, zhaoliu])
            session.add_all([python, fastapi, sqlalchemy, database, frontend])
            await session.flush()

            articles = [
                Article(
                    title="FastAPI 入门：第一个接口",
                    content="从安装到写出第一个 GET 接口……",
                    status=ArticleStatus.PUBLISHED,
                    view_count=320,
                    author=zhangsan,
                    tags=[python, fastapi],
                ),
                Article(
                    title="SQLAlchemy 2.0 异步写法总结",
                    content="AsyncSession、select、selectinload……",
                    status=ArticleStatus.PUBLISHED,
                    view_count=185,
                    author=zhangsan,
                    tags=[python, sqlalchemy, database],
                ),
                Article(
                    title="Pydantic 校验技巧（未写完）",
                    content="草稿……",
                    author=zhangsan,
                    tags=[python, fastapi],
                ),
                Article(
                    title="PostgreSQL 索引怎么建",
                    content="什么时候该加索引，联合索引的顺序……",
                    status=ArticleStatus.PUBLISHED,
                    view_count=96,
                    author=lisi,
                    tags=[database],
                ),
                Article(
                    title="前后端分离项目怎么联调",
                    content="草稿……",
                    author=lisi,
                    tags=[fastapi, frontend],
                ),
                Article(
                    title="社区发文规范",
                    content="请勿发布广告……",
                    status=ArticleStatus.PUBLISHED,
                    view_count=1024,
                    author=admin,
                ),
            ]

            session.add_all(articles)

        print(f"已清空 {tables}，重新插入：5 个用户、5 个标签、6 篇文章")


async def main():
    await init_data()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
