from typing import List
import json
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from fastapi.encoders import jsonable_encoder
import jwt
from passlib.context import CryptContext
from sqlalchemy import or_
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from app.database.database_connector import database
from app.database.database_schema import users

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

with open("config.json") as config_file:
    data = json.load(config_file)

SECRET_KEY = data["secret_key"]
ALGORITHM = "HS256"

RESET_TOKEN_EXPIRE_MINUTES = 60

SENDGRID = data["sendgrid"]
SENDGRID_API_KEY = SENDGRID["api_key"]
SENDGRID_DOMAIN = SENDGRID["domain"]
SENDGRID_SEND_USER = SENDGRID["send_user"]
SENDGRID_RESET_TEMPLATE = SENDGRID["reset_password_template"]

sendgrid = SendGridAPIClient(SENDGRID_API_KEY)


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login", auto_error=False)

async def authenticate_user(username: str, password: str):
    query = users.select()
    query = query.where(or_(users.c.url == username, users.c.email == username))
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

async def get_optional_user(token: str = Depends(oauth2_scheme)):
    if token is None:
        return None
    else:
        return await get_current_user(token)

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(status_code=401, detail="Invalid Credentials", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
    query = users.select()
    query = query.where(users.c.email == username)
    user = await database.fetch_one(query)
    if user is None:
        raise credentials_exception
    return user

async def password_reset_request(email: str):
    query = users.select()
    query = query.where(users.c.email == email)
    user = await database.fetch_one(query)
    if(user == None):
        return
    reset_token_timer = timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)
    reset_token = create_access_token(data={"sub": user["email"]}, expires_delta=reset_token_timer)
    user_name = user["displayname"]
    message = Mail(from_email=SENDGRID_SEND_USER, to_emails= user["email"])
    message.dynamic_template_data = {"USER_NAME": user_name, "PASSWORD_RESET_TOKEN": reset_token}
    message.template_id = SENDGRID_RESET_TEMPLATE
    try:
        response = sendgrid.send(message)
        print("OK")
    except Exception as e:
        print(e)
        return
    return