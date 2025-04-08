import os
import re
import secrets
import string
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Optional, Self
from urllib.parse import urlparse

import bcrypt
import jwt
from b2sdk._internal.exception import FileNotHidden, FileNotPresent
from constance import config
from django.conf import settings
from django.contrib.auth.models import User as DjangoUser
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils.text import slugify
from icosa.helpers.format_roles import (
    BLOCKS_FORMAT,
    DOWNLOADABLE_FORMAT_NAMES,
    FORMAT_ROLE_CHOICES,
    GLB_FORMAT,
    ORIGINAL_FBX_FORMAT,
    ORIGINAL_GLTF_FORMAT,
    ORIGINAL_OBJ_FORMAT,
    ORIGINAL_TRIANGULATED_OBJ_FORMAT,
    POLYGONE_FBX_FORMAT,
    POLYGONE_GLB_FORMAT,
    POLYGONE_GLTF_FORMAT,
    POLYGONE_OBJ_FORMAT,
    TILT_FORMAT,
    TILT_NATIVE_GLTF,
    UPDATED_GLTF_FORMAT,
    USD_FORMAT,
    USDZ_FORMAT,
    USER_SUPPLIED_GLTF,
)

from .helpers.snowflake import get_snowflake_timestamp
from .helpers.storage import get_b2_bucket

FILENAME_MAX_LENGTH = 1024

LIKES_WEIGHT = 100
VIEWS_WEIGHT = 0.1
RECENCY_WEIGHT = 1

PUBLIC = "PUBLIC"
PRIVATE = "PRIVATE"
UNLISTED = "UNLISTED"
ARCHIVED = "ARCHIVED"
ASSET_VISIBILITY_CHOICES = [
    (PUBLIC, "Public"),
    (PRIVATE, "Private"),
    (UNLISTED, "Unlisted"),
    (ARCHIVED, "Archived"),
]

V4_CC_LICENSE_CHOICES = [
    ("CREATIVE_COMMONS_BY_4_0", "CC BY Attribution 4.0 International"),
    (
        "CREATIVE_COMMONS_BY_ND_4_0",
        "CC BY-ND Attribution-NoDerivatives 4.0 International",
    ),
    ("CREATIVE_COMMONS_0", "CC0 1.0 Universal"),
]

V3_CC_LICENSE_CHOICES = [
    ("CREATIVE_COMMONS_BY_3_0", "CC BY Attribution 3.0 International"),
    (
        "CREATIVE_COMMONS_BY_ND_3_0",
        "CC BY-ND Attribution-NoDerivatives 3.0 International",
    ),
]
V3_CC_LICENSES = [x[0] for x in V3_CC_LICENSE_CHOICES]
V4_CC_LICENSES = [x[0] for x in V4_CC_LICENSE_CHOICES]
V3_CC_LICENSE_MAP = {x[0]: x[1] for x in V3_CC_LICENSE_CHOICES}
V4_CC_LICENSE_MAP = {x[0]: x[1] for x in V4_CC_LICENSE_CHOICES}
V3_TO_V4_UPGRADE_MAP = {
    x[0]: x[1]
    for x in zip(
        V3_CC_LICENSES,
        V4_CC_LICENSES,
    )
}

ALL_RIGHTS_RESERVED = "ALL_RIGHTS_RESERVED"
RESERVED_LICENSE = (ALL_RIGHTS_RESERVED, "All rights reserved")
CC_LICENSES = [x[0] for x in V3_CC_LICENSE_CHOICES] + [x[0] for x in V4_CC_LICENSE_CHOICES]

REMIX_REGEX = re.compile("(^.*BY_[0-9]_|CREATIVE_COMMONS_0)")

CC_REMIX_LICENCES = [x for x in CC_LICENSES if REMIX_REGEX.match(x)]

LICENSE_CHOICES = (
    [
        ("", "No license chosen"),
    ]
    + V3_CC_LICENSE_CHOICES
    + V4_CC_LICENSE_CHOICES
    + [RESERVED_LICENSE]
)

ARCHIVE_PREFIX = "https://web.archive.org/web/"
STORAGE_PREFIX = f"{settings.DJANGO_STORAGE_URL}/{settings.DJANGO_STORAGE_BUCKET_NAME}/"


def suffix(name):
    if name is None:
        return None
    if name.endswith(".gltf"):
        return "".join([f"{p[0]}_(GLTFupdated){p[1]}" for p in [os.path.splitext(name)]])
    return name


