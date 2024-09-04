from icosa.models import (
    Asset,
    DeviceCode,
    FormatComplexity,
    Oauth2Client,
    Oauth2Code,
    Oauth2Token,
    PolyFormat,
    PolyResource,
    Tag,
    User,
)

from django.contrib import admin
from django.utils.safestring import mark_safe


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
        "role",
    )
    search_fields = ("file",)


class PolyFormatInline(admin.TabularInline):
    extra = 0
    model = PolyFormat
    show_change_link = True

    fields = (
        "format_type",
        "archive_url",
    )


class PolyResourceInline(admin.TabularInline):
    extra = 0
    model = PolyResource

    fields = (
        "is_root",
        "file",
        "external_url",
        "role",
    )


class FormatComplexityInline(admin.TabularInline):
    extra = 0
    model = FormatComplexity

    fields = (
        "triangle_count",
        "lod_hint",
    )


@admin.register(PolyFormat)
class PolyFormatAdmin(admin.ModelAdmin):

    list_display = (
        "asset",
        "format_type",
    )

    inlines = (
        PolyResourceInline,
        FormatComplexityInline,
    )
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
        "is_viewer_compatible",
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
        "imported",
        ("thumbnail", admin.EmptyFieldListFilter),
    )

    def _thumbnail_image(self, obj):
        html = ""

        if obj.thumbnail:
            html = f"""
<img src="{obj.thumbnail.url}" width="150" loading="lazy">
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

    date_hierarchy = "expiry"


class UserAssetLikeInline(admin.TabularInline):
    extra = 0
    model = User.likes.through
    raw_id_fields = ["asset"]


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = (
        "displayname",
        "email",
        "url",
    )

    search_fields = (
        "displayname",
        "email",
        "url",
        "id",
    )
    list_filter = (("email", admin.EmptyFieldListFilter),)
    inlines = (UserAssetLikeInline,)


@admin.register(Oauth2Client)
class Oauth2ClientAdmin(admin.ModelAdmin):
    pass


@admin.register(Oauth2Code)
class Oauth2CodeAdmin(admin.ModelAdmin):
    pass


@admin.register(Oauth2Token)
class Oauth2TokenAdmin(admin.ModelAdmin):
    pass
