from django.db import models

from .helpers import get_snowflake_timestamp

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


class User(models.Model):
    id = models.BigAutoField(primary_key=True)
    url = models.CharField("User Name / URL", max_length=255)
    email = models.CharField(max_length=255)
    password = models.BinaryField()
    displayname = models.CharField("Display Name", max_length=50)
    description = models.TextField(blank=True, null=True)
    migrated = models.BooleanField(default=False)
    likes = models.ManyToManyField("Asset", null=True, blank=True)

    def __str__(self):
        return self.displayname

    class Meta:
        db_table = "users"


class Asset(models.Model):
    COLOR_SPACES = [
        ("LINEAR", "LINEAR"),
        ("GAMMA", "GAMMA"),
    ]
    id = models.BigAutoField(primary_key=True)
    url = models.CharField(max_length=255, blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    # TODO(james) `owner` should be a foreign key, but the production data
    # violates constraints
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
    # TODO(james) make `thumbnail` an image field perhaps.
    thumbnail = models.TextField(blank=True, null=True)
    create_time = models.DateTimeField(auto_now_add=True)
    update_time = models.DateTimeField(auto_now=True)
    license = models.CharField(max_length=50, null=True, blank=True)
    tags = models.JSONField(null=True, blank=True)
    orienting_rotation = models.JSONField(default="[0,0,0,0]")
    color_space = models.CharField(
        max_length=50, choices=COLOR_SPACES, default="GAMMA"
    )
    background_color = models.CharField(max_length=7, null=True, blank=True)

    @property
    def timestamp(self):
        return get_snowflake_timestamp(self.id)

    @property
    def owner_obj(self):
        # TODO(james) replace this with a foreign key
        return User.objects.filter(id=self.owner).first()

    @property
    def preferred_format(self):
        formats = {}
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
        return self.preferred_format["format"] == "GLTF"

    @property
    def is_gltf2(self):
        return self.preferred_format["format"] == "GLTF2"

    def get_absolute_url(self):
        return f"/view/{self.owner_obj.url}/{self.url}"

    def __str__(self):
        return self.name

    class Meta:
        db_table = "assets"


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
