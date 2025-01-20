import os
from collections import OrderedDict
from datetime import datetime

import bcrypt
from b2sdk._internal.exception import FileNotHidden, FileNotPresent
from constance import config
from django.conf import settings
from django.contrib.auth.models import User as DjangoUser
from django.db import models
from django.db.models import Q
from django.utils.safestring import mark_safe
from django.utils.text import slugify
from icosa.helpers.format_roles import (
    BLOCKS_FORMAT,
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
    UPDATED_GLTF_FORMAT,
    USD_FORMAT,
    USDZ_FORMAT,
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
ASSET_VISIBILITY_CHOICES = [
    (PUBLIC, "Public"),
    (PRIVATE, "Private"),
    (UNLISTED, "Unlisted"),
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
CC_LICENSES = [x[0] for x in V3_CC_LICENSE_CHOICES] + [
    x[0] for x in V4_CC_LICENSE_CHOICES
]

LICENSE_CHOICES = (
    [
        ("", "No license chosen"),
    ]
    + V3_CC_LICENSE_CHOICES
    + V4_CC_LICENSE_CHOICES
    + [RESERVED_LICENSE]
)

CATEGORY_CHOICES = [
    ("MISCELLANEOUS", "Miscellaneous"),
    ("ANIMALS", "Animals & Pets"),
    ("ARCHITECTURE", "Architecture"),
    ("ART", "Art"),
    ("CULTURE", "Culture & Humanity"),
    ("EVENTS", "Current Events"),
    ("FOOD", "Food & Drink"),
    ("HISTORY", "History"),
    ("HOME", "Furniture & Home"),
    ("NATURE", "Nature"),
    ("OBJECTS", "Objects"),
    ("PEOPLE", "People & Characters"),
    ("PLACES", "Places & Scenes"),
    ("SCIENCE", "Science"),
    ("SPORTS", "Sports & Fitness"),
    ("TECH", "Tools & Technology"),
    ("TRANSPORT", "Transport"),
    ("TRAVEL", "Travel & Leisure"),
]

CATEGORY_LABELS = [x[0] for x in CATEGORY_CHOICES]

FORMAT_ROLE_CHOICES = [
    (1, "Original OBJ File"),
    (2, "Tilt File"),
    (4, "Unknown GLTF File A"),
    (6, "Original FBX File"),
    (7, "Blocks File"),
    (8, "USD File"),
    (11, "HTML File"),
    (12, "Original glTF File"),
    (13, "Tour Creator Experience"),
    (15, "JSON File"),
    (16, "lullmodel File"),
    (17, "sand File A"),
    (18, "GLB File"),
    (19, "sand File B"),
    (20, "sandc File"),
    (21, "pb File"),
    (22, "Unknown GLTF File B"),
    (24, "Original Triangulated OBJ File"),
    (25, "JPG (Buggy)"),
    (26, "USDZ File"),
    (30, "Updated glTF File"),
    (32, "Editor settings pb file"),
    (35, "Unknown GLTF File C"),
    (36, "Unknown GLB File A"),
    (38, "Unknown GLB File B"),
    (1000, "Polygone Tilt File"),
    (1001, "Polygone Blocks File"),
    (1002, "Polygone GLB File"),
    (1003, "Polygone GLTF File"),
    (1004, "Polygone OBJ File"),
    (1005, "Polygone FBX File"),
]

WEB_UI_DOWNLOAD_COMPATIBLE = [
    ORIGINAL_OBJ_FORMAT,
    # We should offer TILT, but they don't all have an archive URL for the main
    # format and we can't build a zip on the client from individual archive
    # URLS owing to CORS.
    # TILT_FORMAT,
    ORIGINAL_FBX_FORMAT,
    BLOCKS_FORMAT,
    USD_FORMAT,
    GLB_FORMAT,
    ORIGINAL_TRIANGULATED_OBJ_FORMAT,
    USDZ_FORMAT,
    UPDATED_GLTF_FORMAT,
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

    @classmethod
    def from_ninja_request(cls, request):
        instance = None
        if getattr(request.auth, "email", None):
            try:
                instance = cls.objects.get(email=request.auth.email)
            except cls.DoesNotExist:
                pass
        return instance

    @classmethod
    def from_django_request(cls, request):
        instance = None
        if getattr(request.user, "email", None):
            try:
                instance = cls.objects.get(email=request.user.email)
            except cls.DoesNotExist:
                pass
        return instance

    @classmethod
    def from_django_user(cls, user):
        instance = None
        if getattr(user, "email", None):
            try:
                instance = cls.objects.get(email=user.email)
            except cls.DoesNotExist:
                pass
        return instance

    def to_django_user(self):
        instance = None
        if getattr(self, "email", None):
            try:
                instance = DjangoUser.objects.get(email=self.email)
            except DjangoUser.DoesNotExist:
                pass
        return instance

    def get_absolute_url(self):
        return f"/user/{self.url}"

    def set_password(self, password):
        salt = bcrypt.gensalt(10)
        hashed_password = bcrypt.hashpw(password.encode(), salt)
        self.password = hashed_password
        self.save()

    def __str__(self):
        return self.displayname

    class Meta:
        db_table = "users"


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


def thumbnail_upload_path(instance, filename):
    root = settings.MEDIA_ROOT
    return f"{root}/{instance.owner.id}/{instance.id}/{filename}"


def preview_image_upload_path(instance, filename):
    root = settings.MEDIA_ROOT
    return f"{root}/{instance.owner.id}/{instance.id}/preview_image/{filename}"


class Asset(models.Model):
    COLOR_SPACES = [
        ("LINEAR", "LINEAR"),
        ("GAMMA", "GAMMA"),
    ]
    id = models.BigAutoField(primary_key=True)
    url = models.CharField(max_length=255, blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    owner = models.ForeignKey(
        "AssetOwner", null=True, blank=True, on_delete=models.CASCADE
    )
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
    create_time = models.DateTimeField(auto_now_add=True)
    update_time = models.DateTimeField(auto_now=True)
    license = models.CharField(
        max_length=50, null=True, blank=True, choices=LICENSE_CHOICES
    )
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

    # Denorm fields
    triangle_count = models.PositiveIntegerField(default=0)
    search_text = models.TextField(null=True, blank=True)
    is_viewer_compatible = models.BooleanField(default=False)

    has_tilt = models.BooleanField(default=False)
    has_blocks = models.BooleanField(default=False)
    has_gltf1 = models.BooleanField(default=False)
    has_gltf2 = models.BooleanField(default=False)
    has_gltf_any = models.BooleanField(default=False)
    has_fbx = models.BooleanField(default=False)
    has_obj = models.BooleanField(default=False)

    rank = models.FloatField(default=0)

    @property
    def slug(self):
        return slugify(self.name)

    @property
    def timestamp(self):
        return get_snowflake_timestamp(self.id)

    @property
    def _preferred_viewer_format(self):
        # Return early with an obj if we know the asset is a blocks file.
        # There are some issues with displaying GLTF files from Blocks so we
        # have to return an OBJ and its associated MTL.
        # TODO we now force updated gltf in the template instead of obj
        if False:
            # here: self.is_blocks and not self.has_gltf2:
            # TODO Prefer some roles over others
            # TODO error handling
            obj_format = self.polyformat_set.filter(format_type="OBJ").first()
            obj_resource = obj_format.polyresource_set.filter(
                is_root=True,
            ).first()
            mtl_resource = obj_format.polyresource_set.filter(
                is_root=False,
            ).first()

            if obj_resource:
                return {
                    "format": obj_resource.format.format_type,
                    "url": obj_resource.internal_url_or_none,
                    "materialUrl": mtl_resource.url,
                    "resource": obj_resource,
                }

        # Return early if we can grab a Polygone resource first
        polygone_gltf = self.polyresource_set.filter(
            is_root=True, format__role__in=[1002, 1003]
        ).first()
        if polygone_gltf:
            return {
                "format": polygone_gltf.format.format_type,
                "url": polygone_gltf.internal_url_or_none,
                "resource": polygone_gltf,
            }

        # Return early with either of the role-based formats we care about.
        updated_gltf = self.polyresource_set.filter(
            is_root=True, format__role=30
        ).first()
        if updated_gltf:
            return {
                "format": updated_gltf.format.format_type,
                "url": updated_gltf.internal_url_or_none,
                "resource": updated_gltf,
            }

        original_gltf = self.polyresource_set.filter(
            is_root=True, format__role=12
        ).first()
        if original_gltf:
            return {
                "format": original_gltf.format.format_type,
                "url": original_gltf.internal_url_or_none,
                "resource": original_gltf,
            }

        # If we didn't get any role-based formats, find the remaining formats
        # we care about and choose the "best" one of those.
        formats = {}
        for format in self.polyformat_set.all():
            root = format.root_resource
            formats[format.format_type] = {
                "format": format.format_type,
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
    def has_viewable_format_types(self):
        return (
            self.polyformat_set.filter(format_type__in=VIEWABLE_FORMAT_TYPES).count()
            > 0
        )

    @property
    def has_cors_allowed(self):
        # If this resource has a file managed by Django storage, then it will
        # be viewable.
        if (
            self.polyresource_set.filter(
                file__isnull=False,
            ).count()
            > 0
        ):
            return True

        # If any resource does not have a file managed by Django storage, check
        # if any of the externally-hosted files' sources have been allowed by
        # the site admin in django constance settings.
        if config.EXTERNAL_MEDIA_CORS_ALLOW_LIST:
            allowed_sources = tuple(
                [x.strip() for x in config.EXTERNAL_MEDIA_CORS_ALLOW_LIST.split(",")]
            )
        else:
            allowed_sources = tuple([])

        return (
            len(
                [
                    x.external_url
                    for x in self.polyresource_set.filter(
                        external_url__isnull=False,
                    )
                    if x.external_url.startswith(allowed_sources)
                ]
            )
            > 0
        )

    @property
    def download_url(self):
        if self.license == ALL_RIGHTS_RESERVED or not self.license:
            return None
        updated_gltf = self.polyresource_set.filter(
            is_root=True, format__role=30
        ).first()

        preferred_format = self.preferred_viewer_format

        if updated_gltf is not None:
            if updated_gltf.format.archive_url:
                return f"https://web.archive.org/web/{updated_gltf.format.archive_url}"
        if preferred_format is not None:
            if preferred_format["resource"].format.archive_url:
                return f"https://web.archive.org/web/{preferred_format['resource'].format.archive_url}"
            # TODO: "poly" is hardcoded here and will not necessarily be used
            # for 3rd party installs.
        return f"{settings.DJANGO_STORAGE_URL}/{settings.DJANGO_STORAGE_BUCKET_NAME}/icosa/{self.url}/archive.zip"

    def get_absolute_url(self):
        return f"/view/{self.url}"

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
        self.search_text = (
            f"{self.name} {description} {tag_str} {self.owner.displayname}"
        )

    def calc_is_viewable(self):
        if not self.pk:
            return False
        if self.has_viewable_format_types and self.has_cors_allowed:
            return True
        return False

    def denorm_format_types(self):
        if not self.pk:
            return
        self.has_tilt = self.polyformat_set.filter(format_type="TILT").exists()
        self.has_blocks = self.polyformat_set.filter(format_type="BLOCKS").exists()
        self.has_gltf1 = self.polyformat_set.filter(format_type="GLTF").exists()
        self.has_gltf2 = self.polyformat_set.filter(format_type="GLTF2").exists()
        self.has_gltf_any = self.polyformat_set.filter(
            format_type__in=["GLTF", "GLTF2"]
        ).exists()
        self.has_fbx = self.polyformat_set.filter(format_type="FBX").exists()
        self.has_obj = self.polyformat_set.filter(format_type="OBJ").exists()

    def get_triangle_count(self):
        formats = {}
        for format in self.polyformat_set.filter(triangle_count__gt=0):
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

    def get_updated_rank(self):
        rank = (self.likes + self.historical_likes + 1) * LIKES_WEIGHT
        rank += (self.views + self.historical_views) * VIEWS_WEIGHT
        rank += (
            1 / (datetime.now().timestamp() - self.create_time.timestamp())
        ) * RECENCY_WEIGHT
        return rank

    def inc_views_and_rank(self):
        self.views += 1
        self.rank = self.get_updated_rank()
        self.save()

    def get_all_file_names(self):
        file_list = []
        if self.thumbnail:
            file_list.append(self.thumbnail.file.name)
        for resource in self.polyresource_set.all():
            if resource.file:
                file_list.append(resource.file.name)
        return file_list

    def get_all_absolute_file_names(self):
        file_list = []
        for name in self.get_all_file_names():
            file_list.append(
                f"{settings.DJANGO_STORAGE_URL}/{settings.DJANGO_STORAGE_BUCKET_NAME}/{name}"
            )
        return file_list

    def get_all_downloadable_formats(self):
        formats = {}
        if self.license == ALL_RIGHTS_RESERVED:
            return formats

        def suffix(name):
            if name.endswith(".gltf"):
                return "".join(
                    [f"{p[0]}_(GLTFupdated){p[1]}" for p in [os.path.splitext(name)]]
                )
            return name

        ARCHIVE_PREFIX = "https://web.archive.org/web/"
        STORAGE_PREFIX = (
            f"{settings.DJANGO_STORAGE_URL}/{settings.DJANGO_STORAGE_BUCKET_NAME}/"
        )

        format_name_override_map = {
            "Original OBJ File": "OBJ File",
            "Original Triangulated OBJ File": "Triangulated OBJ File",
            "Updated glTF File": "GLTF File",
        }

        for format in self.polyformat_set.filter(role__in=WEB_UI_DOWNLOAD_COMPATIBLE):
            if format.archive_url:
                resource_data = {"archive_url": f"{ARCHIVE_PREFIX}{format.archive_url}"}
            else:
                # Query all resources which have either an external url or a
                # file.
                query = Q(external_url__isnull=False) & ~Q(external_url="")
                query |= Q(file__isnull=False)
                resources = format.polyresource_set.filter(query)
                if format.role == POLYGONE_GLTF_FORMAT:
                    resource_data = {
                        "files_to_zip": [
                            f"{STORAGE_PREFIX}{x.file.name}"
                            for x in resources
                            if x.file
                        ],
                        "files_to_zip_with_suffix": [
                            f"{STORAGE_PREFIX}{suffix(x.file.name)}"
                            for x in resources
                            if x.file
                        ],
                        "supporting_text": "Try the alternative download if the original doesn't work for you. We're working to fix this.",
                        "role": format.role,
                    }
                elif format.role == UPDATED_GLTF_FORMAT:
                    # If we hit this branch, we have a format which doesn't
                    # have an archive url, but also doesn't have local files.
                    # At time of writing, we can't create a zip on the client
                    # from the archive.org urls because of CORS. So compile a
                    # list of files as if the role was 1003 using our suffixed
                    # upload.
                    try:
                        override_format = self.polyformat_set.get(
                            role=POLYGONE_GLTF_FORMAT
                        )
                        override_resources = override_format.polyresource_set.all()
                        resource_data = {
                            "files_to_zip": [
                                f"{STORAGE_PREFIX}{suffix(x.file.name)}"
                                for x in override_resources
                                if x.file
                            ],
                            "role": format.role,
                        }
                    except (
                        PolyFormat.DoesNotExist,
                        PolyFormat.MultipleObjectsReturned,
                    ):
                        pass
                elif format.role == ORIGINAL_GLTF_FORMAT:
                    # If we hit this branch, we have a format which doesn't
                    # have an archive url, but also doesn't have local files.
                    # At time of writing, we can't create a zip on the client
                    # from the archive.org urls because of CORS. We also don't
                    # have the suffixed version to hand. Skip this format until
                    # we can resolve this.
                    continue
                else:
                    resource = resources.first()
                    if resource.file:
                        storage = settings.DJANGO_STORAGE_URL
                        bucket = settings.DJANGO_STORAGE_BUCKET_NAME
                        resource_data = {
                            "file": f"{storage}/{bucket}/{resource.file.name}"
                        }
                    elif resource.external_url:
                        resource_data = {"file": resource.external_url}
                    else:
                        resource_data = {}

            format_name = format_name_override_map.get(
                format.get_role_display(), format.get_role_display()
            )
            formats.setdefault(format_name, resource_data)
        return OrderedDict(sorted(formats.items(), key=lambda x: x[0].lower()))

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
        if self._state.adding is False:
            # Only denorm fields when updating an existing model
            self.rank = self.get_updated_rank()
            self.update_search_text()
            self.is_viewer_compatible = self.calc_is_viewable()
            self.denorm_format_types()
            self.denorm_triangle_count()
        super().save(*args, **kwargs)

    class Meta:
        db_table = "assets"
        indexes = [
            models.Index(
                fields=[
                    "is_viewer_compatible",
                    "visibility",
                ]
            )
        ]


class OwnerAssetLike(models.Model):
    user = models.ForeignKey(
        AssetOwner, on_delete=models.CASCADE, related_name="likedassets"
    )
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    date_liked = models.DateTimeField(auto_now_add=True)


def format_upload_path(instance, filename):
    root = settings.MEDIA_ROOT
    format = instance.format
    asset = format.asset
    ext = filename.split(".")[-1]
    if instance.is_root:
        name = f"model.{ext}"
    if ext == "obj" and instance.format.role == ORIGINAL_TRIANGULATED_OBJ_FORMAT:
        name = f"model-triangulated.{ext}"
    else:
        name = filename
    return f"{root}/{asset.owner.id}/{asset.id}/{format.format_type}/{name}"


class PolyFormat(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    format_type = models.CharField(max_length=255)
    archive_url = models.CharField(
        max_length=FILENAME_MAX_LENGTH, null=True, blank=True
    )
    triangle_count = models.PositiveIntegerField(null=True, blank=True)
    lod_hint = models.PositiveIntegerField(null=True, blank=True)
    role = models.IntegerField(
        null=True,
        blank=True,
        choices=FORMAT_ROLE_CHOICES,
    )

    @property
    def root_resource(self):
        return self.polyresource_set.filter(is_root=True).first()


class PolyResource(models.Model):
    is_root = models.BooleanField(default=False)
    asset = models.ForeignKey(Asset, null=True, blank=False, on_delete=models.CASCADE)
    format = models.ForeignKey(PolyFormat, on_delete=models.CASCADE)
    contenttype = models.CharField(max_length=255, null=True, blank=False)
    file = models.FileField(
        null=True,
        blank=True,
        max_length=FILENAME_MAX_LENGTH,
        upload_to=format_upload_path,
    )
    external_url = models.CharField(
        max_length=FILENAME_MAX_LENGTH, null=True, blank=True
    )

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


def masthead_image_upload_path(instance, filename):
    root = settings.MEDIA_ROOT
    return f"{root}/masthead_images/{instance.id}/{filename}"


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

    class Meta:
        db_table = "devicecodes"


class Oauth2Client(models.Model):
    id = models.BigAutoField(primary_key=True)
    client_id = models.CharField(max_length=48, unique=True)
    client_secret = models.CharField(max_length=120, blank=True, null=True)
    client_id_issued_at = models.IntegerField(default=0)
    client_secret_expires_at = models.IntegerField(default=0)
    client_metadata = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "oauth2_client"


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

    class Meta:
        db_table = "oauth2_code"


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

    class Meta:
        db_table = "oauth2_token"


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
