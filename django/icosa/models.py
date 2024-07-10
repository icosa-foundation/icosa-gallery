from django.conf import settings
from django.db import models

from .helpers.snowflake import get_snowflake_timestamp

PUBLIC = "PUBLIC"
PRIVATE = "PRIVATE"
UNLISTED = "UNLISTED"
ASSET_VISIBILITY_CHOICES = [
    (
        PUBLIC,
        "Public",
    ),
    (
        PRIVATE,
        "Private",
    ),
    (
        UNLISTED,
        "Unlisted",
    ),
]
STORAGE_URL = "https://f005.backblazeb2.com/file/icosa-gallery/poly"


class User(models.Model):
    id = models.BigAutoField(primary_key=True)
    url = models.CharField("User Name / URL", max_length=255, unique=True)
    email = models.CharField(max_length=255, null=True)
    password = models.BinaryField()
    displayname = models.CharField("Display Name", max_length=255)
    description = models.TextField(blank=True, null=True)
    migrated = models.BooleanField(default=False)
    likes = models.ManyToManyField(
        "Asset", through="UserAssetLike", blank=True
    )

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
    def from_request(cls, request):
        instance = None
        if getattr(request.user, "email", None):
            try:
                instance = cls.objects.get(email=request.user.email)
            except cls.DoesNotExist:
                pass
        return instance

    def get_absolute_url(self):
        return f"/user/{self.url}"

    def __str__(self):
        return self.displayname

    class Meta:
        db_table = "users"


class Tag(models.Model):
    name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.name


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
    formats = models.JSONField()
    visibility = models.CharField(
        max_length=255,
        default=PRIVATE,
        choices=ASSET_VISIBILITY_CHOICES,
        db_default=PRIVATE,
    )
    curated = models.BooleanField(blank=True, null=True)
    polyid = models.CharField(max_length=255, blank=True, null=True)
    polydata = models.JSONField(blank=True, null=True)
    presentation_params = models.ForeignKey(
        "PresentationParams", null=True, blank=True, on_delete=models.CASCADE
    )
    thumbnail = models.ImageField(
        max_length=255,
        blank=True,
        null=True,
        upload_to=thumbnail_upload_path,
    )
    create_time = models.DateTimeField(auto_now_add=True)
    update_time = models.DateTimeField(auto_now=True)
    license = models.CharField(max_length=50, null=True, blank=True)
    tags = models.ManyToManyField("Tag", blank=True)
    imported = models.BooleanField(default=False)

    @property
    def timestamp(self):
        return get_snowflake_timestamp(self.id)

    # TODO(james): This whole function is cursed
    @property
    def preferred_format(self):
        formats = {}
        if self.imported:
            for format in self.polyformat_set.all():
                formats[format.format_type] = {
                    "format": format.format_type,
                    "url": format.root_resource.file.url,
                }
            # TODO(james): We need this list to be more exhaustive; we're
            # returning None in too many cases.
            # If we have a GLTF2 format, it's most likely actually a GLTF1.
            if "GLTF2" in formats.keys():
                return formats["GLTF2"]
            if "GLTF" in formats.keys():
                return formats["GLTF"]
            # If we have a GLB format, it's most likely actually a GLTF2.
            if "GLB" in formats.keys():
                return formats["GLB"]
        else:
            for format in self.formats:
                formats[format["format"]] = format
            if "GLTF2" in formats.keys():
                return formats["GLTF2"]
            if "GLTF" in formats.keys():
                return formats["GLTF"]
            if "TILT" in formats:
                return formats["TILT"]
        return None

    @property
    def is_gltf(self):
        if self.preferred_format is None:
            return False
        if self.polydata and self.imported:
            # If we have a GLTF2 format, it's most likely actually a GLTF1.
            return self.preferred_format["format"] in ["GLTF", "GLTF2"]
        else:
            return self.preferred_format["format"] == "GLTF"

    @property
    def is_gltf2(self):
        if self.preferred_format is None:
            return False
        if self.polydata and self.imported:
            # If we have a GLB format, it's most likely actually a GLTF2.
            return self.preferred_format["format"] == "GLB"
        else:
            return self.preferred_format["format"] == "GLTF2"

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
        if self.imported:
            thumbnail_url = f"{STORAGE_URL}/{self.polyid}/thumbnail.png"
        else:
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
        return self.name

    class Meta:
        db_table = "assets"


class UserAssetLike(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    date_liked = models.DateTimeField(auto_now_add=True)


def format_upload_path(instance, filename):
    root = settings.MEDIA_ROOT
    format = instance.format
    asset = format.asset
    ext = filename.split(".")[-1]
    if instance.is_root:
        name = f"model.{ext}"
    else:
        name = filename
    return f"{root}/{asset.owner.id}/{asset.id}/{format.format_type}/{name}"


class PolyFormat(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    format_type = models.CharField(max_length=255)

    @property
    def root_resource(self):
        return self.polyresource_set.filter(is_root=True).first()


class FormatComplexity(models.Model):
    format = models.ForeignKey(PolyFormat, on_delete=models.CASCADE)
    triangle_count = models.PositiveIntegerField(null=True, blank=True)
    lod_hint = models.PositiveIntegerField(null=True, blank=True)


class PolyResource(models.Model):
    is_root = models.BooleanField(default=False)
    is_thumbnail = models.BooleanField(default=False)
    asset = models.ForeignKey(
        Asset, null=True, blank=False, on_delete=models.CASCADE
    )
    format = models.ForeignKey(PolyFormat, on_delete=models.CASCADE)
    contenttype = models.CharField(max_length=255, null=True, blank=False)
    file = models.FileField(
        max_length=255,
        upload_to=format_upload_path,
    )

    @property
    def url(self):
        return self.file.url

    @property
    def relative_path(self):
        return self.file.name.split("/")[-1]

    @property
    def content_type(self):
        return self.file.content_type


class OrientingRotation(models.Model):
    x = models.FloatField(null=True, blank=True)
    y = models.FloatField(null=True, blank=True)
    z = models.FloatField(null=True, blank=True)
    w = models.FloatField(null=True, blank=True)


class PresentationParams(models.Model):
    COLOR_SPACES = [
        ("LINEAR", "LINEAR"),
        ("GAMMA", "GAMMA"),
    ]
    orienting_rotation = models.ForeignKey(
        OrientingRotation, on_delete=models.CASCADE
    )
    color_space = models.CharField(
        max_length=50, choices=COLOR_SPACES, default="GAMMA"
    )
    background_color = models.CharField(max_length=7, null=True, blank=True)

    class Meta:
        verbose_name = "Presentation Params"
        verbose_name_plural = "Presentation Params"


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
