from icosa.models import AssetOwner


def get_owner(user):
    email = getattr(user, "username", None)
    owner = None
    if email:
        try:
            owner = AssetOwner.objects.get(email=email)
        except (AssetOwner.DoesNotExist, AssetOwner.MultipleObjectsReturned):
            pass
    return owner
