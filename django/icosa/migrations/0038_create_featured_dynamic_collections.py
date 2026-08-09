from django.db import migrations


ICOSA_GALLERY_OWNER_URL = "icosa-gallery"
PUBLIC = "PUBLIC"
APPROVED = "APPROVED"

COLLECTIONS = (
    {
        "url": "open-brush",
        "name": "Open Brush",
        "description": "Explore assets for [Open Brush](https://openbrush.app/).",
        "query_parameters": {
            "format": ["TILT"],
            "curated": True,
            "orderBy": "BEST",
        },
    },
    {
        "url": "open-blocks",
        "name": "Open Blocks",
        "description": "Explore assets for [Open Blocks](https://openblocks.app/).",
        "query_parameters": {
            "filter": "(authorId=4aEd8rQgKu2)|(format=BLOCKS,curated=true)",
            "orderBy": "BEST",
        },
    },
)


def create_featured_dynamic_collections(apps, schema_editor):
    AssetCollection = apps.get_model("icosa", "AssetCollection")
    AssetOwner = apps.get_model("icosa", "AssetOwner")
    database = schema_editor.connection.alias
    owner = AssetOwner.objects.using(database).get(url=ICOSA_GALLERY_OWNER_URL)

    for collection_data in COLLECTIONS:
        existing = (
            AssetCollection.objects.using(database)
            .filter(url=collection_data["url"])
            .first()
        )
        if existing is not None and existing.owner_id != owner.pk:
            raise RuntimeError(
                f"Collection URL '{collection_data['url']}' is already owned by "
                "someone other than Icosa Gallery."
            )

        AssetCollection.objects.using(database).update_or_create(
            url=collection_data["url"],
            defaults={
                "owner_id": owner.pk,
                "name": collection_data["name"],
                "description": collection_data["description"],
                "visibility": PUBLIC,
                "query_parameters": collection_data["query_parameters"],
                "markdown": True,
                "moderation_state": APPROVED,
            },
        )


def remove_featured_dynamic_collections(apps, schema_editor):
    AssetCollection = apps.get_model("icosa", "AssetCollection")
    AssetOwner = apps.get_model("icosa", "AssetOwner")
    database = schema_editor.connection.alias
    owner = (
        AssetOwner.objects.using(database)
        .filter(url=ICOSA_GALLERY_OWNER_URL)
        .first()
    )
    if owner is None:
        return

    for collection_data in COLLECTIONS:
        AssetCollection.objects.using(database).filter(
            owner_id=owner.pk,
            url=collection_data["url"],
            name=collection_data["name"],
            description=collection_data["description"],
            visibility=PUBLIC,
            query_parameters=collection_data["query_parameters"],
            markdown=True,
            moderation_state=APPROVED,
        ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("icosa", "0037_assetcollection_markdown"),
    ]

    operations = [
        migrations.RunPython(
            create_featured_dynamic_collections,
            remove_featured_dynamic_collections,
        ),
    ]
