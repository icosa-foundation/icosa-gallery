from enum import Enum, auto
import re
from typing import List, Optional
from urllib.parse import unquote

from constance import config
from django.core.exceptions import ValidationError
from django.db.models import F, Q
from django.db.models.query import QuerySet
from ninja import Field, FilterSchema, Schema
from ninja.errors import HttpError
from pydantic import model_validator
from pydantic.json_schema import SkipJsonSchema

from icosa.api.exceptions import FilterException
from icosa.model_mixins import MOD_HIDDEN
from icosa.models import ALL_RIGHTS_RESERVED, PUBLIC, Asset


class FilterCategory(Enum):
    MISCELLANEOUS = "MISCELLANEOUS"
    ANIMALS = "ANIMALS"
    ARCHITECTURE = "ARCHITECTURE"
    ART = "ART"
    CULTURE = "CULTURE"
    EVENTS = "EVENTS"
    FOOD = "FOOD"
    HISTORY = "HISTORY"
    HOME = "HOME"
    NATURE = "NATURE"
    OBJECTS = "OBJECTS"
    PEOPLE = "PEOPLE"
    PLACES = "PLACES"
    SCIENCE = "SCIENCE"
    SPORTS = "SPORTS"
    TECH = "TECH"
    TRANSPORT = "TRANSPORT"
    TRAVEL = "TRAVEL"
    NONE = ""

    @classmethod
    def _missing_(cls, value):
        for member in cls:
            if member.name.lower() == str(value).lower():
                return member


class FilterComplexity(Enum):
    COMPLEX = "COMPLEX"
    MEDIUM = "MEDIUM"
    SIMPLE = "SIMPLE"


class FilterFormat(Enum):
    TILT = "TILT"
    BLOCKS = "BLOCKS"
    GLTF = "GLTF"
    GLTF1 = "GLTF1"
    GLTF2 = "GLTF2"
    OBJ = "OBJ"
    FBX = "FBX"
    VOX = "VOX"
    NO_TILT = "-TILT"
    NO_BLOCKS = "-BLOCKS"
    NO_GLTF = "-GLTF"
    NO_GLTF1 = "-GLTF1"
    NO_GLTF2 = "-GLTF2"
    NO_OBJ = "-OBJ"
    NO_FBX = "-FBX"
    NO_VOX = "-VOX"


class FilterLicense(Enum):
    REMIXABLE = "REMIXABLE"
    ALL_CC = "ALL_CC"
    CREATIVE_COMMONS_BY_3_0 = "CREATIVE_COMMONS_BY_3_0"
    CREATIVE_COMMONS_BY_ND_3_0 = "CREATIVE_COMMONS_BY_ND_3_0"
    CREATIVE_COMMONS_BY_4_0 = "CREATIVE_COMMONS_BY_4_0"
    CREATIVE_COMMONS_BY_SA_4_0 = "CREATIVE_COMMONS_BY_SA_4_0"
    CREATIVE_COMMONS_BY_ND_4_0 = "CREATIVE_COMMONS_BY_ND_4_0"
    CREATIVE_COMMONS_NC_4_0 = "CREATIVE_COMMONS_NC_4_0"
    CREATIVE_COMMONS_NC_SA_4_0 = "CREATIVE_COMMONS_NC_SA_4_0"
    CREATIVE_COMMONS_NC_ND_4_0 = "CREATIVE_COMMONS_NC_ND_4_0"
    CREATIVE_COMMONS_BY = "CREATIVE_COMMONS_BY"
    CREATIVE_COMMONS_BY_ND = "CREATIVE_COMMONS_BY_ND"
    CREATIVE_COMMONS_0 = "CREATIVE_COMMONS_0"


class FilterOrder(Enum):
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

    @classmethod
    def _missing_(cls, value):
        for member in cls:
            if member.name.lower() == str(value).lower():
                return member


class FilterVisibility(Enum):
    UNSPECIFIED = "UNSPECIFIED"
    PUBLISHED = "PUBLISHED"
    PRIVATE = "PRIVATE"
    UNLISTED = "UNLISTED"


class SortDirection(Enum):
    DESC = auto()
    ASC = auto()


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


