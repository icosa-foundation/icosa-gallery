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

class AssetData(BaseModel):
    token: str
    name: str
    description: Optional[str] = None
    url: str

class Asset(BaseModel):
    id: int
    token: str
    data: AssetData
    owner: int
