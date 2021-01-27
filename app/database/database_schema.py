import sqlalchemy

metadata = sqlalchemy.MetaData()

users = sqlalchemy.Table("users",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column("token", sqlalchemy.VARCHAR(32), nullable=False),
    sqlalchemy.Column("email", sqlalchemy.VARCHAR(255), nullable=False),
    sqlalchemy.Column("password", sqlalchemy.Binary),
    sqlalchemy.Column("displayname", sqlalchemy.VARCHAR(50), nullable=False),
    sqlalchemy.Column("description", sqlalchemy.TEXT),
)

models = sqlalchemy.Table("models",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column("token", sqlalchemy.VARCHAR(32), nullable=False),
    sqlalchemy.Column("data", sqlalchemy.Binary, nullable=False),
    sqlalchemy.Column("owner", sqlalchemy.Integer, sqlalchemy.ForeignKey("users.id"), nullable=False)
)
