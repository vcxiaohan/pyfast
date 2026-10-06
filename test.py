"""
FastAPI + SQLAlchemy 2.0 异步 ORM 练习：图书管理

- 模型：Book 为主表；BookDetail 一对一、Publisher 一对多、BookTag 多对多（中间表 BookAndTag）
- 查询：where / like / in_ / 分组 / 查部分列 / 分页 / 联表（outerjoin）/ 原生 SQL（text）
- 增删改：add、先查再 assign、update()、先查再 delete、delete() 语句、批量删除
- 关联操作：selectinload 加载关联数据，book.tags.append / remove 维护多对多
"""

import asyncio
from datetime import date, datetime

from fastapi import APIRouter, Cookie, Depends, FastAPI, Header, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Text,
    delete,
    func,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    selectinload,
    sessionmaker,
)

from settings import DB_URI

app = FastAPI()

engine = create_async_engine(
    DB_URI,
    # 将输出所有执行SQL的日志（默认是关闭的）
    echo=True,
    # 连接池大小（默认是5个）
    pool_size=10,
    # 允许连接池最大的连接数（默认是10个）
    max_overflow=20,
    # 获得连接超时时间（默认是30s）
    pool_timeout=10,
    # 连接回收时间（默认是-1，代表永不回收）
    pool_recycle=3600,
    # 连接前是否预检查（默认为False）
    pool_pre_ping=True,
)

AsyncSessionFactory = sessionmaker(
    # Engine或者其子类对象（这里是AsyncEngine）
    bind=engine,
    # Session类的代替（默认是Session类）
    class_=AsyncSession,
    # 是否在查找之前执行flush操作（默认是True）
    autoflush=True,
    # 是否在执行commit操作后Session就过期（默认是True）
    expire_on_commit=False
)


# 定义命名约定的Base类
class Base(DeclarativeBase):
    metadata = MetaData(naming_convention={
        # ix: index，索引。
        "ix": 'ix_%(column_0_label)s',
        # un：unique，唯一约束
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        # ck：Check，检查约束
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        # fk：Foreign Key，外键约束
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        # pk：Primary Key，主键约束
        "pk": "pk_%(table_name)s"
    })
    # func.now() 要带括号：生成 SQL 的 now()，由数据库取时间。onupdate 在更新时自动改 update_time
    create_time: Mapped[datetime] = mapped_column(DateTime, default=func.now(), comment="创建时间")
    update_time: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), comment="更新时间")

    # 按字典批量改字段。必须用 setattr，直接改 __dict__ 不会生成 UPDATE
    def assign(self, data: dict):
        for key, value in data.items():
            setattr(self, key, value)


class Publisher(Base):
    __tablename__ = "publisher"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, comment="出版社名")
    address: Mapped[str | None] = mapped_column(String(200), comment="地址")
    phone: Mapped[str | None] = mapped_column(String(20), comment="联系电话")

    # 一对多：一个出版社有多本书，所以是 list
    # passive_deletes="all"：删出版社时 ORM 不去动名下的书，交给数据库的 RESTRICT 来拒绝删除
    books: Mapped[list["Book"]] = relationship(back_populates="publisher", passive_deletes="all")


class Book(Base):
    __tablename__ = "book"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bookname: Mapped[str] = mapped_column(String(100), index=True, comment="书名")
    author: Mapped[str] = mapped_column(String(50), comment="作者")
    price: Mapped[int] = mapped_column(Integer, comment="价格")

    # 多对一：外键放在“多”的这一边。ondelete="RESTRICT"：出版社名下还有书时，数据库不让删
    publisher_id: Mapped[int] = mapped_column(Integer, ForeignKey("publisher.id", ondelete="RESTRICT"),
                                              comment="出版社id")
    publisher: Mapped["Publisher"] = relationship(back_populates="books")

    # 一对一：一本书对应一条详情。uselist=False 表示 book.detail 是单个对象，不是列表
    # cascade="all, delete-orphan"：用 session.delete(book) 删书时，详情跟着删
    detail: Mapped["BookDetail"] = relationship(back_populates="book", uselist=False, cascade="all, delete-orphan")

    # 多对多：secondary 指定中间表的表名，SQLAlchemy 通过中间表把书和标签连起来
    tags: Mapped[list["BookTag"]] = relationship(secondary="book_and_tag", back_populates="books")


class BookDetail(Base):
    __tablename__ = "book_detail"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    isbn: Mapped[str] = mapped_column(String(20), unique=True, comment="ISBN书号")
    summary: Mapped[str | None] = mapped_column(Text, comment="简介")
    publish_date: Mapped[date] = mapped_column(Date, comment="出版日期")

    # unique=True 保证一本书只能有一条详情，这是“一对一”在数据库层面的保证
    # ondelete="CASCADE"：用 delete(Book) 语句删书时，数据库自动删掉对应详情
    book_id: Mapped[int] = mapped_column(Integer, ForeignKey("book.id", ondelete="CASCADE"), unique=True)
    book: Mapped["Book"] = relationship(back_populates="detail")


