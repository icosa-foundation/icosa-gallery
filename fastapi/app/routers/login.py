from datetime import datetime, timedelta

import app.utilities.authentication as authentication
from app.database.database_connector import database
from app.database.database_schema import devicecodes, users
from app.utilities.schema_models import FullUser, LoginToken
from fastapi.encoders import jsonable_encoder
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import and_, delete, func, select

from fastapi import APIRouter, Depends, HTTPException

router = APIRouter(prefix="/login", tags=["Login"])

ACCESS_TOKEN_EXPIRE_MINUTES = 131400


@router.post("", response_model=LoginToken)
@router.post("/", response_model=LoginToken, include_in_schema=False)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = jsonable_encoder(
        await authentication.authenticate_user(
            form_data.username, form_data.password
        )
    )
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = authentication.create_access_token(
        data={"sub": user["email"]}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/device_login", response_model=LoginToken)
async def device_login(device_code: str):
    current_time = datetime.utcnow()
    devicecodes_users_join = devicecodes.join(
        users, devicecodes.c.user_id == users.c.id
    )
    valid_code = await database.fetch_one(
        select([devicecodes, users.c.email])
        .select_from(devicecodes_users_join)  # Use the join you created
        .where(
            and_(
                func.lower(devicecodes.c.devicecode)
                == func.lower(device_code),
                devicecodes.c.expiry > current_time,
            )
        )
    )
    if valid_code:
        await database.execute(
            delete(devicecodes).where(devicecodes.c.id == valid_code["id"])
        )
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = authentication.create_access_token(
            data={"sub": valid_code["email"]},
            expires_delta=access_token_expires,
        )
        return {"access_token": access_token, "token_type": "bearer"}
    else:
        raise HTTPException(
            status_code=401,
            detail="Authentication failed.",
            headers={"WWW-Authenticate": "Bearer"},
        )
