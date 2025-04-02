from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as OriginalUserAdmin
from django.contrib.auth.models import User
from django.db.models import Count
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
from import_export.admin import ExportMixin

FORMAT_ROLE_CHOICES = {
    1: "Original OBJ File",
    2: "Tilt File",
    4: "Unknown GLTF File A",
    6: "Original FBX File",
    7: "Blocks File",
    8: "USD File",
    11: "HTML File",
    12: "Original glTF File",
    13: "TOUR CREATOR EXPERIENCE",
    15: "JSON File",
    16: "lullmodel File",
    17: "SAND File A",
    18: "GLB File",
    19: "SAND File B",
    20: "SANDC File",
    21: "PB File",
    22: "Unknown GLTF File B",
    24: "Original Triangulated OBJ File",
    25: "JPG BUGGY",
    26: "USDZ File",
    30: "Updated glTF File",
    32: "Editor settings pb file",
    35: "Unknown GLTF File C",
    36: "Unknown GLB File A",
    38: "Unknown GLB File B",
    39: "TILT NATIVE glTF",
    40: "USER SUPPLIED glTF",
}


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

    fields = (
        "format_type",
        "zip_archive_url",
        "role",
        "is_preferred_for_viewer",
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
    )
    raw_id_fields = [
        "asset",
        "root_resource",
    ]


@admin.register(Asset)
class AssetAdmin(ExportMixin, admin.ModelAdmin):
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
        "display_preferred_viewer_format",
    )

    def display_preferred_viewer_format(self, obj):
        if obj.preferred_viewer_format:  # and obj.preferred_viewer_format.format:
            try:
                change_url = reverse(
                    "admin:icosa_format_change",
                    args=(obj.preferred_viewer_format["format"].id,),
                )
                role_text = FORMAT_ROLE_CHOICES[obj.preferred_viewer_format["format"].role]
                html = f"<a href='{change_url}'>{role_text}</a>"
            except Exception as e:
                html = f"{e.message}"
        else:
            html = "-"
        return mark_safe(html)
    display_preferred_viewer_format.short_description = "Preferred viewer format"
    display_preferred_viewer_format.allow_tags = True

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


@admin.register(DeviceCode)
class DeviceCodeAdmin(ExportMixin, admin.ModelAdmin):
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
    )
    inlines = (UserAssetLikeInline,)
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
            change_url = reverse("admin:auth_user_change", args=(obj.django_user.id,))
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


class UserAdmin(OriginalUserAdmin):
    actions = [
        "make_not_staff",
    ]

    @admin.action(description="Mark selected users as not staff")
    def make_not_staff(modeladmin, request, queryset):
        queryset.update(is_staff=False)


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
