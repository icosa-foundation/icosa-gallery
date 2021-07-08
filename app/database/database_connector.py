import json
import sqlalchemy
from sqlalchemy.pool import NullPool
from databases import Database

with open("config.json") as config_file:
    data = json.load(config_file)

DATABASE_URL = "postgresql://" + \
    data["dbuser"]+":" + data["dbpassword"] + "@" + \
    data["dblocation"] + "/"+data["dbname"]

database = Database(DATABASE_URL)

metadata = sqlalchemy.MetaData()

engine = sqlalchemy.create_engine(DATABASE_URL, poolclass=NullPool)
metadata.create_all(engine)
