from fastapi import APIRouter

router = APIRouter(
    prefix="/poly",
    tags=["poly"])


@router.get("/assets", tags=["poly"])
async def get_poly_assets_list():
    return 1

@router.get("/assets/{asset}", tags=["poly"])
async def get_poly_asset():
    return 1