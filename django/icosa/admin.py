from icosa.models import (
    Asset,
    DeviceCode,
    Oauth2Client,
    Oauth2Code,
    Oauth2Token,
    OrientingRotation,
    PolyFormat,
    PolyResource,
    PresentationParams,
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
        "is_thumbnail",
        "contenttype",
    )

    list_filter = (
        "is_root",
        "is_thumbnail",
        "contenttype",
    )
    search_fields = ("file",)


@admin.register(PresentationParams)
class PresentationParamsAdmin(admin.ModelAdmin):
    pass


@admin.register(OrientingRotation)
class OrientingRotationAdmin(admin.ModelAdmin):
    pass


class PolyFormatInline(admin.TabularInline):
    extra = 0
    model = PolyFormat
    show_change_link = True

    fields = ("format_type",)


class PolyResourceInline(admin.TabularInline):
    extra = 0
    model = PolyResource

    fields = (
        "is_root",
        "file",
    )


@admin.register(PolyFormat)
class PolyFormatAdmin(admin.ModelAdmin):

    list_display = (
        "asset",
        "format_type",
    )

    inlines = (PolyResourceInline,)


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "_thumbnail_image",
        "url",
        "owner",
        "description",
        "_formats",
        "visibility",
        "curated",
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
        "owner",
        ("thumbnail", admin.EmptyFieldListFilter),
    )

    @admin.display(description="Formats")
    def _formats(self, obj):
        return (
            f"{', '.join([x['format'] for x in obj.formats if 'format' in x])}"
        )

    def _thumbnail_image(self, obj):
        html = ""

        thumbnail_resource = PolyResource.objects.filter(
            asset=obj, is_thumbnail=True
        ).first()
        if thumbnail_resource:
            html = f'<img src="{thumbnail_resource.file.url}" width="150" loading="lazy">'
        return mark_safe(html)

    _thumbnail_image.short_description = "Thumbnail"
    _thumbnail_image.allow_tags = True

    search_fields = (
        "name",
        "url",
        "owner__displayname",
    )

    filter_horizontal = ("tags",)
    inlines = (PolyFormatInline,)


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
