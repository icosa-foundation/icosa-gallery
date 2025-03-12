from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as OriginalUserAdmin
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils.safestring import mark_safe
from icosa.models import (
    Asset,
    AssetOwner,
    BulkSaveLog,
    DeviceCode,
    Format,
    HiddenMediaFileLog,
    MastheadSection,
    Oauth2Client,
    Oauth2Code,
    Oauth2Token,
    Resource,
    Tag,
)
from import_export.admin import ExportActionMixin, ImportExportModelAdmin


@admin.register(Tag)
class TagAdmin(ImportExportModelAdmin, ExportActionMixin):
    search_fields = ("name",)


@admin.register(Resource)
class ResourceAdmin(ImportExportModelAdmin, ExportActionMixin):
    list_display = (
        "id",
        "asset",
        "file",
        "contenttype",
    )

    list_filter = ("contenttype",)
    search_fields = ("file",)
    raw_id_fields = [
        "asset",
        "format",
    ]


class FormatInline(admin.TabularInline):
    extra = 0
    model = Format
    show_change_link = True

    fields = (
        "format_type",
        "archive_url",
        "role",
    )


class ResourceInline(admin.TabularInline):
    extra = 0
    model = Resource

    fields = (
        "file",
        "external_url",
    )


@admin.register(Format)
class FormatAdmin(ImportExportModelAdmin, ExportActionMixin):
    list_display = (
        "asset",
        "format_type",
    )

    inlines = (ResourceInline,)
    list_filter = (
        "role",
        "format_type",
    )
    raw_id_fields = [
        "asset",
        "root_resource",
    ]


@admin.register(Asset)
class AssetAdmin(ImportExportModelAdmin, ExportActionMixin):
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
    inlines = (FormatInline,)
    raw_id_fields = ["owner"]


@admin.register(DeviceCode)
class DeviceCodeAdmin(ImportExportModelAdmin, ExportActionMixin):
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
class AssetOwnerAdmin(ImportExportModelAdmin, ExportActionMixin):
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
    raw_id_fields = [
        "django_user",
        "merged_with",
    ]

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
class MastheadSectionAdmin(ImportExportModelAdmin, ExportActionMixin):
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
class HiddenMediaFileLogAdmin(ImportExportModelAdmin, ExportActionMixin):
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
class Oauth2ClientAdmin(ImportExportModelAdmin, ExportActionMixin):
    pass


@admin.register(Oauth2Code)
class Oauth2CodeAdmin(ImportExportModelAdmin, ExportActionMixin):
    pass


@admin.register(Oauth2Token)
class Oauth2TokenAdmin(ImportExportModelAdmin, ExportActionMixin):
    pass


class UserAdmin(OriginalUserAdmin):
    actions = [
        "make_not_staff",
    ]

    @admin.action(description="Mark selected users as not staff")
    def make_not_staff(modeladmin, request, queryset):
        queryset.update(is_staff=False)


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