class FiltersBase(FilterSchema):
    category: Optional[FilterCategory] = Field(default=None, example="ANIMALS", q="category__iexact")
    curated: Optional[bool] = Field(default=None)
    format: Optional[List[FilterFormat]] = Field(
        default=None, description="Filter by format", q="format__format_type__in"
    )
    keywords: Optional[str] = None
    name: Optional[str] = Field(default=None, q="name__icontains")
    description: Optional[str] = Field(default=None, q="description__icontains")
    tag: List[str] = Field(default=None, q="tags__name__in")
    triangleCountMin: Optional[int] = None
    triangleCountMax: Optional[int] = None
    maxComplexity: Optional[FilterComplexity] = Field(default=None)
    zipArchiveUrl: Optional[str] = Field(default=None, q="format__zip_archive_url__icontains")
    inCollection: Optional[bool] = None

    def filter_inCollection(self, value: bool) -> Q:
        q = Q(assetcollection__isnull=not value)
        return q

    def filter_category(self, value: FilterCategory) -> Q:
        POLY_CATEGORY_MAP = {
            "TECHNOLOGY": "TECH",
        }
        if value is not None:
            category_str = value.value.upper()
            category_str = POLY_CATEGORY_MAP.get(category_str, category_str)
            return Q(category__iexact=category_str)

    def filter_keywords(self, value: str) -> Q:
        q = Q()
        if value:
            # The original API spec says "Multiple keywords should be separated
            # by spaces.". I believe this could be implemented better to allow
            # multi-word searches. Perhaps implemented in a different namespace,
            # such as `search=` and have multiple queries as `search=a&search=b`.
            keyword_list = value.split(" ")
            if len(keyword_list) > 16:
                raise HttpError(400, "Exceeded 16 space-separated keywords.")
            for keyword in keyword_list:
                q &= Q(name__icontains=keyword)
        return q

    def filter_triangleCountMin(self, value: int) -> Q:
        return Q(triangle_count__gte=value) & Q(triangle_count__gte=0) if value else Q()

    def filter_triangleCountMax(self, value: int) -> Q:
        return Q(triangle_count__lte=value) & Q(triangle_count__gte=0) if value else Q()

    def filter_format(self, value: List[FilterFormat]) -> Q:
        positive_q = Q()
        negative_q = Q()
        if value:
            valid_q = False
            for format_type in value:
                # Reliant on the fact that each of FILTERABLE_FORMATS has an
                # associated has_<format_type> field in the db.
                format_value = format_type.value
                if format_type == FilterFormat.GLTF:
                    format_value = "GLTF_ANY"
                if format_type == FilterFormat.NO_GLTF:
                    format_value = "-GLTF_ANY"

                if format_value.startswith("-"):
                    negative_q |= Q(**{f"has_{format_value.lower()[1:]}": False})
                else:
                    positive_q |= Q(**{f"has_{format_value.lower()}": True})

                # TODO(james): valid_q should really check a list of valid types and break early if not in the list
                valid_q = True

            if not valid_q:
                choices = ", ".join([x.value for x in FilterFormat])
                raise FilterException(f"Format filter not one of {choices}")

        # The query we want is, for example Q: (AND: (OR: ('has_fbx', True), ('has_obj', True), ('has_gltf2', True)), (OR: ('has_blocks', False), ('has_tilt', False)))
        q = positive_q
        q &= negative_q
        return q

    def filter_maxComplexity(self, value: FilterComplexity) -> Q:
        q = Q()

        # TODO are ninja filters aware of each other? See https://stackoverflow.com/a/71917466
        # to modify a Q object after it is constructed.
        # Ignore this filter if superceded by newer triangle count filters.
        # if filters.triangleCountMin or filters.triangleCountMax:
        #     return q

        # See https://github.com/icosa-foundation/icosa-gallery/issues/107#issuecomment-2518016302
        complex = 50000000
        medium = 10000
        simple = 1000

        if value:
            if value == FilterComplexity.COMPLEX:
                q = Q(triangle_count__lte=complex)
            if value == FilterComplexity.MEDIUM:
                q = Q(triangle_count__lte=medium)
            if value == FilterComplexity.SIMPLE:
                q = Q(triangle_count__lte=simple)
            q &= Q(triangle_count__gt=1)
        return q

    @model_validator(mode="before")
    def remove_empty_strings(cls, values):
        # changing empty strings to None
        for f in cls.__pydantic_fields__:
            if getattr(values, f, None) == "":
                setattr(values, f, None)
        return values


