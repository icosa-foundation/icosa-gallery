from icosa.models import AssetOwner


def get_owner(user):
    owner = None
    try:
        owner = AssetOwner.objects.get(django_user=user)
    except (AssetOwner.DoesNotExist, AssetOwner.MultipleObjectsReturned):
        pass
    return owner
