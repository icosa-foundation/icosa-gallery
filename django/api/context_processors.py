from api.utils import get_owner


def owner_processor(request):
    return {"owner": get_owner(request.user)}