class Category(models.TextChoices):
    MISCELLANEOUS = "MISCELLANEOUS", "Miscellaneous"
    ANIMALS = "ANIMALS", "Animals & Pets"
    ARCHITECTURE = "ARCHITECTURE", "Architecture"
    ART = "ART", "Art"
    CULTURE = "CULTURE", "Culture & Humanity"
    EVENTS = "EVENTS", "Current Events"
    FOOD = "FOOD", "Food & Drink"
    HISTORY = "HISTORY", "History"
    HOME = "HOME", "Furniture & Home"
    NATURE = "NATURE", "Nature"
    OBJECTS = "OBJECTS", "Objects"
    PEOPLE = "PEOPLE", "People & Characters"
    PLACES = "PLACES", "Places & Scenes"
    SCIENCE = "SCIENCE", "Science"
    SPORTS = "SPORTS", "Sports & Fitness"
    TECH = "TECH", "Tools & Technology"
    TRANSPORT = "TRANSPORT", "Transport"
    TRAVEL = "TRAVEL", "Travel & Leisure"


CATEGORY_LABELS = [x[0] for x in Category.choices]
CATEGORY_LABEL_MAP = {x[0].lower(): x[1] for x in Category.choices}


WEB_UI_DOWNLOAD_COMPATIBLE = [
    ORIGINAL_OBJ_FORMAT,
    TILT_FORMAT,
    ORIGINAL_FBX_FORMAT,
    BLOCKS_FORMAT,
    USD_FORMAT,
    GLB_FORMAT,
    ORIGINAL_TRIANGULATED_OBJ_FORMAT,
    USDZ_FORMAT,
    UPDATED_GLTF_FORMAT,
    TILT_NATIVE_GLTF,
    USER_SUPPLIED_GLTF,
]

API_DOWNLOAD_COMPATIBLE = [
    ORIGINAL_OBJ_FORMAT,
    TILT_FORMAT,
    ORIGINAL_FBX_FORMAT,
    BLOCKS_FORMAT,
    USD_FORMAT,
    GLB_FORMAT,
    ORIGINAL_TRIANGULATED_OBJ_FORMAT,
    USDZ_FORMAT,
    UPDATED_GLTF_FORMAT,
    TILT_NATIVE_GLTF,
    USER_SUPPLIED_GLTF,
]

BLOCKS_VIEWABLE_TYPES = [
    "OBJ",
    "GLB",
    "GLTF2",
]

# This only returns roles that are associated with the poly scrape for now
VIEWABLE_ROLES = [
    POLYGONE_GLB_FORMAT,
    POLYGONE_GLTF_FORMAT,
    POLYGONE_OBJ_FORMAT,
]

VIEWABLE_FORMAT_TYPES = [
    "FBX",
    "GLB",
    "GLTF",
    "GLTF2",
    "OBJ",
]

ASSET_STATE_BARE = "BARE"
ASSET_STATE_UPLOADING = "UPLOADING"
ASSET_STATE_COMPLETE = "COMPLETE"
ASSET_STATE_FAILED = "FAILED"
ASSET_STATE_CHOICES = [
    (ASSET_STATE_BARE, "Bare"),
    (ASSET_STATE_UPLOADING, "Uploading"),
    (ASSET_STATE_COMPLETE, "Complete"),
    (ASSET_STATE_FAILED, "Failed"),
]


