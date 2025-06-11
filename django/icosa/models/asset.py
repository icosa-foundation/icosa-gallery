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
from icosa.helpers.format_roles import (
    DOWNLOADABLE_FORMAT_NAMES,
    GLB_FORMAT,
    ORIGINAL_FBX_FORMAT,
    ORIGINAL_GLTF_FORMAT,
    ORIGINAL_OBJ_FORMAT,
    ORIGINAL_TRIANGULATED_OBJ_FORMAT,
    POLYGONE_FBX_FORMAT,
    POLYGONE_GLB_FORMAT,
    POLYGONE_GLTF_FORMAT,
    POLYGONE_OBJ_FORMAT,
    UPDATED_GLTF_FORMAT,
)
from icosa.helpers.snowflake import get_snowflake_timestamp

from .common import (
    ALL_RIGHTS_RESERVED,
    ASSET_STATE_CHOICES,
    ASSET_VISIBILITY_CHOICES,
    CATEGORY_CHOICES,
    CC_LICENSES,
    FILENAME_MAX_LENGTH,
    LICENSE_CHOICES,
    PRIVATE,
    PUBLIC,
    STORAGE_PREFIX,
    UNLISTED,
    V3_CC_LICENSES,
    V4_CC_LICENSES,
    VALID_THUMBNAIL_EXTENSIONS,
    preview_image_upload_path,
    suffix,
    thumbnail_upload_path,
)

LIKES_WEIGHT = 100
VIEWS_WEIGHT = 0.1
RECENCY_WEIGHT = 1


