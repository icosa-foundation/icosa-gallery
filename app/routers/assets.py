from typing import List, Optional
import re
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, BackgroundTasks
from fastapi.encoders import jsonable_encoder
import secrets

from app.utilities.schema_models import Asset, _DBAsset, AssetFormat, User, FullUser, AssetPatchData
from app.database.database_schema import assets, expandedassets

from app.routers.users import get_user_assets

from app.utilities.authentication import get_current_user, get_optional_user
from app.utilities.snowflake import generate_snowflake
from app.database.database_connector import database
from app.storage.storage import upload_file_gcs, remove_folder_gcs

router = APIRouter(
    prefix="/assets",
    tags=["Assets"]
    )


IMAGE_REGEX = re.compile('(jpe?g|tiff?|png|webp|bmp)')

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

async def get_my_id_asset(asset: int, current_user: User = Depends(get_current_user)):
    asset = await get_id_asset(asset, current_user)
    if (current_user["id"] != asset["owner"]):
        raise HTTPException(status_code=403, detail="Unauthorized user.")
    return asset

@router.get("/{userurl}/{asseturl}", response_model=Asset)
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
    # Need to check if the resource is a main file or helper file.
    # Return format is (file: UploadFile, extension: str, filetype: str, mainfile: bool)
    # Ordered in most likely file types for 'performance'
    if (extension == "tilt"):
        return (file, extension, "TILT", True)

    # GLTF/GLB/BIN
    if (extension == "glb"):
        return (file, extension, "GLTF2", True)

    if (extension == "gltf"):
        #TODO: need extra checks here to determine if GLTF 1 or 2.
        return (file, extension, "GLTF2", True)
    if (extension == "bin"):
        return (file, extension, "BIN", False)

    # OBJ
    if (extension == "obj"):
        return (file, extension, "OBJ", True)
    if (extension == "mtl"):
        return (file, extension, "MTL", False)

    # FBX
    if (extension == "fbx"):
        return (file, extension, "FBX", True)
    if (extension == "fbm"):
        return (file, extension, "FBM", False)
    
    # Images
    if (IMAGE_REGEX.match(extension)):
        return (file, extension, "IMAGE", False)
    return None

async def upload_background(current_user: User, files: List[UploadFile], job_snowflake: int):
    if len(files) == 0:
        raise HTTPException(422, "No files provided.")

    # Loop on files provided and check types.
    # We need to see one of: tilt, glb, gltf, obj, fbx
    mainfile_details = []
    subfile_details = []
    name = ""
    for file in files:
        splitnames = file.filename.split(".")
        extension = splitnames[-1].lower()
        uploadDetails = validate_file(file, extension)
        if uploadDetails:
            if uploadDetails[3]:
                mainfile_details.append(uploadDetails)
                name = splitnames[0]
            else:
                subfile_details.append(uploadDetails)

    if name == "":
        raise HTTPException(415, "Not supplied with one of tilt, glb, gltf, obj, fbx.")

    #begin upload process
    assetsnowflake = job_snowflake
    assettoken = secrets.token_urlsafe(8)
    formats = []

    for mainfile in mainfile_details:
        # Main files determine folder
        base_path = f'{current_user["id"]}/{assetsnowflake}/{mainfile[2]}/'
        model_path = base_path + f'model.{mainfile[1]}'
        model_uploaded_url = await upload_file_gcs(mainfile[0].file, model_path)

        #Only bother processing extras if success
        if (model_uploaded_url):
            mainfile_snowflake = generate_snowflake()
            extras = []

            for subfile in subfile_details:
                # Horrendous check for supposedly compatible subfiles. can definitely be improved with parsing, but is it necessary?
                if  (mainfile[2] == "GLTF2" and (subfile[2] == "BIN" or subfile[2] == "IMAGE")) or \
                    (mainfile[2] == "OBJ"   and (subfile[2] == "MTL" or subfile[2] == "IMAGE")) or \
                    (mainfile[2] == "FBX"   and (subfile[2] == "FBM" or subfile[2] == "IMAGE")):
                    subfile_path = base_path + f'{subfile[0].filename}'
                    subfile_uploaded_url = await upload_file_gcs(subfile[0].file, subfile_path)
                    if subfile_uploaded_url:
                        subfile_snowflake = generate_snowflake()
                        extras.append({"id" : subfile_snowflake, "url" : subfile_uploaded_url, "format" : subfile[2]})
            if len(extras) > 0:
                formats.append({"id" : mainfile_snowflake, "url" : model_uploaded_url, "format" : mainfile[2], "subfiles" : extras})
            else:
                formats.append({"id" : mainfile_snowflake, "url" : model_uploaded_url, "format" : mainfile[2]})
    
    # Add to database
    if len(formats) == 0:
            raise HTTPException(500, "Unable to upload any files.")
    query = assets.insert(None).values(id=assetsnowflake, url=assettoken, name=name, owner = current_user["id"], formats=formats)
    await database.execute(query)
    query = assets.select()
    query = query.where(assets.c.id == assetsnowflake)
    newasset = jsonable_encoder(await database.fetch_one(query))
    print("DONE")
    print(newasset["id"])
    print(newasset)
    return newasset

