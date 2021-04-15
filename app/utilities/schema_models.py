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
    id: str
    url: str
    email: EmailStr
    displayname: str
    description: Optional[str]

class User(BaseModel):
    url: str
    displayname: str
    description: Optional[str]

class PatchUser(BaseModel):
    url: Optional[str]
    displayname: Optional[str]
    description: Optional[str]

class AssetFormat(BaseModel):
    id: str
    url: str
    format: str

class Asset(BaseModel):
    id: str
    url: Optional[str]
    name: str
    owner: str
    description: Optional[str]
    formats: List[AssetFormat]
class PasswordReset(BaseModel):
    email: str

class PasswordChangeToken(BaseModel):
    token: str
    newPassword: str

class PasswordChangeAuthenticated(BaseModel):
    oldPassword: str
    newPassword: str

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
    isCurated: Optional[bool]
    presentationParams: PolyPresentationParams
    metadata: Optional[str]
    remixInfo: Optional[PolyRemixInfo]

class PolyList(BaseModel):
    assets: List[PolyAsset]
