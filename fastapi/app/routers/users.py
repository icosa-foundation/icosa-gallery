import json
import secrets
import string
from datetime import datetime, timedelta
from typing import List, Optional

import bcrypt
from app.database.database_connector import database
from app.database.database_schema import devicecodes, expandedassets, users
from app.utilities.authentication import (
    authenticate_user,
    get_current_user,
    get_optional_user,
    password_reset_request,
)
from app.utilities.schema_models import (
    Asset,
    DeviceCode,
    EmailChangeAuthenticated,
    FullUser,
    NewUser,
    PasswordChangeAuthenticated,
    PasswordChangeToken,
    PasswordReset,
    PatchUser,
    User,
)
from app.utilities.snowflake import generate_snowflake
from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete, func, insert, or_

from fastapi import APIRouter, Depends, HTTPException

router = APIRouter(prefix="/users", tags=["Users"])

with open("config.json") as config_file:
    data = json.load(config_file)

ALLOWED_USERS = data.get("allowed_users", [])

DEVICE_CODE_EXPIRE_MINUTES = 2


@router.get("/me", response_model=FullUser)
async def get_users_me(current_user: FullUser = Depends(get_current_user)):
    return current_user


def generate_code(length=5):
    # Define a string of characters to exclude
    exclude = "I1O0"
    characters = "".join(
        set(string.ascii_uppercase + string.digits) - set(exclude)
    )
    return "".join(secrets.choice(characters) for i in range(length))


