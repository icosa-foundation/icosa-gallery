from admin_tools.dashboard import Dashboard, modules

from django.utils.translation import gettext_lazy as _


class MainDashboard(Dashboard):
    title = "Dashboard"
    columns = 3

    def init_with_context(self, context):
        self.children.append(
            modules.ModelList(
                _("API"),
                models=("api.models.*",),
            )
        )
        self.children.append(modules.RecentActions(_("Recent Actions"), 10))

        self.children.append(
            modules.ModelList(
                _("Administration"),
                models=("django.contrib.auth.models.User",),
            )
        )
