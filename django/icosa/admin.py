from icosa.models import (
    Asset,
    DeviceCode,
    IcosaFormat,
    Oauth2Client,
    Oauth2Code,
    Oauth2Token,
    Tag,
    User,
)

from django.contrib import admin


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    pass


@admin.register(IcosaFormat)
class IcosaFormatAdmin(admin.ModelAdmin):

    list_display = (
        "asset",
        "format",
        "is_mainfile",
    )

    filter_horizontal = ("subfiles",)


class IcosaFormatInline(admin.TabularInline):
    extra = 0
    model = IcosaFormat
    filter_horizontal = ("subfiles",)


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
    inlines = (IcosaFormatInline,)


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
