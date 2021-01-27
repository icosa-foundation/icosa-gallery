from pydantic import BaseModel, EmailStr
from typing import Optional

class LoginToken(BaseModel):
    access_token: str
    token_type: str

class NewUser(BaseModel):
    email: EmailStr
    password: str
    displayName: str

class FullUser(BaseModel):
    token: str
    email: EmailStr
    displayname: str
    description: Optional[str] = None

class User(BaseModel):
    token: str
    displayname: str
    description: Optional[str] = None

class ModelData(BaseModel):
    token: str

class Model(BaseModel):
    id: int
    token: str
    data: ModelData
    owner: int
