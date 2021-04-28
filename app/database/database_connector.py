import json
import sqlalchemy
from sqlalchemy.pool import QueuePool
from databases import Database

with open("config.json") as config_file:
    data = json.load(config_file)

DATABASE_URL = "postgresql://"+data["dbuser"]+":" + data["dbpassword"] + "@" + data["dblocation"] + "/icosa"

database = Database(DATABASE_URL)

metadata = sqlalchemy.MetaData()

engine = sqlalchemy.create_engine(DATABASE_URL, pool_size=20, poolclass=QueuePool)
metadata.create_all(engine)
