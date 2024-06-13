from icosa.models import User as IcosaUser


def get_owner(user):
    email = getattr(user, "username", None)
    owner = None
    if email:  # TODO:(safety) coercing to boolean
        try:
            owner = IcosaUser.objects.get(email=email)
        except (IcosaUser.DoesNotExist, IcosaUser.MultipleObjectsReturned):
            pass
    return owner