class BookTag(Base):
    __tablename__ = "book_tag"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, comment="标签名")

    # 从标签找书。back_populates 写的是对方的属性名（Book.tags），不是表名
    books: Mapped[list["Book"]] = relationship(secondary="book_and_tag", back_populates="tags")


# 中间表：一行表示“某本书有某个标签”。两个外键一起做联合主键，同一本书不能重复打同一个标签
# ondelete="CASCADE"：删书或删标签时，数据库自动删掉对应的关联行（书和标签本身不受影响）
class BookAndTag(Base):
    __tablename__ = "book_and_tag"
    book_id: Mapped[int] = mapped_column(Integer, ForeignKey("book.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(Integer, ForeignKey("book_tag.id", ondelete="CASCADE"), primary_key=True)


# 给 FastAPI 的 Depends 用。脚本里不能 session = get_session()，要用 async for session in get_session()
async def get_session():
    session: AsyncSession = AsyncSessionFactory()
    try:
        yield session
    finally:
        await session.close()


# drop_all 只删本文件模型对应的表；create_all 不会给已经存在的表加列
async def reset_all():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


async def add_books():
    async for session in get_session():
        async with session.begin():
            heima = Publisher(name="黑马出版社", address="北京市昌平区", phone="010-12345678")
            renmin = Publisher(name="人民文学出版社", address="北京市东城区", phone="010-87654321")
            gudian = BookTag(name="古典名著")
            sida = BookTag(name="四大名著")
            tonghua = BookTag(name="童话")
            shici = BookTag(name="诗词")
            jingdian = BookTag(name="经典")
            # 只 add 书，关联对象会一起插入，并按外键排好顺序。标签对象要复用，重复创建会因 name 唯一而报错
            session.add_all([
                Book(bookname="红楼梦", author="曹雪芹", price=200, publisher=heima,
                     detail=BookDetail(isbn="9787020002207", summary="贾宝玉与林黛玉的爱情悲剧",
                                       publish_date=date(1982, 3, 1)),
                     tags=[gudian, sida, jingdian]),
                Book(bookname="西游记", author="吴承恩", price=188, publisher=heima,
                     detail=BookDetail(isbn="9787020008735", summary="唐僧师徒西天取经", publish_date=date(1980, 5, 1)),
                     tags=[gudian, sida]),
                Book(bookname="水浒传", author="施耐庵", price=166, publisher=heima,
                     detail=BookDetail(isbn="9787020008742", summary="一百零八将聚义梁山",
                                       publish_date=date(1975, 10, 1)),
                     tags=[gudian, sida]),
                Book(bookname="三国演义", author="罗贯中", price=201, publisher=heima,
                     detail=BookDetail(isbn="9787020008728", summary="魏蜀吴三国争霸", publish_date=date(1973, 12, 1)),
                     tags=[gudian, sida, jingdian]),
                Book(bookname="安徒生童话", author="安徒生", price=55, publisher=renmin,
                     detail=BookDetail(isbn="9787020042494", summary=None, publish_date=date(2004, 6, 1)),
                     tags=[tonghua, jingdian]),
                Book(bookname="七步诗", author="曹植", price=100, publisher=heima,
                     detail=BookDetail(isbn="9787101003048", summary="煮豆燃豆萁", publish_date=date(1990, 1, 1)),
                     tags=[shici]),
            ])


async def init_books():
    await reset_all()
    await add_books()


# 建表并插入示例数据。跑完记得重新注释掉，否则每次加载文件都会清空重建
# asyncio.run(init_books())


@app.get('/select_some')
async def select_some(
        id: int | None = None,
        keyword: str | None = None,
        session: AsyncSession = Depends(get_session)
):
    async with session.begin():
        # 查询所有
        # result = await session.execute(select(Book))
        # data = result.scalars().all()
        # return data

        # 查询第一个
        # result = await session.execute(select(Book))
        # data = result.scalars().first()
        # return data

        # 根据主键查询
        # data = await session.get(Book, id)
        # return data

        # where查询 ==
        # result = await session.execute(select(Book).where(Book.id == id))
        # data = result.scalar_one_or_none()
        # return data

        # where查询 >
        # result = await session.execute(select(Book).where(Book.id > id))
        # data = result.scalars().all()
        # return data

        # where查询 like
        # result = await session.execute(select(Book).where(Book.bookname.like(f"%{keyword}%")))
        # data = result.scalars().all()
        # return data

        # where查询 , 默认就表示&
        # result = await session.execute(select(Book).where(Book.bookname.like(f"%{keyword}%"), Book.id > id))
        # data = result.scalars().all()
        # return data

        # where查询 & 需要两边加上括号，防止优先级问题
        # result = await session.execute(select(Book).where((Book.bookname.like(f"%{keyword}%")) & (Book.id > id)))
        # data = result.scalars().all()
        # return

        # where查询 or_
        # result = await session.execute(select(Book).where(or_(Book.bookname.like(f"%{keyword}%"), Book.id > id)))
        # data = result.scalars().all()
        # return data

        # where查询 in_
        # arr = [2, 3, 333]
        # result = await session.execute(select(Book).where(Book.id.in_(arr)))
        # data = result.scalars().all()
        # return data

        # 分组查询。查的是字段不是对象，用 mappings().all() 得到字典；scalars() 只会剩第一列
        # result = await session.execute(
        #     select(
        #         Book.publisher_id,
        #         func.count(Book.id).label("count"),
        #         func.avg(Book.price).label("avg_price")
        #     )
        #     .group_by(Book.publisher_id)
        #     # .having(func.count(Book.id) > 1) # 分组后再筛选
        # )
        # data = result.mappings().all()
        # return data

        # 查询某些列，同样用 mappings().all()
        # result = await session.execute(
        #     select(
        #         Book.id,
        #         Book.publisher_id,
        #         Book.price
        #     )
        #     .where(Book.price > 100)
        #     .order_by(Book.price.desc())
        # )
        # data = result.mappings().all()
        # return data

        # 直接写 SQL。参数用 :name 占位，不要用 f-string 拼进 SQL，否则有注入风险
        # result = await session.execute(
        #     text("""
        #         SELECT b.id, b.bookname, b.price, p.name AS publisher_name
        #         FROM book b
        #         LEFT JOIN publisher p ON b.publisher_id = p.id
        #         WHERE b.price > :price AND p.name LIKE :keyword
        #     """),
        #     {"price": 100, "keyword": f"%{keyword}%"}
        # )
        # data = result.mappings().all()
        # return data

        stmt = (
            select(Book.id, Book.bookname, Book.price, Publisher.name.label("publisher_name"))
            # outerjoin = LEFT JOIN。ON 由 Book.publisher 的外键自动补上
            # .join(...) 是 INNER JOIN；不借助 relationship 要写成 .outerjoin(Publisher, Book.publisher_id == Publisher.id)
            .outerjoin(Book.publisher)
            .where(Book.price > 100)
        )
        # 多次 where 是 AND。右表条件写在 where 里时，LEFT JOIN 的效果和 INNER JOIN 一样
        if keyword:
            stmt = stmt.where(Publisher.name.like(f"%{keyword}%"))
        result = await session.execute(stmt)
        data = result.mappings().all()
        return data


@app.get('/together_some')
async def together_some(
        id: int | None = None,
        keyword: str | None = None,
        session: AsyncSession = Depends(get_session)
):
    async with session.begin():
        # 聚合查询 count
        # result = await session.execute(select(func.count(Book.bookname)))
        # data = result.scalar()
        # return data

        # 聚合查询 avg。scalar() 取这一个值；PostgreSQL 的 avg 会返回很长的小数
        result = await session.execute(select(func.avg(Book.price)))
        data = result.scalar()
        return data


@app.get('/pagelist_some')
async def pagelist_some(
        # ge=1：必须大于等于 1，le=100：最多 100 条，不满足时 FastAPI 直接返回 422
        page: int = Query(1, ge=1),
        size: int = Query(10, ge=1, le=100),
        session: AsyncSession = Depends(get_session)
):
    async with session.begin():
        stmt = select(Book).offset((page - 1) * size).limit(size)
        result = await session.execute(stmt)
        data = result.scalars().all()
        return data


class BookCreateSchame(BaseModel):
    bookname: str
    author: str
    price: int
    publisher_id: int


@app.post('/add_some')
async def add_some(
        payload: BookCreateSchame,
        session: AsyncSession = Depends(get_session)
):
    async with session.begin():
        if await session.get(Publisher, payload.publisher_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="出版社不存在")
        # model_dump() 把 Schema 转成字典，** 拆成关键字参数。add 不用 await，提交时才 INSERT
        data = Book(**payload.model_dump())
        session.add(data)
        return data


# 字段都是可选的。配合 exclude_unset=True，只修改前端实际传了的字段
class BookUpdateSchame(BaseModel):
    id: int
    bookname: str | None = None
    author: str | None = None
    price: int | None = None
    publisher_id: int | None = None


@app.post('/edit_some')
async def edit_some(
        payload: BookUpdateSchame,
        session: AsyncSession = Depends(get_session)
):
    async with session.begin():
        # exclude_unset-去掉前端没传的字段 exclude_none-去掉值是None的字段，不管前端有没有传
        # exclude={"id"}-id 只用来找是哪一条，不能当成要修改的字段
        # data = payload.model_dump(exclude_unset=True, exclude_none=True, exclude={"id"})
        # result = await session.get(Book, payload.id)
        # if result is None:
        #     raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="暂无数据")
        # result.assign(data)
        # return {"msg": "编辑成功"}

        data = payload.model_dump(exclude_unset=True, exclude_none=True, exclude={"id"})
        if "publisher_id" in data and await session.get(Publisher, data["publisher_id"]) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="出版社不存在")
        result = await session.execute(update(Book).where(Book.id == payload.id).values(**data))
        if result.rowcount == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="暂无数据")
        return {"msg": "编辑成功"}


