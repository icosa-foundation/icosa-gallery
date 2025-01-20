from django.contrib import admin
from django.urls import reverse
from django.utils.safestring import mark_safe
from icosa.models import (
    Asset,
    AssetOwner,
    DeviceCode,
    HiddenMediaFileLog,
    MastheadSection,
    Oauth2Client,
    Oauth2Code,
    Oauth2Token,
    PolyFormat,
    PolyResource,
    Tag,
)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    pass


@admin.register(PolyResource)
class PolyResourceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "asset",
        "file",
        "is_root",
        "contenttype",
    )

    list_filter = (
        "is_root",
        "contenttype",
    )
    search_fields = ("file",)
    raw_id_fields = [
        "asset",
        "format",
    ]


class PolyFormatInline(admin.TabularInline):
    extra = 0
    model = PolyFormat
    show_change_link = True

    fields = (
        "format_type",
        "archive_url",
        "role",
    )


class PolyResourceInline(admin.TabularInline):
    extra = 0
    model = PolyResource

    fields = (
        "is_root",
        "file",
        "external_url",
    )


@admin.register(PolyFormat)
class PolyFormatAdmin(admin.ModelAdmin):
    list_display = (
        "asset",
        "format_type",
    )

    inlines = (PolyResourceInline,)
    list_filter = ("role",)
    raw_id_fields = ["asset"]


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "_thumbnail_image",
        "url",
        "owner",
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
        "owner__displayname",
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
        ("thumbnail", admin.EmptyFieldListFilter),
        "license",
        "category",
        "state",
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
        "last_reported_by",
        "last_reported_time",
    )

    def _thumbnail_image(self, obj):
        html = ""

        if obj.thumbnail:
            html = f"""
<a href="{obj.get_absolute_url()}">
<img src="{obj.thumbnail.url}" width="150" loading="lazy">
</a>
            """
        else:
            html = f"""
<a href="{obj.get_absolute_url()}">View on site</a>
            """

        return mark_safe(html)

    _thumbnail_image.short_description = "Thumbnail"
    _thumbnail_image.allow_tags = True

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
    inlines = (PolyFormatInline,)
    raw_id_fields = ["owner"]


@admin.register(DeviceCode)
class DeviceCodeAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "devicecode",
        "expiry",
    )

    raw_id_fields = ["user"]

    date_hierarchy = "expiry"


class UserAssetLikeInline(admin.TabularInline):
    extra = 0
    model = AssetOwner.likes.through
    raw_id_fields = ["asset"]


@admin.register(AssetOwner)
class AssetOwnerAdmin(admin.ModelAdmin):
    list_display = (
        "displayname",
        "email",
        "url",
        "_django_user_link",
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
    )
    inlines = (UserAssetLikeInline,)
    raw_id_fields = ["django_user"]

    def _django_user_link(self, obj):
        html = "-"
        if obj.django_user:
            change_url = reverse(
                "admin:auth_user_change",
                args=(obj.django_user.id,),
            )
            html = f"""
<a href="{change_url}">{obj.django_user}</a>
"""

        return mark_safe(html)

    _django_user_link.short_description = "Django User"
    _django_user_link.allow_tags = True


@admin.register(MastheadSection)
class MastheadSectionAdmin(admin.ModelAdmin):
    list_display = (
        "_thumbnail_image",
        "asset",
        "headline_text",
        "sub_text",
    )

    def _thumbnail_image(self, obj):
        html = ""

        if obj.image:
            html = f"""
<img src="{obj.image.url}" width="150" loading="lazy">
            """
        else:
            html = ""

        return mark_safe(html)

    _thumbnail_image.short_description = "Thumbnail"
    _thumbnail_image.allow_tags = True


@admin.register(HiddenMediaFileLog)
class HiddenMediaFileLogAdmin(admin.ModelAdmin):
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
class Oauth2ClientAdmin(admin.ModelAdmin):
    pass


@admin.register(Oauth2Code)
class Oauth2CodeAdmin(admin.ModelAdmin):
    pass


@admin.register(Oauth2Token)
class Oauth2TokenAdmin(admin.ModelAdmin):
    pass
