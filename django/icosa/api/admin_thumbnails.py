"""
Admin API endpoints for batch thumbnail generation.
"""
from typing import List

from django.db.models import Q
from django.http import HttpRequest
from icosa.helpers.file import b64_to_img, validate_mime
from icosa.jwt.authentication import JWTAuth
from icosa.models import Asset
from icosa.models.common import VALID_THUMBNAIL_MIME_TYPES
from ninja import Router, Schema
from ninja.errors import HttpError

router = Router()


class ThumbnailAssetSchema(Schema):
    """Schema for assets needing thumbnails."""

    id: int
    url: str
    name: str
    owner_displayname: str | None
    formats: List[dict]


class BatchThumbnailListResponse(Schema):
    """Response for listing assets without thumbnails."""

    assets: List[ThumbnailAssetSchema]
    total_count: int
    has_more: bool


class UploadThumbnailRequest(Schema):
    """Request schema for uploading a generated thumbnail."""

    thumbnail_base64: str


@router.get(
    "/assets/missing-thumbnails",
    response=BatchThumbnailListResponse,
    auth=JWTAuth(),
)
def list_assets_missing_thumbnails(
    request: HttpRequest,
    limit: int = 50,
    offset: int = 0,
    viewer_compatible_only: bool = True,
    asset_ids: str = None,
):
    """
    Get a list of assets that are missing thumbnails.

    Only accessible to staff users. Returns assets in batches for processing.

    Args:
        limit: Number of assets to return (max 100)
        offset: Starting offset for pagination
        viewer_compatible_only: Only return assets that can be rendered in the viewer
        asset_ids: Optional comma-separated list of specific asset IDs to fetch
    """
    # Check if user is staff
    if not request.auth.is_staff:
        raise HttpError(403, "Admin access required")

    # Limit the max batch size
    limit = min(limit, 100)

    # Build query
    if asset_ids:
        # Fetch specific assets by ID
        id_list = [int(id.strip()) for id in asset_ids.split(",") if id.strip()]
        query = Q(id__in=id_list)
    else:
        # Build query for assets without thumbnails
        query = Q(thumbnail="") | Q(thumbnail__isnull=True)

        if viewer_compatible_only:
            query &= Q(is_viewer_compatible=True)

        # Also filter out assets in certain states
        query &= Q(state__in=["ACTIVE", ""])

    # Get assets
    assets_queryset = (
        Asset.objects.filter(query)
        .select_related("owner")
        .prefetch_related("format_set__resource_set")
        .order_by("-create_time")
    )

    total_count = assets_queryset.count()
    assets = list(assets_queryset[offset : offset + limit])

    # Format response
    asset_data = []
    for asset in assets:
        # Get format information for rendering
        formats = []
        for fmt in asset.format_set.all():
            # Get the root resource URL
            root_url = None
            if fmt.root_resource:
                root_url = fmt.root_resource.get_url()
            elif fmt.zip_archive_url:
                root_url = fmt.zip_archive_url

            formats.append({
                "format_type": fmt.format_type,
                "root_url": root_url,
                "is_preferred": fmt.is_preferred_for_gallery_viewer,
            })

        asset_data.append(
            ThumbnailAssetSchema(
                id=asset.id,
                url=asset.url,
                name=asset.name or "Untitled",
                owner_displayname=asset.owner.displayname if asset.owner else None,
                formats=formats,
            )
        )

    return BatchThumbnailListResponse(
        assets=asset_data,
        total_count=total_count,
        has_more=(offset + limit) < total_count,
    )


@router.post(
    "/assets/{asset_id}/thumbnail",
    auth=JWTAuth(),
)
def upload_generated_thumbnail(
    request: HttpRequest,
    asset_id: int,
    payload: UploadThumbnailRequest,
):
    """
    Upload a generated thumbnail for an asset.

    Only accessible to staff users. Accepts a base64-encoded image.

    Args:
        asset_id: The ID of the asset
        payload: Request containing base64 thumbnail image
    """
    # Check if user is staff
    if not request.auth.is_staff:
        raise HttpError(403, "Admin access required")

    # Get the asset
    try:
        asset = Asset.objects.get(id=asset_id)
    except Asset.DoesNotExist:
        raise HttpError(404, "Asset not found")

    try:
        # Convert base64 to image file
        thumbnail_file = b64_to_img(payload.thumbnail_base64)

        # Validate MIME type
        thumbnail_file.seek(0)
        mime_type = validate_mime(thumbnail_file.read())
        thumbnail_file.seek(0)

        if mime_type not in VALID_THUMBNAIL_MIME_TYPES:
            raise HttpError(
                400,
                f"Invalid image type: {mime_type}. Must be PNG or JPEG.",
            )

        # Save to both thumbnail and preview_image
        asset.thumbnail.save(f"thumbnail_{asset.url}.jpg", thumbnail_file, save=False)
        asset.preview_image.save(
            f"preview_{asset.url}.jpg", thumbnail_file, save=False
        )
        asset.thumbnail_contenttype = mime_type
        asset.save()

        return {
            "success": True,
            "thumbnail_url": asset.thumbnail.url,
            "asset_url": asset.url,
        }

    except Exception as e:
        raise HttpError(500, f"Failed to save thumbnail: {str(e)}")