@app.post('/delete_some')
async def delete_some(
        id: int,
        session: AsyncSession = Depends(get_session)
):
    async with session.begin():
        # 先查再删。查出来的对象不用 add；delete 要 await（它可能要先查关联数据），add 不用
        # result = await session.get(Book, id)
        # if result is None:
        #     raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="暂无数据")
        # await session.delete(result)
        # return {"msg": "删除成功"}

        # rowcount 是实际删掉的条数。它在 CursorResult 上，编辑器可能误报这个属性不存在
        result = await session.execute(delete(Book).where(Book.id == id))
        if result.rowcount == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="暂无数据")
        return {"msg": "删除成功", "count": result.rowcount}


class BookDeleteSchame(BaseModel):
    ids: list[int]


@app.post('/delete_many')
async def delete_many(
        payload: BookDeleteSchame,
        session: AsyncSession = Depends(get_session)
):
    async with session.begin():
        # result = await session.execute(select(Book).where(Book.id.in_(payload.ids)))
        # books = result.scalars().all()
        # if not books:
        #     raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="暂无数据")
        # session.delete 一次只能删一个对象，没有 delete_all，所以要循环。循环只是标记，提交时批量删除
        # for book in books:
        #     await session.delete(book)
        # return {"msg": "删除成功", "count": len(books)}

        # in_ 对应 SQL 的 IN，一条语句删多条。部分 id 不存在不会报错
        result = await session.execute(delete(Book).where(Book.id.in_(payload.ids)))
        if result.rowcount == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="暂无数据")
        return {"msg": "删除成功", "count": result.rowcount}


