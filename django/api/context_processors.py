from api.models import User as IcosaUser


def owner_processor(request):
    email = getattr(request.user, "username", None)
    owner = None
    if email:  # TODO:(safety) coercing to boolean
        try:
            owner = IcosaUser.objects.get(email=email)
        except (IcosaUser.DoesNotExist, IcosaUser.MultipleObjectsReturned):
            pass
    return {"owner": owner}
