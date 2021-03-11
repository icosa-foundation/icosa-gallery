import sqlalchemy
import sqlalchemy.dialects.postgresql

metadata = sqlalchemy.MetaData()

users = sqlalchemy.Table("users",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.BigInteger, primary_key=True),
    sqlalchemy.Column("token", sqlalchemy.VARCHAR(32), nullable=False),
    sqlalchemy.Column("email", sqlalchemy.VARCHAR(255), nullable=False),
    sqlalchemy.Column("password", sqlalchemy.Binary),
    sqlalchemy.Column("displayname", sqlalchemy.VARCHAR(50), nullable=False),
    sqlalchemy.Column("description", sqlalchemy.TEXT),
)

assets = sqlalchemy.Table("assets",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.BigInteger, primary_key=True),
    sqlalchemy.Column("token", sqlalchemy.VARCHAR(32), nullable=False),
    sqlalchemy.Column("owner", sqlalchemy.VARCHAR(32), sqlalchemy.ForeignKey("users.id"), nullable=False),
    sqlalchemy.Column("data", sqlalchemy.dialects.postgresql.JSONB, nullable=False),
)
