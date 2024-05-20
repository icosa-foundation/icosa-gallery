from api.models import (
    Asset,
    DeviceCode,
    Oauth2Client,
    Oauth2Code,
    Oauth2Token,
    User,
)

from django.contrib import admin


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "visibility",
    )


@admin.register(DeviceCode)
class DeviceCodeAdmin(admin.ModelAdmin):
    pass


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    pass


@admin.register(Oauth2Client)
class Oauth2ClientAdmin(admin.ModelAdmin):
    pass


@admin.register(Oauth2Code)
class Oauth2CodeAdmin(admin.ModelAdmin):
    pass


@admin.register(Oauth2Token)
class Oauth2TokenAdmin(admin.ModelAdmin):
    pass
