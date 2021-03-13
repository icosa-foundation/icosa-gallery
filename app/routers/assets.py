from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from fastapi.encoders import jsonable_encoder
import json
import secrets

from app.utilities.schema_models import Asset, AssetFormat, User, FullUser
from app.database.database_schema import assets

from app.routers.users import get_user_assets

from app.utilities.authentication import get_current_user
from app.utilities.snowflake import generate_snowflake
from app.database.database_connector import database
from app.storage.storage import upload_file_gcs

with open("config.json") as config_file:
    data = json.load(config_file)

router = APIRouter(
    prefix="/assets",
    tags=["Assets"]
    )

@router.get("/id/{asset}", response_model=Asset)
async def get_id_asset(asset: int):
    query = assets.select()
    query = query.where(assets.c.id == asset)
    asset = await database.fetch_one(query)
    print(asset)
    if (asset == None):
        raise HTTPException(status_code=404, detail="Asset not found.")
    return asset

@router.get("/{userurl}/{asseturl}", response_model=Asset)
async def get_asset(userurl: str, asseturl: str):
    userassets = await(get_user_assets(userurl))
    for asset in userassets:
        if (asset["url"] == asseturl):
            return asset
    raise HTTPException(status_code=404, detail="Asset not found.")

@router.post("", response_model=Asset)
@router.post("/", response_model=Asset, include_in_schema=False)
async def upload_tilt_asset(current_user: User = Depends(get_current_user), file: UploadFile = File(...)):
    #TODO: Proper validation that it's a tilt/open brush file
    splitnames = file.filename.split(".")
    extension = splitnames[len(splitnames)-1]
    if (extension.lower() != "tilt"):
        return HTTPException(400, "Not a valid tilt file.")
        
    name = splitnames[0]
    snowflake = generate_snowflake()
    model_path = f'{current_user["id"]}/{snowflake}/model.tilt'
    success = upload_file_gcs(file.file, model_path)
    if (success):
        #Generate asset object  
        url = f'https://storage.cloud.google.com/{data["gcloud_bucket_name"]}/{model_path}'
        assetinfo={"id" : snowflake, "url" : url, "format" : "TILT"}
        query = assets.insert(None).values(id=snowflake, name=name, owner = current_user["id"], formats=[assetinfo])
        asset_data = jsonable_encoder(await database.execute(query))
        query = assets.select()
        query = query.where(assets.c.id == snowflake)
        newasset = await database.fetch_one(query)
        return newasset
