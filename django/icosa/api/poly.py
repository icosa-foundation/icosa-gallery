from ninja import Router

router = Router()


@router.get("")
def add(request):
    return {"result": "poly"}
