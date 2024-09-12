import bcrypt

from django.conf import settings
from django.contrib.auth.models import User as DjangoUser
from django.db import models

from .helpers.snowflake import get_snowflake_timestamp

PUBLIC = "PUBLIC"
PRIVATE = "PRIVATE"
UNLISTED = "UNLISTED"
ASSET_VISIBILITY_CHOICES = [
    (PUBLIC, "Public"),
    (PRIVATE, "Private"),
    (UNLISTED, "Unlisted"),
]

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

RESOURCE_ROLE_CHOICES = [
    (1, "Original OBJ File"),
    (2, "Tilt File"),
    (4, "Unknown GLTF File"),
    (6, "Original FBX File"),
    (7, "Blocks File"),
    (8, "USD File"),
    (11, "HTML File"),
    (12, "Original glTF File"),
    (13, "Tour Creator Experience"),
    (15, "JSON File"),
    (16, "lullmodel File"),
    (17, "sand File"),
    (18, "GLB File"),
    (19, "sand File"),
    (20, "sandc File"),
    (21, "pb File"),
    (22, "Unknown GLTF File"),
    (24, "Original Triangulated OBJ File"),
    (25, "JPG (Buggy)"),
    (26, "USDZ File"),
    (30, "Updated glTF File"),
    (32, "Editor settings pb file"),
    (35, "Unknown GLTF File"),
    (36, "Unknown GLB File"),
    (38, "Unknown GLB File"),
    (1000, "Polygone Tilt File"),
    (1001, "Polygone Blocks File"),
    (1002, "Polygone GLB File"),
    (1003, "Polygone GLTF File"),
    (1004, "Polygone OBJ File"),
    (1005, "Polygone FBX File"),
]

BLOCKS_VIEWABLE_TYPES = [
    "OBJ",
    "GLB",
    "GLTF2",
]

# This only returns roles that are associated with the poly scrape for now
VIEWABLE_ROLES = [
    1002,
    1003,
    1004,
]


class User(models.Model):
    id = models.BigAutoField(primary_key=True)
    url = models.CharField("User Name / URL", max_length=255, unique=True)
    email = models.EmailField(max_length=255, null=True)
    password = models.BinaryField()
    displayname = models.CharField("Display Name", max_length=255)
    description = models.TextField(blank=True, null=True)
    migrated = models.BooleanField(default=False)
    likes = models.ManyToManyField(
        "Asset", through="UserAssetLike", blank=True
    )
    access_token = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )  # Only used while we are emulating fastapi auth. Should be removed.
    imported = models.BooleanField(default=False)

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


