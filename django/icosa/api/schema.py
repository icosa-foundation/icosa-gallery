from datetime import datetime
from enum import Enum, auto
from typing import List, Literal, Optional

from django.db.models import Q
from django.urls import reverse_lazy
from icosa.helpers.format_roles import role_display
from icosa.models import API_DOWNLOAD_COMPATIBLE, Asset, Category
from ninja import Field, ModelSchema, Schema
from ninja.errors import HttpError
from pydantic import EmailStr
from pydantic.json_schema import SkipJsonSchema


class LicenseFilter(Enum):
    REMIXABLE = "REMIXABLE"
    ALL_CC = "ALL_CC"
    CREATIVE_COMMONS_BY_3_0 = "CREATIVE_COMMONS_BY_3_0"
    CREATIVE_COMMONS_BY_ND_3_0 = "CREATIVE_COMMONS_BY_ND_3_0"
    CREATIVE_COMMONS_BY_4_0 = "CREATIVE_COMMONS_BY_4_0"
    CREATIVE_COMMONS_BY_ND_4_0 = "CREATIVE_COMMONS_BY_ND_4_0"
    CREATIVE_COMMONS_BY = "CREATIVE_COMMONS_BY"
    CREATIVE_COMMONS_BY_ND = "CREATIVE_COMMONS_BY_ND"
    CREATIVE_COMMONS_0 = "CREATIVE_COMMONS_0"


class Complexity(Enum):
    COMPLEX = "COMPLEX"
    MEDIUM = "MEDIUM"
    SIMPLE = "SIMPLE"


class FormatFilter(Enum):
    TILT = "TILT"
    BLOCKS = "BLOCKS"
    GLTF = "GLTF"
    GLTF1 = "GLTF1"
    GLTF2 = "GLTF2"
    OBJ = "OBJ"
    FBX = "FBX"
    NO_TILT = "-TILT"
    NO_BLOCKS = "-BLOCKS"
    NO_GLTF = "-GLTF"
    NO_GLTF1 = "-GLTF1"
    NO_GLTF2 = "-GLTF2"
    NO_OBJ = "-OBJ"
    NO_FBX = "-FBX"


class SortDirection(Enum):
    DESC = auto()
    ASC = auto()


class Order(Enum):
    NEWEST = "NEWEST"
    OLDEST = "OLDEST"
    BEST = "BEST"
    CREATE_TIME_ASC = "CREATE_TIME"
    CREATE_TIME_DESC = "-CREATE_TIME"
    UPDATE_TIME_ASC = "UPDATE_TIME"
    UPDATE_TIME_DESC = "-UPDATE_TIME"
    TRIANGLE_COUNT_ASC = "TRIANGLE_COUNT"
    TRIANGLE_COUNT_DESC = "-TRIANGLE_COUNT"
    LIKED_TIME_ASC = "LIKED_TIME"
    LIKED_TIME_DESC = "-LIKED_TIME"
    LIKES_ASC = "LIKES"
    LIKES_DESC = "-LIKES"
    DOWNLOADS_ASC = "DOWNLOADS"
    DOWNLOADS_DESC = "-DOWNLOADS"
    DISPLAY_NAME_ASC = "DISPLAY_NAME"
    DISPLAY_NAME_DESC = "-DISPLAY_NAME"
    AUTHOR_NAME_ASC = "AUTHOR_NAME"
    AUTHOR_NAME_DESC = "-AUTHOR_NAME"


