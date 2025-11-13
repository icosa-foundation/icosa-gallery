from datetime import datetime
from enum import Enum
from typing import List, Literal, Optional

from django.urls import reverse_lazy
from icosa.models import PUBLIC, Asset, AssetCollection
from ninja import Field, ModelSchema, Schema
from pydantic import EmailStr

API_DOWNLOAD_COMPATIBLE_ROLES = [
    "ORIGINAL_OBJ_FORMAT",
    "TILT_FORMAT",
    "ORIGINAL_FBX_FORMAT",
    "BLOCKS_FORMAT",
    "USD_FORMAT",
    "GLB_FORMAT",
    "ORIGINAL_TRIANGULATED_OBJ_FORMAT",
    "USDZ_FORMAT",
    "UPDATED_GLTF_FORMAT",
    "TILT_NATIVE_GLTF",
    "USER_SUPPLIED_GLTF",
]


class LoginToken(Schema):
    access_token: str
    token_type: str


class FullUserSchema(Schema):
    id: int
    username: str
    email: EmailStr
    displayName: str = Field(None, alias="displayname")
    description: Optional[str] = None
    url: str

    @staticmethod
    def resolve_url(obj):
        # TODO(james): This is a temporary fix until we get URL on the django
        # user instead.
        if obj.assetowner_set.first():
            url = obj.assetowner_set.first().url
        else:
            url = ""
        return url


class PatchUserSchema(Schema):
    # TODO(james): I don't think a user should be able to update their email
    # via the api.
    # email: Optional[EmailStr] = None
    url: Optional[str] = None
    displayName: str = Field(None, alias="displayname")
    description: Optional[str] = None


class AssetResource(Schema):
    relativePath: str
    contentType: str
    url: str

    @staticmethod
    def resolve_relativePath(obj):
        return obj.relative_path

    @staticmethod
    def resolve_contentType(obj):
        if obj.contenttype:
            return obj.contenttype
        else:
            return ""

    @staticmethod
    def resolve_url(obj):
        return obj.url


class Thumbnail(Schema):
    relativePath: Optional[str] = None
    contentType: Optional[str] = None
    url: Optional[str] = None


class FormatComplexity(Schema):
    triangleCount: Optional[int] = None
    lodHint: Optional[int] = None


class ImageSchema(Schema):
    url: Optional[str] = None


class AssetFormat(Schema):
    root: Optional[AssetResource] = Field(
        None,
        alias="root_resource",
    )
    resources: Optional[List[AssetResource]] = Field(
        None,
        alias="resource_set",
    )
    formatComplexity: FormatComplexity
    formatType: str = Field(None, alias="format_type")
    zip_archive_url: Optional[str] = None
    role: Optional[str] = Field(
        default=None,
        description="This field is deprecated. Do not rely on it for anything.",
        deprecated=True,
    )
    isPreferredForDownload: bool = Field(default=False, alias="is_preferred_for_download")

    @staticmethod
    def resolve_formatComplexity(obj):
        format_complexity = {
            "triangleCount": obj.triangle_count,
            "lodHint": obj.lod_hint,
        }
        return format_complexity


class AssetSchema(ModelSchema):
    authorId: str = Field(None, alias=("owner.url"))
    authorName: str
    # authorUrl: str # TODO create API endpoints for user
    name: str
    description: Optional[str]
    createTime: datetime = Field(..., alias=("create_time"))
    updateTime: Optional[datetime] = Field(..., alias=("update_time"))
    url: Optional[str]
    assetId: str
    displayName: Optional[str]
    visibility: str
    tags: List[str] = []
    isCurated: Optional[bool] = Field(None, alias=("curated"))
    thumbnail: Optional[Thumbnail]
    triangleCount: int = Field(..., alias=("triangle_count"))
    license: str
    licenseVersion: Optional[str]
    presentationParams: Optional[dict] = Field(None, alias=("presentation_params"))
    formats: List[AssetFormat]

    class Config:
        model = Asset
        model_fields = ["url", "license"]

    @staticmethod
    def resolve_name(obj, context):
        return f"assets/{obj.url}"

    @staticmethod
    def resolve_displayName(obj, context):
        return obj.name

    @staticmethod
    def resolve_license(obj, context):
        return obj.get_base_license()

    @staticmethod
    def resolve_licenseVersion(obj, context):
        return obj.get_license_version()

    @staticmethod
    def resolve_url(obj, context):
        request = context["request"]
        root_url = request.build_absolute_uri("/").rstrip("/")
        return f"{root_url}{reverse_lazy('icosa:api:asset_list')}/{obj.url}"

    @staticmethod
    def resolve_assetId(obj, context):
        return obj.url

    @staticmethod
    def resolve_formats(obj, context):
        return [
            f
            for f in obj.format_set.filter(
                role__in=API_DOWNLOAD_COMPATIBLE_ROLES,
            )
        ]

    @staticmethod
    def resolve_tags(obj):
        return [t.name for t in obj.tags.all()]

    @staticmethod
    def resolve_thumbnail(obj):
        data = {}
        if obj.thumbnail:
            data = {
                "relativePath": obj.thumbnail.name.split("/")[-1],
                "contentType": obj.thumbnail_contenttype,
                "url": obj.thumbnail.url,
            }
        return data

    @staticmethod
    def resolve_authorName(obj):
        if obj.owner:
            return f"{obj.owner}"
        else:
            return ""

    # TODO: Uncomment this method to have a Google Poly-compatible schema.
    # @staticmethod
    # def resolve_presentationParams(obj):
    #     params = {}
    #     presentationParams = obj.presentation_params
    #     params["backgroundColor"] = presentationParams.get(
    #         "backgroundColor", None
    #     )
    #     orientingRotation = presentationParams.get("orientingRotation", None)
    #     if orientingRotation:
    #         params["orientingRotation"] = {
    #             "x": orientingRotation.get("x", None),
    #             "y": orientingRotation.get("y", None),
    #             "z": orientingRotation.get("z", None),
    #             "w": orientingRotation.get("w", None),
    #         }
    #     params["colorSpace"] = presentationParams.get("colorSpace", None)
    #     return params


