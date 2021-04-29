import sqlalchemy
import sqlalchemy.dialects.postgresql

metadata = sqlalchemy.MetaData()

users = sqlalchemy.Table("users",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.BigInteger, primary_key=True),
    sqlalchemy.Column("url", sqlalchemy.VARCHAR(255), nullable=False),
    sqlalchemy.Column("email", sqlalchemy.VARCHAR(255), nullable=False),
    sqlalchemy.Column("password", sqlalchemy.Binary),
    sqlalchemy.Column("displayname", sqlalchemy.VARCHAR(50), nullable=False),
    sqlalchemy.Column("description", sqlalchemy.TEXT),
)

assets = sqlalchemy.Table("assets",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.BigInteger, primary_key=True),
    sqlalchemy.Column("url", sqlalchemy.VARCHAR(255)),
    sqlalchemy.Column("name", sqlalchemy.VARCHAR(255), nullable=False),
    sqlalchemy.Column("owner", sqlalchemy.BigInteger, sqlalchemy.ForeignKey("users.id"), nullable=False),
    sqlalchemy.Column("description", sqlalchemy.TEXT),
    sqlalchemy.Column("formats", sqlalchemy.dialects.postgresql.JSONB, nullable=False),
    sqlalchemy.Column("visibility", sqlalchemy.VARCHAR(255), nullable=False),
    sqlalchemy.Column("curated", sqlalchemy.BOOLEAN),
    sqlalchemy.Column("polyid", sqlalchemy.VARCHAR(255)),
    sqlalchemy.Column("polydata", sqlalchemy.dialects.postgresql.JSONB)
)

expandedassets = sqlalchemy.Table("expandedassets",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.BigInteger),
    sqlalchemy.Column("url", sqlalchemy.VARCHAR(255)),
    sqlalchemy.Column("name", sqlalchemy.VARCHAR(255)),
    sqlalchemy.Column("owner", sqlalchemy.BigInteger),
    sqlalchemy.Column("ownername", sqlalchemy.VARCHAR(255)),
    sqlalchemy.Column("ownerurl", sqlalchemy.VARCHAR(255)),
    sqlalchemy.Column("formats", sqlalchemy.dialects.postgresql.JSONB),
    sqlalchemy.Column("description", sqlalchemy.TEXT),
    sqlalchemy.Column("visibility", sqlalchemy.VARCHAR(255)),
    sqlalchemy.Column("curated", sqlalchemy.BOOLEAN),
    sqlalchemy.Column("polyid", sqlalchemy.VARCHAR(255)),
    sqlalchemy.Column("polydata", sqlalchemy.dialects.postgresql.JSONB)
)
