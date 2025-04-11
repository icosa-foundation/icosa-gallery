from django.apps import AppConfig

from ninja_keys.apps import NinjaKeysConfig

class IcosaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "icosa"
    default = True

class IcosaAPIKeyConfig(NinjaKeysConfig):
    name = "ninja_keys"
    verbose_name = "Ninja API Keys"
    def get_models(self, include_auto_created=False, include_swapped=False):
        return []