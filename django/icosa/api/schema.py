from typing import List, Optional

from ninja import Field, Schema


class LoginToken(Schema):
    access_token: str
    token_type: str


class DeviceCode(Schema):
    deviceCode: str


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
    triangleCount: Optional[str]
    lodHint: Optional[int]


class PolyFormat(Schema):
    root: PolyResource
    resources: Optional[List[PolyResource]]
    formatComplexity: PolyFormatComplexity
    formatType: str


class PolyQuaternion(Schema):
    x: Optional[float]
    y: Optional[float]
    z: Optional[float]
    w: Optional[float]


class PolyPresentationParams(Schema):
    orientingRotation: Optional[PolyQuaternion]
    colorSpace: Optional[str]
    backgroundColor: Optional[str]


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


class PolyPizzaList(Schema):
    results: List[PolyPizzaAsset]


class PolyList(Schema):
    assets: List[PolyAsset]
    nextPageToken: str
    totalSize: int


# Asset data
class SubAssetFormat(Schema):
    id: str
    url: str
    format: str


class AssetFormat(Schema):
    id: str
    url: str
    format: str
    subfiles: Optional[List[SubAssetFormat]]


class _DBAsset(Schema):
    id: int
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


class AssetSchema(_DBAsset):
    ownername: str = Field(None, alias=("owner.name"))
    ownerurl: str = Field(None, alias=("owner.url"))


class AssetPatchData(Schema):
    name: Optional[str]
    url: Optional[str]
    description: Optional[str]
    visibility: Optional[str]