class PublisherSchame(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    address: str | None
    phone: str | None


class BookDetailSchame(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    isbn: str
    summary: str | None
    publish_date: date


class BookTagSchame(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class BookFullSchame(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    bookname: str
    author: str
    price: int
    publisher: PublisherSchame
    detail: BookDetailSchame | None
    tags: list[BookTagSchame]


# 一对一、多对一、多对多一起查。异步下要用 selectinload，否则访问关联属性会报 MissingGreenlet
# 打开下面的 response_model 后，只返回 Schema 里定义的字段
@app.get('/book_full')
# @app.get('/book_full', response_model=BookFullSchame)
async def book_full(
        id: int,
        session: AsyncSession = Depends(get_session)
):
    async with session.begin():
        stmt = (
            select(Book)
            .where(Book.id == id)
            .options(
                selectinload(Book.detail),
                selectinload(Book.publisher),
                selectinload(Book.tags),
            )
        )
        result = await session.execute(stmt)
        book = result.scalar_one_or_none()
        if book is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="暂无数据")
        return book


# 给书打标签：往 book.tags 列表里 append，提交时 SQLAlchemy 自动往 book_and_tag 中间表插一行
@app.post('/book_add_tag')
async def book_add_tag(
        book_id: int,
        tag_id: int,
        session: AsyncSession = Depends(get_session)
):
    async with session.begin():
        # 先把已有标签加载出来。查出来的对象已在 session 里，不用 add；append 在提交时写入中间表
        book = await session.get(Book, book_id, options=[selectinload(Book.tags)])
        if book is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="书不存在")
        tag = await session.get(BookTag, tag_id)
        if tag is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="标签不存在")
        if tag not in book.tags:
            book.tags.append(tag)
        return {"msg": "添加成功", "tags": [t.name for t in book.tags]}


# 去掉书的标签：从 book.tags 列表里 remove，提交时 SQLAlchemy 自动删掉 book_and_tag 中间表里对应的那一行
@app.post('/book_remove_tag')
async def book_remove_tag(
        book_id: int,
        tag_id: int,
        session: AsyncSession = Depends(get_session)
):
    async with session.begin():
        book = await session.get(Book, book_id, options=[selectinload(Book.tags)])
        if book is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="书不存在")
        tag = await session.get(BookTag, tag_id)
        if tag is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="标签不存在")
        if tag in book.tags:
            book.tags.remove(tag)
        return {"msg": "删除成功", "tags": [t.name for t in book.tags]}
