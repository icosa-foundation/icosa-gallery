from icosa.models import (
    Asset,
    DeviceCode,
    Oauth2Client,
    Oauth2Code,
    Oauth2Token,
    PolyFormat,
    PolyResource,
    Tag,
    User,
)

from django.contrib import admin


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    pass


@admin.register(PolyResource)
class PolyResourceAdmin(admin.ModelAdmin):
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
        "url",
        "owner",
        "description",
        "_formats",
        "visibility",
        "curated",
        "polyid",
        "polydata",
        "thumbnail",
    )
    search_fields = (
        "name",
        "url",
    )
    list_filter = (
        "visibility",
        "curated",
        "imported",
    )

    @admin.display(description="Formats")
    def _formats(self, obj):
        return (
            f"{', '.join([x['format'] for x in obj.formats if 'format' in x])}"
        )

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
