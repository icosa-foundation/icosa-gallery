from import_export.admin import ExportMixin

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as OriginalUserAdmin
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.safestring import mark_safe
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from icosa.models import (
    Asset,
    AssetCollection,
    AssetCollectionAsset,
    AssetOwner,
    BulkSaveLog,
    DeviceCode,
    Format,
    FormatRoleLabel,
    HiddenMediaFileLog,
    MastheadSection,
    Oauth2Client,
    Oauth2Code,
    Oauth2Token,
    Resource,
    Tag,
    UserLike,
)

User = get_user_model()


@admin.register(Tag)
class TagAdmin(ExportMixin, admin.ModelAdmin):
    search_fields = ("name",)


@admin.register(Resource)
class ResourceAdmin(ExportMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "asset",
        "format",
        "file",
        "contenttype",
    )

    list_filter = ("contenttype", "format__format_type")
    search_fields = ("file",)
    raw_id_fields = [
        "asset",
        "format",
    ]


class FormatInline(admin.TabularInline):
    extra = 0
    model = Format
    show_change_link = True
    readonly_fields = ("is_preferred_for_gallery_viewer",)

    fields = (
        "format_type",
        "zip_archive_url",
        "role",
        "is_preferred_for_gallery_viewer",
        "is_preferred_for_download",
    )


class ResourceInline(admin.TabularInline):
    extra = 0
    model = Resource

    fields = (
        "file",
        "external_url",
    )


@admin.register(Format)
class FormatAdmin(ExportMixin, admin.ModelAdmin):
    list_display = (
        "asset",
        "format_type",
    )

    inlines = (ResourceInline,)
    list_filter = (
        "role",
        "format_type",
        "is_preferred_for_gallery_viewer",
        "is_preferred_for_download",
    )
    raw_id_fields = [
        "asset",
        "root_resource",
    ]


@admin.register(FormatRoleLabel)
class FormatRoleLabelAdmin(admin.ModelAdmin):
    list_display = (
        "role_text",
        "label",
    )

    list_filter = (
        "role_text",
        "label",
    )


