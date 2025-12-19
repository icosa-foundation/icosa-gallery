import re
from enum import Enum

from django.conf import settings
from django.utils.translation import gettext_lazy as _

PUBLIC = "PUBLIC"
PRIVATE = "PRIVATE"
UNLISTED = "UNLISTED"
ARCHIVED = "ARCHIVED"
ASSET_VISIBILITY_CHOICES = [
    (PUBLIC, _("Public")),
    (PRIVATE, _("Private")),
    (UNLISTED, _("Unlisted")),
    (ARCHIVED, _("Archived")),
]

ASSET_STATE_BARE = "BARE"
ASSET_STATE_UPLOADING = "UPLOADING"
ASSET_STATE_COMPLETE = "COMPLETE"
ASSET_STATE_FAILED = "FAILED"
ASSET_STATE_CHOICES = [
    (ASSET_STATE_BARE, _("Bare")),
    (ASSET_STATE_UPLOADING, _("Uploading")),
    (ASSET_STATE_COMPLETE, _("Complete")),
    (ASSET_STATE_FAILED, _("Failed")),
]
FILENAME_MAX_LENGTH = 1024

VALID_THUMBNAIL_EXTENSIONS = [
    "jpeg",
    "jpg",
    "png",
]

VALID_THUMBNAIL_MIME_TYPES = [
    "image/jpeg",
    "image/png",
]

VALID_IMAGE_MIME_TYPES = VALID_THUMBNAIL_MIME_TYPES + [
    "image/bmp",
    "image/tiff",
    "image/webp",
]
VALID_IMAGE_EXTENSIONS = VALID_THUMBNAIL_EXTENSIONS + [
    "bmp",
    "tif",
    "tiff",
    "webp",
]


V4_CC_LICENSE_CHOICES = [
    # ("CREATIVE_COMMONS_SA_4_0", _("CC SA Attribution 4.0 International")), # Not yet supported
    # ("CREATIVE_COMMONS_ND_4_0", _("CC ND Attribution 4.0 International")), # Not yet supported
    # ("CREATIVE_COMMONS_NC_4_0", _("CC NC Attribution 4.0 International")), # Not yet supported
    # ("CREATIVE_COMMONS_NC_ND_4_0", _("CC NC_ND Attribution 4.0 International")), # Not yet supported
    # ("CREATIVE_COMMONS_NC_SA_4_0", _("CC NC_SA Attribution 4.0 International")), # Not yet supported
    ("CREATIVE_COMMONS_BY_4_0", _("CC BY Attribution 4.0 International")),
    ("CREATIVE_COMMONS_0", _("CC0 1.0 Universal")),
]
V4_CC_LICENSE_CHOICES_PLUS_ND = V4_CC_LICENSE_CHOICES + [
    (
        "CREATIVE_COMMONS_BY_ND_4_0",
        _("CC BY-ND Attribution-NoDerivatives 4.0 International"),
    ),
]
V3_CC_LICENSE_CHOICES = [
    # ("CREATIVE_COMMONS_SA_3_0", _("CC SA Attribution 3.0 International")), # Not yet supported
    # ("CREATIVE_COMMONS_ND_3_0", _("CC ND Attribution 3.0 International")), # Not yet supported
    # ("CREATIVE_COMMONS_NC_3_0", _("CC NC Attribution 3.0 International")), # Not yet supported
    # ("CREATIVE_COMMONS_NC_ND_3_0", _("CC NC_ND Attribution 3.0 International")), # Not yet supported
    # ("CREATIVE_COMMONS_NC_SA_3_0", _("CC NC_SA Attribution 3.0 International")), # Not yet supported
    ("CREATIVE_COMMONS_BY_3_0", _("CC BY Attribution 3.0 International")),
    (
        "CREATIVE_COMMONS_BY_ND_3_0",
        _("CC BY-ND Attribution-NoDerivatives 3.0 International"),
    ),
]
V3_CC_LICENSES = [x[0] for x in V3_CC_LICENSE_CHOICES]
V4_CC_LICENSES = [x[0] for x in V4_CC_LICENSE_CHOICES]
V3_CC_LICENSE_MAP = {x[0]: x[1] for x in V3_CC_LICENSE_CHOICES}

ALL_RIGHTS_RESERVED = "ALL_RIGHTS_RESERVED"
RESERVED_LICENSE = (ALL_RIGHTS_RESERVED, _("All rights reserved"))
CC_LICENSES = [x[0] for x in V3_CC_LICENSE_CHOICES] + [x[0] for x in V4_CC_LICENSE_CHOICES]

REMIX_REGEX = re.compile("(^.*BY_[0-9]_|CREATIVE_COMMONS_0)")

CC_REMIX_LICENCES = [x for x in CC_LICENSES if REMIX_REGEX.match(x)]

LICENSE_CHOICES = (
    [
        ("", _("No license chosen")),
    ]
    + V3_CC_LICENSE_CHOICES
    + V4_CC_LICENSE_CHOICES
    + [RESERVED_LICENSE]
)

STORAGE_PREFIX = f"{settings.DJANGO_STORAGE_URL}/{settings.DJANGO_STORAGE_BUCKET_NAME}/"


class Category(Enum):
    MISCELLANEOUS = _("Miscellaneous")
    ANIMALS = _("Animals & Pets")
    ARCHITECTURE = _("Architecture")
    ART = _("Art")
    CULTURE = _("Culture & Humanity")
    EVENTS = _("Current Events")
    FOOD = _("Food & Drink")
    HISTORY = _("History")
    HOME = _("Furniture & Home")
    NATURE = _("Nature")
    OBJECTS = _("Objects")
    PEOPLE = _("People & Characters")
    PLACES = _("Places & Scenes")
    SCIENCE = _("Science")
    SPORTS = _("Sports & Fitness")
    TECH = _("Tools & Technology")
    TRANSPORT = _("Transport")
    TRAVEL = _("Travel & Leisure")


CATEGORY_CHOICES = [(x.name, x.value) for x in Category]
CATEGORY_LABELS = [x[0] for x in CATEGORY_CHOICES]
CATEGORY_LABEL_MAP = {x[0].lower(): x[1] for x in CATEGORY_CHOICES}
