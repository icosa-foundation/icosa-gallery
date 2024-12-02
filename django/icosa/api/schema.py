from datetime import datetime
from typing import List, Literal, Optional

from icosa.models import API_DOWNLOAD_COMPATIBLE, Asset
from ninja import Field, ModelSchema, Schema
from ninja.errors import HttpError
from pydantic import EmailStr

from django.db.models import Q
from django.urls import reverse_lazy


class LoginToken(Schema):
    access_token: str
    token_type: str


class FullUserSchema(Schema):
    id: int
    url: str
    email: EmailStr
    displayName: str = Field(None, alias="displayname")
    description: str


class PatchUserSchema(Schema):
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


class AssetFormat(Schema):
    root: Optional[AssetResource]
    resources: Optional[List[AssetResource]]
    formatComplexity: FormatComplexity
    formatType: str

    @staticmethod
    def resolve_root(obj):
        return obj.polyresource_set.filter(is_root=True).first()

    @staticmethod
    def resolve_resources(obj):
        return obj.polyresource_set.filter(is_root=False)

    @staticmethod
    def resolve_formatType(obj):
        return obj.format_type

    @staticmethod
    def resolve_formatComplexity(obj):
        format_complexity = {
            "triangleCount": obj.triangle_count,
            "lodHint": obj.lod_hint,
        }
        return format_complexity


class _DBAsset(ModelSchema):
    authorId: str = Field(None, alias=("owner.url"))
    authorName: str
    # authorUrl: str # TODO create API endpoints for user
    name: str
    description: Optional[str]
    createTime: datetime = Field(..., alias=("create_time"))
    updateTime: datetime = Field(..., alias=("update_time"))
    url: Optional[str]
    assetId: str
    formats: List[AssetFormat]
    displayName: Optional[str]
    visibility: str
    tags: List[str] = []
    isCurated: Optional[bool] = Field(None, alias=("curated"))
    thumbnail: Optional[Thumbnail]
    presentationParams: Optional[dict] = Field(
        None, alias=("presentation_params")
    )
    license: Optional[str] = None

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
        return obj.get_license_display

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
            for f in obj.polyformat_set.filter(
                role__in=API_DOWNLOAD_COMPATIBLE
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


class AssetSchemaIn(_DBAsset):
    pass


class AssetSchemaOut(_DBAsset):
    # TODO: If this doesn't differ from AssetSchemaIn, we should probably
    # remove inheritence.
    pass


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
    author_name: Optional[str] = (
        None  # The name of the author/owner of the resource.
    )
    author_url: Optional[str] = (
        None  # A URL for the author/owner of the resource.
    )
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
    category: Optional[str] = None
    curated: bool = False
    format: List[str] = Field(None, alias="format")
    keywords: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    tag: List[str] = Field(None, alias="tag")
    orderBy: Optional[str] = None
    order_by: Optional[str] = None


class AssetFilters(FilterBase):
    authorName: Optional[str] = None
    author_name: Optional[str] = None
    license: Optional[str] = None


class UserAssetFilters(FilterBase):
    visibility: Optional[str] = None


# TODO(james): use more of these abstractions
def filter_license(query_string: str) -> Q:
    license_str = query_string.upper()
    if license_str == "CREATIVE_COMMONS_BY":
        variants = [
            "CREATIVE_COMMONS_BY_3_0",
            "CREATIVE_COMMONS_BY_4_0",
        ]
    elif license_str == "CREATIVE_COMMONS_BY_ND":
        variants = [
            "CREATIVE_COMMONS_BY_ND_3_0",
            "CREATIVE_COMMONS_BY_ND_4_0",
        ]
    else:
        variants = None
    if variants is not None:
        q = Q(license__in=variants)
    else:
        q = Q(license__iexact=license_str)
    return q


def get_keyword_q(filters):
    keyword_q = Q()
    if filters.keywords:
        # The original API spec says "Multiple keywords should be separated
        # by spaces.". I believe this could be implemented better to allow
        # multi-word searches. Perhaps implemented in a different namespace,
        # such as `search=` and have multiple queries as `search=a&search=b`.
        keyword_list = filters.keywords.split(" ")
        if len(keyword_list) > 16:
            raise HttpError(400, "Exceeded 16 space-separated keywords.")
        for keyword in keyword_list:
            keyword_q &= Q(search_text__icontains=keyword)
    return keyword_q
