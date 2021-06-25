from pydantic import BaseModel, EmailStr
from typing import Optional, List

class LoginToken(BaseModel):
    access_token: str
    token_type: str

class NewUser(BaseModel):
    email: EmailStr
    url: Optional[str]
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

class PasswordReset(BaseModel):
    email: str

class PasswordChangeToken(BaseModel):
    token: str
    newPassword: str

class PasswordChangeAuthenticated(BaseModel):
    oldPassword: str
    newPassword: str

class EmailChangeAuthenticated(BaseModel):
    newEmail: str
    currentPassword: str

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
    orientingRotation: Optional[PolyQuaternion]
    colorSpace: Optional[str]
    backgroundColor: Optional[str]

class PolyRemixInfo(BaseModel):
    sourceAsset: List[str]

class PolyAsset(BaseModel):
    name: str
    displayName: str
    authorName: str
    description: Optional[str]
    createTime: str
    updateTime: str
    formats: List[PolyFormat]
    thumbnail: Optional[PolyResource]
    licence: Optional[str]
    visibility: str
    isCurated: Optional[bool]
    presentationParams: Optional[PolyPresentationParams]
    metadata: Optional[str]
    remixInfo: Optional[PolyRemixInfo]

class PolyList(BaseModel):
    assets: List[PolyAsset]
    nextPageToken: str
    totalSize: int

# Asset data
class SubAssetFormat(BaseModel):
    id: str
    url: str
    format: str

class AssetFormat(BaseModel):
    id: str
    url: str
    format: str
    subfiles: Optional[List[SubAssetFormat]]

class _DBAsset(BaseModel):
    id: str
    url: Optional[str]
    formats: List[AssetFormat]
    name: str
    description: Optional[str]
    owner: str
    visibility: str
    curated: Optional[bool]
    polyid: Optional[str]
    polydata: Optional[PolyAsset]
    thumbnail: Optional[str]

class Asset(_DBAsset):
    ownername: str
    ownerurl: str

class AssetPatchData(BaseModel):
    name: Optional[str]
    url: Optional[str]
    description: Optional[str]
    visibility: Optional[str]