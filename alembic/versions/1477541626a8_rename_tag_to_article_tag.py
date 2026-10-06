"""rename tag to article_tag

Revision ID: 1477541626a8
Revises: d6d62aec74b3
Create Date: 2026-10-06 10:45:08.734805

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1477541626a8'
down_revision: Union[str, Sequence[str], None] = 'd6d62aec74b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 手写的改名迁移：autogenerate 会把改表名识别成“删旧表 + 建新表”，数据会丢。
# 顺序不能反：先把旧的 article_tag（中间表）改走，tag 才能改成 article_tag。
# 约束名也要跟着改，否则和 Base 里的命名约定对不上，下次 autogenerate 会生成多余的改动。
def upgrade() -> None:
    """Upgrade schema."""
    op.rename_table("article_tag", "article_and_tag")
    op.execute("ALTER TABLE article_and_tag RENAME CONSTRAINT pk_article_tag TO pk_article_and_tag")
    op.execute(
        "ALTER TABLE article_and_tag RENAME CONSTRAINT fk_article_tag_article_id_article "
        "TO fk_article_and_tag_article_id_article"
    )
    op.execute(
        "ALTER TABLE article_and_tag RENAME CONSTRAINT fk_article_tag_tag_id_tag "
        "TO fk_article_and_tag_tag_id_article_tag"
    )

    op.rename_table("tag", "article_tag")
    op.execute("ALTER TABLE article_tag RENAME CONSTRAINT pk_tag TO pk_article_tag")
    op.execute("ALTER TABLE article_tag RENAME CONSTRAINT uq_tag_name TO uq_article_tag_name")
    op.execute("ALTER SEQUENCE tag_id_seq RENAME TO article_tag_id_seq")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("ALTER SEQUENCE article_tag_id_seq RENAME TO tag_id_seq")
    op.execute("ALTER TABLE article_tag RENAME CONSTRAINT uq_article_tag_name TO uq_tag_name")
    op.execute("ALTER TABLE article_tag RENAME CONSTRAINT pk_article_tag TO pk_tag")
    op.rename_table("article_tag", "tag")

    op.execute(
        "ALTER TABLE article_and_tag RENAME CONSTRAINT fk_article_and_tag_tag_id_article_tag "
        "TO fk_article_tag_tag_id_tag"
    )
    op.execute(
        "ALTER TABLE article_and_tag RENAME CONSTRAINT fk_article_and_tag_article_id_article "
        "TO fk_article_tag_article_id_article"
    )
    op.execute("ALTER TABLE article_and_tag RENAME CONSTRAINT pk_article_and_tag TO pk_article_tag")
    op.rename_table("article_and_tag", "article_tag")