@admin.register(Asset)
class AssetAdmin(ExportMixin, admin.ModelAdmin):
    actions = ["generate_thumbnails_for_selected"]

    list_display = (
        "name",
        "display_thumbnail",
        "display_owner",
        "description",
        "visibility",
        "curated",
        "rank",
        "is_viewer_compatible",
        "category",
        "state",
    )
    search_fields = (
        "name",
        "url",
        "tags",
        "display_owner",
        "description",
    )
    list_filter = (
        "visibility",
        "curated",
        "imported_from",
        "is_viewer_compatible",
        "has_tilt",
        "has_blocks",
        "has_gltf1",
        "has_gltf2",
        "has_gltf_any",
        "has_obj",
        "has_fbx",
        "has_vox",
        ("thumbnail", admin.EmptyFieldListFilter),
        "license",
        "category",
        "state",
        "last_reported_time",
    )
    readonly_fields = (
        "rank",
        "search_text",
        "is_viewer_compatible",
        "has_tilt",
        "has_blocks",
        "has_gltf1",
        "has_gltf2",
        "has_gltf_any",
        "has_obj",
        "has_fbx",
        "has_vox",
        "last_reported_by",
        "last_reported_time",
    )

    def display_thumbnail(self, obj):
        html = f"{obj.url}"
        if obj.thumbnail:
            html = f"<img src='{obj.thumbnail.url}' width='150' loading='lazy'><br>{html}"
        html = f"<a href='{obj.get_absolute_url()}'>{html}</a>"
        return mark_safe(html)

    display_thumbnail.short_description = "View"
    display_thumbnail.allow_tags = True
    display_thumbnail.admin_order_field = "url"

    def display_owner(self, obj):
        html = "-"
        if obj.owner:
            change_url = reverse("admin:icosa_assetowner_change", args=(obj.owner.id,))
            html = f"<a href='{change_url}'>{obj.owner.displayname}</a>"
        return mark_safe(html)

    display_owner.short_description = "Owner"

    search_fields = (
        "name",
        "url",
        "owner__displayname",
    )

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.instance.update_search_text()
        form.instance.save()

    filter_horizontal = ("tags",)
    inlines = (FormatInline,)
    raw_id_fields = [
        "owner",
        "preferred_viewer_format_override",
    ]

    def get_urls(self):
        """Add custom admin URLs for batch thumbnail generation."""
        urls = super().get_urls()
        custom_urls = [
            path(
                "batch-thumbnail-generator/",
                self.admin_site.admin_view(self.batch_thumbnail_generator_view),
                name="icosa_asset_batch_thumbnail_generator",
            ),
            path(
                "upload-thumbnail/<int:asset_id>/",
                self.admin_site.admin_view(self.upload_thumbnail_view),
                name="icosa_asset_upload_thumbnail",
            ),
        ]
        return custom_urls + urls

    def batch_thumbnail_generator_view(self, request):
        """Custom admin view for batch thumbnail generation."""
        # Get pre-selected asset IDs from session (if coming from admin action)
        selected_asset_ids = request.session.pop("thumbnail_gen_asset_ids", None)

        # Fetch assets
        from django.db.models import Q

        if selected_asset_ids:
            # Fetch specific selected assets
            assets_queryset = Asset.objects.filter(id__in=selected_asset_ids)
        else:
            # Fetch all assets missing thumbnails
            query = Q(thumbnail="") | Q(thumbnail__isnull=True)
            query &= Q(is_viewer_compatible=True)
            query &= Q(state__in=["ACTIVE", ""])
            assets_queryset = Asset.objects.filter(query)

        # Get assets with related data (limit to 20 for memory/rate limit safety)
        assets = (
            assets_queryset.select_related("owner")
            .prefetch_related("format_set__resource_set")
            .order_by("-create_time")[:20]
        )

        # Format assets for JSON
        assets_data = []
        for asset in assets:
            formats = []
            for fmt in asset.format_set.all():
                root_url = None
                if fmt.root_resource:
                    root_url = fmt.root_resource.url
                elif fmt.zip_archive_url:
                    root_url = fmt.zip_archive_url

                formats.append({
                    "format_type": fmt.format_type,
                    "root_url": root_url,
                    "is_preferred": fmt.is_preferred_for_gallery_viewer,
                })

            assets_data.append({
                "id": asset.id,
                "url": asset.url,
                "name": asset.name or "Untitled",
                "owner_displayname": asset.owner.displayname if asset.owner else None,
                "formats": formats,
            })

        context = {
            **self.admin_site.each_context(request),
            "title": "Batch Thumbnail Generator",
            "opts": self.model._meta,
            "selected_asset_ids": selected_asset_ids,
            "assets_json": assets_data,
        }
        return render(request, "admin/asset_batch_thumbnail_generator.html", context)

    def upload_thumbnail_view(self, request, asset_id):
        """Handle thumbnail upload for an asset."""
        if request.method != "POST":
            return JsonResponse({"error": "POST required"}, status=405)

        try:
            asset = Asset.objects.get(id=asset_id)
        except Asset.DoesNotExist:
            return JsonResponse({"error": "Asset not found"}, status=404)

        # Get the base64 thumbnail from POST data
        import json

        try:
            data = json.loads(request.body)
            thumbnail_base64 = data.get("thumbnail_base64")
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        if not thumbnail_base64:
            return JsonResponse({"error": "No thumbnail data provided"}, status=400)

        # Convert base64 to image and save
        from icosa.helpers.file import b64_to_img, validate_mime
        from icosa.models.common import VALID_THUMBNAIL_MIME_TYPES

        try:
            thumbnail_file = b64_to_img(thumbnail_base64)

            # Validate MIME type
            thumbnail_file.seek(0)
            mime_type = validate_mime(thumbnail_file.read())
            thumbnail_file.seek(0)

            if mime_type not in VALID_THUMBNAIL_MIME_TYPES:
                return JsonResponse(
                    {"error": f"Invalid image type: {mime_type}"}, status=400
                )

            # Save to both thumbnail and preview_image
            asset.thumbnail.save(
                f"thumbnail_{asset.url}.jpg", thumbnail_file, save=False
            )
            asset.preview_image.save(
                f"preview_{asset.url}.jpg", thumbnail_file, save=False
            )
            asset.thumbnail_contenttype = mime_type
            asset.save()

            return JsonResponse(
                {
                    "success": True,
                    "thumbnail_url": asset.thumbnail.url,
                    "asset_url": asset.url,
                }
            )

        except Exception as e:
            return JsonResponse({"error": f"Failed to save thumbnail: {str(e)}"}, status=500)

    @admin.action(description="Generate thumbnails (opens batch generator)")
    def generate_thumbnails_for_selected(self, request, queryset):
        """Admin action to generate thumbnails for selected assets."""
        # Store selected asset IDs in session
        asset_ids = list(queryset.values_list("id", flat=True))
        request.session["thumbnail_gen_asset_ids"] = asset_ids

        # Redirect to batch thumbnail generator
        from django.shortcuts import redirect

        return redirect("admin:icosa_asset_batch_thumbnail_generator")

    def changelist_view(self, request, extra_context=None):
        """Override to add custom context to the changelist view."""
        extra_context = extra_context or {}
        extra_context["batch_thumbnail_generator_url"] = reverse(
            "admin:icosa_asset_batch_thumbnail_generator"
        )
        return super().changelist_view(request, extra_context=extra_context)


class AssetCollectionAssetInline(admin.TabularInline):
    extra = 0
    model = AssetCollectionAsset

    raw_id_fields = [
        "asset",
    ]

    fields = (
        "asset",
        "order",
    )