class FiltersAsset(FiltersBase):
    authorName: Optional[str] = Field(default=None, q="owner__displayname__icontains")
    author_name: SkipJsonSchema[Optional[str]] = Field(default=None, q="owner__displayname__icontains")
    # NOTE: Not using icontains for owner__url. This would allow enumerating
    # users, which I'm not sure we want to allow just yet. displayname is
    # different because the search space is much larger.
    authorId: Optional[str] = Field(default=None, q="owner__url")
    author_id: SkipJsonSchema[Optional[str]] = Field(default=None, q="owner__url")
    license: Optional[FilterLicense] = Field(default=None)

    def filter_license(self, value: FilterLicense) -> Q:
        if value:
            if value == FilterLicense.CREATIVE_COMMONS_BY:
                variants = [
                    "CREATIVE_COMMONS_BY_3_0",
                    "CREATIVE_COMMONS_BY_4_0",
                ]
            elif value == FilterLicense.CREATIVE_COMMONS_BY_ND:
                variants = [
                    "CREATIVE_COMMONS_BY_ND_3_0",
                    "CREATIVE_COMMONS_BY_ND_4_0",
                ]
            elif value == FilterLicense.REMIXABLE:
                variants = [
                    "CREATIVE_COMMONS_BY_3_0",
                    "CREATIVE_COMMONS_BY_4_0",
                    "CREATIVE_COMMONS_0",
                ]
            elif value == FilterLicense.ALL_CC:
                variants = [
                    "CREATIVE_COMMONS_BY_3_0",
                    "CREATIVE_COMMONS_BY_4_0",
                    "CREATIVE_COMMONS_BY_SA_4_0",
                    "CREATIVE_COMMONS_BY_ND_3_0",
                    "CREATIVE_COMMONS_BY_ND_4_0",
                    "CREATIVE_COMMONS_NC_4_0",
                    "CREATIVE_COMMONS_NC_SA_4_0",
                    "CREATIVE_COMMONS_NC_ND_4_0",
                    "CREATIVE_COMMONS_0",
                ]
            else:
                variants = None

            return Q(license__in=variants) if variants else Q(license__iexact=value.value)
        else:
            return Q()


class FiltersUserAsset(FiltersBase):
    visibility: Optional[str] = None

    def filter_visibility(self, value: Optional[str]) -> Q:
        q = Q()
        if value:
            if value in [FilterVisibility.PRIVATE, FilterVisibility.UNLISTED]:
                q = Q(value.value)
            elif value == "PUBLISHED":
                q = Q(visibility=FilterVisibility.PUBLIC.value)
            elif value == "UNSPECIFIED":
                pass
        return q