class Asset(models.Model):
    COLOR_SPACES = [
        ("LINEAR", "LINEAR"),
        ("GAMMA", "GAMMA"),
    ]
    id = models.BigAutoField(primary_key=True)
    url = models.CharField(max_length=255, blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    owner = models.ForeignKey("AssetOwner", null=True, blank=True, on_delete=models.CASCADE)
    description = models.TextField(blank=True, null=True)
    formats = models.JSONField(null=True, blank=True)
    visibility = models.CharField(
        max_length=255,
        default=PRIVATE,
        choices=ASSET_VISIBILITY_CHOICES,
        db_default=PRIVATE,
    )
    curated = models.BooleanField(default=False)
    last_reported_by = models.ForeignKey(
        "User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reported_assets",
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
    thumbnail_contenttype = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )
    create_time = models.DateTimeField()
    update_time = models.DateTimeField(null=True, blank=True)
    license = models.CharField(max_length=50, null=True, blank=True, choices=LICENSE_CHOICES)
    tags = models.ManyToManyField("Tag", blank=True)
    category = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        choices=CATEGORY_CHOICES,
    )
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
    state = models.CharField(
        max_length=255,
        choices=ASSET_STATE_CHOICES,
        default="BARE",
        db_default="BARE",
    )
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

    def handle_blocks_preferred_format(self):
        # TODO(james): This handler is specific to data collected from blocks.
        # We should use this logic to populate the database with the correct
        # information. But for now, we don't know this method is 100% correct,
        # so I'm leaving this here.
        if not self.has_gltf2:
            # There are some issues with displaying GLTF1 files from Blocks
            # so we have to return an OBJ and its associated MTL.
            obj_format = self.format_set.filter(
                format_type="OBJ",
                root_resource__isnull=False,
            ).first()
            obj_resource = obj_format.root_resource
            mtl_resource = obj_format.resource_set.first()

            if not obj_resource:
                # TODO: If we fail to find an obj, do we want to handle this
                # with an error?
                return None
            return {
                "format": obj_format,
                "url": obj_resource.internal_url_or_none,
                "materialUrl": mtl_resource.url,
                "resource": obj_resource,
            }
        # We have a gltf2, but we must currently return the suffixed version we
        # have in storage; the non-suffixed version currently does not work.
        blocks_format = self.format_set.filter(format_type="GLTF2").first()
        blocks_resource = None
        if blocks_format is not None:
            blocks_resource = blocks_format.root_resource
        if blocks_format is None or blocks_resource is None:
            # TODO: If we fail to find a gltf2, do we want to handle this with
            # an error?
            return None
        filename = blocks_resource.url
        if filename is None:
            return None
        filename = f"poly/{self.url}/{filename.split('/')[-1]}"
        # TODO(datacleanup): NUMBER_1 When we hit this block, we need to save the suffix to the file field
        url = f"{STORAGE_PREFIX}{suffix(filename)}"
        return {
            "format": blocks_format,
            "url": url,
            "resource": blocks_resource,
        }

    @property
    def _preferred_viewer_format(self):
        if self.preferred_viewer_format_override is not None:
            format = self.preferred_viewer_format_override
            root_resource = format.root_resource
            return {
                "format": format,
                "url": root_resource.internal_url_or_none,
                "resource": root_resource,
            }

        if self.has_blocks:
            return self.handle_blocks_preferred_format()

        # Return early if we can grab a Polygone resource first
        polygone_gltf = None
        format = self.format_set.filter(
            role__in=[1002, 1003],
            root_resource__isnull=False,
        ).first()
        if format:
            polygone_gltf = format.root_resource

        if polygone_gltf:
            return {
                "format": format,
                "url": polygone_gltf.internal_url_or_none,
                "resource": polygone_gltf,
            }

        # Return early with either of the role-based formats we care about.
        updated_gltf = None
        format = self.format_set.filter(
            root_resource__isnull=False,
            role=30,
        ).first()
        if format:
            updated_gltf = format.root_resource

        if updated_gltf:
            return {
                "format": format,
                "url": updated_gltf.internal_url_or_none,
                "resource": updated_gltf,
            }

        original_gltf = None
        format = self.format_set.filter(
            root_resource__isnull=False,
            role=12,
        ).first()
        if format:
            original_gltf = format.root_resource

        if original_gltf:
            return {
                "format": format,
                "url": original_gltf.internal_url_or_none,
                "resource": original_gltf,
            }

        # If we didn't get any role-based formats, find the remaining formats
        # we care about and choose the "best" one of those.
        formats = {}
        for format in self.format_set.all():
            root = format.root_resource
            formats[format.format_type] = {
                "format": format,
                "url": root.internal_url_or_none,
                "resource": root,
            }
        # GLB is our primary preferred format;
        if "GLB" in formats.keys():
            return formats["GLB"]
        # GLTF2 is the next best option;
        if "GLTF2" in formats.keys():
            return formats["GLTF2"]
        # GLTF1, if we must.
        if "GLTF" in formats.keys():
            return formats["GLTF"]
        # Last chance, OBJ
        if "OBJ" in formats.keys():
            return formats["OBJ"]
        return None

    @property
    def preferred_viewer_format(self):
        format = self._preferred_viewer_format
        if format is None:
            return None
        if format["url"] is None:
            return None
        # TODO(datacleanup): NUMBER_2 Mark this as the preferred format in the database
        return format

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

    @property
    def download_url(self):
        if self.license == ALL_RIGHTS_RESERVED or not self.license:
            return None
        updated_gltf = None
        format = self.format_set.filter(
            root_resource__isnull=False,
            role=30,
        ).first()
        if format:
            updated_gltf = format.root_resource

        preferred_format = self.preferred_viewer_format

        if updated_gltf is not None:
            if updated_gltf.format.zip_archive_url:
                return f"https://web.archive.org/web/{updated_gltf.format.zip_archive_url}"
        if preferred_format is not None:
            if preferred_format["resource"].format.zip_archive_url:
                return f"https://web.archive.org/web/{preferred_format['resource'].format.zip_archive_url}"
            # TODO: "poly" is hardcoded here and will not necessarily be used
            # for 3rd party installs.
        return f"{settings.DJANGO_STORAGE_URL}/{settings.DJANGO_STORAGE_BUCKET_NAME}/icosa/{self.url}/archive.zip"

    def get_absolute_url(self):
        return reverse("icosa:asset_view", kwargs={"asset_url": self.url})

    def get_edit_url(self):
        return reverse("icosa:asset_edit", kwargs={"asset_url": self.url})

    def get_delete_url(self):
        return reverse("icosa:asset_delete", kwargs={"asset_url": self.url})

    def get_thumbnail_url(self):
        thumbnail_url = "/static/images/nothumbnail.png?v=1"
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
        self.has_gltf1 = self.format_set.filter(format_type="GLTF").exists()
        self.has_gltf2 = self.format_set.filter(format_type="GLTF2").exists()
        self.has_gltf_any = self.format_set.filter(format_type__in=["GLTF", "GLTF2"]).exists()
        self.has_fbx = self.format_set.filter(format_type="FBX").exists()
        self.has_obj = self.format_set.filter(format_type="OBJ").exists()

    def get_triangle_count(self):
        formats = {}
        for format in self.format_set.filter(triangle_count__gt=0):
            formats.setdefault(format.role, format.triangle_count)
        if POLYGONE_GLTF_FORMAT in formats.keys():
            return formats[POLYGONE_GLTF_FORMAT]
        if ORIGINAL_TRIANGULATED_OBJ_FORMAT in formats.keys():
            return formats[ORIGINAL_OBJ_FORMAT]
        if UPDATED_GLTF_FORMAT in formats.keys():
            return formats[UPDATED_GLTF_FORMAT]
        if ORIGINAL_GLTF_FORMAT in formats.keys():
            return formats[ORIGINAL_GLTF_FORMAT]
        if POLYGONE_OBJ_FORMAT in formats.keys():
            return formats[POLYGONE_OBJ_FORMAT]
        if POLYGONE_GLB_FORMAT in formats.keys():
            return formats[POLYGONE_GLB_FORMAT]
        if GLB_FORMAT in formats.keys():
            return formats[GLB_FORMAT]
        if POLYGONE_FBX_FORMAT in formats.keys():
            return formats[POLYGONE_FBX_FORMAT]
        if ORIGINAL_FBX_FORMAT in formats.keys():
            return formats[ORIGINAL_FBX_FORMAT]
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
        rank += (1 / (datetime.now().timestamp() - self.create_time.timestamp())) * RECENCY_WEIGHT
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
        # Originally, Google Poly made these roles available for download:
        # - Original FBX File
        # - Original OBJ File
        # - GLB File
        # - Original Triangulated OBJ File
        # - Original glTF File
        # - USDZ File
        # - Updated glTF File
        formats = {}
        if self.license == ALL_RIGHTS_RESERVED:
            # We do not provide any downloads for assets with restrictive
            # licenses.
            return formats

        if user is not None and not user.is_anonymous and self.owner in user.assetowner_set.all():
            # The user owns this asset so can view all files.
            dl_formats = self.format_set.all()
        elif self.license in ["CREATIVE_COMMONS_BY_ND_3_0", "CREATIVE_COMMONS_BY_ND_4_0"]:
            # We don't allow downoad of source files for ND-licensed work.
            dl_formats = self.format_set.filter(role__in=ND_WEB_UI_DOWNLOAD_COMPATIBLE)
        else:
            dl_formats = self.format_set.filter(role__in=WEB_UI_DOWNLOAD_COMPATIBLE)
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
                    resource_data = format.get_resource_data_by_role(
                        resources,
                        format.role,
                    )
                # If there is only one resource, there is no need to create
                # a zip file; we can offer our local file, or a link to the
                # external host.
                else:
                    resource = resources[0]
                    if resource.file:
                        storage = settings.DJANGO_STORAGE_URL
                        bucket = settings.DJANGO_STORAGE_BUCKET_NAME
                        resource_data = {"file": f"{storage}/{bucket}/{resource.file.name}"}
                    elif resource.external_url:
                        resource_data = {"file": resource.external_url}
                    else:
                        resource_data = {}

            if resource_data:
                format_name = DOWNLOADABLE_FORMAT_NAMES.get(format.get_role_display(), format.get_role_display())
                # TODO: Currently, we only offer the first format per role
                # that we find. This might be a mistake. Should we include all
                # duplicate roles?
                formats.setdefault(format_name, resource_data)
        formats = OrderedDict(
            sorted(
                formats.items(),
                key=lambda x: x[0].lower(),
            )
        )
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
                HiddenMediaFileLog.objects.create(
                    original_asset_id=self.pk,
                    file_name=file_name,
                )
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
            models.Index(
                fields=[
                    "is_viewer_compatible",
                    "visibility",
                ]
            ),
            models.Index(
                fields=[
                    "likes",
                ]
            ),
            models.Index(
                fields=[
                    "owner",
                ]
            ),
            # Index for paginator
            models.Index(
                fields=[
                    "is_viewer_compatible",
                    "last_reported_time",
                    "visibility",
                    "license",
                ]
            ),
        ]