class AssetSchemaWithState(AssetSchema):
    state: str


class AssetSchemaPrivate(AssetSchema):
    state: str

    @staticmethod
    def resolve_formats(obj, context):
        return [f for f in obj.format_set.all()]


class AssetStateSchema(ModelSchema):
    class Config:
        model = Asset
        model_fields = ["state"]


class AssetPatchData(Schema):
    name: Optional[str]
    url: Optional[str]
    description: Optional[str]
    visibility: Optional[str]


class AssetMetaData(Schema):
    objPolyCount: Optional[int] = None
    triangulatedObjPolyCount: Optional[int] = None
    remixIds: Optional[List[str]] = None
    formatOverride: Optional[List[str]] = None


class UploadJobSchemaOut(Schema):
    publishUrl: str
    assetId: str


class OembedOut(Schema):
    type: Literal["rich"]
    version: Literal["1.0"]
    title: Optional[str] = None  # A text title, describing the resource.
    author_name: Optional[str] = None  # The name of the author/owner of the resource.
    author_url: Optional[str] = None  # A URL for the author/owner of the resource.
    provider_name: Optional[str] = None  # The name of the resource provider.
    provider_url: Optional[str] = None  # The url of the resource provider.
    cache_age: Optional[str] = (
        None  # The suggested cache lifetime for this resource, in seconds.
        # Consumers may choose to use this value or not.
    )
    thumbnail_url: Optional[str] = (
        None  # A URL to a thumbnail image representing the resource. The
        # thumbnail must respect any maxwidth and maxheight parameters. If this
        # parameter is present, thumbnail_width and thumbnail_height must also
        # be present.
    )
    thumbnail_width: Optional[str] = (
        None  # The width of the optional thumbnail. If this parameter is
        # present, thumbnail_url and thumbnail_height must also be present.
    )
    thumbnail_height: Optional[str] = (
        None  # The height of the optional thumbnail. If this parameter is
        # present, thumbnail_url and thumbnail_width must also be present.
    )
    # Specific to "rich" type
    html: str
    width: int
    height: int


class AssetCollectionSchema(ModelSchema):
    name: str
    description: str
    url: str
    createTime: datetime = Field(..., alias=("create_time"))
    updateTime: Optional[datetime] = Field(..., alias=("update_time"))
    visibility: str
    imageUrl: Optional[str] = Field(None)
    assets: Optional[List[AssetSchema]] = Field(None)

    @staticmethod
    def resolve_assets(obj, context):
        # NOTE: obj.assets are the raw assets without any of the collection's
        # metadata (e.g. time added, order in the collection).
        assets = obj.assets.filter(visibility__in=[PUBLIC])
        return assets

    @staticmethod
    def resolve_imageUrl(obj, context):
        if not bool(obj.image):
            return None
        return obj.image

    class Config:
        model = AssetCollection
        model_fields = [
            "url",
            "name",
            "description",
            "visibility",
        ]


class AssetCollectionSchemaWithRejections(Schema):
    collection: AssetCollectionSchema
    rejectedAssetUrls: Optional[List[str]] = None


class AssetVisibility(Enum):
    # TODO(james): This should be accessible to others
    PRIVATE = "PRIVATE"
    PUBLIC = "PUBLIC"
    UNLISTED = "UNLISTED"


class AssetCollectionPostSchema(Schema):
    name: str
    description: str
    visibility: Optional[AssetVisibility] = None
    asset_url: Optional[List[str]] = None


class Error(Schema):
    message: str
