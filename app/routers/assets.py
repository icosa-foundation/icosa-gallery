from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from fastapi.encoders import jsonable_encoder
import secrets

from app.utilities.schema_models import Asset, AssetFormat, User, FullUser
from app.database.database_schema import assets

from app.routers.users import get_user_assets

from app.utilities.authentication import get_current_user
from app.utilities.snowflake import generate_snowflake
from app.database.database_connector import database
from app.storage.storage import upload_file_gcs

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

def validate_file(file: UploadFile, extension: str):
    #TODO: Proper validation that it's a tilt/open brush file

    if (extension == "tilt"):
        return "TILT"
    if (extension == "glb"):
        return "GLB"
    raise HTTPException(400, f'Not a valid upload type: {extension}')

@router.post("", response_model=Asset)
@router.post("/", response_model=Asset, include_in_schema=False)
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