class FiltersOrder(Schema):
    orderBy: Optional[FilterOrder] = Field(
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
    order_by: SkipJsonSchema[Optional[FilterOrder]] = Field(default=None)  # For backwards compatibility


class FiltersExpression(Schema):
    filter: Optional[str] = Field(
        default=None,
        description=(
            "OR groups of existing asset filters. Conditions within parentheses "
            "are ANDed and parenthesised groups separated by | are ORed, for "
            "example (authorId=alice)|(format=BLOCKS,curated=true)."
        ),
    )


FILTER_EXPRESSION_FIELD = "filter"
MAX_FILTER_GROUPS = 16
MAX_FILTER_CONDITIONS = 16


def _split_filter_conditions(group_text):
    conditions = []
    condition = []
    position = 0
    while position < len(group_text):
        character = group_text[position]
        if (
            character == "\\"
            and position + 1 < len(group_text)
            and group_text[position + 1] in {",", "\\"}
        ):
            condition.append(group_text[position + 1])
            position += 2
            continue
        if character == "," and re.match(
            r"\s*[A-Za-z][A-Za-z0-9_]*\s*=",
            group_text[position + 1 :],
        ):
            conditions.append("".join(condition))
            condition = []
        else:
            condition.append(character)
        position += 1
    conditions.append("".join(condition))
    return conditions


def parse_asset_filter_expression(expression):
    """Parse a shallow `(field=value,field=value)|(field=value)` expression."""
    if expression is None:
        return []
    if not isinstance(expression, str) or not expression.strip():
        raise ValueError("filter must be a non-empty string.")

    expression = expression.strip()
    groups = []
    position = 0
    while position < len(expression):
        if expression[position] != "(":
            raise ValueError("filter groups must start with '('.")

        close_position = expression.find(")", position + 1)
        if close_position == -1:
            raise ValueError("filter group is missing a closing ')'.")

        group_text = expression[position + 1 : close_position]
        if not group_text:
            raise ValueError("filter groups cannot be empty.")
        if "(" in group_text:
            raise ValueError("nested filter groups are not supported.")

        conditions = _split_filter_conditions(group_text)
        if len(conditions) > MAX_FILTER_CONDITIONS:
            raise ValueError(
                "filter groups cannot contain more than "
                f"{MAX_FILTER_CONDITIONS} conditions."
            )

        group_values = {}
        for condition in conditions:
            field_name, separator, value = condition.partition("=")
            field_name = field_name.strip()
            value = value.strip()
            if not separator or not field_name or not value:
                raise ValueError("filter conditions must use field=value syntax.")
            if field_name not in FiltersAsset.model_fields:
                raise ValueError(f"Unsupported filter field: {field_name}.")

            value = unquote(value)
            if field_name in group_values:
                current_value = group_values[field_name]
                if not isinstance(current_value, list):
                    current_value = [current_value]
                current_value.append(value)
                group_values[field_name] = current_value
            elif field_name in {"format", "tag"}:
                group_values[field_name] = [value]
            else:
                group_values[field_name] = value

        groups.append(FiltersAsset.model_validate(group_values))
        if len(groups) > MAX_FILTER_GROUPS:
            raise ValueError(
                f"filter cannot contain more than {MAX_FILTER_GROUPS} groups."
            )

        position = close_position + 1
        if position == len(expression):
            break
        if expression[position] != "|":
            raise ValueError("filter groups must be separated by '|'.")
        position += 1
        if position == len(expression):
            raise ValueError("filter cannot end with '|'.")

    return groups


def asset_filter_expression_to_q(expression):
    group_filters = parse_asset_filter_expression(expression)
    expression_q = Q()
    for group_filters_item in group_filters:
        expression_q |= group_filters_item.get_filter_expression()
    return expression_q


def validate_asset_query_parameters(query_parameters):
    if not isinstance(query_parameters, dict):
        raise ValidationError(
            {"query_parameters": "Query parameters must be a JSON object."}
        )

    allowed_fields = (
        set(FiltersAsset.model_fields)
        | set(FiltersOrder.model_fields)
        | {FILTER_EXPRESSION_FIELD}
    )
    unknown_fields = set(query_parameters) - allowed_fields
    if unknown_fields:
        field_names = ", ".join(sorted(unknown_fields))
        raise ValidationError(
            {"query_parameters": f"Unsupported query parameter(s): {field_names}."}
        )

    try:
        filters = FiltersAsset.model_validate(query_parameters)
        order = FiltersOrder.model_validate(query_parameters)
        expression_q = asset_filter_expression_to_q(
            query_parameters.get(FILTER_EXPRESSION_FIELD)
        )
    except ValueError as error:
        raise ValidationError({"query_parameters": str(error)}) from error
    return filters, order, expression_q


def assets_from_query_parameters(query_parameters):
    filters, order, expression_q = validate_asset_query_parameters(query_parameters)
    return get_public_assets(filters, order, expression_q=expression_q)


def get_public_assets(filters, order, filter_expression=None, expression_q=None):
    expression_q = expression_q or Q()
    if filter_expression is not None:
        try:
            expression_q &= asset_filter_expression_to_q(filter_expression)
        except ValueError as error:
            raise HttpError(400, str(error)) from error
    excluded = Q(license__isnull=True) | Q(license=ALL_RIGHTS_RESERVED)
    if config.HIDE_REPORTED_ASSETS:
        excluded |= Q(moderation_state__in=MOD_HIDDEN)
    return filter_and_sort_assets(
        filters,
        order,
        assets=Asset.objects.filter(visibility=PUBLIC),
        inc_q=expression_q,
        exc_q=excluded,
    )


def sort_assets(key: FilterOrder, assets: QuerySet[Asset]) -> QuerySet[Asset]:
    (sort_key, sort_direction) = ORDER_FIELD_MAP.get(key.value)

    if sort_direction == SortDirection.DESC:
        assets = assets.order_by(F(sort_key).desc(nulls_last=True))
    if sort_direction == SortDirection.ASC:
        assets = assets.order_by(F(sort_key).asc(nulls_last=True))
    return assets


def filter_and_sort_assets(
    filters: FilterSchema,
    order: Schema,
    assets: QuerySet[Asset] = Asset.objects.all(),
    inc_q: Q = Q(),
    exc_q: Q = Q(),
) -> QuerySet[Asset]:
    inc_q &= filters.get_filter_expression()
    try:
        assets = (
            assets.filter(inc_q)
            .exclude(exc_q)
            .exclude(moderation_state__in=MOD_HIDDEN)
            .select_related("owner")
            .prefetch_related(
                "resource_set",
                "format_set",
                "tags",
            )
            .distinct()
        )

        order_by = order.orderBy or order.order_by or None
        if order_by is not None:
            assets = sort_assets(order_by, assets)
        return assets
    except FilterException as err:
        raise HttpError(400, f"{err}")
