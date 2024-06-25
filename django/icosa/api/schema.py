from typing import List, Literal, Optional

from ninja import Field, Schema
from pydantic import EmailStr


class LoginToken(Schema):
    access_token: str
    token_type: str


class DeviceCodeSchema(Schema):
    deviceCode: str


class NewUser(Schema):
    email: EmailStr
    url: Optional[str] = None
    password: str
    displayName: str


class FullUserSchema(Schema):
    id: int
    url: str
    email: EmailStr
    displayname: str
    description: str


class UserSchema(Schema):
    url: str
    displayname: str
    description: Optional[str]


class PatchUserSchema(Schema):
    url: Optional[str] = None
    displayname: Optional[str] = None
    description: Optional[str] = None


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


class OembedOut(Schema):
    type: Literal["rich"]
    version: Literal["1.0"]
    title: Optional[str] = None  # A text title, describing the resource.
    author_name: Optional[str] = (
        None  # The name of the author/owner of the resource.
    )
    author_url: Optional[str] = (
        None  # A URL for the author/owner of the resource.
    )
    provider_name: Optional[str] = None  # The name of the resource provider.
    provider_url: Optional[str] = None  # The url of the resource provider.
    cache_age: Optional[str] = (
        None  # The suggested cache lifetime for this resource, in seconds. Consumers may choose to use this value or not.
    )
    thumbnail_url: Optional[str] = (
        None  # A URL to a thumbnail image representing the resource. The thumbnail must respect any maxwidth and maxheight parameters. If this parameter is present, thumbnail_width and thumbnail_height must also be present.
    )
    thumbnail_width: Optional[str] = (
        None  # The width of the optional thumbnail. If this parameter is present, thumbnail_url and thumbnail_height must also be present.
    )
    thumbnail_height: Optional[str] = (
        None  # The height of the optional thumbnail. If this parameter is present, thumbnail_url and thumbnail_width must also be present.
    )
    # Specific to "rich" type
    html: str
    width: int
    height: int