ORDER_FIELD_MAP = {
    "NEWEST": ("create_time", SortDirection.DESC),
    "OLDEST": ("create_time", SortDirection.ASC),
    "BEST": ("rank", SortDirection.DESC),
    "CREATE_TIME": ("create_time", SortDirection.DESC),
    "-CREATE_TIME": ("create_time", SortDirection.ASC),
    "UPDATE_TIME": ("update_time", SortDirection.DESC),
    "-UPDATE_TIME": ("update_time", SortDirection.ASC),
    "TRIANGLE_COUNT": ("triangle_count", SortDirection.DESC),
    "-TRIANGLE_COUNT": ("triangle_count", SortDirection.ASC),
    "LIKED_TIME": ("last_liked_time", SortDirection.DESC),
    "-LIKED_TIME": ("last_liked_time", SortDirection.ASC),
    "LIKES": ("likes", SortDirection.DESC),
    "-LIKES": ("likes", SortDirection.ASC),
    "DOWNLOADS": ("downloads", SortDirection.DESC),
    "-DOWNLOADS": ("downloads", SortDirection.ASC),
    "DISPLAY_NAME": ("name", SortDirection.DESC),
    "-DISPLAY_NAME": ("name", SortDirection.ASC),
    "AUTHOR_NAME": ("owner__displayname", SortDirection.DESC),
    "-AUTHOR_NAME": ("owner__displayname", SortDirection.ASC),
}


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
    email: Optional[EmailStr] = None
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

    @staticmethod
    def resolve_role(obj):
        return role_display.get(obj.role, None)

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
    formats: List[AssetFormat]
    displayName: Optional[str]
    visibility: str
    tags: List[str] = []
    isCurated: Optional[bool] = Field(None, alias=("curated"))
    thumbnail: Optional[Thumbnail]
    triangleCount: int = Field(..., alias=("triangle_count"))
    presentationParams: Optional[dict] = Field(None, alias=("presentation_params"))
    license: str
    licenseVersion: Optional[str]

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
        return f"{root_url}{reverse_lazy('api-1.0.0:asset_list')}/{obj.url}"

    @staticmethod
    def resolve_assetId(obj, context):
        return obj.url

    @staticmethod
    def resolve_formats(obj, context):
        return [
            f
            for f in obj.format_set.filter(
                role__in=API_DOWNLOAD_COMPATIBLE,
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


class AssetStateSchema(ModelSchema):
    class Config:
        model = Asset
        model_fields = ["state"]


class AssetPatchData(Schema):
    name: Optional[str]
    url: Optional[str]
    description: Optional[str]
    visibility: Optional[str]


class AssetFinalizeData(Schema):
    objPolyCount: int
    triangulatedObjPolyCount: int
    remixIds: Optional[List[str]] = None


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


class FilterBase(Schema):
    category: Optional[Category] = Field(default=None, example="ANIMALS")
    curated: bool = Field(default=False)
    format: Optional[List[FormatFilter]] = Field(default=None, description="Filter by format")
    keywords: Optional[str] = Field(default=None)
    name: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None)
    tag: List[str] = Field(default=None, alias="tag")
    orderBy: Optional[Order] = Field(
        # NOTE(james): Ninja doesn't use pydantic's `examples` list. Instead
        # it has `example`, which also accepts a list, but does not render it
        # nicely at all.
        # See: https://github.com/vitalik/django-ninja/issues/1342
        # example=[
        #     "LIKES (most first)",
        #     "-LIKES (least first)",
        # ],
        default=None,
    )
    order_by: SkipJsonSchema[Optional[Order]] = Field(default=None)  # For backwards compatibility
    maxComplexity: Optional[Complexity] = Field(default=None)
    triangleCountMin: Optional[int] = None
    triangleCountMax: Optional[int] = None
    zipArchiveUrl: Optional[str] = None


class AssetFilters(FilterBase):
    authorName: Optional[str] = None
    author_name: SkipJsonSchema[Optional[str]] = None
    license: Optional[LicenseFilter] = Field(default=None)


class UserAssetFilters(FilterBase):
    visibility: Optional[str] = None


def filter_license(filters) -> Q:
    q = Q()
    if filters.license:
        license_variant = filters.license
        if license_variant == LicenseFilter.CREATIVE_COMMONS_BY:
            variants = [
                "CREATIVE_COMMONS_BY_3_0",
                "CREATIVE_COMMONS_BY_4_0",
            ]
        elif license_variant == LicenseFilter.CREATIVE_COMMONS_BY_ND:
            variants = [
                "CREATIVE_COMMONS_BY_ND_3_0",
                "CREATIVE_COMMONS_BY_ND_4_0",
            ]
        elif license_variant == LicenseFilter.REMIXABLE:
            variants = [
                "CREATIVE_COMMONS_BY_3_0",
                "CREATIVE_COMMONS_BY_4_0",
                "CREATIVE_COMMONS_0",
            ]
        elif license_variant == LicenseFilter.ALL_CC:
            variants = [
                "CREATIVE_COMMONS_BY_3_0",
                "CREATIVE_COMMONS_BY_4_0",
                "CREATIVE_COMMONS_BY_ND_3_0",
                "CREATIVE_COMMONS_BY_ND_4_0",
                "CREATIVE_COMMONS_0",
            ]
        else:
            variants = None
        if variants is not None:
            q = Q(license__in=variants)
        else:
            q = Q(license__iexact=license_variant.value)
    return q


def filter_complexity(filters) -> Q:
    q = Q()

    # Ignore this filter if superceded by newer triangle count filters.
    if filters.triangleCountMin or filters.triangleCountMax:
        return q

    # See https://github.com/icosa-foundation/icosa-gallery/issues/107#issuecomment-2518016302
    complex = 50000000
    medium = 10000
    simple = 1000

    if filters.maxComplexity:
        if filters.maxComplexity == Complexity.COMPLEX:
            q = Q(triangle_count__lte=complex)
        if filters.maxComplexity == Complexity.MEDIUM:
            q = Q(triangle_count__lte=medium)
        if filters.maxComplexity == Complexity.SIMPLE:
            q = Q(triangle_count__lte=simple)
        q &= Q(triangle_count__gt=1)
    return q


def filter_triangle_count(filters) -> Q:
    q = Q()
    min = filters.triangleCountMin
    max = filters.triangleCountMax
    if min:
        q &= Q(triangle_count__gte=min)
    if max:
        q &= Q(triangle_count__lte=max)
    if min or max:
        q &= Q(triangle_count__gt=0)
    return q


def filter_zip_archive_url(filters) -> Q:
    q = Q()
    if filters.zipArchiveUrl:
        q &= Q(format__zip_archive_url__icontains=filters.zipArchiveUrl)
    return q


def get_keyword_q(filters) -> Q:
    q = Q()
    if filters.keywords:
        # The original API spec says "Multiple keywords should be separated
        # by spaces.". I believe this could be implemented better to allow
        # multi-word searches. Perhaps implemented in a different namespace,
        # such as `search=` and have multiple queries as `search=a&search=b`.
        keyword_list = filters.keywords.split(" ")
        if len(keyword_list) > 16:
            raise HttpError(400, "Exceeded 16 space-separated keywords.")
        for keyword in keyword_list:
            q &= Q(search_text__icontains=keyword)
    return q