@admin.register(AssetCollection)
class AssetCollectionAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "user",
        "create_time",
        "display_asset_count",
        "visibility",
    )

    search_fields = (
        "name",
        "url",
        "user__displayname",
    )

    inlines = (AssetCollectionAssetInline,)

    list_filter = ("visibility",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(asset_count=Count("assets"))

    def display_asset_count(self, obj):
        return obj.assets.count()

    display_asset_count.short_description = "Assets"
    display_asset_count.admin_order_field = "asset_count"


@admin.register(DeviceCode)
class DeviceCodeAdmin(ExportMixin, admin.ModelAdmin):
    list_display = (
        "user",
        "devicecode",
        "expiry",
    )

    raw_id_fields = ["user"]

    date_hierarchy = "expiry"


@admin.register(AssetOwner)
class AssetOwnerAdmin(ExportMixin, admin.ModelAdmin):
    list_display = (
        "displayname",
        "email",
        "url",
        "display_asset_count",
        "display_django_user",
    )

    search_fields = (
        "displayname",
        "email",
        "url",
        "id",
    )
    list_filter = (
        "imported",
        ("email", admin.EmptyFieldListFilter),
        ("django_user", admin.EmptyFieldListFilter),
        "is_claimed",
        "disable_profile",
    )
    raw_id_fields = [
        "django_user",
        "merged_with",
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(asset_count=Count("asset"))

    def display_asset_count(self, obj):
        lister_url = f"{reverse('admin:icosa_asset_changelist')}?owner__id__exact={obj.id}"
        return mark_safe(f"<a href='{lister_url}'>{obj.asset_set.count()}</a>")

    display_asset_count.short_description = "Assets"
    display_asset_count.admin_order_field = "asset_count"

    def display_django_user(self, obj):
        html = "-"
        if obj.django_user:
            change_url = reverse(
                "admin:icosa_user_change",
                args=(obj.django_user.id,),
            )
            html = f"<a href='{change_url}'>{obj.django_user}</a>"

        return mark_safe(html)

    display_django_user.short_description = "Django User"


@admin.register(MastheadSection)
class MastheadSectionAdmin(ExportMixin, admin.ModelAdmin):
    list_display = (
        "display_thumbnail",
        "asset",
        "headline_text",
        "sub_text",
    )

    def display_thumbnail(self, obj):
        if obj.image:
            html = f"<img src='{obj.image.url}' width='150' loading='lazy'>"
        else:
            html = ""
        return mark_safe(html)

    display_thumbnail.short_description = "Thumbnail"
    display_thumbnail.allow_tags = True


@admin.register(BulkSaveLog)
class BulkSaveLogAdmin(admin.ModelAdmin):
    list_display = ("create_time", "finish_status")
    readonly_fields = (
        "create_time",
        "update_time",
        "finish_time",
        "finish_status",
    )

    list_filter = ("finish_status",)


@admin.register(HiddenMediaFileLog)
class HiddenMediaFileLogAdmin(ExportMixin, admin.ModelAdmin):
    list_display = (
        "original_asset_id",
        "file_name",
        "deleted_from_source",
    )
    search_fields = (
        "original_asset_id",
        "file_name",
    )
    readonly_fields = (
        "original_asset_id",
        "file_name",
        "deleted_from_source",
    )

    list_filter = ("deleted_from_source",)

    def has_delete_permission(self, request, obj=None):
        # Disable delete from admin UI, but not the shell or other code.
        return False


@admin.register(Oauth2Client)
class Oauth2ClientAdmin(ExportMixin, admin.ModelAdmin):
    pass


@admin.register(Oauth2Code)
class Oauth2CodeAdmin(ExportMixin, admin.ModelAdmin):
    pass


@admin.register(Oauth2Token)
class Oauth2TokenAdmin(ExportMixin, admin.ModelAdmin):
    pass


class UserLikeInline(admin.TabularInline):
    extra = 0
    model = UserLike
    raw_id_fields = ["asset"]


class UserAdmin(OriginalUserAdmin):
    model = User
    actions = [
        "make_not_staff",
    ]

    list_display = (
        "username",
        "display_owners",
        "email",
        "date_joined",
        "last_login",
        "is_staff",
    )

    search_fields = (
        "displayname",
        "username",
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "id",
    )

    list_filter = (
        "is_staff",
        "is_superuser",
        "is_active",
        "date_joined",
        "last_login",
    )

    fieldsets = OriginalUserAdmin.fieldsets + ((None, {"fields": ("displayname",)}),)

    inlines = (UserLikeInline,)

    def display_owners(self, obj):
        if obj.assetowner_set.exists():
            if obj.assetowner_set.count() > 1:
                url = f"{reverse('admin:icosa_assetowner_changelist')}?django_user__id__exact={obj.id}"
                link_str = ", ".join([x.displayname for x in obj.assetowner_set.all()])
            else:
                owner = obj.assetowner_set.first()
                url = f"{reverse('admin:icosa_assetowner_change', args=[owner.pk])}"
                link_str = owner.displayname
            link_html = f"<a href='{url}'>{link_str}</a>"
        else:
            link_html = ""
        return mark_safe(link_html)

    display_owners.short_description = "Asset Owners"
    display_owners.admin_order_field = "assetowner__displayname"

    @admin.action(description="Mark selected users as not staff")
    def make_not_staff(modeladmin, request, queryset):
        queryset.update(is_staff=False)


admin.site.register(User, UserAdmin)
