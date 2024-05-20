from django.db import models


class User(models.Model):
    id = models.BigAutoField(primary_key=True)
    url = models.CharField(max_length=255)
    email = models.CharField(max_length=255)
    password = models.BinaryField()
    displayname = models.CharField(max_length=50)
    description = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "users"


class Asset(models.Model):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"
    ASSET_VISIBILITY_CHOICES = [
        (
            PUBLIC,
            "Public",
        ),
        (
            PRIVATE,
            "Private",
        ),
    ]
    id = models.BigAutoField(primary_key=True)
    url = models.CharField(max_length=255, blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    # TODO(james) `owner` should be a foreign key, but the production data
    # violates constraints
    owner = models.BigIntegerField()
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

    class Meta:
        db_table = "assets"


class DeviceCode(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    device_code = models.CharField(max_length=6)
    expiry = models.DateTimeField()

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