class AssetOwner(models.Model):
    id = models.BigAutoField(primary_key=True)
    url = models.CharField("User Name / URL", max_length=255, unique=True)
    email = models.EmailField(max_length=255, null=True, blank=True)
    password = models.BinaryField()
    displayname = models.CharField("Display Name", max_length=255)
    description = models.TextField(blank=True, null=True)
    migrated = models.BooleanField(default=False)
    likes = models.ManyToManyField(
        "Asset",
        through="OwnerAssetLike",
        blank=True,
    )
    access_token = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )  # Only used while we are emulating fastapi auth. Should be removed.
    imported = models.BooleanField(default=False)
    is_claimed = models.BooleanField(default=True)
    django_user = models.ForeignKey(
        DjangoUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    merged_with = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    disable_profile = models.BooleanField(default=False)

    @classmethod
    def from_ninja_request(cls, request):
        instance = None
        if getattr(request.auth, "email", None):
            try:
                instance = cls.objects.get(django_user=request.auth)
            except cls.DoesNotExist:
                pass
        return instance

    @classmethod
    def from_django_user(cls, user: DjangoUser) -> Optional[Self]:
        try:
            instance = cls.objects.get(django_user=user)
        except (cls.DoesNotExist, TypeError):
            instance = None
        return instance

    @classmethod
    def from_django_request(cls, request) -> Optional[Self]:
        return cls.from_django_user(request.user)

    def get_absolute_url(self):
        return f"/user/{self.url}"

    def set_password(self, raw_password):
        if raw_password:
            salt = bcrypt.gensalt(10)
            hashedpw = bcrypt.hashpw(raw_password.encode(), salt)

            self.password = hashedpw
            self.update_access_token()
            self.save
            if self.django_user:
                self.django_user.set_password(raw_password)
                self.django_user.save()

    @staticmethod
    def generate_device_code(length=5):
        # Define a string of characters to exclude
        exclude = "I1O0"
        characters = "".join(
            set(string.ascii_uppercase + string.digits) - set(exclude),
        )
        return "".join(secrets.choice(characters) for i in range(length))

    @staticmethod
    def generate_access_token(*, data: dict, expires_delta: timedelta = None):
        ALGORITHM = "HS256"
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=expires_delta)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(
            to_encode,
            settings.JWT_KEY,
            algorithm=ALGORITHM,
        )
        return encoded_jwt

    def update_access_token(self):
        subject = f"{self.email}"
        data = {"sub": subject}
        expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = self.generate_access_token(
            data=data,
            expires_delta=expires_delta,
        )
        self.access_token = access_token
        self.save()
        return access_token

    def __str__(self):
        return self.displayname


class Tag(models.Model):
    name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = [
            "name",
        ]


def default_orienting_rotation():
    return "[0, 0, 0, 0]"


def get_cloud_media_root():
    if settings.DJANGO_STORAGE_MEDIA_ROOT is not None:
        return f"{settings.DJANGO_STORAGE_MEDIA_ROOT}/"
    else:
        # We are writing to whatever is defined in settings.MEDIA_ROOT.
        return ""


def thumbnail_upload_path(instance, filename):
    root = get_cloud_media_root()
    path = f"{root}{instance.owner.id}/{instance.id}/{filename}"
    return path


