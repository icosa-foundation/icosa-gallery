from pydantic import BaseModel, EmailStr
from typing import Optional, List

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
    owner: str
    data: AssetData
# Poly helpers
class PolyResource(BaseModel):
    relativePath: str
    url: str
    contentType: str

class PolyFormatComplexity(BaseModel):
    triangleCount: Optional[str]
    lodHint: Optional[int]

class PolyFormat(BaseModel):
    root: PolyResource
    resources: Optional[List[PolyResource]]
    formatComplexity: PolyFormatComplexity
    formatType: str

class PolyQuaternion(BaseModel):
    x: Optional[float]
    y: Optional[float]
    z: Optional[float]
    w: Optional[float]

class PolyPresentationParams(BaseModel):
    orientingRotation: PolyQuaternion
    colorSpace: str
    backgroundColor: str

class PolyRemixInfo(BaseModel):
    sourceAsset: List[str]

class PolyAsset(BaseModel):
    name: str
    displayName: str
    authorName: str
    createTime: str
    updateTime: str
    formats: List[PolyFormat]
    thumbnail: PolyResource
    licence: Optional[str]
    visibility: str
    isCurated: bool
    presentationParams: PolyPresentationParams
    metadata: Optional[str]
    remixInfo: Optional[PolyRemixInfo]

class PolyList(BaseModel):
    assets: List[PolyAsset]