@router.get("/me/devicecode", response_model=DeviceCode)
async def get_users_device_code(
    current_user: FullUser = Depends(get_current_user),
):
    if current_user is not None:
        code = generate_code()
        expiry_time = datetime.utcnow() + timedelta(minutes=1)

        # Delete any other codes for this user
        await database.execute(
            delete(devicecodes).where(
                devicecodes.c.user_id == current_user["id"]
            )
        )
        # Delete any expired codes
        await database.execute(
            delete(devicecodes).where(devicecodes.c.expiry < datetime.utcnow())
        )
        insert_statement = insert(devicecodes).values(
            user_id=current_user["id"], devicecode=code, expiry=expiry_time
        )
        foo = await database.execute(insert_statement)
        print(foo)

        return {"deviceCode": code}
    raise HTTPException(
        status_code=401,
        detail="Authentication failed.",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.patch("/me", response_model=FullUser)
async def update_user(
    patch_user: PatchUser, current_user: FullUser = Depends(get_current_user)
):
    if patch_user.url != None and patch_user.url.strip() == "":
        patch_user.url = current_user["url"]
    if patch_user.url != current_user["url"]:
        dupequery = users.select()
        dupequery = dupequery.where(
            func.lower(users.c.url) == func.lower(patch_user.url)
        )
        test = await database.fetch_one(dupequery)
        if test != None:
            raise HTTPException(
                status_code=403, detail="this URL is already in use."
            )
    user_data = FullUser(**current_user)
    update_data = patch_user.dict(exclude_unset=True)
    updated_user = user_data.copy(update=update_data)
    updated_user.id = int(updated_user.id)
    query = users.update(None)
    query = query.where(users.c.id == current_user["id"])
    query = query.values(updated_user.dict())
    db_update = await database.execute(query)
    return updated_user


@router.get("/me/assets", response_model=List[Asset])
async def get_me_assets(current_user: User = Depends(get_current_user)):
    return await get_id_user_assets(current_user["id"], current_user)


# TODO add db support for "liked" - currently returns all assets
@router.get("/me/likedassets", response_model=List[Asset])
async def get_me_likedassets(
    current_user: User = Depends(get_current_user),
    format: Optional[str] = None,
    orderBy: Optional[str] = None,
    results: int = 20,
    page: int = 0,
):
    query = expandedassets.select()
    # TODO
    # query = query.where(something current_user likes)
    if format:
        query = query.where(
            expandedassets.c.formats.contains([{"format": format}])
        )

    if orderBy and orderBy == "LIKED_TIME":
        # TODO
        # query = query.order_by(...)
        pass
    query = query.limit(results)
    query = query.offset(page * results)
    assetlist = jsonable_encoder(await database.fetch_all(query))
    return assetlist


@router.patch("/me/password")
async def change_authenticated_user_password(
    passwordData: PasswordChangeAuthenticated,
    current_user: FullUser = Depends(get_current_user),
):
    user = await authenticate_user(
        current_user["email"], passwordData.oldPassword
    )
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect Password.")
    salt = bcrypt.gensalt(10)
    newPasswordHashed = bcrypt.hashpw(passwordData.newPassword.encode(), salt)
    query = users.update(None)
    query = query.where(users.c.id == user["id"])
    query = query.values(password=newPasswordHashed)
    await database.execute(query)


@router.patch("/me/email")
async def change_authenticated_user_email(
    emailData: EmailChangeAuthenticated,
    current_user: FullUser = Depends(get_current_user),
):
    user = await authenticate_user(
        current_user["email"], emailData.currentPassword
    )
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect Password.")
    emailData.newEmail = emailData.newEmail.lower()
    query = users.select().where(
        func.lower(users.c.email) == func.lower(emailData.newEmail)
    )
    already_exists = await database.fetch_one(query)
    print(already_exists)
    if already_exists != None:
        raise HTTPException(status_code=409, detail="Email exists.")
    query = users.update(None)
    query = query.where(users.c.id == user["id"])
    query = query.values(email=emailData.newEmail)
    await database.execute(query)


@router.post("", response_model=FullUser)
@router.post("/", response_model=FullUser, include_in_schema=False)
async def create_user(user: NewUser):
    query = users.select()
    user.email = user.email.lower()
    # TODO(james) This setting is for debug mode only. Should be removed in
    # production.
    if user.email not in ALLOWED_USERS:
        raise HTTPException(status_code=409, detail="User exists.")
    query = query.where(
        or_(
            func.lower(users.c.url) == func.lower(user.url),
            func.lower(users.c.email) == func.lower(user.email),
        )
    )
    user_check = jsonable_encoder(await database.fetch_one(query))
    if user_check != None:
        raise HTTPException(status_code=409, detail="User exists.")
    if user.url != None and user.url.strip() == "":
        user.url = None
    salt = bcrypt.gensalt(10)
    hashedpw = bcrypt.hashpw(user.password.encode(), salt)
    snowflake = generate_snowflake()
    assettoken = secrets.token_urlsafe(8) if user.url is None else user.url
    query = users.insert(None).values(
        id=snowflake,
        url=assettoken,
        email=user.email,
        password=hashedpw,
        displayname=user.displayName,
    )
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
    if user != None:
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
    if user == None:
        raise HTTPException(status_code=404, detail="User not found.")
    return user


@router.get("/id/{user}/assets", response_model=List[Asset])
async def get_id_user_assets(
    user: int,
    current_user: User = Depends(get_optional_user),
    results: int = 20,
    page: int = 0,
):
    query = expandedassets.select()
    if (current_user is None) or (current_user["id"] != user):
        query = query.where(expandedassets.c.visibility == "PUBLIC")
    query = query.where(expandedassets.c.owner == user)
    query = query.limit(results)
    query = query.offset(page * results)
    assetlist = jsonable_encoder(await database.fetch_all(query))
    return assetlist


@router.get("/{user}", response_model=User)
async def get_user(user: str):
    query = users.select()
    query = query.where(users.c.url == user)
    user = await database.fetch_one(query)
    if user == None:
        raise HTTPException(status_code=404, detail="User not found.")
    return user


@router.get("/{user}/assets", response_model=List[Asset])
async def get_user_assets(
    user: str,
    current_user: User = Depends(get_optional_user),
    results: int = 20,
    page: int = 0,
):
    userdata = await get_user(user)
    return await get_id_user_assets(
        userdata["id"], current_user, results, page, format
    )
