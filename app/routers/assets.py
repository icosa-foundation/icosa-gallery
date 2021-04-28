from typing import List
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from fastapi.encoders import jsonable_encoder
import secrets

from app.utilities.schema_models import Asset, _DBAsset, AssetFormat, User, FullUser
from app.database.database_schema import assets, expandedassets

from app.routers.users import get_user_assets

from app.utilities.authentication import get_current_user, get_optional_user
from app.utilities.snowflake import generate_snowflake
from app.database.database_connector import database
from app.storage.storage import upload_file_gcs, remove_file_gcs

router = APIRouter(
    prefix="/assets",
    tags=["Assets"]
    )

ASSET_NOT_FOUND = HTTPException(status_code=404, detail="Asset not found.")


@router.get("/id/{asset}", response_model=Asset)
async def get_id_asset(asset: int, current_user: User = Depends(get_optional_user)):

    query = expandedassets.select()
    query = query.where(expandedassets.c.id == asset)
    asset = await database.fetch_one(query)
    if asset == None:
        raise ASSET_NOT_FOUND
    if asset["visibility"] == "PRIVATE":
        if(current_user == None or current_user["id"] != asset["owner"]):
            raise ASSET_NOT_FOUND
    return asset

@router.get("/{userurl}/{asseturl}", response_model=_DBAsset)
async def get_asset(userurl: str, asseturl: str, current_user: User = Depends(get_optional_user)):
    userassets = await(get_user_assets(userurl, current_user))
    query = expandedassets.select()
    query = query.where(expandedassets.c.ownerurl == userurl)
    assets = await database.fetch_all(query)
    for asset in assets:
        if (asset["url"] == asseturl):
            if asset["visibility"] == "PRIVATE":
                if(current_user == None or current_user["id"] != asset["owner"]):
                    raise ASSET_NOT_FOUND
            return asset
    raise HTTPException(status_code=404, detail="Asset not found.")

def validate_file(file: UploadFile, extension: str):
    #TODO: Proper validation that it's a tilt/open brush file

    if (extension == "tilt"):
        return "TILT"
    if (extension == "glb"):
        return "GLTF2"
    raise HTTPException(400, f'Not a valid upload type: {extension}')

@router.post("", response_model=_DBAsset)
@router.post("/", response_model=_DBAsset, include_in_schema=False)
async def upload_new_asset(current_user: User = Depends(get_current_user), file: UploadFile = File(...)):
    splitnames = file.filename.split(".")
    extension = splitnames[len(splitnames)-1].lower()

    uploadType = validate_file(file, extension)

    name = splitnames[0]
    snowflake = generate_snowflake()
    model_path = f'{current_user["id"]}/{snowflake}/model.{extension}'
    success_file_path = upload_file_gcs(file.file, model_path)
    if (success_file_path):
        #Generate asset object  
        assettoken = secrets.token_urlsafe(8)
        url = success_file_path
        assetinfo={"id" : snowflake, "url" : url, "format" : uploadType}
        query = assets.insert(None).values(id=snowflake, url=assettoken, name=name, owner = current_user["id"], formats=[assetinfo])
        asset_data = jsonable_encoder(await database.execute(query))
        query = assets.select()
        query = query.where(assets.c.id == snowflake)
        newasset = await database.fetch_one(query)
        return newasset
    
@router.patch("/{asset}/publish")
async def publish_asset(asset: int, unlisted: bool = False, current_user: User = Depends(get_current_user), thumbnail: UploadFile = File(None)):
    check_asset = await get_id_asset(asset, current_user)
    visibility = "UNLISTED" if unlisted else "PUBLIC"
    query = assets.update()
    query = query.where(assets.c.id == asset)
    query = query.values(visibility = visibility)
    await database.execute(query)

@router.patch("/{asset}/unpublish")
async def unpublish_asset(asset: int, current_user: User = Depends(get_current_user)):
    check_asset = await get_id_asset(asset, current_user)
    query = assets.update()
    query = query.where(assets.c.id == asset)
    query = query.values(visibility = "PRIVATE")
    await database.execute(query)

@router.delete("/{asset}")
async def delete_asset(asset: int, current_user: User = Depends(get_current_user)):
    check_asset = await get_id_asset(asset, current_user)
    query = assets.delete()
    query = query.where(assets.c.id == asset)
    await database.execute(query)
    for format_option in check_asset["formats"]:
        filename = format_option["url"].split("/")[-1]
        blob = f'{current_user["id"]}/{asset}/{filename}'
        if not remove_file_gcs(blob):
            print(f'Failed to remove blob {blob} at {format_option["url"]}')
    return check_asset

        

@router.get("", response_model=List[Asset])
@router.get("/", response_model=List[Asset], include_in_schema=False)
async def get_assets(results: int = 20, page: int = 0, curated: bool = False):
    results = min(results, 100)
    query = expandedassets.select()
    query = query.where(expandedassets.c.visibility == "PUBLIC")
    query = query.order_by(expandedassets.c.id.desc())
    query = query.limit(results)
    query = query.offset(page * results)
    return await database.fetch_all(query)