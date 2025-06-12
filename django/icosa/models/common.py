import re
from enum import Enum

from django.conf import settings

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
    # ("CREATIVE_COMMONS_SA_4_0", "CC SA Attribution 4.0 International"), # Not yet supported
    # ("CREATIVE_COMMONS_ND_4_0", "CC ND Attribution 4.0 International"), # Not yet supported
    # ("CREATIVE_COMMONS_NC_4_0", "CC NC Attribution 4.0 International"), # Not yet supported
    # ("CREATIVE_COMMONS_NC_ND_4_0", "CC NC_ND Attribution 4.0 International"), # Not yet supported
    # ("CREATIVE_COMMONS_NC_SA_4_0", "CC NC_SA Attribution 4.0 International"), # Not yet supported
    ("CREATIVE_COMMONS_BY_4_0", "CC BY Attribution 4.0 International"),
    ("CREATIVE_COMMONS_0", "CC0 1.0 Universal"),
]
V4_CC_LICENSE_CHOICES_PLUS_ND = V4_CC_LICENSE_CHOICES + [
    (
        "CREATIVE_COMMONS_BY_ND_4_0",
        "CC BY-ND Attribution-NoDerivatives 4.0 International",
    ),
]
V3_CC_LICENSE_CHOICES = [
    # ("CREATIVE_COMMONS_SA_3_0", "CC SA Attribution 3.0 International"), # Not yet supported
    # ("CREATIVE_COMMONS_ND_3_0", "CC ND Attribution 3.0 International"), # Not yet supported
    # ("CREATIVE_COMMONS_NC_3_0", "CC NC Attribution 3.0 International"), # Not yet supported
    # ("CREATIVE_COMMONS_NC_ND_3_0", "CC NC_ND Attribution 3.0 International"), # Not yet supported
    # ("CREATIVE_COMMONS_NC_SA_3_0", "CC NC_SA Attribution 3.0 International"), # Not yet supported
    ("CREATIVE_COMMONS_BY_3_0", "CC BY Attribution 3.0 International"),
    (
        "CREATIVE_COMMONS_BY_ND_3_0",
        "CC BY-ND Attribution-NoDerivatives 3.0 International",
    ),
]
V3_CC_LICENSES = [x[0] for x in V3_CC_LICENSE_CHOICES]
V4_CC_LICENSES = [x[0] for x in V4_CC_LICENSE_CHOICES]
V3_CC_LICENSE_MAP = {x[0]: x[1] for x in V3_CC_LICENSE_CHOICES}

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


class Category(Enum):
    MISCELLANEOUS = "Miscellaneous"
    ANIMALS = "Animals & Pets"
    ARCHITECTURE = "Architecture"
    ART = "Art"
    CULTURE = "Culture & Humanity"
    EVENTS = "Current Events"
    FOOD = "Food & Drink"
    HISTORY = "History"
    HOME = "Furniture & Home"
    NATURE = "Nature"
    OBJECTS = "Objects"
    PEOPLE = "People & Characters"
    PLACES = "Places & Scenes"
    SCIENCE = "Science"
    SPORTS = "Sports & Fitness"
    TECH = "Tools & Technology"
    TRANSPORT = "Transport"
    TRAVEL = "Travel & Leisure"


CATEGORY_CHOICES = [(x.name, x.value) for x in Category]
CATEGORY_LABELS = [x[0] for x in CATEGORY_CHOICES]
CATEGORY_LABEL_MAP = {x[0].lower(): x[1] for x in CATEGORY_CHOICES}
