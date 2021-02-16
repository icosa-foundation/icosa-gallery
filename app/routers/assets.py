from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from fastapi.encoders import jsonable_encoder
import json
import secrets

from app.utilities.schema_models import Asset, AssetData, User, FullUser
from app.database.database_schema import assets

from app.utilities.authentication import get_current_user
from app.database.database_connector import database
from app.storage.storage import upload_file_gcs

with open("config.json") as config_file:
    data = json.load(config_file)

router = APIRouter(
    prefix="/assets",
    tags=["Assets"]
    )

@router.get("/{asset}")
async def get_asset(asset: str):
    query = assets.select()
    query = query.where(assets.c.token == asset)
    asset = await database.fetch_one(query)
    print(asset)
    if (asset == None):
        raise HTTPException(status_code=404, detail="Asset not found.")
    return asset

@router.post("")
@router.post("/", include_in_schema=False)
async def upload_tilt_asset(current_user: User = Depends(get_current_user), file: UploadFile = File(...)):
    #TODO: Proper validation that it's a tilt/open brush file
    splitnames = file.filename.split(".")
    extension = splitnames[len(splitnames)-1]
    if (extension.lower() != "tilt"):
        return HTTPException(400, "Not a valid tilt file.")
        
    name = splitnames[0]
    assettoken = secrets.token_urlsafe(8)
    model_path = f'{current_user["token"]}/{assettoken}/model.tilt'
    success = upload_file_gcs(file.file, model_path)
    if (success):
        #Generate asset object  
        url = f'https://storage.cloud.google.com/{data["gcloud_bucket_name"]}/{model_path}'
        assetinfo={"token" : assettoken, "name": name, "url": url}
        print(assetinfo)
        query = assets.insert(None).values(token=assettoken, owner = current_user["token"], data=assetinfo)
        asset_data = jsonable_encoder(await database.execute(query))
        query = assets.select()
        query = query.where(assets.c.id == asset_data)
        newasset = await database.fetch_one(query)
        return newasset
