from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from .asset import Asset
from .common import FILENAME_MAX_LENGTH, PUBLIC, VALID_THUMBNAIL_EXTENSIONS
from .helpers import masthead_image_upload_path


class MastheadSection(models.Model):
    image = models.ImageField(
        _("Image"),
        max_length=FILENAME_MAX_LENGTH,
        blank=True,
        null=True,
        upload_to=masthead_image_upload_path,
        validators=[FileExtensionValidator(allowed_extensions=VALID_THUMBNAIL_EXTENSIONS)],
        help_text=_("Background image for this masthead section"),
    )
    asset = models.ForeignKey(
        Asset,
        verbose_name=_("Asset"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text=_("Featured asset for this masthead section"),
    )
    url = models.CharField(
        _("URL"),
        max_length=1024,
        null=True,
        blank=True,
        help_text=_("URL to link to in place of an asset's viewer page."),
    )
    headline_text = models.CharField(
        _("Headline Text"),
        max_length=1024,
        null=True,
        blank=True,
        help_text=_("Text displayed in place of an asset's name."),
    )
    sub_text = models.CharField(
        _("Sub Text"),
        max_length=1024,
        null=True,
        blank=True,
        help_text=_("Text displayed in place of an asset's owner's name."),
    )

    class Meta:
        verbose_name = _("Masthead Section")
        verbose_name_plural = _("Masthead Sections")

    @property
    def visibility(self):
        if self.asset is None:
            return PUBLIC
        return self.asset.visibility

    async def avisibility(self):
        if self.asset is None:
            return PUBLIC
        return self.asset.visibility
