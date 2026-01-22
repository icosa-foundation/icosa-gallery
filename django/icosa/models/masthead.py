from django.core.validators import FileExtensionValidator
from django.db import models

from .asset import Asset
from .common import FILENAME_MAX_LENGTH, PUBLIC, VALID_THUMBNAIL_EXTENSIONS
from .helpers import masthead_image_upload_path


class MastheadSection(models.Model):
    image = models.ImageField(
        max_length=FILENAME_MAX_LENGTH,
        blank=True,
        null=True,
        upload_to=masthead_image_upload_path,
        validators=[FileExtensionValidator(allowed_extensions=VALID_THUMBNAIL_EXTENSIONS)],
    )
    asset = models.ForeignKey(Asset, on_delete=models.SET_NULL, null=True, blank=True)
    url = models.CharField(
        max_length=1024,
        null=True,
        blank=True,
        help_text="URL to link to in place of an asset's viewer page.",
    )
    headline_text = models.CharField(
        max_length=1024,
        null=True,
        blank=True,
        help_text="Text displayed in place of an asset's name.",
    )
    sub_text = models.CharField(
        max_length=1024,
        null=True,
        blank=True,
        help_text="Text displayed in place of an asset's owner's name.",
    )

    @property
    def visibility(self):
        if self.asset is None:
            return PUBLIC
        return self.asset.visibility

    async def avisibility(self):
        if self.asset is None:
            return PUBLIC
        return self.asset.visibility
