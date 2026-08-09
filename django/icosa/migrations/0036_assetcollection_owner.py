import django.db.models.deletion
from django.db import migrations, models
from django.utils import timezone


ICOSA_GALLERY_OWNER_URL = "icosa-gallery"


def _owner_for_user(AssetOwner, User, database, user_id):
    owner = (
        AssetOwner.objects.using(database)
        .filter(django_user_id=user_id)
        .order_by("pk")
        .first()
    )
    if owner is not None:
        return owner

    user = User.objects.using(database).get(pk=user_id)
    base_url = f"collection-owner-{user_id}"
    url = base_url
    suffix = 2
    while AssetOwner.objects.using(database).filter(url=url).exists():
        url = f"{base_url}-{suffix}"
        suffix += 1

    return AssetOwner.objects.using(database).create(
        create_time=timezone.now(),
        url=url,
        email=user.email or None,
        displayname=user.displayname or user.username,
        django_user_id=user_id,
    )


def assign_collection_owners(apps, schema_editor):
    AssetCollection = apps.get_model("icosa", "AssetCollection")
    AssetOwner = apps.get_model("icosa", "AssetOwner")
    User = apps.get_model("icosa", "User")
    database = schema_editor.connection.alias

    owner_ids = {}
    for collection in AssetCollection.objects.using(database).all().iterator():
        owner_id = owner_ids.get(collection.user_id)
        if owner_id is None:
            owner = _owner_for_user(
                AssetOwner,
                User,
                database,
                collection.user_id,
            )
            owner_id = owner.pk
            owner_ids[collection.user_id] = owner_id
        collection.owner_id = owner_id
        collection.save(update_fields=["owner"])

    AssetOwner.objects.using(database).get_or_create(
        url=ICOSA_GALLERY_OWNER_URL,
        defaults={
            "create_time": timezone.now(),
            "displayname": "Icosa Gallery",
            "django_user_id": None,
        },
    )


def restore_collection_users(apps, schema_editor):
    AssetCollection = apps.get_model("icosa", "AssetCollection")
    AssetOwner = apps.get_model("icosa", "AssetOwner")
    database = schema_editor.connection.alias

    for collection in AssetCollection.objects.using(database).select_related("owner"):
        collection.user_id = collection.owner.django_user_id
        collection.save(update_fields=["user"])

    owner = AssetOwner.objects.using(database).filter(
        url=ICOSA_GALLERY_OWNER_URL,
        displayname="Icosa Gallery",
        django_user_id=None,
    ).first()
    if owner and not owner.asset_collections.exists() and not owner.asset_set.exists():
        owner.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("icosa", "0035_assetcollection_dynamic_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="assetcollection",
            name="user",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="user_collections",
                to="icosa.user",
            ),
        ),
        migrations.AddField(
            model_name="assetcollection",
            name="owner",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="asset_collections",
                to="icosa.assetowner",
            ),
        ),
        migrations.RunPython(
            assign_collection_owners,
            restore_collection_users,
        ),
        migrations.AlterField(
            model_name="assetcollection",
            name="owner",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="asset_collections",
                to="icosa.assetowner",
            ),
        ),
        migrations.RemoveField(
            model_name="assetcollection",
            name="user",
        ),
    ]
