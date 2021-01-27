from typing import List
import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
import jwt
import sqlalchemy
import bcrypt
from passlib.context import CryptContext

from app.database.database_connector import database
from app.database.database_schema import users
from app.utilities.schema_models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

with open("config.json") as config_file:
    data = json.load(config_file)

SECRET_KEY = data["secret_key"]
ALGORITHM = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

async def authenticate_user(username: str, password: str, response_model=User):
    query = users.select()
    query = query.where(users.c.email == username)
    user = jsonable_encoder(await database.fetch_one(query))
    if (user == None):
        return False
    if not pwd_context.verify(password, user["password"]):
        return False
    return user

def create_access_token(*, data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=timedelta)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(status_code=401, detail="Invalid Credentials", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except PyJWTError:
        raise credentials_exception
    query = users.select()
    query = query.where(users.c.email == username)
    user = jsonable_encoder(await database.fetch_one(query))
    if user is None:
        raise credentials_exception
    return user