class Asset(models.Model):
    COLOR_SPACES = [
        ("LINEAR", "LINEAR"),
        ("GAMMA", "GAMMA"),
    ]
    id = models.BigAutoField(primary_key=True)
    url = models.CharField(max_length=255, blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    owner = models.ForeignKey(
        "User", null=True, blank=True, on_delete=models.SET_NULL
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
    polyid = models.CharField(max_length=255, blank=True, null=True)
    polydata = models.JSONField(blank=True, null=True)
    thumbnail = models.ImageField(
        max_length=255,
        blank=True,
        null=True,
        upload_to=thumbnail_upload_path,
    )
    thumbnail_contenttype = models.CharField(blank=True, null=True)
    create_time = models.DateTimeField(auto_now_add=True)
    update_time = models.DateTimeField(auto_now=True)
    license = models.CharField(max_length=50, null=True, blank=True)
    tags = models.ManyToManyField("Tag", blank=True)
    category = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        choices=CATEGORY_CHOICES,
    )
    color_space = models.CharField(
        max_length=50, choices=COLOR_SPACES, default="GAMMA"
    )
    background_color = models.CharField(
        max_length=7,
        null=True,
        blank=True,
        help_text="A valid css colour, such as #00CC83",
    )
    orienting_rotation_x = models.FloatField(null=True, blank=True)
    orienting_rotation_y = models.FloatField(null=True, blank=True)
    orienting_rotation_z = models.FloatField(null=True, blank=True)
    orienting_rotation_w = models.FloatField(null=True, blank=True)
    imported = models.BooleanField(default=False)
    search_text = models.TextField(null=True, blank=True)
    remix_ids = models.JSONField(null=True, blank=True)
    is_viewer_compatible = models.BooleanField(default=False)
    historical_likes = models.PositiveIntegerField(default=0)
    historical_views = models.PositiveIntegerField(default=0)
    likes = models.PositiveIntegerField(default=0)
    views = models.PositiveIntegerField(default=0)
    downloads = models.PositiveIntegerField(default=0)

    @property
    def timestamp(self):
        return get_snowflake_timestamp(self.id)

    @property
    def _preferred_viewer_format(self):
        # Return early with an obj if we know the asset is a blocks file.
        if self.is_blocks:
            # TODO Prefer some roles over others
            # TODO error handling
            obj_format = self.polyformat_set.filter(format_type="OBJ").first()
            obj_resource = obj_format.polyresource_set.filter(
                is_root=True
            ).first()
            mtl_resource = obj_format.polyresource_set.filter(
                is_root=False
            ).first()

            if obj_resource:
                return {
                    "format": obj_resource.format.format_type,
                    "url": obj_resource.internal_url_or_none,
                    "materialUrl": mtl_resource.url,
                }

        # Return early if we can grab a Polygone resource first
        polygone_gltf = self.polyresource_set.filter(
            is_root=True, format__role__in=[1002, 1003]
        ).first()
        if polygone_gltf:
            return {
                "format": polygone_gltf.format.format_type,
                "url": polygone_gltf.internal_url_or_none,
            }

        # Return early with either of the role-based formats we care about.
        updated_gltf = self.polyresource_set.filter(
            is_root=True, format__role=30
        ).first()
        if updated_gltf:
            return {
                "format": updated_gltf.format.format_type,
                "url": updated_gltf.internal_url_or_none,
            }

        original_gltf = self.polyresource_set.filter(
            is_root=True, format__role=12
        ).first()
        if original_gltf:
            return {
                "format": original_gltf.format.format_type,
                "url": original_gltf.internal_url_or_none,
            }

        # If we didn't get any role-based formats, find the remaining formats
        # we care about and choose the "best" one of those.
        formats = {}
        for format in self.polyformat_set.all():
            root = format.root_resource
            formats[format.format_type] = {
                "format": format.format_type,
                "url": root.internal_url_or_none,
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

    def get_absolute_url(self):
        if self.polydata:
            # TODO(james): hack for not knowing author/user/situation for poly
            # data right now.
            return f"/view/{self.url}"
        else:
            return f"/view/{self.owner.url}/{self.url}"

    def get_edit_url(self):
        return f"/edit/{self.owner.url}/{self.url}"

    def get_thumbnail_url(self):
        thumbnail_url = "/static/images/nothumbnail.png?v=1"
        if self.thumbnail:
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

    def __str__(self):
        return self.name if self.name else "(Un-named asset)"

    def update_search_text(self):
        tag_str = " ".join([t.name for t in self.tags.all()])
        description = self.description if self.description is not None else ""
        self.search_text = (
            f"{self.name} {description} {tag_str} {self.owner.displayname}"
        )

    def validate(self):
        if self.is_blocks:
            return self.is_blocks_viewable
        else:
            return True

    @property
    def is_blocks(self):
        return bool(self.polyformat_set.filter(format_type="BLOCKS").count())

    @property
    def is_blocks_viewable(self):
        return bool(
            self.polyformat_set.filter(
                format_type__in=BLOCKS_VIEWABLE_TYPES,
                role__in=VIEWABLE_ROLES,
            ).count()
        )

    def save(self, *args, **kwargs):
        self.update_search_text()
        self.is_viewer_compatible = self.validate()
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


class UserAssetLike(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="likedassets"
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
    if ext == "obj" and instance.format.role == 24:
        name = f"model-triangulated.{ext}"
    else:
        name = filename
    return f"{root}/{asset.owner.id}/{asset.id}/{format.format_type}/{name}"


class PolyFormat(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    format_type = models.CharField(max_length=255)
    archive_url = models.CharField(max_length=1024, null=True, blank=True)
    triangle_count = models.PositiveIntegerField(null=True, blank=True)
    lod_hint = models.PositiveIntegerField(null=True, blank=True)
    role = models.IntegerField(
        null=True,
        blank=True,
        choices=RESOURCE_ROLE_CHOICES,
    )

    @property
    def root_resource(self):
        return self.polyresource_set.filter(is_root=True).first()


class PolyResource(models.Model):
    is_root = models.BooleanField(default=False)
    asset = models.ForeignKey(
        Asset, null=True, blank=False, on_delete=models.CASCADE
    )
    format = models.ForeignKey(PolyFormat, on_delete=models.CASCADE)
    contenttype = models.CharField(max_length=255, null=True, blank=False)
    file = models.FileField(
        null=True,
        blank=True,
        max_length=1024,
        upload_to=format_upload_path,
    )
    external_url = models.CharField(max_length=1024, null=True, blank=True)

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


class DeviceCode(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
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
    code_challenge_method = models.CharField(
        max_length=48, blank=True, null=True
    )
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
