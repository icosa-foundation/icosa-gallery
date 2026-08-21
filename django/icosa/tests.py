from django import forms
from django.contrib.admin.sites import AdminSite
from django.test import SimpleTestCase

from icosa.admin import AssetAdmin
from icosa.models import Asset


class AssetUrlTests(SimpleTestCase):
    def test_admin_form_rejects_url_containing_slash(self):
        class AssetUrlForm(forms.ModelForm):
            class Meta:
                model = Asset
                fields = ("url",)

        form = AssetUrlForm(data={"url": "invalid/asset-url"})

        self.assertFalse(form.is_valid())
        self.assertIn("url", form.errors)

    def test_admin_list_display_handles_invalid_stored_url(self):
        asset = Asset(url="invalid/asset-url")
        asset_admin = AssetAdmin(Asset, AdminSite())

        self.assertEqual(asset_admin.display_thumbnail(asset), "invalid/asset-url")

    def test_admin_list_display_links_valid_url(self):
        asset = Asset(url="valid-asset-url")
        asset_admin = AssetAdmin(Asset, AdminSite())

        self.assertEqual(
            asset_admin.display_thumbnail(asset),
            "<a href='/view/valid-asset-url'>valid-asset-url</a>",
        )
