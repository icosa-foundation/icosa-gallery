from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.security import OAuth2PasswordRequestForm

from app.utilities.schema_models import LoginToken
import app.utilities.authentication as authentication

router = APIRouter(
    prefix="/login",
    tags=["Login"])

ACCESS_TOKEN_EXPIRE_MINUTES = 131400

@router.post("", response_model=LoginToken)
@router.post("/", response_model=LoginToken, include_in_schema=False)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = jsonable_encoder(await authentication.authenticate_user(form_data.username, form_data.password))
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect username or password.", headers={"WWW-Authenticate": "Bearer"})
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = authentication.create_access_token(data={"sub": user["email"]}, expires_delta=access_token_expires)
    return {"access_token": access_token, "token_type": "bearer"}