@router.post("", status_code=202)
@router.post("/", status_code=202, include_in_schema=False)
async def upload_new_assets(background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user), files: List[UploadFile] = File(...)):
    if len(files) == 0:
        raise HTTPException(422, "No files provided.")
    job_snowflake = generate_snowflake()
    background_tasks.add_task(upload_background, current_user, files, job_snowflake)
    return { "upload_job" : str(job_snowflake) }

    
@router.patch("/{asset}", response_model=Asset)
async def update_asset(asset: int, data: AssetPatchData, current_user: User = Depends(get_current_user)):
    current_asset = _DBAsset(**(await get_my_id_asset(asset, current_user)))
    update_data = data.dict(exclude_unset=True)
    updated_asset = current_asset.copy(update=update_data)
    updated_asset.id = int(updated_asset.id)
    updated_asset.owner = int(updated_asset.owner)
    query = assets.update(None)
    query = query.where(assets.c.id == updated_asset.id)
    query = query.values(updated_asset.dict())
    await database.execute(query)
    return await get_my_id_asset(asset, current_user)

@router.patch("/{asset}/unpublish")
async def unpublish_asset(asset: int, current_user: User = Depends(get_current_user)):
    check_asset = await get_my_id_asset(asset, current_user)
    query = assets.update()
    query = query.where(assets.c.id == asset)
    query = query.values(visibility = "PRIVATE")
    await database.execute(query)

@router.delete("/{asset}")
async def delete_asset(asset: int, current_user: User = Depends(get_current_user)):
    check_asset = await get_my_id_asset(asset, current_user)
    # Database removal
    query = assets.delete()
    query = query.where(assets.c.id == asset)
    await database.execute(query)
    # Asset removal from storage
    asset_folder = f'{current_user["id"]}/{asset}/'
    if not (await remove_folder_gcs(asset_folder)):
        print(f'Failed to remove asset {asset}')
        raise HTTPException(status_code=500, detail=f'Failed to remove asset {asset}')
    return check_asset

        

@router.get("", response_model=List[Asset])
@router.get("/", response_model=List[Asset], include_in_schema=False)
async def get_assets(
        results: int = 20,
        page: int = 0,
        curated: bool = False,
        name: Optional[str] = None,
        description: Optional[str] = None,
        ownername: Optional[str] = None
):
    results = min(results, 100)
    query = expandedassets.select()
    query = query.where(expandedassets.c.visibility == "PUBLIC")
    if (curated):
        query = query.where(expandedassets.c.curated == True)

    if name:
        name_search = f"%{name}%"
        query = query.where(expandedassets.c.name.ilike(name_search))
    if description:
        description_search = f"%{description}%"
        query = query.where(expandedassets.c.description.ilike(description_search))
    if ownername:
        ownername_search = f"%{ownername}%"
        query = query.where(expandedassets.c.ownername.ilike(ownername_search))

    query = query.order_by(expandedassets.c.id.desc())
    query = query.limit(results)
    query = query.offset(page * results)
    return await database.fetch_all(query)