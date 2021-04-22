from typing import List
from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
import requests
import json
import bcrypt
import secrets

from app.utilities.schema_models import User, FullUser, NewUser, PatchUser, Asset, PasswordReset, PasswordChangeToken, PasswordChangeAuthenticated, EmailChangeAuthenticated
from app.database.database_schema import users, assets

from app.utilities.authentication import get_current_user, password_reset_request, authenticate_user
from app.utilities.snowflake import generate_snowflake
from app.database.database_connector import database

router = APIRouter(
    prefix="/users",
    tags=["Users"]
    )

@router.get("/me", response_model=FullUser)
async def get_users_me(current_user: FullUser = Depends(get_current_user)):
    return current_user

@router.patch("/me", response_model=FullUser)
async def update_user(patch_user: PatchUser, current_user: FullUser = Depends(get_current_user)):
    if patch_user.url != current_user["url"]:
        dupequery = users.select()
        dupequery = dupequery.where(users.c.url == patch_user.url)
        test = await database.fetch_one(dupequery)
        if test != None:
            raise HTTPException(status_code=403, detail="this URL is already in use.")
    user_data = FullUser(**current_user)
    update_data = patch_user.dict(exclude_unset=True)
    updated_user = user_data.copy(update=update_data)
    updated_user.id = int(updated_user.id)
    query = users.update(None)
    query = query.where(users.c.id == current_user["id"])
    query = query.values(updated_user.dict())
    db_update = await database.execute(query);
    return updated_user

@router.get("/me/assets", response_model=List[Asset])
async def get_me_assets(current_user: User = Depends(get_current_user)):
    return await get_id_user_assets(current_user["id"])

@router.patch("/me/password")
async def change_authenticated_user_password(passwordData: PasswordChangeAuthenticated, current_user: FullUser = Depends(get_current_user)):
    user = await authenticate_user(current_user["email"], passwordData.oldPassword)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect Password.")
    salt = bcrypt.gensalt(10)
    newPasswordHashed = bcrypt.hashpw(passwordData.newPassword.encode(), salt)
    query = users.update(None)
    query = query.where(users.c.id == user["id"])
    query = query.values(password=newPasswordHashed)
    await database.execute(query)

@router.patch("/me/email")
async def change_authenticated_user_email(emailData: EmailChangeAuthenticated, current_user: FullUser = Depends(get_current_user)):
    user = await authenticate_user(current_user["email"], emailData.currentPassword)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect Password.")
    query = users.select().where(users.c.email == emailData.newEmail)
    already_exists = await database.fetch_one(query)
    print(already_exists)
    if(already_exists != None):
        raise HTTPException(status_code=409, detail="Email exists.")
    query = users.update(None)
    query = query.where(users.c.id == user["id"])
    query = query.values(email=emailData.newEmail)
    await database.execute(query)


@router.post("", response_model=FullUser)
@router.post("/", response_model=FullUser, include_in_schema=False)
async def create_user(user: NewUser):
    query = users.select()
    query = query.where(users.c.email == user.email)
    user_check = jsonable_encoder(await database.fetch_one(query))
    if (user_check != None):
        raise HTTPException(status_code=409, detail="User exists.")
    salt = bcrypt.gensalt(10)
    hashedpw = bcrypt.hashpw(user.password.encode(), salt)
    snowflake = generate_snowflake()
    assettoken = secrets.token_urlsafe(8)
    query = users.insert(None).values(id=snowflake, url=assettoken, email=user.email, password=hashedpw, displayname=user.displayName)
    user_data = jsonable_encoder(await database.execute(query))
    query = users.select()
    query = query.where(users.c.id == snowflake)
    newuser = await database.fetch_one(query)
    return newuser

@router.put("/password/reset", status_code=202)
async def user_password_reset_request(email: PasswordReset):
    return await password_reset_request(email.email)
    
@router.patch("/password")
async def change_password_via_token(resetData: PasswordChangeToken):
    user = await get_current_user(token=resetData.token)
    if (user != None):
        salt = bcrypt.gensalt(10)
        newPasswordHashed = bcrypt.hashpw(resetData.newPassword.encode(), salt)
        query = users.update(None)
        query = query.where(users.c.id == user["id"])
        query = query.values(password=newPasswordHashed)
        await database.execute(query)
    return

@router.get("/id/{user}", response_model=User)
async def get_user(user: int):
    query = users.select()
    query = query.where(users.c.id == user)
    user = await database.fetch_one(query)
    if (user == None):
        raise HTTPException(status_code=404, detail="User not found.")
    return user

@router.get("/id/{user}/assets", response_model=List[Asset])
async def get_id_user_assets(user: int):
    query = assets.select()
    query = query.where(assets.c.owner == user)
    assetlist = jsonable_encoder(await database.fetch_all(query))
    return assetlist

@router.get("/{user}", response_model=User)
async def get_user(user: str):
    query = users.select()
    query = query.where(users.c.url == user)
    user = await database.fetch_one(query)
    if (user == None):
        raise HTTPException(status_code=404, detail="User not found.")
    return user

@router.get("/{user}/assets", response_model=List[Asset])
async def get_user_assets(user: str):
    userdata = await get_user(user)
    query = assets.select()
    query = query.where(assets.c.owner == userdata["id"])
    assetlist = jsonable_encoder(await database.fetch_all(query))
    return assetlist