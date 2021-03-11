from typing import List
from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
import requests
import json
import bcrypt
import secrets

from app.utilities.schema_models import User, FullUser, NewUser, Asset
from app.database.database_schema import users, assets

from app.utilities.authentication import get_current_user
from app.utilities.snowflake import generate_snowflake
from app.database.database_connector import database

router = APIRouter(
    prefix="/users",
    tags=["Users"]
    )

@router.get("/me", response_model=FullUser)
async def get_users_me(current_user: FullUser = Depends(get_current_user)):
    return current_user

@router.get("/me/assets", response_model=List[Asset])
async def get_me_assets(current_user: User = Depends(get_current_user)):
    return await get_user_assets(current_user["token"])

@router.post("", response_model=FullUser)
@router.post("/", response_model=FullUser, include_in_schema=False)
async def create_user(user: NewUser):
    salt = bcrypt.gensalt(10)
    hashedpw = bcrypt.hashpw(user.password.encode(), salt)
    token = secrets.token_urlsafe(8)
    query = users.select()
    query = query.where(users.c.email == user.email)
    user_check = jsonable_encoder(await database.fetch_one(query))
    if (user_check != None):
        raise HTTPException(status_code=409, detail="User exists.")
    snowflake = generate_snowflake()
    query = users.insert(None).values(id=snowflake, email=user.email, password=hashedpw, token=token, displayname=user.displayName)
    user_data = jsonable_encoder(await database.execute(query))
    query = users.select()
    query = query.where(users.c.id == snowflake)
    newuser = await database.fetch_one(query)
    return newuser

@router.get("/{user}", response_model=User)
async def get_user(user: str):
    query = users.select()
    query = query.where(users.c.token == user)
    user = await database.fetch_one(query)
    if (user == None):
        raise HTTPException(status_code=404, detail="User not found.")
    return user

@router.get("/{user}/assets", response_model=List[Asset])
async def get_user_assets(user: str):
    query = assets.select()
    query = query.where(assets.c.owner == user)
    assetlist = jsonable_encoder(await database.fetch_all(query))
    return assetlist