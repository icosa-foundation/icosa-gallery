from typing import List, Optional

from ninja import Field, Schema
from pydantic import EmailStr


class LoginToken(Schema):
    access_token: str
    token_type: str


class DeviceCode(Schema):
    deviceCode: str


class NewUser(Schema):
    email: EmailStr
    url: Optional[str]
    password: str
    displayName: str


class FullUser(Schema):
    id: str
    url: str
    email: EmailStr
    displayname: str
    description: Optional[str]


class User(Schema):
    url: str
    displayname: str
    description: Optional[str]


class PatchUser(Schema):
    url: Optional[str]
    displayname: Optional[str]
    description: Optional[str]


class PasswordReset(Schema):
    email: str


class PasswordChangeToken(Schema):
    token: str
    newPassword: str


class PasswordChangeAuthenticated(Schema):
    oldPassword: str
    newPassword: str


class EmailChangeAuthenticated(Schema):
    newEmail: str
    currentPassword: str


# Poly helpers
class PolyResource(Schema):
    relativePath: str
    url: str
    contentType: str


class PolyFormatComplexity(Schema):
    triangleCount: Optional[str] = None
    lodHint: Optional[int] = None


class PolyFormat(Schema):
    root: PolyResource
    resources: Optional[List[PolyResource]] = None
    formatComplexity: Optional[PolyFormatComplexity] = None
    formatType: str


class PolyQuaternion(Schema):
    x: Optional[float] = None
    y: Optional[float] = None
    z: Optional[float] = None
    w: Optional[float] = None


class PolyPresentationParams(Schema):
    orientingRotation: Optional[PolyQuaternion] = None
    colorSpace: Optional[str] = None
    backgroundColor: Optional[str] = None


class PolyRemixInfo(Schema):
    sourceAsset: List[str]


class PolyPizzaCreator(Schema):
    Username: str
    DPURL: str


class PolyPizzaOrbit(Schema):
    phi: str
    radius: str
    theta: str


class PolyPizzaAsset(Schema):
    ID: str
    Title: str
    Creator: Optional[PolyPizzaCreator]
    Description: Optional[str]
    Tags: List[str]
    # Uploaded: Optional[str]
    Thumbnail: Optional[str]
    Licence: Optional[str]
    Attribution: str
    Download: str
    # TriCount: int
    Category: str
    Animated: bool
    Orbit: Optional[PolyPizzaOrbit]


class PolyAsset(Schema):
    name: str
    displayName: str
    authorName: str
    description: Optional[str] = None
    createTime: str
    updateTime: str
    formats: List[PolyFormat]
    thumbnail: Optional[PolyResource] = None
    licence: Optional[str] = None
    visibility: str
    isCurated: Optional[bool] = None
    presentationParams: Optional[PolyPresentationParams]
    metadata: Optional[str] = None
    remixInfo: Optional[PolyRemixInfo] = None


class PolyPizzaList(Schema):
    results: List[PolyPizzaAsset]


class PolyList(Schema):
    assets: List[PolyAsset]
    nextPageToken: str
    totalSize: int


# Asset data
class SubAssetFormat(Schema):
    id: int  # TODO(james) should output a str
    url: str
    format: str


class AssetFormat(Schema):
    id: int  # TODO(james) should output a str
    url: str
    format: str
    # subfiles: Optional[List[SubAssetFormat]]  # TODO(james): this is broken


class _DBAsset(Schema):
    url: Optional[str]
    formats: List[AssetFormat]
    name: str
    description: Optional[str]
    owner: int = Field(None, alias=("owner.id"))
    visibility: str
    curated: Optional[bool]
    polyid: Optional[str]
    polydata: Optional[PolyAsset]
    thumbnail: Optional[str]
    ownername: str = Field(None, alias=("owner.displayname"))
    ownerurl: str = Field(None, alias=("owner.url"))


class AssetSchemaIn(_DBAsset):
    pass


class AssetSchemaOut(_DBAsset):
    id: int  # TODO(james) should output a str


class AssetPatchData(Schema):
    name: Optional[str]
    url: Optional[str]
    description: Optional[str]
    visibility: Optional[str]
