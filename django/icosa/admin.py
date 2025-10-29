from import_export.admin import ExportMixin

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as OriginalUserAdmin
from django.db.models import Count
from django.urls import reverse
from django.utils.safestring import mark_safe
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