def preview_image_upload_path(instance, filename):
    root = get_cloud_media_root()
    return f"{root}{instance.owner.id}/{instance.id}/preview_image/{filename}"


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
        "AssetOwner",
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
    )
    preview_image = models.ImageField(
        max_length=FILENAME_MAX_LENGTH,
        blank=True,
        null=True,
        upload_to=preview_image_upload_path,
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
        choices=Category.choices,
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
    def model_is_editable(self):
        # Once a permissable license has been chosen, and the asset is
        # available for use in other models, we cannot allow changing anything
        # about it. Doing so would allow abuse.
        is_editable = True
        if self.visibility in [PUBLIC, UNLISTED] and self.license != ALL_RIGHTS_RESERVED:
            is_editable = False
        return is_editable

    @property
    def slug(self):
        return slugify(self.name)

    @property
    def timestamp(self):
        return get_snowflake_timestamp(self.id)

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
        return reverse("asset_view", kwargs={"asset_url": self.url})

    def get_edit_url(self):
        return f"/edit/{self.url}"

    def get_delete_url(self):
        return f"/delete/{self.url}"

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
        last_liked = self.ownerassetlike_set.order_by("-date_liked").first()
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

    def get_all_downloadable_formats(self):
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

        for format in self.format_set.filter(
            role__in=WEB_UI_DOWNLOAD_COMPATIBLE,
        ):
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

    def save(self, *args, **kwargs):
        update_timestamps = kwargs.pop("update_timestamps", False)
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


class OwnerAssetLike(models.Model):
    user = models.ForeignKey(AssetOwner, on_delete=models.CASCADE, related_name="likedassets")
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    date_liked = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        date_str = self.date_liked.strftime("%d/%m/%Y %H:%M:%S %Z")
        return f"{self.user.displayname} -> {self.asset.name} @ {date_str}"


def format_upload_path(instance, filename):
    root = get_cloud_media_root()
    format = instance.format
    if format is None:
        # This is a root resource. TODO(james): implement a get_format method
        # that can handle this for us.
        format = instance.root_formats.first()
    asset = instance.asset
    ext = filename.split(".")[-1]
    if instance.format is None:  # proxy test for if this is a root resource.
        name = f"model.{ext}"
    if ext == "obj" and instance.format.role == ORIGINAL_TRIANGULATED_OBJ_FORMAT:
        name = f"model-triangulated.{ext}"
    else:
        name = filename
    return f"{root}{asset.owner.id}/{asset.id}/{format.format_type}/{name}"


class Format(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    format_type = models.CharField(max_length=255)
    zip_archive_url = models.CharField(max_length=FILENAME_MAX_LENGTH, null=True, blank=True)
    triangle_count = models.PositiveIntegerField(null=True, blank=True)
    lod_hint = models.PositiveIntegerField(null=True, blank=True)
    role = models.IntegerField(
        null=True,
        blank=True,
        choices=FORMAT_ROLE_CHOICES,
    )
    root_resource = models.ForeignKey(
        "Resource",
        null=True,
        blank=True,
        related_name="root_formats",
        on_delete=models.SET_NULL,
    )
    is_preferred_for_viewer = models.BooleanField(default=False)
    is_preferred_for_download = models.BooleanField(default=False)

    def add_root_resource(self, resource):
        if not resource.format:
            from icosa.api.exceptions import RootResourceException

            raise RootResourceException("Resource must have a format associated with it.")
        self.root_resource = resource
        resource.format = None
        resource.save()

    def get_all_resources(self, query: Q = Q()):
        resources = self.resource_set.filter(query)
        # We can only union on another queryset, even though we just want one
        # instance.
        root_resources = Resource.objects.filter(pk=self.root_resource.pk)
        resources = resources.union(root_resources)
        return resources

    def get_resource_data(self, resources):
        if all([x.is_cors_allowed and x.remote_host for x in resources]):
            external_files = [x.external_url for x in resources if x.external_url]
            local_files = [f"{STORAGE_PREFIX}{x.file.name}" for x in resources if x.file]
            resource_data = {
                "files_to_zip": external_files + local_files,
                "role": self.role,
            }
        elif all([x.file for x in resources]):
            resource_data = {
                "files_to_zip": [f"{STORAGE_PREFIX}{suffix(x.file.name)}" for x in resources if x.file],
                "role": self.role,
            }
        else:
            resource_data = {}
        return resource_data

    def get_resource_data_by_role(self, resources, role):
        if self.role == POLYGONE_GLTF_FORMAT:
            # If we hit this branch, we are not clear on if all gltf files work
            # correctly. Try both the original data we ingested and include
            # the suffixed data which attempts to fix any errors. Add some
            # supporting text to make it clear to the user this is the case.
            resource_data = {
                "files_to_zip": [f"{STORAGE_PREFIX}{x.file.name}" for x in resources if x.file],
                "files_to_zip_with_suffix": [f"{STORAGE_PREFIX}{suffix(x.file.name)}" for x in resources if x.file],
                "supporting_text": "Try the alternative download if the original doesn't work for you. We're working to fix this.",
                "role": self.role,
            }
        elif self.role == UPDATED_GLTF_FORMAT:
            # If we hit this branch, we have a format which doesn't
            # have an archive url, but also doesn't have local files.
            # At time of writing, we can't create a zip on the client
            # from the archive.org urls because of CORS. So compile a
            # list of files as if the role was 1003 using our suffixed
            # upload.
            try:
                override_format = self.asset.format_set.get(role=POLYGONE_GLTF_FORMAT)
                override_resources = list(override_format.resource_set.all())
                override_format_root = override_format.root_resource
                if override_format_root is not None:
                    if override_format_root.file or override_format_root.external_url:
                        override_resources.append(override_format_root)
                resource_data = {
                    "files_to_zip": [f"{STORAGE_PREFIX}{suffix(x.file.name)}" for x in override_resources if x.file],
                    "role": self.role,
                }
            except (
                Format.DoesNotExist,
                Format.MultipleObjectsReturned,
            ):
                resource_data = {}
        else:
            resource_data = self.get_resource_data(resources)
        return resource_data

    class Meta:
        indexes = [
            models.Index(
                fields=[
                    "role",
                ]
            )
        ]


class Resource(models.Model):
    asset = models.ForeignKey(Asset, null=True, blank=False, on_delete=models.CASCADE)
    format = models.ForeignKey(Format, null=True, blank=True, on_delete=models.CASCADE)
    contenttype = models.CharField(max_length=255, null=True, blank=False)
    file = models.FileField(
        null=True,
        blank=True,
        max_length=FILENAME_MAX_LENGTH,
        upload_to=format_upload_path,
    )
    external_url = models.CharField(max_length=FILENAME_MAX_LENGTH, null=True, blank=True)

    @property
    def url(self):
        url_str = None
        if self.file:
            url_str = self.file.url
        elif self.external_url:
            url_str = self.external_url
        return url_str

    @property
    def internal_url_or_none(self):
        if self.file:
            return self.file.url
        return None

    @property
    def relative_path(self):
        file_name = None
        if self.file:
            file_name = self.file.name.split("/")[-1]
        elif self.external_url:
            file_name = self.external_url.split("/")[-1]
        return file_name

    @property
    def content_type(self):
        return self.file.content_type if self.file else self.contenttype

    @property
    def remote_host(self):
        if self.external_url:
            return urlparse(self.external_url).netloc
        else:
            return None

    @property
    def is_cors_allowed(self):
        if config.EXTERNAL_MEDIA_CORS_ALLOW_LIST:
            allowed_sources = tuple([x.strip() for x in config.EXTERNAL_MEDIA_CORS_ALLOW_LIST.split(",")])
        else:
            allowed_sources = tuple([])
        if self.remote_host is None:
            # Local files (those served by Django storages) are always
            # considered cors-friendly.
            return True
        return self.remote_host in allowed_sources


def masthead_image_upload_path(instance, filename):
    root = get_cloud_media_root()
    return f"{root}masthead_images/{instance.id}/{filename}"


class MastheadSection(models.Model):
    image = models.ImageField(
        max_length=FILENAME_MAX_LENGTH,
        blank=True,
        null=True,
        upload_to=masthead_image_upload_path,
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


class DeviceCode(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(AssetOwner, on_delete=models.CASCADE)
    devicecode = models.CharField(max_length=6)
    expiry = models.DateTimeField()

    def __str__(self):
        return f"{self.devicecode}: {self.expiry}"


class Oauth2Client(models.Model):
    id = models.BigAutoField(primary_key=True)
    client_id = models.CharField(max_length=48, unique=True)
    client_secret = models.CharField(max_length=120, blank=True, null=True)
    client_id_issued_at = models.IntegerField(default=0)
    client_secret_expires_at = models.IntegerField(default=0)
    client_metadata = models.TextField(blank=True, null=True)


class Oauth2Code(models.Model):
    id = models.BigAutoField(primary_key=True)
    user_id = models.BigIntegerField()
    code = models.CharField(max_length=120, unique=True)
    client_id = models.CharField(max_length=48, blank=True, null=True)
    redirect_uri = models.TextField(blank=True, null=True)
    response_type = models.TextField(blank=True, null=True)
    auth_time = models.IntegerField()
    code_challenge = models.TextField(blank=True, null=True)
    code_challenge_method = models.CharField(max_length=48, blank=True, null=True)
    scope = models.TextField(blank=True, null=True)
    nonce = models.TextField(blank=True, null=True)


class Oauth2Token(models.Model):
    id = models.BigAutoField(primary_key=True)
    user_id = models.BigIntegerField(blank=True, null=True)
    client_id = models.CharField(max_length=48, blank=True, null=True)
    token_type = models.CharField(max_length=40, blank=True, null=True)
    access_token = models.CharField(max_length=255, unique=True)
    refresh_token = models.CharField(max_length=255, blank=True, null=True)
    scope = models.TextField(blank=True, null=True)
    issued_at = models.IntegerField()
    access_token_revoked_at = models.IntegerField(default=0)
    refresh_token_revoked_at = models.IntegerField(default=0)
    expires_in = models.IntegerField(default=0)


class HiddenMediaFileLog(models.Model):
    original_asset_id = models.BigIntegerField()
    file_name = models.CharField(max_length=FILENAME_MAX_LENGTH)
    deleted_from_source = models.BooleanField(default=False)

    def unhide(self):
        bucket = get_b2_bucket()
        try:
            bucket.unhide_file(self.file_name)
        except FileNotPresent:
            print("File not present in storage, marking as deleted")
            self.deleted_from_source = True
            self.save()
        except FileNotHidden:
            print("File already not hidden, nothing to do.")

    def __str__(self):
        return f"{self.original_asset_id}: {self.file_name}"


class BulkSaveLog(models.Model):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    KILLED = "KILLED"
    RESUMED = "RESUMED"

    BULK_SAVE_STATUS_CHOICES = [
        (SUCCEEDED, "Succeeded"),
        (FAILED, "Failed"),
        (KILLED, "Killed"),
        (RESUMED, "Resumed"),
    ]
    create_time = models.DateTimeField(auto_now_add=True)
    update_time = models.DateTimeField(auto_now=True)
    finish_time = models.DateTimeField(null=True, blank=True)
    finish_status = models.CharField(
        max_length=9,
        null=True,
        blank=True,
        choices=BULK_SAVE_STATUS_CHOICES,
    )
    kill_sig = models.BooleanField(default=False)
    last_id = models.BigIntegerField(null=True, blank=True)
