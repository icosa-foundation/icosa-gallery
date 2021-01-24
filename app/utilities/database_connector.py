import json
import sqlalchemy
from databases import Database

with open("config.json") as config_file:
    data = json.load(config_file)

DATABASE_URL = "postgresql://"+data["dbuser"]+":" + data["dbpassword"] + "@" + data["dblocation"] + "/icosa"

database = Database(DATABASE_URL)

metadata = sqlalchemy.MetaData()

engine = sqlalchemy.create_engine(DATABASE_URL, connect_args={})
metadata.create_all(engine)
