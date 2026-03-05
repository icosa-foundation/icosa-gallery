import datetime
from dataclasses import dataclass
from typing import Optional

from django.contrib.contenttypes.models import ContentType
from django.db.models import QuerySet
from icosa.model_mixins import (
    MOD_MODIFIED,
    MOD_NEW,
    MOD_REPORTED,
)
from icosa.models.asset import Asset
from icosa.models.asset_owner import AssetOwner
from icosa.models.collection import AssetCollection

MOD_STATES_OF_INTEREST = [MOD_MODIFIED, MOD_NEW, MOD_REPORTED]


@dataclass
class ModerationObjects:
    assets: QuerySet[Asset]
    asset_collections: QuerySet[AssetCollection]
    asset_owners: QuerySet[AssetOwner]

    def count(self) -> int:
        return self.assets.count() + self.asset_collections.count() + self.asset_owners.count()

    def first(self) -> Optional[Asset | AssetCollection | AssetOwner]:
        order = "moderation_state_change_time"
        asset = self.assets.order_by(order).first()
        asset_collection = self.asset_collections.order_by(order).first()
        asset_owner = self.asset_owners.order_by(order).first()

        objs = [x for x in [asset, asset_collection, asset_owner] if x is not None]
        if objs == []:
            return None
        return sorted(
            objs,
            key=lambda x: (
                x.moderation_state_change_time if x.moderation_state_change_time else datetime.datetime(1970, 1, 1)
            ),
        )[0]


def get_objects_to_moderate() -> ModerationObjects:

    assets = Asset.objects.filter(
        moderation_state__in=MOD_STATES_OF_INTEREST,
    ).order_by("moderation_state_change_time")
    collections = AssetCollection.objects.filter(
        moderation_state__in=MOD_STATES_OF_INTEREST,
    ).order_by("moderation_state_change_time")
    owners = AssetOwner.objects.filter(
        moderation_state__in=MOD_STATES_OF_INTEREST,
    ).order_by("moderation_state_change_time")

    return ModerationObjects(
        assets=assets,
        asset_collections=collections,
        asset_owners=owners,
    )


def get_str_content_type(obj: Optional[Asset | AssetCollection | AssetOwner]) -> Optional[str]:
    if obj is None:
        return None
    return str(ContentType.objects.get_for_model(obj)).split("|")[-1].strip()
