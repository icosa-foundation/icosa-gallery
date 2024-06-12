import sqlalchemy
import sqlalchemy.dialects.postgresql

metadata = sqlalchemy.MetaData()

users = sqlalchemy.Table(
    "users",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.BigInteger, primary_key=True),
    sqlalchemy.Column("url", sqlalchemy.VARCHAR(255), nullable=False),
    sqlalchemy.Column("email", sqlalchemy.VARCHAR(255), nullable=False),
    sqlalchemy.Column("password", sqlalchemy.Binary),
    sqlalchemy.Column("displayname", sqlalchemy.VARCHAR(50), nullable=False),
    sqlalchemy.Column("description", sqlalchemy.TEXT),
)

assets = sqlalchemy.Table(
    "assets",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.BigInteger, primary_key=True),
    sqlalchemy.Column("url", sqlalchemy.VARCHAR(255)),
    sqlalchemy.Column("name", sqlalchemy.VARCHAR(255), nullable=False),
    sqlalchemy.Column(
        "owner",
        sqlalchemy.BigInteger,
        sqlalchemy.ForeignKey("users.id"),
        nullable=False,
    ),
    sqlalchemy.Column("description", sqlalchemy.TEXT),
    sqlalchemy.Column(
        "formats", sqlalchemy.dialects.postgresql.JSONB, nullable=False
    ),
    sqlalchemy.Column("visibility", sqlalchemy.VARCHAR(255), nullable=False),
    sqlalchemy.Column("curated", sqlalchemy.BOOLEAN),
    sqlalchemy.Column("polyid", sqlalchemy.VARCHAR(255)),
    sqlalchemy.Column("polydata", sqlalchemy.dialects.postgresql.JSONB),
    sqlalchemy.Column("thumbnail", sqlalchemy.TEXT),
    sqlalchemy.Column("create_time", sqlalchemy.DateTime(timezone=True)),
    sqlalchemy.Column("update_time", sqlalchemy.DateTime(timezone=True)),
    sqlalchemy.Column("license", sqlalchemy.VARCHAR(50)),
    sqlalchemy.Column("tags", sqlalchemy.dialects.postgresql.JSONB),
    # sqlalchemy.Column("likes"), # TODO: perhaps this can wait until we move to ninja
    sqlalchemy.Column(
        "orienting_rotation", sqlalchemy.dialects.postgresql.JSONB
    ),
    sqlalchemy.Column("color_space", sqlalchemy.VARCHAR(50)),
    sqlalchemy.Column("background_color", sqlalchemy.VARCHAR(7)),
)


expandedassets = sqlalchemy.Table(
    "expandedassets",
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
    sqlalchemy.Column("polydata", sqlalchemy.dialects.postgresql.JSONB),
    sqlalchemy.Column("thumbnail", sqlalchemy.TEXT),
)

devicecodes = sqlalchemy.Table(
    "devicecodes",
    metadata,
    sqlalchemy.Column(
        "id",
        sqlalchemy.BigInteger,
        primary_key=True,
        default=sqlalchemy.Sequence("devicecodes_id_seq"),
    ),
    sqlalchemy.Column(
        "user_id",
        sqlalchemy.BigInteger,
        sqlalchemy.ForeignKey("users.id"),
        nullable=False,
        unique=True,
    ),
    sqlalchemy.Column("devicecode", sqlalchemy.CHAR(6), nullable=False),
    sqlalchemy.Column("expiry", sqlalchemy.TIMESTAMP, nullable=False),
)
