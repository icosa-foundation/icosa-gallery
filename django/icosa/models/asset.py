from collections import OrderedDict
from datetime import datetime
from typing import Optional

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models, transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils.text import slugify
from icosa.helpers.snowflake import get_snowflake_timestamp
from icosa.helpers.storage import get_b2_bucket

from .common import (
    ALL_RIGHTS_RESERVED,
    ARCHIVE_PREFIX,
    ASSET_STATE_CHOICES,
    ASSET_VISIBILITY_CHOICES,
    CATEGORY_CHOICES,
    CC_LICENSES,
    FILENAME_MAX_LENGTH,
    LICENSE_CHOICES,
    PRIVATE,
    PUBLIC,
    UNLISTED,
    V3_CC_LICENSES,
    V4_CC_LICENSES,
    VALID_THUMBNAIL_EXTENSIONS,
)
from .helpers import (
    preview_image_upload_path,
    thumbnail_upload_path,
)
from .log import HiddenMediaFileLog

LIKES_WEIGHT = 100
VIEWS_WEIGHT = 0.1
RECENCY_WEIGHT = 1

NON_REMIXABLE_FORMAT_TYPES = ["TILT", "BLOCKS"]


class Asset(models.Model):
    COLOR_SPACES = [("LINEAR", "LINEAR"), ("GAMMA", "GAMMA")]
    id = models.BigAutoField(primary_key=True)
    url = models.CharField(max_length=255, blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    owner = models.ForeignKey("AssetOwner", null=True, blank=True, on_delete=models.CASCADE)
    description = models.TextField(blank=True, null=True)
    formats = models.JSONField(null=True, blank=True)
    visibility = models.CharField(max_length=255, default=PRIVATE, choices=ASSET_VISIBILITY_CHOICES, db_default=PRIVATE)
    curated = models.BooleanField(default=False)
    last_reported_by = models.ForeignKey(
        "User", null=True, blank=True, on_delete=models.SET_NULL, related_name="reported_assets"
    )
    last_reported_time = models.DateTimeField(null=True, blank=True)
    polyid = models.CharField(max_length=255, blank=True, null=True)
    polydata = models.JSONField(blank=True, null=True)
    thumbnail = models.ImageField(
        max_length=FILENAME_MAX_LENGTH,
        blank=True,
        null=True,
        upload_to=thumbnail_upload_path,
        validators=[FileExtensionValidator(allowed_extensions=VALID_THUMBNAIL_EXTENSIONS)],
    )
    preview_image = models.ImageField(
        max_length=FILENAME_MAX_LENGTH,
        blank=True,
        null=True,
        upload_to=preview_image_upload_path,
        validators=[FileExtensionValidator(allowed_extensions=VALID_THUMBNAIL_EXTENSIONS)],
    )
    thumbnail_contenttype = models.CharField(max_length=255, blank=True, null=True)
    create_time = models.DateTimeField()
    update_time = models.DateTimeField(null=True, blank=True)
    license = models.CharField(max_length=50, null=True, blank=True, choices=LICENSE_CHOICES)
    tags = models.ManyToManyField("Tag", blank=True)
    category = models.CharField(max_length=255, null=True, blank=True, choices=CATEGORY_CHOICES)
    transform = models.JSONField(blank=True, null=True)
    camera = models.JSONField(blank=True, null=True)
    presentation_params = models.JSONField(null=True, blank=True)
    imported_from = models.CharField(max_length=255, null=True, blank=True)
    remix_ids = models.JSONField(null=True, blank=True)
    historical_likes = models.PositiveIntegerField(default=0)
    historical_views = models.PositiveIntegerField(default=0)
    likes = models.PositiveIntegerField(default=0)
    views = models.PositiveIntegerField(default=0)
    downloads = models.PositiveIntegerField(default=0)
    state = models.CharField(max_length=255, choices=ASSET_STATE_CHOICES, default="BARE", db_default="BARE")
    preferred_viewer_format_override = models.OneToOneField(
        "Format",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="preferred_format_override_for",
        # limit_choices_to cannot have a reference to self. We must limit the
        # choices another way.
    )

    # Denorm fields
    triangle_count = models.PositiveIntegerField(default=0)
    search_text = models.TextField(null=True, blank=True)
    is_viewer_compatible = models.BooleanField(default=False)
    last_liked_time = models.DateTimeField(null=True, blank=True)

    has_tilt = models.BooleanField(default=False)
    has_blocks = models.BooleanField(default=False)
    has_gltf1 = models.BooleanField(default=False)
    has_gltf2 = models.BooleanField(default=False)
    has_gltf_any = models.BooleanField(default=False)
    has_fbx = models.BooleanField(default=False)
    has_obj = models.BooleanField(default=False)

    rank = models.FloatField(default=0)

    @property
    def is_published(self):
        return self.visibility in [PUBLIC, UNLISTED]

    @property
    def model_is_editable(self):
        # Once a permissable license has been chosen, and the asset is
        # available for use in other models, we cannot allow changing anything
        # about it. Doing so would allow abuse.
        is_editable = True
        if self.is_published and self.license not in [
            None,
            ALL_RIGHTS_RESERVED,
            "CREATIVE_COMMONS_BY_ND_3_0",
            "CREATIVE_COMMONS_BY_3_0",
        ]:
            is_editable = False
        return is_editable

    @property
    def slug(self):
        return slugify(self.name)

    @property
    def timestamp(self):
        return get_snowflake_timestamp(self.id)

    def get_base_license(self) -> str:
        # Transform our internal license representations to be compatible with
        # the Google Poly API.
        if self.license == "ALL_RIGHTS_RESERVED":
            return self.license
        if self.license == "CREATIVE_COMMONS_0":
            return "CC0"
        elif self.license in V3_CC_LICENSES:
            return self.license.replace("_3_0", "")
        elif self.license in V4_CC_LICENSES:
            return self.license.replace("_4_0", "")
        else:
            # We shouldn't hit this, but it's a valid option in Google Poly.
            return "UNKNOWN"

    def get_license_version(self) -> Optional[str]:
        if self.license in ["ALL_RIGHTS_RESERVED", "CREATIVE_COMMONS_0"]:
            return None
        if self.license in V3_CC_LICENSES:
            return "3.0"
        if self.license in V4_CC_LICENSES:
            return "4.0"
        else:
            return None

    def get_preferred_viewer_format_for_assignment(self):
        formats = self.format_set.filter(root_resource__isnull=False)
        # GLB is our primary preferred format;
        inst = formats.filter(format_type="GLB").last()
        if inst is not None:
            return inst

        # GLTF2 is the next best option;
        inst = formats.filter(format_type="GLTF2").last()
        if inst is not None:
            return inst

        # GLTF1, if we must.
        inst = formats.filter(format_type="GLTF1").last()
        if inst is not None:
            return inst

        # OBJ, if we really must
        inst = formats.filter(format_type="OBJ").last()
        if inst is not None:
            return inst

        # Last chance, can we get one of the newer format types?
        # TODO: the ordering of these matters, but perhaps it is unlikely that
        # a usdz and ksplat are present (for example).
        for format_type in ["KSPLAT", "PLY", "STL", "SOG", "SPZ", "SPLAT", "USDZ", "VOX"]:
            inst = formats.filter(format_type=format_type).last()
            if inst is not None:
                # This will return the first we find from the list above; this
                # is why ordering matters.
                return inst

        return None

    def assign_preferred_viewer_format(self):
        preferred_format = self.get_preferred_viewer_format_for_assignment()
        if preferred_format is not None:
            # TODO(james) do we mark all other formats as not preferred?
            preferred_format.is_preferred_for_gallery_viewer = True
            preferred_format.save()
        return preferred_format

    @property
    def preferred_viewer_format(self):
        return self.format_set.filter(is_preferred_for_gallery_viewer=True).first()

    @property
    def has_cors_allowed_preferred_format(self):
        preferred_format = self.preferred_viewer_format
        if not preferred_format:
            return False

        # If this asset's preferred_format has a file managed by Django
        # storage, or if any of the externally-hosted files' sources have been
        # allowed by the site admin in django constance settings, then it will
        # be viewable.
        is_allowed = False

        for format in self.format_set.all():
            root = format.root_resource
            if root is not None:
                if root.file or root.is_cors_allowed:
                    is_allowed = True
                    break

        return is_allowed

    def get_absolute_url(self):
        return reverse("icosa:asset_view", kwargs={"asset_url": self.url})

    def get_edit_url(self):
        return reverse("icosa:asset_edit", kwargs={"asset_url": self.url})

    def get_delete_url(self):
        return reverse("icosa:asset_delete", kwargs={"asset_url": self.url})

    def get_thumbnail_url(self):
        thumbnail_url = (
            f"{settings.DEPLOYMENT_SCHEME}{settings.DEPLOYMENT_HOST_WEB}{settings.STATIC_URL}images/nothumbnail.png?v=1"
        )
        if self.preview_image:
            thumbnail_url = self.preview_image.url
        elif self.thumbnail:
            thumbnail_url = self.thumbnail.url
        return thumbnail_url

    @property
    def thumbnail_url(self):
        return self.thumbnail.url

    @property
    def thumbnail_relative_path(self):
        return self.thumbnail.name.split("/")[-1]

    @property
    def thumbnail_content_type(self):
        return self.thumbnail.content_type

    def img_tag(self, src):
        return f"<img src='{settings.STATIC_URL}/images/{src}'>"

    def get_license_icons(self):
        icons = []
        if self.license in CC_LICENSES:
            icons.append(self.img_tag("cc.svg"))
            if self.license == "CREATIVE_COMMONS_0":
                icons.append(self.img_tag("zero.svg"))
            else:
                typ = self.license.replace("CREATIVE_COMMONS_", "")[:-4]
                if typ == "BY":
                    icons.append(self.img_tag("by.svg"))
                if typ == "BY_ND":
                    icons.append(self.img_tag("by.svg"))
                    icons.append(self.img_tag("nd.svg"))
        else:
            icons.append("&copy;")
        return mark_safe("".join(icons))

    def __str__(self):
        return self.name if self.name else "(Un-named asset)"

    def is_owned_by_django_user(self, user=None):
        return user is not None and not user.is_anonymous and self.owner in user.assetowner_set.all()

    def update_search_text(self):
        if not self.pk:
            return
        tag_str = " ".join([t.name for t in self.tags.all()])
        description = self.description if self.description is not None else ""
        self.search_text = f"{self.name} {description} {tag_str} {self.owner.displayname}"

    def calc_is_viewer_compatible(self):
        if not self.pk:
            return False
        return self.has_cors_allowed_preferred_format

    def denorm_format_types(self):
        if not self.pk:
            return
        self.has_tilt = self.format_set.filter(format_type="TILT").exists()
        self.has_blocks = self.format_set.filter(format_type="BLOCKS").exists()
        self.has_gltf1 = self.format_set.filter(format_type="GLTF1").exists()
        self.has_gltf2 = self.format_set.filter(format_type="GLTF2").exists()
        self.has_gltf_any = self.format_set.filter(format_type__in=["GLTF1", "GLTF2"]).exists()
        self.has_fbx = self.format_set.filter(format_type="FBX").exists()
        self.has_obj = self.format_set.filter(format_type="OBJ").exists()

    def get_triangle_count(self):
        formats = {}
        for format in self.format_set.filter(triangle_count__gt=0):
            formats.setdefault(format.role, format.triangle_count)
        if "POLYGONE_GLTF_FORMAT" in formats.keys():
            return formats["POLYGONE_GLTF_FORMAT"]
        if "ORIGINAL_TRIANGULATED_OBJ_FORMAT" in formats.keys():
            return formats["ORIGINAL_OBJ_FORMAT"]
        if "UPDATED_GLTF_FORMAT" in formats.keys():
            return formats["UPDATED_GLTF_FORMAT"]
        if "ORIGINAL_GLTF_FORMAT" in formats.keys():
            return formats["ORIGINAL_GLTF_FORMAT"]
        if "POLYGONE_OBJ_FORMAT" in formats.keys():
            return formats["POLYGONE_OBJ_FORMAT"]
        if "POLYGONE_GLB_FORMAT" in formats.keys():
            return formats["POLYGONE_GLB_FORMAT"]
        if "GLB_FORMAT" in formats.keys():
            return formats["GLB_FORMAT"]
        if "POLYGONE_FBX_FORMAT" in formats.keys():
            return formats["POLYGONE_FBX_FORMAT"]
        if "ORIGINAL_FBX_FORMAT" in formats.keys():
            return formats["ORIGINAL_FBX_FORMAT"]
        return 0

    def denorm_triangle_count(self):
        self.triangle_count = self.get_triangle_count()

    def denorm_liked_time(self):
        last_liked = self.userlike_set.order_by("-date_liked").first()
        if last_liked is not None:
            self.last_liked_time = last_liked.date_liked

    def get_updated_rank(self):
        rank = (self.likes + self.historical_likes + 1) * LIKES_WEIGHT
        rank += (self.views + self.historical_views) * VIEWS_WEIGHT
        now = datetime.now().timestamp()
        create_time = self.create_time.timestamp()
        # Prevent a divide by zero error if this function is called very soon
        # after asset creation.
        one_tick = 0.0001
        elapsed = now - create_time
        elapsed = elapsed or one_tick
        rank += (1 / elapsed) * RECENCY_WEIGHT
        return rank

    def inc_views_and_rank(self):
        self.views += 1
        self.rank = self.get_updated_rank()
        self.save()

    def get_all_file_names(self):
        file_list = []
        if self.thumbnail:
            file_list.append(self.thumbnail.file.name)
        for resource in self.resource_set.all():
            if resource.file:
                file_list.append(resource.file.name)
        return file_list

    def get_all_downloadable_formats(self, user=None):
        # The user owns this asset so can view all files.
        if self.is_owned_by_django_user(user):
            return self.format_set.all()

        # We do not provide any downloads for assets with restrictive licenses.
        if self.license == ALL_RIGHTS_RESERVED:
            return self.format_set.none()
        else:
            dl_formats = self.format_set.filter(hide_from_downloads=False)
            if self.license in ["CREATIVE_COMMONS_BY_ND_3_0", "CREATIVE_COMMONS_BY_ND_4_0"]:
                # We don't allow downoad of source files for ND-licensed work.
                dl_formats = dl_formats.exclude(format_type__in=NON_REMIXABLE_FORMAT_TYPES)

        formats = {}

        for format in dl_formats:
            # If the format in its entirety is on a remote host, just provide
            # the link to that.
            if format.zip_archive_url:
                resource_data = {"zip_archive_url": f"{ARCHIVE_PREFIX}{format.zip_archive_url}"}
            else:
                # Query all resources which have either an external url or a
                # file. Ignoring resources which have neither.
                query = Q(external_url__isnull=False) & ~Q(external_url="")
                query |= Q(file__isnull=False)
                resources = format.get_all_resources(query)

                # If there is more than one resource, this means we need to
                # create a zip file of it on the client. We can only do this
                # if either:
                # a) the resource is hosted by Django
                # b) all the resources we need to zip are accessible because
                #    they are on the CORS allow list.
                # The second criteria is met if the resource's remote host is
                # in the EXTERNAL_MEDIA_CORS_ALLOW_LIST setting in constance.
                if len(resources) > 1:
                    resource_data = format.get_resource_data(resources)
                # If there is only one resource, there is no need to create
                # a zip file; we can offer our local file, or a link to the
                # external host.
                elif len(resources) == 1:
                    resource = resources[0]
                    file_url = resource.url
                    if file_url is None:
                        resource_data = {}
                    else:
                        resource_data = {"file": file_url}
                else:
                    resource_data = {}

            format_name = format.user_label()

            if resource_data:
                # TODO: Currently, we only offer the first format per type (or
                # role) that we find. This might be a mistake. Should we include
                # all duplicates?
                formats.setdefault(format_name, resource_data)

        formats = OrderedDict(sorted(formats.items(), key=lambda x: x[0].lower()))
        return formats

    def hide_media(self):
        """For B2, at least, call `hide` on each item from
        self.get_all_files() then delete the model instance and all its related
        models. For the moment, this should not be part of Asset's delete
        method, for safety."""

        hidden_files = []
        file_names = self.get_all_file_names()
        if len(file_names) == 0:
            return hidden_files

        bucket = get_b2_bucket()
        for file_name in file_names:
            if file_name.startswith("poly/"):
                # This is a poly file and we might not want to delete/hide it.
                pass  # TODO
            elif file_name.startswith("icosa/"):
                # This is a user file, so we are ok to delete/hide it.
                bucket.hide_file(file_name)
                HiddenMediaFileLog.objects.create(original_asset_id=self.pk, file_name=file_name)
            else:
                # This is not a file we care to mess with.
                pass

    @transaction.atomic
    def save(self, *args, **kwargs):
        update_timestamps = kwargs.pop("update_timestamps", False)
        bypass_custom_logic = kwargs.pop("bypass_custom_logic", False)
        if not bypass_custom_logic:
            now = timezone.now()
            if self._state.adding:
                self.create_time = now
            else:
                # Only denorm fields when updating an existing model
                self.rank = self.get_updated_rank()
                self.update_search_text()
                self.is_viewer_compatible = self.calc_is_viewer_compatible()
                self.denorm_format_types()
                self.denorm_triangle_count()
                self.denorm_liked_time()
                if update_timestamps:
                    self.update_time = now
        super().save(*args, **kwargs)

    class Meta:
        indexes = [
            models.Index(fields=["is_viewer_compatible", "visibility"]),
            models.Index(fields=["likes"]),
            models.Index(fields=["owner"]),
            # Index for paginator
            models.Index(fields=["is_viewer_compatible", "last_reported_time", "visibility", "license"]),
        ]
